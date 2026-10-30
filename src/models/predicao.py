"""Risco de evasão: as regras do cálculo e o histórico de predições (tabela predicao_ia)."""
from models.banco import consultar, transacao

# pesos fixos (os do readme); semana 05 deixa configurável e soma a LLM (semana 06)
REGRAS = [
    ("freq", lambda v: v < 75, 2, "Frequência abaixo de 75%"),
    ("nota", lambda v: v < 60, 2, "Nota média abaixo de 60"),
    ("reprovacoes", lambda v: v > 0, 1, "Reprovações no histórico"),
    ("reclamacoes", lambda v: v > 0, 1, "Reclamações no feedback"),
    ("distancia", lambda v: v > 30, 1, "Mora a mais de 30 km do campus"),
]


def calcular_risco(aluno):
    score, fatores = 0, []
    for campo, ruim, peso, descricao in REGRAS:
        if aluno[campo] is None:
            continue  # sem dado, não conta nem a favor nem contra
        negativo = ruim(aluno[campo])
        score += peso * negativo
        fatores.append({"descricao": descricao, "negativo": negativo})
    risco = "alto" if score >= 4 else "medio" if score >= 2 else "baixo"
    return {"risco": risco, "score": score, "fatores": fatores}


def salvar(matricula, resultado):
    """Cada cálculo vira uma linha nova no histórico (nada é sobrescrito)."""
    with transacao() as con:
        con.execute("""
            INSERT INTO predicao_ia (matricula_curso_id, nivel_risco, score)
            SELECT matricula_curso_id, ?, ? FROM matriculas_curso JOIN alunos USING (aluno_id)
             WHERE codigo_academico = ?""", (resultado["risco"], resultado["score"], matricula))


def historico(matricula):
    return consultar("""
        SELECT p.predicao_id AS id, p.criado_em, p.nivel_risco AS risco, p.score, p.comentario_predicao,
               p.alterada_por, p.justificativa
          FROM predicao_ia p JOIN matriculas_curso USING (matricula_curso_id) JOIN alunos a USING (aluno_id)
         WHERE a.codigo_academico = ? ORDER BY p.predicao_id DESC""", matricula)
