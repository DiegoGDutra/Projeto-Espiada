"""Acesso ao SQLite: conexão, criação das tabelas, transação e consulta."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import abort

from . import config

SCHEMA = Path(__file__).with_name("schema.sql")


def conectar(caminho=None):
    con = sqlite3.connect(caminho or config.BANCO)
    con.execute("PRAGMA foreign_keys = ON")  # o SQLite vem com as chaves estrangeiras desligadas
    con.row_factory = sqlite3.Row
    return con


def criar_banco(caminho=None):
    """Cria as tabelas que ainda não existem (pode rodar toda vez que o app sobe)."""
    with conectar(caminho) as con:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))


@contextmanager
def transacao():
    """Grava tudo ou nada. Regra do banco violada vira 400 (ou 409 se já existe)."""
    con = conectar()
    try:
        with con:
            yield con
    except sqlite3.IntegrityError as e:
        abort(409 if "UNIQUE" in str(e) else 400, f"dados inválidos: {e}")
    finally:
        con.close()


def consultar(sql, *args):
    con = conectar()
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()
