"""SIMPA - API em Flask (formato das rotas e dos JSON no readme.md, seção "API").

Rodar:  python src/Espiada.py   ->  http://127.0.0.1:5000
Toda resposta da API é JSON. Erros sempre vêm como {"erro": "mensagem"} com o status HTTP certo.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
RAIZ = Path(__file__).resolve().parent.parent  # pasta do projeto, onde ficam os .html
BANCO = Path(__file__).with_name("funcionaai.db")
SCHEMA = Path(__file__).with_name("schema.sql")


def conectar(caminho=None):
    con = sqlite3.connect(caminho or BANCO)
    con.execute("PRAGMA foreign_keys = ON")  # o SQLite vem com as chaves estrangeiras desligadas
    con.row_factory = sqlite3.Row
    return con


def criar_banco(caminho=None):
    """Cria as tabelas que ainda não existem (pode rodar toda vez que o app sobe)."""
    with conectar(caminho) as con:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))


@app.errorhandler(HTTPException)
def erro_json(e):
    return jsonify(erro=e.description), e.code


def ler_json(*obrigatorios):
    """Corpo da requisição como dict; 400 se não for objeto JSON ou faltar campo obrigatório."""
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        abort(400, "o corpo deve ser um objeto JSON")
    faltando = [c for c in obrigatorios if dados.get(c) in (None, "")]
    if faltando:
        abort(400, "campos obrigatórios: " + ", ".join(faltando))
    return dados


@contextmanager
def transacao():
    """Grava tudo ou nada. Regra do banco violada vira 400 (ou 409 se já existe)."""
    con = conectar()
    try:
        with con:
            yield con
    except sqlite3.IntegrityError as e:
        abort(409 if "UNIQUE" in str(e) else 400, f"dados inválidos: {e}")
    finally:
        con.close()


def consultar(sql, *args):
    con = conectar()
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


# ---------- páginas ----------

@app.get("/")
def login():
    return send_file(RAIZ / "login.html")


@app.get("/interface.html")
def interface():
    return send_file(RAIZ / "interface.html")


# ---------- estrutura acadêmica (só leitura: vem do dataset, RN11) ----------

LISTAS = {
    "cursos": "SELECT * FROM cursos ORDER BY curso_id",
    "disciplinas": "SELECT * FROM disciplinas ORDER BY disciplina_id",
    "docentes": "SELECT * FROM docentes ORDER BY docente_id",
    "turmas": "SELECT * FROM turmas ORDER BY turma_id",
}


@app.get("/api/<recurso>")
def listar(recurso):
    if recurso not in LISTAS:
        abort(404, "recurso não encontrado")
    return jsonify(consultar(LISTAS[recurso]))


# ---------- alunos ----------

# Indicadores por aluno (fórmulas no readme). Campo fica null quando ainda não há dado.
# A matrícula do aluno é o codigo_academico do dataset (RN01).
RESUMO_ALUNO = """
SELECT a.codigo_academico AS matricula, a.nome_sintetico AS nome, c.nome AS curso,
       mc.periodo_atual AS periodo, mc.status AS situacao,
       ci.distancia_rodoviaria_aprox_km AS distancia,
       (SELECT group_concat(d.nome, ', ') FROM registros_academicos r
          JOIN turmas t USING (turma_id) JOIN disciplinas d USING (disciplina_id)
         WHERE r.matricula_curso_id = mc.matricula_curso_id AND r.situacao = 'EM_CURSO') AS turma,
       (SELECT round(avg(frequencia_percentual), 1) FROM registros_academicos r
         WHERE r.matricula_curso_id = mc.matricula_curso_id) AS freq,
       (SELECT round(avg(coalesce(nota_final, nota_parcial)), 1) FROM registros_academicos r
         WHERE r.matricula_curso_id = mc.matricula_curso_id) AS nota,
       (SELECT count(*) FROM registros_academicos r
         WHERE r.matricula_curso_id = mc.matricula_curso_id AND r.situacao LIKE 'REPROVADO%') AS reprovacoes,
       (SELECT count(*) FROM feedback f
         WHERE f.aluno_id = a.aluno_id AND f.avaliacao_curso <= 2) AS reclamacoes
  FROM alunos a JOIN matriculas_curso mc USING (aluno_id) JOIN cursos c USING (curso_id)
  LEFT JOIN enderecos_alunos e USING (aluno_id) LEFT JOIN cidades ci USING (cidade_id)
"""

# ponytail: pesos fixos (os do readme); semana 05 deixa configurável (RF06) e soma a LLM (semana 06)
REGRAS = [
    ("freq", lambda v: v < 75, 2, "Frequência abaixo de 75%"),
    ("nota", lambda v: v < 60, 2, "Nota média abaixo de 60"),
    ("reprovacoes", lambda v: v > 0, 1, "Reprovações no histórico"),
    ("reclamacoes", lambda v: v > 0, 1, "Reclamações no feedback"),
    ("distancia", lambda v: v > 30, 1, "Mora a mais de 30 km do campus"),
]


def calcular_risco(aluno):
    score, fatores = 0, []
    for campo, ruim, peso, descricao in REGRAS:
        if aluno[campo] is None:
            continue  # sem dado, não conta nem a favor nem contra
        negativo = ruim(aluno[campo])
        score += peso * negativo
        fatores.append({"descricao": descricao, "negativo": negativo})
    risco = "alto" if score >= 4 else "medio" if score >= 2 else "baixo"
    return {"risco": risco, "score": score, "fatores": fatores}


def buscar_aluno(matricula):
    achados = consultar(RESUMO_ALUNO + " WHERE a.codigo_academico = ?", matricula)
    if not achados:
        abort(404, "aluno não encontrado")
    return achados[0]


@app.get("/api/alunos")
def listar_alunos():
    alunos = consultar(RESUMO_ALUNO + " ORDER BY a.nome_sintetico")
    return jsonify([a | {"risco": calcular_risco(a)["risco"]} for a in alunos])


@app.get("/api/alunos/<matricula>")
def obter_aluno(matricula):
    aluno = buscar_aluno(matricula)
    aluno["risco"] = calcular_risco(aluno)["risco"]
    aluno["disciplinas"] = consultar("""
        SELECT t.codigo_turma, d.nome AS disciplina, t.ano_letivo || '.' || t.semestre_letivo AS semestre,
               r.tentativa, r.situacao, r.nota_n1, r.nota_n2, r.nota_projeto, r.nota_parcial, r.nota_final,
               r.frequencia_percentual, r.faltas_horas
          FROM registros_academicos r JOIN turmas t USING (turma_id) JOIN disciplinas d USING (disciplina_id)
          JOIN matriculas_curso mc USING (matricula_curso_id) JOIN alunos a USING (aluno_id)
         WHERE a.codigo_academico = ? ORDER BY semestre, d.nome""", matricula)
    return jsonify(aluno)


@app.post("/api/alunos/<matricula>/feedback")
def registrar_feedback(matricula):
    buscar_aluno(matricula)  # 404 se não existir
    dados = ler_json("alvo")
    with transacao() as con:
        novo_id = con.execute("""
            INSERT INTO feedback (aluno_id, alvo, comentarios, avaliacao_curso)
            SELECT aluno_id, ?, ?, ? FROM alunos WHERE codigo_academico = ?""",
            (dados["alvo"], dados.get("comentarios"), dados.get("avaliacao_curso"), matricula)).lastrowid
    return jsonify(consultar("SELECT * FROM feedback WHERE feedback_id = ?", novo_id)[0]), 201


@app.post("/api/alunos/<matricula>/predicao")
def gerar_predicao(matricula):
    resultado = calcular_risco(buscar_aluno(matricula))
    with transacao() as con:  # cada cálculo vira uma linha nova no histórico
        con.execute("""
            INSERT INTO predicao_ia (matricula_curso_id, nivel_risco, score)
            SELECT matricula_curso_id, ?, ? FROM matriculas_curso JOIN alunos USING (aluno_id)
             WHERE codigo_academico = ?""", (resultado["risco"], resultado["score"], matricula))
    return jsonify({"matricula": matricula} | resultado), 201


@app.get("/api/alunos/<matricula>/predicao")
def historico_predicao(matricula):
    buscar_aluno(matricula)  # 404 se não existir
    return jsonify(consultar("""
        SELECT p.predicao_id AS id, p.criado_em, p.nivel_risco AS risco, p.score, p.comentario_predicao,
               p.alterada_por, p.justificativa
          FROM predicao_ia p JOIN matriculas_curso USING (matricula_curso_id) JOIN alunos a USING (aluno_id)
         WHERE a.codigo_academico = ? ORDER BY p.predicao_id DESC""", matricula))


if __name__ == "__main__":
    criar_banco()
    app.run(debug=True)
