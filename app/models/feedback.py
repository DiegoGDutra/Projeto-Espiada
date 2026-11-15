"""Comentários do aluno sobre o curso ou a instituição (tabela feedback)."""
from models.banco import consultar, transacao


def registrar(matricula, alvo, comentarios=None, avaliacao_curso=None):
    with transacao() as con:  # alvo fora de curso/instituição ou nota fora de 1 a 5: o banco recusa
        novo_id = con.execute("""
            INSERT INTO feedback (aluno_id, alvo, comentarios, avaliacao_curso)
            SELECT aluno_id, %s, %s, %s FROM alunos WHERE codigo_academico = %s
            RETURNING feedback_id""", (alvo, comentarios, avaliacao_curso, matricula)).fetchone()
    return consultar("SELECT * FROM feedback WHERE feedback_id = %s", novo_id["feedback_id"])[0]
