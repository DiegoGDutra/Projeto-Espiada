"""Estrutura acadêmica (cursos, disciplinas, docentes, turmas). Só leitura: vem do dataset."""
from models.banco import consultar

LISTAS = {
    "cursos": "SELECT * FROM cursos ORDER BY curso_id",
    "disciplinas": "SELECT * FROM disciplinas ORDER BY disciplina_id",
    "docentes": "SELECT * FROM docentes ORDER BY docente_id",
    "turmas": "SELECT * FROM turmas ORDER BY turma_id",
}


def listar(recurso):
    return consultar(LISTAS[recurso])
