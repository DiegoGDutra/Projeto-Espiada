"""SIMPA - API de monitoramento de risco de evasão.

Rodar:  uvicorn Projeto_SIMPA:app --reload   (dentro de src/)
Docs:   http://127.0.0.1:8000/docs  (schemas JSON de entrada/saída gerados automaticamente)
"""
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field

DB = os.environ.get("SIMPA_DB", Path(__file__).with_name("funcionaai.db"))
META_MIN_AVA = 600  # ponytail: 600 min no AVA = 100% de engajamento; trocar por regra da coordenação
PERFIL_ALUNO = 1

Risco = Literal["alto", "medio", "baixo"]

app = FastAPI(title="SIMPA API", version="0.1.0")


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def hash_senha(senha: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${h}"


# ---------- Schemas JSON ----------

class CursoIn(BaseModel):
    nome: str = Field(min_length=1)


class Curso(CursoIn):
    id: int


class AlunoIn(BaseModel):
    matricula: int
    nome: str = Field(min_length=1)
    email: EmailStr | None = None
    senha: str = Field(min_length=6)
    id_curso: int
    periodo: int | None = Field(None, ge=1)
    situacao: int = 1
    data_ingresso: date | None = None
    distancia: float | None = Field(None, ge=0, description="km até o campus")


class Fator(BaseModel):
    descricao: str
    negativo: bool


class Aluno(BaseModel):
    """Mesmos nomes de campo que interface.html já usa."""
    matricula: int
    nome: str
    curso: str | None
    turma: int | None
    freq: int | None = Field(description="% de presença")
    nota: float | None = Field(description="nota média 0-10")
    ava: int | None = Field(description="% de engajamento no AVA")
    reclamacoes: int
    distancia: float | None
    risco: Risco


class DesempenhoIn(BaseModel):
    materia: int
    turma: int | None = None
    situacao_materia: str | None = None
    nota_cic1: float | None = Field(None, ge=0, le=10)
    nota_cic2: float | None = Field(None, ge=0, le=10)
    nota_cic3: float | None = Field(None, ge=0, le=10)
    total_aulas: int = Field(ge=0)
    faltas_totais: int = Field(ge=0)
    media_final: float | None = Field(None, ge=0, le=10)


class AvaIn(BaseModel):
    data_acesso: date
    min_sessao: float = Field(ge=0, description="minutos acumulados no AVA")


class FeedbackIn(BaseModel):
    comentarios: str
    avaliacao_curso: int = Field(ge=1, le=5)


class Predicao(BaseModel):
    matricula: int
    data: datetime
    risco: Risco
    score: int
    fatores: list[Fator]


# ---------- Regras ----------

def computar_risco(a: dict) -> tuple[Risco, int, list[dict]]:
    """Mesma regra do computeRisk() da interface. Indicador sem dado não pontua."""
    regras = [
        (a["freq"], lambda v: v < 75, 2, "Frequência abaixo de 75%", "Frequência adequada"),
        (a["nota"], lambda v: v < 6, 2, "Nota média abaixo de 6,0", "Desempenho acadêmico regular"),
        (a["ava"], lambda v: v < 50, 1, "Baixo engajamento no AVA", "Engajamento no AVA satisfatório"),
        (a["reclamacoes"], lambda v: v > 0, 1, "Reclamação registrada sobre o curso", "Nenhuma reclamação registrada"),
        (a["distancia"], lambda v: v > 30, 1, "Distância elevada até o campus", "Distância dentro do esperado"),
    ]
    score, fatores = 0, []
    for valor, ruim, peso, msg_ruim, msg_ok in regras:
        neg = valor is not None and ruim(valor)
        score += peso if neg else 0
        fatores.append({"descricao": msg_ruim if neg else msg_ok, "negativo": neg})
    return nivel(score), score, fatores


def nivel(score: int) -> Risco:
    return "alto" if score >= 4 else "medio" if score >= 2 else "baixo"


SQL_ALUNO = """
SELECT a.matricula, u.nome, c.nome_curso AS curso, d.turma_aluno AS turma,
       a.distancia_universidade AS distancia, d.total_aulas, d.faltas_totais,
       d.media_final, d.nota_cic1, d.nota_cic2, d.nota_cic3, l.min_sessao, f.comentarios
FROM aluno a
JOIN usuario u ON u.matricula = a.matricula
LEFT JOIN curso c ON CAST(c.id_curso AS TEXT) = a.curso_aluno
LEFT JOIN desempenho_aluno d ON d.matricula = a.matricula
LEFT JOIN log_ava l ON l.matricula = a.matricula
LEFT JOIN feedback f ON f.matricula = a.matricula
"""


def montar_aluno(r: sqlite3.Row) -> dict:
    notas = [r[k] for k in ("nota_cic1", "nota_cic2", "nota_cic3") if r[k] is not None]
    nota = r["media_final"] if r["media_final"] is not None else (sum(notas) / len(notas) if notas else None)
    a = {
        "matricula": r["matricula"],
        "nome": r["nome"],
        "curso": r["curso"],
        "turma": r["turma"],
        "freq": round(100 * (1 - r["faltas_totais"] / r["total_aulas"])) if r["total_aulas"] else None,
        "nota": None if nota is None else round(float(nota), 1),
        "ava": None if r["min_sessao"] is None else min(100, round(100 * r["min_sessao"] / META_MIN_AVA)),
        "reclamacoes": 1 if r["comentarios"] else 0,  # feedback tem 1 linha por aluno (PK matricula)
        "distancia": None if r["distancia"] is None else float(r["distancia"]),
    }
    a["risco"] = computar_risco(a)[0]
    return a


def buscar_aluno(con, matricula: int) -> dict:
    r = con.execute(SQL_ALUNO + " WHERE a.matricula = ?", (matricula,)).fetchone()
    if not r:
        raise HTTPException(404, "Aluno não encontrado")
    return montar_aluno(r)


# ---------- Endpoints ----------

@app.get("/cursos", response_model=list[Curso])
def listar_cursos():
    with db() as con:
        return [{"id": r[0], "nome": r[1]} for r in con.execute("SELECT id_curso, nome_curso FROM curso ORDER BY nome_curso")]


@app.post("/cursos", response_model=Curso, status_code=201)
def criar_curso(c: CursoIn):
    with db() as con:
        novo_id = con.execute("SELECT COALESCE(MAX(id_curso), 0) + 1 FROM curso").fetchone()[0]
        con.execute("INSERT INTO curso (id_curso, nome_curso) VALUES (?, ?)", (novo_id, c.nome))
    return {"id": novo_id, "nome": c.nome}


@app.get("/alunos", response_model=list[Aluno])
def listar_alunos():
    with db() as con:
        return [montar_aluno(r) for r in con.execute(SQL_ALUNO + " ORDER BY u.nome")]


@app.get("/alunos/{matricula}", response_model=Aluno)
def obter_aluno(matricula: int):
    with db() as con:
        return buscar_aluno(con, matricula)


@app.post("/alunos", response_model=Aluno, status_code=201)
def criar_aluno(a: AlunoIn):
    with db() as con:
        if not con.execute("SELECT 1 FROM curso WHERE id_curso = ?", (a.id_curso,)).fetchone():
            raise HTTPException(422, "Curso inexistente")
        try:
            con.execute("INSERT INTO usuario (matricula, perfil, nome, senha, email) VALUES (?, ?, ?, ?, ?)",
                        (a.matricula, PERFIL_ALUNO, a.nome, hash_senha(a.senha), a.email))
            con.execute("INSERT INTO aluno (matricula, curso_aluno, periodo, situacao_aluno, data_ingresso, distancia_universidade)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (a.matricula, str(a.id_curso), a.periodo, a.situacao,
                         a.data_ingresso and a.data_ingresso.isoformat(), a.distancia))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Matrícula ou e-mail já cadastrado")
        return buscar_aluno(con, a.matricula)


@app.put("/alunos/{matricula}/desempenho", response_model=Aluno)
def registrar_desempenho(matricula: int, d: DesempenhoIn):
    if d.faltas_totais > d.total_aulas:
        raise HTTPException(422, "faltas_totais maior que total_aulas")
    with db() as con:
        buscar_aluno(con, matricula)
        con.execute("INSERT OR REPLACE INTO desempenho_aluno (matricula, turma_aluno, situacao_materia, materia, nota_cic1,"
                    " nota_cic2, nota_cic3, total_aulas, faltas_totais, media_final) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (matricula, d.turma, d.situacao_materia, d.materia, d.nota_cic1, d.nota_cic2, d.nota_cic3,
                     d.total_aulas, d.faltas_totais, d.media_final))
        return buscar_aluno(con, matricula)


@app.put("/alunos/{matricula}/ava", response_model=Aluno)
def registrar_ava(matricula: int, l: AvaIn):
    with db() as con:
        buscar_aluno(con, matricula)
        con.execute("INSERT OR REPLACE INTO log_ava (matricula, data_acesso, min_sessao) VALUES (?, ?, ?)",
                    (matricula, l.data_acesso.isoformat(), l.min_sessao))
        return buscar_aluno(con, matricula)


@app.put("/alunos/{matricula}/feedback", response_model=Aluno)
def registrar_feedback(matricula: int, f: FeedbackIn):
    agora = datetime.now()
    with db() as con:
        buscar_aluno(con, matricula)
        con.execute("INSERT OR REPLACE INTO feedback (matricula, comentarios, avaliacao_curso, data_comentario, hora_comentario)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (matricula, f.comentarios, f.avaliacao_curso, agora.date().isoformat(), agora.strftime("%H:%M")))
        return buscar_aluno(con, matricula)


@app.post("/alunos/{matricula}/predicao", response_model=Predicao, status_code=201)
def gerar_predicao(matricula: int):
    with db() as con:
        risco, score, fatores = computar_risco(buscar_aluno(con, matricula))
        agora = datetime.now().replace(microsecond=0)
        con.execute("INSERT OR REPLACE INTO predicao_ia (matricula, data_predicao, comentario_predicao, nivel_risco)"
                    " VALUES (?, ?, ?, ?)", (matricula, agora.isoformat(), json.dumps(fatores, ensure_ascii=False), score))
    return {"matricula": matricula, "data": agora, "risco": risco, "score": score, "fatores": fatores}


@app.get("/alunos/{matricula}/predicao", response_model=Predicao)
def obter_predicao(matricula: int):
    with db() as con:
        r = con.execute("SELECT * FROM predicao_ia WHERE matricula = ?", (matricula,)).fetchone()
    if not r:
        raise HTTPException(404, "Nenhuma predição gerada para este aluno")
    score = int(r["nivel_risco"])
    return {"matricula": matricula, "data": r["data_predicao"], "score": score,
            "risco": nivel(score),
            "fatores": json.loads(r["comentario_predicao"])}
