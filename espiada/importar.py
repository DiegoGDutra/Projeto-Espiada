"""Importa o dataset sintético (CSVs em dados/) para o banco. É a única entrada de notas e frequência (RN11).
Também cria um login padrão de cada perfil (LOGINS_PADRAO), para o sistema já abrir usável.

Rodar:  flask --app espiada importar   ->  enche o funcionaai.db (se já tiver alunos, só confere os logins padrão)
Para importar de novo: apague funcionaai.db e rode outra vez.
"""
import csv

import click
from werkzeug.security import generate_password_hash

from .banco import conectar, criar_banco
from .config import DADOS

ORDEM = ["cursos", "periodos_curriculares", "disciplinas", "cidades", "docentes", "alunos", "enderecos_alunos",
         "perfis_socioeconomicos", "tipos_bolsa", "bolsas_alunos", "matriculas_curso", "turmas",
         "registros_academicos", "indicadores_risco", "desfechos_alunos"]  # ordem das chaves estrangeiras

# login, perfil, senha, vínculo (matrícula do aluno / docente_id). Senhas seguem o RF01; troque-as fora do ambiente de teste.
LOGINS_PADRAO = [
    ("secretaria@simpa.test", "secretaria", "Secretaria#2026", None),
    ("professor@simpa.test", "professor", "Professor#2026", 1),  # Docente Ada
    ("aluno@simpa.test", "aluno", "Aluno#2026", "AES0001"),
]


def criar_logins_padrao(con):
    """Grava os LOGINS_PADRAO que ainda não existem (o nome vem do dataset)."""
    for login, perfil, senha, vinculo in LOGINS_PADRAO:
        hash_ = generate_password_hash(senha)
        if perfil == "secretaria":
            con.execute("INSERT OR IGNORE INTO usuario VALUES (?, 'secretaria', 'Secretaria', ?, NULL, NULL)",
                        (login, hash_))
        elif perfil == "professor":
            con.execute("""INSERT OR IGNORE INTO usuario SELECT ?, 'professor', nome_sintetico, ?, NULL, docente_id
                             FROM docentes WHERE docente_id = ?""", (login, hash_, vinculo))
        else:
            con.execute("""INSERT OR IGNORE INTO usuario SELECT ?, 'aluno', nome_sintetico, ?, aluno_id, NULL
                             FROM alunos WHERE codigo_academico = ?""", (login, hash_, vinculo))


def importar(caminho=None, pasta=DADOS):
    criar_banco(caminho)
    con = conectar(caminho)
    try:
        if con.execute("SELECT count(*) FROM alunos").fetchone()[0]:
            with con:
                criar_logins_padrao(con)
            raise SystemExit("O banco já tem dados importados (logins padrão conferidos). "
                             "Apague funcionaai.db para importar de novo.")
        with con:  # tudo ou nada
            for tabela in ORDEM:
                with open(pasta / f"{tabela}.csv", encoding="utf-8-sig", newline="") as f:
                    linhas = list(csv.DictReader(f))
                colunas = list(linhas[0])
                sql = f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})"
                con.executemany(sql, [[v if v != "" else None for v in l.values()] for l in linhas])  # vazio = NULL
            criar_logins_padrao(con)
        return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ORDEM + ["usuario"]}
    finally:
        con.close()


@click.command("importar")
def importar_cli():
    """Importa o dataset sintético (dados/) para o banco."""
    for tabela, qtd in importar().items():
        click.echo(f"{tabela:24} {qtd}")
