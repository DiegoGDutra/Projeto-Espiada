"""Confere as regras do schema.sql num banco em memória.  Rodar:  python src/test_banco.py"""
import sqlite3

from Espiada import SCHEMA, conectar

con = conectar(":memory:")  # banco temporário, não mexe no funcionaai.db
con.executescript(SCHEMA.read_text(encoding="utf-8"))


def recusa(sql, *args):
    try:
        con.execute(sql, args)
    except sqlite3.IntegrityError:
        return True
    return False


con.execute("INSERT INTO curso VALUES (1, 'Engenharia de Software')")
con.execute("INSERT INTO usuario VALUES (2024001, 'aluno', 'Ana', 'ana@email.com', 'hash')")
con.execute("INSERT INTO usuario VALUES (900, 'professor', 'Prof', NULL, 'hash')")
con.execute("INSERT INTO aluno VALUES (2024001, 1, 2, 1, '2024-02-01', 12.5)")
con.execute("INSERT INTO materia VALUES (10, 1, 'Cálculo')")
con.execute("INSERT INTO turma VALUES (3, 10, 900, '2026.2')")
con.execute("INSERT INTO desempenho_aluno VALUES (2024001, 3, 'cursando', 70, 65, NULL, NULL, 80, 12)")
con.execute("INSERT INTO predicao_ia (matricula, nivel_risco) VALUES (2024001, 'baixo')")
con.execute("INSERT INTO predicao_ia (matricula, nivel_risco) VALUES (2024001, 'medio')")

assert con.execute("SELECT count(*) FROM predicao_ia").fetchone()[0] == 2, "histórico guarda várias predições"
assert recusa("INSERT INTO usuario VALUES (1, 'admin', 'X', NULL, 'h')"), "perfil inválido"
assert recusa("INSERT INTO aluno VALUES (5, 1, 1, 1, NULL, NULL)"), "aluno sem usuário (chave estrangeira)"
assert recusa("INSERT INTO aluno VALUES (900, 99, 1, 1, NULL, NULL)"), "curso inexistente"
assert recusa("UPDATE desempenho_aluno SET nota_cic1 = 101"), "nota acima de 100 (RN04)"
assert recusa("UPDATE desempenho_aluno SET faltas_totais = 81"), "mais faltas que aulas"
assert recusa("INSERT INTO predicao_ia (matricula, nivel_risco) VALUES (2024001, 'altissimo')"), "nível de risco inválido (RN06)"
assert recusa("INSERT INTO predicao_ia (matricula, nivel_risco, alterada_por) VALUES (2024001, 'alto', 900)"), \
    "alteração manual sem justificativa (RN15)"
assert recusa("INSERT INTO feedback (matricula, alvo) VALUES (2024001, 'professor')"), "feedback só de curso/instituição (RN05)"
print("ok: todas as regras do banco funcionam")
