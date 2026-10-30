"""Confere as regras do schema.sql num banco em memória.  Rodar:  python src/teste_banco.py"""
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


con.execute("INSERT INTO cursos VALUES (1, 'Engenharia de Software', 'Bacharelado', 8, 40, 'Presencial', 'Anápolis', 'GO')")
con.execute("INSERT INTO periodos_curriculares VALUES (1, 1, 1, 5, 400)")
con.execute("INSERT INTO disciplinas VALUES (1, 1, 'ES0101', 'Lógica', 80, 'Teórica', 0.2)")
con.execute("INSERT INTO docentes VALUES (1, 'Docente Ada', 'Mestre', 'Integral')")
con.execute("INSERT INTO alunos VALUES (1, 'AES0001', 'Estudante 001', '2000-01-01', 'NÃO_INFORMADO', 'SINTETICO')")
con.execute("INSERT INTO matriculas_curso VALUES (1, 1, 1, '2026-08-01', 2026, 2, 1, 'Noturno', 'ATIVO', 'ENEM', '2026-08-01')")
con.execute("INSERT INTO turmas VALUES (1, 1, 1, 2026, 2, 'ES0101-2026.2-A', 'Noturno', 'Presencial', 45, 80)")
con.execute("INSERT INTO registros_academicos VALUES (1, 1, 1, 1, 'EM_CURSO', 70, NULL, NULL, 70, NULL, 90, 8, 80, '2026-10-01')")
con.execute("INSERT INTO usuario VALUES ('ada@simpa.test', 'professor', 'Ada', 'hash', NULL, 1)")
con.execute("INSERT INTO predicao_ia (matricula_curso_id, nivel_risco) VALUES (1, 'baixo')")
con.execute("INSERT INTO predicao_ia (matricula_curso_id, nivel_risco) VALUES (1, 'medio')")

assert con.execute("SELECT count(*) FROM predicao_ia").fetchone()[0] == 2, "histórico guarda várias predições"
assert recusa("INSERT INTO alunos VALUES (2, 'AES0001', 'X', '2000-01-01', 'X', 'X')"), "matrícula repetida"
assert recusa("INSERT INTO matriculas_curso VALUES (2, 99, 1, 'x', 2026, 2, 1, 'x', 'x', 'x', 'x')"), "aluno inexistente"
assert recusa("UPDATE registros_academicos SET nota_n1 = 101"), "nota acima de 100"
assert recusa("UPDATE registros_academicos SET frequencia_percentual = -1"), "frequência abaixo de 0"
assert recusa("INSERT INTO usuario VALUES ('x', 'admin', 'X', 'h', NULL, NULL)"), "perfil inválido"
assert recusa("INSERT INTO usuario VALUES ('x', 'aluno', 'X', 'h', NULL, NULL)"), "usuário aluno sem aluno ligado"
assert recusa("INSERT INTO predicao_ia (matricula_curso_id, nivel_risco) VALUES (1, 'altissimo')"), "nível inválido"
assert recusa("INSERT INTO predicao_ia (matricula_curso_id, nivel_risco, alterada_por) VALUES (1, 'alto', 'ada@simpa.test')"), \
    "alteração manual sem justificativa"
assert recusa("INSERT INTO feedback (aluno_id, alvo) VALUES (1, 'professor')"), "feedback só de curso/instituição"
print("ok: todas as regras do banco funcionam")
