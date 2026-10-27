"""Rotas HTTP: lê a requisição, chama as regras (auth, risco, banco) e devolve JSON.
Formato das rotas e dos JSON no readme.md, seção "API".
"""
from flask import Blueprint, abort, jsonify, redirect, request, send_file, session
from werkzeug.exceptions import HTTPException

from .auth import autenticar, criar_usuario, exige, negar, visiveis
from .banco import consultar, transacao
from .config import PAGINAS
from .risco import calcular_risco

bp = Blueprint("rotas", __name__)


@bp.app_errorhandler(HTTPException)
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


# ---------- login e cadastro (RF01, RF11) ----------

@bp.post("/api/login")
def entrar():
    dados = ler_json("login", "senha")
    u = autenticar(dados["login"], dados["senha"])
    session.clear()
    session.update(login=u["login"], perfil=u["perfil"], nome=u["nome"],
                   aluno_id=u["aluno_id"], docente_id=u["docente_id"])
    return sessao_atual()


@bp.post("/api/logout")
def sair():
    session.clear()
    return jsonify(ok=True)


@bp.get("/api/sessao")
def sessao_atual():
    return jsonify({k: session[k] for k in ("login", "perfil", "nome")})


@bp.post("/api/usuarios")
def cadastrar_usuario():
    exige("secretaria")  # RF11: só a secretaria cadastra perfis
    d = ler_json("login", "perfil", "nome", "senha")
    return jsonify(criar_usuario(d["login"], d["perfil"], d["nome"], d["senha"], d.get("vinculo"))), 201


# ---------- páginas ----------

@bp.get("/")
def login():
    return send_file(PAGINAS / "login.html")


@bp.get("/interface.html")
def interface():
    if "login" not in session:
        return redirect("/")
    return send_file(PAGINAS / "interface.html")


# ---------- estrutura acadêmica (só leitura: vem do dataset, RN11) ----------

LISTAS = {
    "cursos": "SELECT * FROM cursos ORDER BY curso_id",
    "disciplinas": "SELECT * FROM disciplinas ORDER BY disciplina_id",
    "docentes": "SELECT * FROM docentes ORDER BY docente_id",
    "turmas": "SELECT * FROM turmas ORDER BY turma_id",
}


@bp.get("/api/<recurso>")
def listar(recurso):
    if recurso not in LISTAS:
        abort(404, "recurso não encontrado")
    exige("professor", "secretaria")
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


def buscar_aluno(matricula):
    filtro, args = visiveis()
    achados = consultar(RESUMO_ALUNO + f" WHERE a.codigo_academico = ? AND {filtro}", matricula, *args)
    if achados:
        return achados[0]
    if consultar("SELECT 1 FROM alunos WHERE codigo_academico = ?", matricula):
        negar(f"aluno {matricula} fora do seu acesso")
    abort(404, "aluno não encontrado")


@bp.get("/api/alunos")
def listar_alunos():
    filtro, args = visiveis()
    alunos = consultar(RESUMO_ALUNO + f" WHERE {filtro} ORDER BY a.nome_sintetico", *args)
    return jsonify([a | {"risco": calcular_risco(a)["risco"]} for a in alunos])


@bp.get("/api/alunos/<matricula>")
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


@bp.post("/api/alunos/<matricula>/feedback")
def registrar_feedback(matricula):
    exige("aluno")  # RN05: só o próprio aluno comenta
    buscar_aluno(matricula)  # 404 se não existir
    dados = ler_json("alvo")
    with transacao() as con:
        novo_id = con.execute("""
            INSERT INTO feedback (aluno_id, alvo, comentarios, avaliacao_curso)
            SELECT aluno_id, ?, ?, ? FROM alunos WHERE codigo_academico = ?""",
            (dados["alvo"], dados.get("comentarios"), dados.get("avaliacao_curso"), matricula)).lastrowid
    return jsonify(consultar("SELECT * FROM feedback WHERE feedback_id = ?", novo_id)[0]), 201


@bp.post("/api/alunos/<matricula>/predicao")
def gerar_predicao(matricula):
    exige("professor", "secretaria")  # aluno só consulta
    resultado = calcular_risco(buscar_aluno(matricula))
    with transacao() as con:  # cada cálculo vira uma linha nova no histórico
        con.execute("""
            INSERT INTO predicao_ia (matricula_curso_id, nivel_risco, score)
            SELECT matricula_curso_id, ?, ? FROM matriculas_curso JOIN alunos USING (aluno_id)
             WHERE codigo_academico = ?""", (resultado["risco"], resultado["score"], matricula))
    return jsonify({"matricula": matricula} | resultado), 201


@bp.get("/api/alunos/<matricula>/predicao")
def historico_predicao(matricula):
    buscar_aluno(matricula)  # 404 se não existir
    return jsonify(consultar("""
        SELECT p.predicao_id AS id, p.criado_em, p.nivel_risco AS risco, p.score, p.comentario_predicao,
               p.alterada_por, p.justificativa
          FROM predicao_ia p JOIN matriculas_curso USING (matricula_curso_id) JOIN alunos a USING (aluno_id)
         WHERE a.codigo_academico = ? ORDER BY p.predicao_id DESC""", matricula))
