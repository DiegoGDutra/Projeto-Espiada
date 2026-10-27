"""python -m espiada  ->  cria as tabelas que faltam e sobe o servidor em http://127.0.0.1:5000"""
from . import create_app
from .banco import criar_banco

criar_banco()
create_app().run(debug=True)
