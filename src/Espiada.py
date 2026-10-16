"""SIMPA - API em Flask (formato das rotas e dos JSON no readme.md, seção "API").

Rodar:  python src/Espiada.py   ->  http://127.0.0.1:5000
Toda resposta da API é JSON. Erros sempre vêm como {"erro": "mensagem"} com o status HTTP certo.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash

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


def inserir(con, tabela, dados, colunas):
    """INSERT só com as colunas permitidas que vieram no JSON (tabela/colunas são fixas no código)."""
    usadas = [c for c in colunas if c in dados]
    sql = f"INSERT INTO {tabela} ({', '.join(usadas)}) VALUES ({', '.join('?' * len(usadas))})"
    return con.execute(sql, [dados[c] for c in usadas]).lastrowid


# ---------- páginas ----------

@app.get("/")
def login():
    return send_file(RAIZ / "login.html")


@app.get("/interface.html")
def interface():
    return send_file(RAIZ / "interface.html")


# ---------- estrutura acadêmica: cursos, matérias, turmas ----------
# Mesmo formato para os três: GET lista, POST cria e devolve o registro com o id.

ESTRUTURA = {
    "cursos": ("curso", "id_curso", ["nome_curso"], []),
    "materias": ("materia", "id_materia", ["id_curso", "nome_materia"], []),
    "turmas": ("turma", "id_turma", ["id_materia", "semestre"], ["matricula_professor"]),
}


@app.get("/api/<recurso>")
def listar(recurso):
    if recurso not in ESTRUTURA:
        abort(404, "recurso não encontrado")
    tabela, chave, _, _ = ESTRUTURA[recurso]
    return jsonify(consultar(f"SELECT * FROM {tabela} ORDER BY {chave}"))


@app.post("/api/<recurso>")
def criar(recurso):
    if recurso not in ESTRUTURA:
        abort(404, "recurso não encontrado")
    tabela, chave, obrigatorios, opcionais = ESTRUTURA[recurso]
    dados = ler_json(*obrigatorios)
    with transacao() as con:
        novo_id = inserir(con, tabela, dados, obrigatorios + opcionais)
    return jsonify(consultar(f"SELECT * FROM {tabela} WHERE {chave} = ?", novo_id)[0]), 201


# ---------- alunos ----------

# Indicadores por aluno (fórmulas no readme). Campo fica null quando ainda não há dado.
RESUMO_ALUNO = """
SELECT a.matricula, u.nome, c.nome_curso AS curso, a.periodo, a.situacao,
       a.distancia_km AS distancia,
       (SELECT group_concat(m.nome_materia, ', ') FROM desempenho_aluno d
          JOIN turma t USING (id_turma) JOIN materia m USING (id_materia)
         WHERE d.matricula = a.matricula) AS turma,
       (SELECT round(100.0 * (1 - 1.0 * sum(faltas_totais) / sum(total_aulas)), 1)
          FROM desempenho_aluno d WHERE d.matricula = a.matricula) AS freq,
       (SELECT round(avg(coalesce(media_final,
                 (coalesce(nota_cic1, 0) + coalesce(nota_cic2, 0) + coalesce(nota_cic3, 0))
                 / nullif((nota_cic1 IS NOT NULL) + (nota_cic2 IS NOT NULL) + (nota_cic3 IS NOT NULL), 0))), 1)
          FROM desempenho_aluno d WHERE d.matricula = a.matricula) AS nota,
       (SELECT round(min(100, 100.0 * sum(min_sessao) / 600))
          FROM log_ava l WHERE l.matricula = a.matricula) AS ava,
       (SELECT count(*) FROM feedback f
         WHERE f.matricula = a.matricula AND f.avaliacao_curso <= 2) AS reclamacoes
  FROM aluno a JOIN usuario u USING (matricula) JOIN curso c USING (id_curso)
"""

# ponytail: pesos fixos (os do readme); semana 05 deixa configurável (RF06) e soma a LLM (semana 06)
REGRAS = [
    ("freq", lambda v: v < 75, 2, "Frequência abaixo de 75%"),
    ("nota", lambda v: v < 60, 2, "Nota média abaixo de 60"),
    ("ava", lambda v: v < 50, 1, "Pouco acesso ao AVA"),
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
    achados = consultar(RESUMO_ALUNO + " WHERE a.matricula = ?", matricula)
    if not achados:
        abort(404, "aluno não encontrado")
    return achados[0]


@app.get("/api/alunos")
def listar_alunos():
    alunos = consultar(RESUMO_ALUNO + " ORDER BY u.nome")
    return jsonify([a | {"risco": calcular_risco(a)["risco"]} for a in alunos])


@app.get("/api/alunos/<int:matricula>")
def obter_aluno(matricula):
    aluno = buscar_aluno(matricula)
    aluno["risco"] = calcular_risco(aluno)["risco"]
    aluno["disciplinas"] = consultar("""
        SELECT d.id_turma, m.nome_materia, t.semestre, d.situacao_materia, d.nota_cic1, d.nota_cic2,
               d.nota_cic3, d.media_final, d.total_aulas, d.faltas_totais
          FROM desempenho_aluno d JOIN turma t USING (id_turma) JOIN materia m USING (id_materia)
         WHERE d.matricula = ? ORDER BY t.semestre, m.nome_materia""", matricula)
    return jsonify(aluno)


@app.post("/api/alunos")
def criar_aluno():
    dados = ler_json("matricula", "nome", "senha", "id_curso", "situacao")
    dados = dados | {"perfil": "aluno", "senha_hash": generate_password_hash(dados["senha"])}
    with transacao() as con:
        inserir(con, "usuario", dados, ["matricula", "perfil", "nome", "email", "senha_hash"])
        inserir(con, "aluno", dados, ["matricula", "id_curso", "periodo", "situacao", "data_ingresso", "distancia_km"])
    return jsonify(buscar_aluno(dados["matricula"])), 201


# Entrada da importação do AVA (semana 04). Notas/faltas não se editam à mão (RN11): na
# semana 03 esta rota fica restrita ao importador.
@app.put("/api/alunos/<int:matricula>/desempenho")
def registrar_desempenho(matricula):
    buscar_aluno(matricula)  # 404 se não existir
    dados = ler_json("id_turma") | {"matricula": matricula}
    colunas = ["situacao_materia", "nota_cic1", "nota_cic2", "nota_cic3", "media_final",
               "total_aulas", "faltas_totais"]
    with transacao() as con:  # cria ou substitui a linha aluno+turma
        con.execute("DELETE FROM desempenho_aluno WHERE matricula = ? AND id_turma = ?",
                    (matricula, dados["id_turma"]))
        inserir(con, "desempenho_aluno", dados, ["matricula", "id_turma"] + colunas)
    return jsonify(buscar_aluno(matricula))


@app.post("/api/alunos/<int:matricula>/ava")
def registrar_ava(matricula):
    buscar_aluno(matricula)  # 404 se não existir
    dados = ler_json("data_acesso", "min_sessao") | {"matricula": matricula}
    with transacao() as con:
        novo_id = inserir(con, "log_ava", dados, ["matricula", "data_acesso", "min_sessao"])
    return jsonify(consultar("SELECT * FROM log_ava WHERE id = ?", novo_id)[0]), 201


@app.post("/api/alunos/<int:matricula>/feedback")
def registrar_feedback(matricula):
    buscar_aluno(matricula)  # 404 se não existir
    dados = ler_json("alvo") | {"matricula": matricula}
    with transacao() as con:
        novo_id = inserir(con, "feedback", dados, ["matricula", "alvo", "comentarios", "avaliacao_curso"])
    return jsonify(consultar("SELECT * FROM feedback WHERE id = ?", novo_id)[0]), 201


@app.post("/api/alunos/<int:matricula>/predicao")
def gerar_predicao(matricula):
    resultado = calcular_risco(buscar_aluno(matricula))
    with transacao() as con:  # cada cálculo vira uma linha nova no histórico
        con.execute("INSERT INTO predicao_ia (matricula, nivel_risco, score) VALUES (?, ?, ?)",
                    (matricula, resultado["risco"], resultado["score"]))
    return jsonify({"matricula": matricula} | resultado), 201


@app.get("/api/alunos/<int:matricula>/predicao")
def historico_predicao(matricula):
    buscar_aluno(matricula)  # 404 se não existir
    return jsonify(consultar("""
        SELECT id, criado_em, nivel_risco AS risco, score, comentario_predicao, alterada_por, justificativa
          FROM predicao_ia WHERE matricula = ? ORDER BY id DESC""", matricula))


if __name__ == "__main__":
    criar_banco()
    app.run(debug=True)
