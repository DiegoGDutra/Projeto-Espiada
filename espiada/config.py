"""Configuração: caminhos do projeto e a chave das sessões."""
import os
import secrets
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent  # pasta do projeto
BANCO = RAIZ / "funcionaai.db"
PAGINAS = RAIZ / "static"  # login.html e interface.html
DADOS = RAIZ / "dados"  # CSVs do dataset sintético
# ponytail: sem SECRET_KEY no ambiente, gera uma por execução (reiniciar o servidor desloga todo mundo)
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
