"""Conexão com o SQLite e as funções que todos os models usam para ler e gravar."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BANCO = Path(__file__).resolve().parent.parent / "funcionaai.db"
SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


class ErroModelo(Exception):
    """Regra de negócio ou do banco violada. status segue o HTTP (400 inválido, 409 já existe...)."""

    def __init__(self, status, mensagem):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


def conectar(caminho=None):
    con = sqlite3.connect(caminho or BANCO)
    con.execute("PRAGMA foreign_keys = ON")  # o SQLite vem com as chaves estrangeiras desligadas
    con.row_factory = sqlite3.Row
    return con


def criar_banco(caminho=None):
    """Cria as tabelas que ainda não existem (pode rodar toda vez que o app sobe)."""
    with conectar(caminho) as con:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))


@contextmanager
def transacao():
    """Grava tudo ou nada. Regra do banco violada vira ErroModelo 400 (ou 409 se já existe)."""
    con = conectar()
    try:
        with con:
            yield con
    except sqlite3.IntegrityError as e:
        raise ErroModelo(409 if "UNIQUE" in str(e) else 400, f"dados inválidos: {e}")
    finally:
        con.close()


def consultar(sql, *args):
    con = conectar()
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()
