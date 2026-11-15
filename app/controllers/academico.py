"""Listas da estrutura acadêmica: /api/cursos, /api/disciplinas, /api/docentes, /api/turmas."""
from flask import Blueprint, abort, jsonify

from controllers.comum import exige
from models import academico

bp = Blueprint("academico", __name__)


@bp.get("/api/<recurso>")
def listar(recurso):
    if recurso not in academico.LISTAS:
        abort(404, "recurso não encontrado")
    exige("professor", "secretaria")
    return jsonify(academico.listar(recurso))
