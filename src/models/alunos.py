"""Alunos: resumo com os indicadores, ficha com as disciplinas e quem pode ver quem."""
from models.banco import consultar

# Indicadores por aluno (fórmulas no readme). Campo fica null quando ainda não há dado.
# A matrícula do aluno é o codigo_academico do dataset.
RESUMO_ALUNO = """
SELECT a.codigo_academico AS matricula, a.nome_sintetico AS nome, c.nome AS curso,
       mc.periodo_atual AS periodo, mc.status AS situacao,
       ci.distancia_rodoviaria_aprox_km AS distancia,
       (SELECT group_concat(d.nome, ', ') FROM registros_academicos r
          JOIN turmas t USING (turma_id) JOIN disciplinas d USING (disciplina_id)
         WHERE r.matricula_curso_id = mc.matricula_curso_id AND r.situacao = 'EM_CURSO') AS turma,
       (SELECT round(avg(frequencia_percentual), 1) FROM registros_academicos r
         WHERE r.matricula_curso_id = mc.matricula_curso_id) AS freq,
       (SELECT round(avg(coalesce(nota_final, nota_parcial)), 1) FROM registros_academicos r
         WHERE r.matricula_curso_id = mc.matricula_curso_id) AS nota,
       (SELECT count(*) FROM registros_academicos r
         WHERE r.matricula_curso_id = mc.matricula_curso_id AND r.situacao LIKE 'REPROVADO%') AS reprovacoes,
       (SELECT count(*) FROM feedback f
         WHERE f.aluno_id = a.aluno_id AND f.avaliacao_curso <= 2) AS reclamacoes,
       (SELECT count(*) FROM registros_academicos r
         WHERE r.matricula_curso_id = mc.matricula_curso_id) AS registros
  FROM alunos a JOIN matriculas_curso mc USING (aluno_id) JOIN cursos c USING (curso_id)
  LEFT JOIN enderecos_alunos e USING (aluno_id) LEFT JOIN cidades ci USING (cidade_id)
"""


def filtro_visiveis(usuario):
    """Filtro SQL dos alunos que esse usuário pode ver: secretaria todos, professor os das turmas dele,
    aluno só ele mesmo. usuario é um dict com perfil, docente_id e aluno_id."""
    if usuario["perfil"] == "secretaria":
        return "1", ()
    if usuario["perfil"] == "professor":  # alunos que já passaram por alguma turma dele
        return """mc.matricula_curso_id IN (SELECT r.matricula_curso_id FROM registros_academicos r
                  JOIN turmas t USING (turma_id) WHERE t.docente_id = ?)""", (usuario["docente_id"],)
    return "a.aluno_id = ?", (usuario["aluno_id"],)


def listar(usuario):
    filtro, args = filtro_visiveis(usuario)
    return consultar(RESUMO_ALUNO + f" WHERE {filtro} ORDER BY a.nome_sintetico", *args)


def buscar(matricula, usuario):
    """Resumo do aluno, ou None se não existe ou o usuário não pode ver."""
    filtro, args = filtro_visiveis(usuario)
    achados = consultar(RESUMO_ALUNO + f" WHERE a.codigo_academico = ? AND {filtro}", matricula, *args)
    return achados[0] if achados else None


def existe(matricula):
    return bool(consultar("SELECT 1 FROM alunos WHERE codigo_academico = ?", matricula))


def comentarios(matricula, limite=3):
    """Últimos feedbacks do aluno (nota e texto livre), do mais novo para o mais antigo. Vão para a LLM só como dado."""
    return consultar("""
        SELECT f.alvo, f.avaliacao_curso AS avaliacao, f.comentarios AS comentario
          FROM feedback f JOIN alunos a USING (aluno_id)
         WHERE a.codigo_academico = ? AND (f.avaliacao_curso IS NOT NULL OR coalesce(f.comentarios, '') <> '')
         ORDER BY f.feedback_id DESC LIMIT ?""", matricula, limite)


def disciplinas(matricula):
    return consultar("""
        SELECT t.codigo_turma, d.nome AS disciplina, t.ano_letivo || '.' || t.semestre_letivo AS semestre,
               r.tentativa, r.situacao, r.nota_n1, r.nota_n2, r.nota_projeto, r.nota_parcial, r.nota_final,
               r.frequencia_percentual, r.faltas_horas
          FROM registros_academicos r JOIN turmas t USING (turma_id) JOIN disciplinas d USING (disciplina_id)
          JOIN matriculas_curso mc USING (matricula_curso_id) JOIN alunos a USING (aluno_id)
         WHERE a.codigo_academico = ? ORDER BY semestre, d.nome""", matricula)
