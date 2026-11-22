"""Modelo estatístico de risco: transforma o histórico do aluno em uma chance de evasão (regressão logística).

Aqui fica só o uso do modelo já treinado; quem treina é o treino.py. Nunca lê indicadores_risco nem desfechos_alunos.
As variáveis são acadêmicas: sem nome, matrícula, gênero, renda ou endereço.
"""
import json
import math

from models.banco import consultar, transacao

CORTE_MEDIO = 0.15  # chance de evasão a partir da qual o risco é "médio" (um pouco acima da taxa geral, 12,8%)
CORTE_ALTO = 0.30   # a partir daqui é "alto" (mais que o dobro da taxa geral)
VARIAVEIS = ("nota", "frequencia", "nota_atual", "taxa_reprovacao", "reprovacoes_log", "periodo", "tendencia_nota",
             "tendencia_frequencia", "queda_nota", "mudanca_ultimo_semestre", "tem_historico")

POR_SEMESTRE = """
SELECT a.codigo_academico AS matricula, mc.periodo_atual AS periodo, t.ano_letivo * 2 + t.semestre_letivo AS semestre,
       sum(coalesce(r.nota_final, r.nota_parcial)) AS soma_nota, count(coalesce(r.nota_final, r.nota_parcial)) AS qtd_nota,
       sum(r.frequencia_percentual) AS soma_freq, count(r.frequencia_percentual) AS qtd_freq,
       avg(r.nota_parcial) FILTER (WHERE r.situacao = 'EM_CURSO') AS nota_atual,
       count(*) FILTER (WHERE r.tentativa = 1 AND r.situacao <> 'EM_CURSO') AS cursadas,
       count(*) FILTER (WHERE r.tentativa = 1 AND starts_with(r.situacao, 'REPROVADO')) AS reprovadas
  FROM registros_academicos r JOIN turmas t USING (turma_id)
  JOIN matriculas_curso mc USING (matricula_curso_id) JOIN alunos a USING (aluno_id)
 WHERE %s::text[] IS NULL OR a.codigo_academico = ANY(%s)
 GROUP BY 1, 2, 3 ORDER BY 1, 3"""


def _inclinacao(xs, ys):
    """Inclinação da reta de regressão: quanto y sobe ou desce por semestre. Com menos de 2 pontos, 0."""
    if len(xs) < 2:
        return 0.0
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


def calcular_variaveis(periodo, semestres):
    """Valores na ordem de VARIAVEIS, a partir das linhas de POR_SEMESTRE. None se o aluno ainda não tem nota."""
    com_nota = [s for s in semestres if s["qtd_nota"]]
    if not com_nota:
        return None
    com_freq = [s for s in semestres if s["qtd_freq"]]
    notas = [s["soma_nota"] / s["qtd_nota"] for s in com_nota]
    freqs = [s["soma_freq"] / s["qtd_freq"] for s in com_freq]
    nota = sum(s["soma_nota"] for s in com_nota) / sum(s["qtd_nota"] for s in com_nota)
    freq = sum(s["soma_freq"] for s in com_freq) / sum(s["qtd_freq"] for s in com_freq) if com_freq else None
    atuais = [s["nota_atual"] for s in semestres if s["nota_atual"] is not None]
    cursadas, reprovadas = sum(s["cursadas"] for s in semestres), sum(s["reprovadas"] for s in semestres)
    tendencia = _inclinacao([s["semestre"] for s in com_nota], notas)
    mudanca = notas[-1] - sum(notas[:-1]) / len(notas[:-1]) if len(notas) > 1 else 0.0
    return [nota, freq, atuais[-1] if atuais else nota, reprovadas / cursadas if cursadas else 0.0,
            math.log1p(reprovadas), float(periodo), tendencia, _inclinacao([s["semestre"] for s in com_freq], freqs),
            min(tendencia, 0.0), mudanca, float(len(notas) > 1)]


def variaveis(matriculas=None):
    """{matricula: valores} dos alunos pedidos (None = todos), numa consulta só."""
    por_aluno = {}
    for linha in consultar(POR_SEMESTRE, matriculas, matriculas):
        por_aluno.setdefault(linha["matricula"], (linha["periodo"], []))[1].append(linha)
    calculadas = {m: calcular_variaveis(periodo, linhas) for m, (periodo, linhas) in por_aluno.items()}
    return {m: valores for m, valores in calculadas.items() if valores}


def probabilidade(pesos, valores):
    """Chance de evasão de 0 a 1. Valor ausente entra como a média do treino (não pesa nem a favor nem contra)."""
    z = [0.0 if v is None else (v - m) / d for v, m, d in zip(valores, pesos["medias"], pesos["desvios"])]
    soma = pesos["intercepto"] + sum(c * v for c, v in zip(pesos["coeficientes"], z))
    return 1 / (1 + math.exp(-max(min(soma, 30), -30)))


def nivel(chance):
    return "alto" if chance >= CORTE_ALTO else "medio" if chance >= CORTE_MEDIO else "baixo"


def ativo():
    """Último modelo aprovado: {id, criado_em, pesos, metricas}. None se nenhum foi treinado."""
    linhas = consultar("""SELECT modelo_id AS id, criado_em, pesos, metricas FROM modelo_risco
                           WHERE aprovado ORDER BY modelo_id DESC LIMIT 1""")
    if not linhas:
        return None
    return linhas[0] | {"pesos": json.loads(linhas[0]["pesos"]), "metricas": json.loads(linhas[0]["metricas"])}


def prever(matriculas=None):
    """{matricula: {probabilidade, nivel, modelo_id}} pelo modelo ativo; vazio se não há modelo ou dados do aluno."""
    modelo = ativo()
    if not modelo:
        return {}
    previsoes = {}
    for matricula, valores in variaveis(matriculas).items():
        chance = probabilidade(modelo["pesos"], valores)
        previsoes[matricula] = {"probabilidade": round(chance, 3), "nivel": nivel(chance), "modelo_id": modelo["id"]}
    return previsoes


def salvar(pesos, metricas, aprovado):
    """Guarda um treinamento (nunca sobrescreve) e devolve a versão."""
    with transacao() as con:
        return con.execute("INSERT INTO modelo_risco (pesos, metricas, aprovado) VALUES (%s, %s, %s) RETURNING modelo_id",
                           (json.dumps(pesos), json.dumps(metricas), aprovado)).fetchone()["modelo_id"]
