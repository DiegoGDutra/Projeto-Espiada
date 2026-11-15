"""Funções que todos os controllers usam: ler o JSON da requisição e checar o perfil do usuário."""
from flask import abort, current_app, request, session


def ler_json(*obrigatorios):
    """Corpo da requisição como dict; 400 se não for objeto JSON ou faltar campo obrigatório."""
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        abort(400, "o corpo deve ser um objeto JSON")
    faltando = [c for c in obrigatorios if dados.get(c) in (None, "")]
    if faltando:
        abort(400, "campos obrigatórios: " + ", ".join(faltando))
    return dados


def negar(motivo):
    """403 e registro no log: cada perfil faz só o que é dele."""
    current_app.logger.warning("acesso negado: %s (%s) %s %s - %s", session.get("login"), session.get("perfil"),
                               request.method, request.path, motivo)
    abort(403, "sem permissão: " + motivo)


def exige(*perfis):
    if session["perfil"] not in perfis:
        negar("função exclusiva de " + "/".join(perfis))
