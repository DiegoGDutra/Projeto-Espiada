"""Rotas de alunos: lista, ficha, feedback e predição de risco. Cada perfil só alcança os alunos que pode ver."""
from flask import Blueprint, abort, jsonify, request, session

from controllers.comum import exige, ler_json, negar
from models import alunos, feedback, predicao

bp = Blueprint("alunos", __name__)


def aluno_visivel(matricula):
    """Resumo do aluno; 403 se existe mas está fora do acesso do usuário, 404 se não existe."""
    aluno = alunos.buscar(matricula, session)
    if aluno:
        return aluno
    if alunos.existe(matricula):
        negar(f"aluno {matricula} fora do seu acesso")
    abort(404, "aluno não encontrado")


@bp.get("/api/alunos")
def listar_alunos():
    return jsonify([a | {"risco": predicao.calcular_risco(a)["risco"]} for a in alunos.listar(session)])


@bp.get("/api/alunos/<matricula>")
def obter_aluno(matricula):
    aluno = aluno_visivel(matricula)
    aluno["risco"] = predicao.calcular_risco(aluno)["risco"]
    aluno["disciplinas"] = alunos.disciplinas(matricula)
    return jsonify(aluno)


@bp.post("/api/alunos/<matricula>/feedback")
def registrar_feedback(matricula):
    exige("aluno")  # só o próprio aluno comenta
    aluno_visivel(matricula)
    dados = ler_json("alvo")
    return jsonify(feedback.registrar(matricula, dados["alvo"], dados.get("comentarios"),
                                      dados.get("avaliacao_curso"))), 201


@bp.post("/api/alunos/<matricula>/predicao")
def gerar_predicao(matricula):
    exige("professor", "secretaria")  # aluno só consulta
    usar_llm = request.args.get("llm") != "0"  # ?llm=0: só as regras
    resultado = predicao.prever(aluno_visivel(matricula), alunos.disciplinas(matricula), feedback.do_aluno(matricula),
                                usar_llm)
    predicao.salvar(matricula, resultado)
    return jsonify({"matricula": matricula} | resultado), 201


@bp.get("/api/alunos/<matricula>/predicao")
def historico_predicao(matricula):
    aluno_visivel(matricula)
    return jsonify(predicao.historico(matricula))
