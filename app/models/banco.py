"""Conexão com o PostgreSQL e as funções que todos os models usam para ler e gravar.

O endereço do banco vem da variável DATABASE_URL; sem ela, usa o do docker-compose.yml.
"""
import atexit
import os
import threading
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

URL = os.environ.get("DATABASE_URL", "postgresql://espiada:espiada@127.0.0.1:5432/espiada")
ESQUEMA = "public"  # os testes trocam por um esquema só deles (usar_esquema_de_teste)
SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"
_pool, _trava_pool = None, threading.Lock()


class ErroModelo(Exception):
    """Regra de negócio ou do banco violada. status segue o HTTP (400 inválido, 409 já existe...)."""

    def __init__(self, status, mensagem):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


def _opcoes():
    return {"row_factory": dict_row, "options": f"-c search_path={ESQUEMA}"}


def conectar():
    """Conexão nova e avulsa (importador, criação das tabelas); `with conectar() as con:` grava tudo no fim
    (ou desfaz se der erro) e fecha. O dia a dia do app usa o pool, em consultar() e transacao()."""
    return psycopg.connect(URL, **_opcoes())


def _do_pool():
    """Empresta uma conexão do pool. Abrir conexão no PostgreSQL custa dezenas de ms; o pool abre poucas e
    reaproveita (o recálculo em lote faz 4 consultas por aluno). Nasce no primeiro uso, já no esquema certo."""
    global _pool
    with _trava_pool:
        if _pool is None:
            _pool = ConnectionPool(URL, kwargs=_opcoes(), min_size=1, max_size=10, open=True)
            atexit.register(_pool.close)  # fecha antes de o Python encerrar (senão sai um aviso no fim)
    return _pool.connection()  # devolve a conexão ao pool no fim: grava tudo, ou desfaz se der erro


def criar_banco():
    """Cria as tabelas que ainda não existem (pode rodar toda vez que o app sobe)."""
    with conectar() as con:
        con.execute(SCHEMA.read_text(encoding="utf-8"))


def usar_esquema_de_teste(nome):
    """Os testes rodam num esquema próprio, recriado vazio: os dados de verdade (esquema public) ficam intactos."""
    global ESQUEMA, _pool
    ESQUEMA = nome
    if _pool is not None:  # o pool aberto ainda aponta para o esquema anterior
        _pool.close()
        _pool = None
    with psycopg.connect(URL, autocommit=True) as con:
        con.execute(f"DROP SCHEMA IF EXISTS {nome} CASCADE")
        con.execute(f"CREATE SCHEMA {nome}")
    criar_banco()


@contextmanager
def erros_do_banco():
    """Regra do banco violada vira ErroModelo 409 (já existe) ou 400 (valor inválido)."""
    try:
        yield
    except psycopg.errors.UniqueViolation as e:
        raise ErroModelo(409, f"dados inválidos: {e.diag.message_primary}")
    except (psycopg.IntegrityError, psycopg.DataError) as e:
        raise ErroModelo(400, f"dados inválidos: {e.diag.message_primary}")


@contextmanager
def transacao():
    """Grava tudo ou nada."""
    with erros_do_banco(), _do_pool() as con:
        yield con


def consultar(sql, *args):
    with erros_do_banco(), _do_pool() as con:
        return con.execute(sql, args).fetchall()
