"""SIMPA - API em Flask (formato das rotas e dos JSON no readme.md, seção "API").

Rodar:  python -m espiada   ->  http://127.0.0.1:5000
Toda resposta da API é JSON. Erros sempre vêm como {"erro": "mensagem"} com o status HTTP certo.
Logins padrão de cada perfil: criados pelo `flask --app espiada importar` (LOGINS_PADRAO); outros pelo criar-usuario.

Cada módulo cuida de uma coisa:
  config.py   caminhos e SECRET_KEY          banco.py   conexão, transação e consulta no SQLite
  auth.py     login, perfis e permissões     risco.py   cálculo do risco (sem Flask)
  rotas.py    endpoints HTTP                 importar.py  carga do dataset sintético
"""
from flask import Flask

from . import auth, config, importar, rotas


def create_app():
    app = Flask(__name__, static_folder=None)  # sem rota /static automática: interface.html só abre com login
    app.secret_key = config.SECRET_KEY
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")
    app.before_request(auth.exige_login)
    app.register_blueprint(rotas.bp)
    app.cli.add_command(auth.criar_usuario_cli)
    app.cli.add_command(importar.importar_cli)
    return app
