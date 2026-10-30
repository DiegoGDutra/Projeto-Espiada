"""SIMPA - ponto de entrada: monta o app Flask juntando as camadas do MVC.

  models/       dados e regras de negócio (SQL, cálculo de risco, validação de usuário)
  views/        telas HTML; o JavaScript delas consome a API
  controllers/  rotas HTTP: conferem login e permissão, chamam o model e devolvem JSON

Rodar:  python src/Espiada.py   ->  http://127.0.0.1:5000
Toda resposta da API é JSON. Erros sempre vêm como {"erro": "mensagem"} com o status HTTP certo.
Logins padrão de cada perfil: criados pelo src/importar.py (LOGINS_PADRAO); outros pelo comando criar-usuario.
"""
import os
import secrets

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from controllers import academico, alunos, auth, paginas
from models.banco import ErroModelo, criar_banco

app = Flask(__name__)  # arquivos do front (fonte) ficam em src/static/ e saem em /static/
# sem SECRET_KEY no ambiente, gera uma por execução (reiniciar o servidor desloga todo mundo)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")

for controller in (auth, paginas, academico, alunos):
    app.register_blueprint(controller.bp)


@app.errorhandler(HTTPException)
def erro_http(e):
    return jsonify(erro=e.description), e.code


@app.errorhandler(ErroModelo)
def erro_modelo(e):
    return jsonify(erro=e.mensagem), e.status


if __name__ == "__main__":
    criar_banco()
    app.run(debug=True)
