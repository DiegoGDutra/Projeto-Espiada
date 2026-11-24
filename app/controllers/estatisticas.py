"""Rotas de estatística. Professor vê só as próprias turmas; fatores, comparações e avaliação são só da secretaria."""
from flask import Blueprint, Response, jsonify, request, session

from controllers.comum import exige
from models import estatistica

bp = Blueprint("estatisticas", __name__)


@bp.get("/api/estatisticas")
def painel():
    exige("professor", "secretaria")
    return jsonify(estatistica.painel(estatistica.ler_filtros(request.args), session))


@bp.get("/api/estatisticas/opcoes")
def opcoes():
    exige("professor", "secretaria")
    return jsonify(estatistica.opcoes(session))


@bp.get("/api/estatisticas/descritiva")
def descritiva():
    """Só as medidas resumidas: é o que os cartões do Painel usam."""
    exige("professor", "secretaria")
    return jsonify(estatistica.descritiva(estatistica.ler_filtros(request.args), session))


@bp.get("/api/estatisticas/evasao")
def evasao():
    exige("secretaria")  # usa o desfecho e o perfil socioeconômico
    return jsonify(estatistica.analise_evasao())


@bp.get("/api/estatisticas/avaliacao")
def avaliacao_por_grupo():
    exige("secretaria")
    return jsonify(estatistica.avaliacao_por_grupo())


@bp.get("/api/estatisticas/exportar/<tabela>")
def exportar(tabela):
    exige("professor", "secretaria")
    if tabela in estatistica.SO_SECRETARIA:
        exige("secretaria")
    corpo = estatistica.exportar_csv(tabela, estatistica.ler_filtros(request.args), session)
    return Response(corpo, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="espiada_{tabela}.csv"'})
