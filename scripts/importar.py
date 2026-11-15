"""Importa o dataset sintético (CSVs em dados/) para o banco. É a única entrada de notas e frequência.
Também cria um login padrão de cada perfil (LOGINS_PADRAO), para o sistema já abrir usável, e um login para cada
aluno (aes0002@simpa.test...) e docente (docente2@simpa.test...) com a senha padrão do perfil.

Rodar:  python scripts/importar.py   ->  enche o PostgreSQL de DATABASE_URL (se já tiver alunos, só confere os logins padrão)
Para importar de novo: zere o banco (com Docker: docker compose down -v && docker compose up -d) e rode outra vez.
"""
import csv
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))  # o sistema (models) fica em app/
from models.banco import conectar, criar_banco

DADOS = Path(__file__).resolve().parent.parent / "dados"
ORDEM = ["cursos", "periodos_curriculares", "disciplinas", "cidades", "docentes", "alunos", "enderecos_alunos",
         "perfis_socioeconomicos", "tipos_bolsa", "bolsas_alunos", "matriculas_curso", "turmas",
         "registros_academicos", "indicadores_risco", "desfechos_alunos"]  # ordem das chaves estrangeiras

# login, perfil, senha, vínculo (matrícula do aluno / docente_id). Troque as senhas fora do ambiente de teste.
LOGINS_PADRAO = [
    ("secretaria@simpa.test", "secretaria", "Secretaria#2026", None),
    ("professor@simpa.test", "professor", "Professor#2026", 1),  # vinculado ao docente_id 1
    ("aluno@simpa.test", "aluno", "Aluno#2026", "AES0001"),
]


def criar_logins_padrao(con):
    """Grava os LOGINS_PADRAO que ainda não existem (secretaria e professor com nome genérico, aluno com o do dataset)."""
    for login, perfil, senha, vinculo in LOGINS_PADRAO:
        hash_ = generate_password_hash(senha)
        if perfil == "secretaria":
            con.execute("""INSERT INTO usuario VALUES (%s, 'secretaria', 'Secretaria', %s, NULL, NULL)
                             ON CONFLICT DO NOTHING""", (login, hash_))
        elif perfil == "professor":
            con.execute("""INSERT INTO usuario SELECT %s, 'professor', 'Professor', %s, NULL, docente_id
                             FROM docentes WHERE docente_id = %s ON CONFLICT DO NOTHING""", (login, hash_, vinculo))
        else:
            con.execute("""INSERT INTO usuario SELECT %s, 'aluno', nome_sintetico, %s, aluno_id, NULL
                             FROM alunos WHERE codigo_academico = %s ON CONFLICT DO NOTHING""", (login, hash_, vinculo))
    # os demais alunos e docentes: login pela matrícula / docente_id, mesma senha padrão do perfil.
    # ON CONFLICT pula quem já tem login (o aluno 1 e o docente 1 são os padrão acima).
    senha = {perfil: generate_password_hash(s) for _, perfil, s, _ in LOGINS_PADRAO}
    con.execute("""INSERT INTO usuario SELECT lower(codigo_academico) || '@simpa.test', 'aluno',
                     nome_sintetico, %s, aluno_id, NULL FROM alunos ON CONFLICT DO NOTHING""", (senha["aluno"],))
    con.execute("""INSERT INTO usuario SELECT 'docente' || docente_id || '@simpa.test', 'professor',
                     nome_sintetico, %s, NULL, docente_id FROM docentes ON CONFLICT DO NOTHING""", (senha["professor"],))


def importar(pasta=DADOS):
    criar_banco()
    with conectar() as con:  # tudo ou nada: só grava no fim, se nada falhar
        if con.execute("SELECT count(*) FROM alunos").fetchone()["count"]:
            criar_logins_padrao(con)
            con.commit()
            raise SystemExit("O banco já tem dados importados (logins padrão conferidos). "
                             "Zere o banco para importar de novo (com Docker: docker compose down -v).")
        for tabela in ORDEM:
            with open(pasta / f"{tabela}.csv", encoding="utf-8-sig", newline="") as f:
                colunas = f.readline().strip()
                # COPY lê o CSV direto (bem mais rápido que um INSERT por linha); campo vazio vira NULL
                with con.cursor().copy(f"COPY {tabela} ({colunas}) FROM STDIN WITH (FORMAT csv)") as copia:
                    copia.write(f.read())
        criar_logins_padrao(con)
        return {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()["count"] for t in ORDEM + ["usuario"]}


if __name__ == "__main__":
    for tabela, qtd in importar().items():
        print(f"{tabela:24} {qtd}")
