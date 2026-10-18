"""Importa o dataset sintético (CSVs em dados/) para o banco. É a única entrada de notas e frequência (RN11).

Rodar:  python src/importar.py   ->  enche o src/funcionaai.db (só se ainda não tiver alunos)
Para importar de novo: apague src/funcionaai.db e rode outra vez.
"""
import csv
from pathlib import Path

import Espiada

DADOS = Path(__file__).resolve().parent.parent / "dados"
ORDEM = ["cursos", "periodos_curriculares", "disciplinas", "cidades", "docentes", "alunos", "enderecos_alunos",
         "perfis_socioeconomicos", "tipos_bolsa", "bolsas_alunos", "matriculas_curso", "turmas",
         "registros_academicos", "indicadores_risco", "desfechos_alunos"]  # ordem das chaves estrangeiras


def importar(caminho=None, pasta=DADOS):
    Espiada.criar_banco(caminho)
    con = Espiada.conectar(caminho)
    try:
        if con.execute("SELECT count(*) FROM alunos").fetchone()[0]:
            raise SystemExit("O banco já tem dados importados. Apague src/funcionaai.db para importar de novo.")
        with con:  # tudo ou nada
            for tabela in ORDEM:
                with open(pasta / f"{tabela}.csv", encoding="utf-8-sig", newline="") as f:
                    linhas = list(csv.DictReader(f))
                colunas = list(linhas[0])
                sql = f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})"
                con.executemany(sql, [[v if v != "" else None for v in l.values()] for l in linhas])  # vazio = NULL
        return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ORDEM}
    finally:
        con.close()


if __name__ == "__main__":
    for tabela, qtd in importar().items():
        print(f"{tabela:24} {qtd}")
