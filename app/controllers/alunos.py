"""Rotas de alunos: lista, ficha, feedback e predição de risco. Cada perfil só alcança os alunos que pode ver."""
from flask import Blueprint, abort, jsonify, session

from controllers.comum import exige, ler_json, negar
from models import alunos, feedback, modelo_risco, predicao

bp = Blueprint("alunos", __name__)


def _com_risco(aluno, ultima, previsao):
    """Junta o risco ao resumo. O aluno vê o próprio nível, mas não a porcentagem: ela é apoio para quem acompanha."""
    dados = aluno | predicao.risco_atual(aluno, ultima, previsao)
    if session["perfil"] == "aluno":
        del dados["probabilidade"]
    return dados


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
    lista = alunos.listar(session)
    ultimas = predicao.ultimas_por_aluno()
    previsoes = modelo_risco.prever([a["matricula"] for a in lista])  # vazio enquanto não houver modelo treinado
    return jsonify([_com_risco(a, ultimas.get(a["matricula"]), previsoes.get(a["matricula"])) for a in lista])


@bp.get("/api/alunos/<matricula>")
def obter_aluno(matricula):
    aluno = aluno_visivel(matricula)
    aluno = _com_risco(aluno, predicao.ultima(matricula), modelo_risco.prever([matricula]).get(matricula))
    aluno["disciplinas"] = alunos.disciplinas(matricula)
    return jsonify(aluno)


@bp.post("/api/alunos/<matricula>/feedback")
def registrar_feedback(matricula):
    exige("aluno")  # só o próprio aluno comenta
    aluno_visivel(matricula)
    dados = ler_json("alvo")
    return jsonify(feedback.registrar(matricula, dados["alvo"], dados.get("comentarios"),
                                      dados.get("avaliacao_curso"))), 201


@bp.get("/api/alunos/<matricula>/feedback")
def listar_feedback(matricula):
    aluno_visivel(matricula)
    return jsonify(feedback.listar(matricula))


@bp.post("/api/alunos/<matricula>/predicao")
def gerar_predicao(matricula):
    exige("professor", "secretaria")  # aluno só consulta
    aluno = aluno_visivel(matricula)
    # modelo (ou regras) + LLM; sem Ollama a predição sai sem comentário e a resposta traz o motivo em "aviso"
    return jsonify({"matricula": matricula} | predicao.analisar(matricula, aluno)), 201


@bp.get("/api/alunos/<matricula>/predicao")
def historico_predicao(matricula):
    aluno_visivel(matricula)
    linhas = predicao.historico(matricula)
    if session["perfil"] == "aluno":  # o aluno não vê a porcentagem (ver _com_risco)
        linhas = [{c: v for c, v in linha.items() if c != "probabilidade"} for linha in linhas]
    return jsonify(linhas)
