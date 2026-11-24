"""Estatística do sistema: medidas descritivas, distribuições, aprovação, evolução, fatores ligados à evasão,
comparação entre grupos, avaliação por período e turma e exportação em CSV.

Professor vê só os registros das próprias turmas; secretaria vê todos. O que usa o desfecho ou o perfil socioeconômico
(fatores e comparações) é só da secretaria. O desfecho vem de avaliacao.gabarito() e nunca volta para a predição.
As escolhas de cada cálculo estão no readme.md, seção "Estatística".
"""
import csv
import io
import re

from models import avaliacao, inferencia, modelo_risco, predicao, treino
from models.banco import ErroModelo, consultar

FAIXAS = 20                # histograma de 0 a 100 em faixas de 5 pontos
TOPO_TURMAS = 15           # quantas turmas aparecem no ranking da tela (o CSV traz todas)
MINIMO_TURMA = 20          # turma com menos matrículas concluídas não entra no ranking: a taxa seria instável
CORTE_DISTANCIA = 30       # o mesmo corte das regras de risco
SO_SECRETARIA = {"fatores", "correlacoes", "comparacoes"}

BASE = """
SELECT r.situacao, coalesce(r.nota_final, r.nota_parcial) AS nota, r.frequencia_percentual AS freq,
       mc.periodo_atual AS periodo, d.codigo AS disciplina_codigo, d.nome AS disciplina, t.codigo_turma,
       t.ano_letivo || '.' || t.semestre_letivo AS semestre, t.ano_letivo * 2 + t.semestre_letivo AS ordem
  FROM registros_academicos r JOIN turmas t USING (turma_id) JOIN disciplinas d USING (disciplina_id)
  JOIN matriculas_curso mc USING (matricula_curso_id)"""
GRUPOS = {"geral": "'geral'", "periodo": "periodo", "disciplina": "disciplina_codigo || ' — ' || disciplina",
          "semestre": "semestre", "turma": "codigo_turma || ' — ' || disciplina"}
VARIAVEIS = {"nota": "nota", "frequencia": "freq"}


def _r(valor, casas=2):
    return None if valor is None else round(valor, casas)


def ler_filtros(args):
    """Filtros da URL (período, disciplina, turma e semestre) validados; 400 se algum vier inválido."""
    filtros = {}
    for chave in ("periodo", "disciplina", "turma"):
        valor = (args.get(chave) or "").strip()
        if valor:
            if not valor.isascii() or not valor.isdigit() or len(valor) > 9:
                raise ErroModelo(400, f"filtro inválido: {chave}")
            filtros[chave] = int(valor)
    semestre = (args.get("semestre") or "").strip()
    if semestre:
        if not re.fullmatch(r"[0-9]{4}\.[12]", semestre):
            raise ErroModelo(400, "filtro inválido: semestre")
        filtros["semestre"] = (int(semestre[:4]), int(semestre[5]))
    return filtros


def _base(filtros, usuario):
    """SQL dos registros que o usuário pode ver, já com os filtros, e seus parâmetros."""
    condicoes, valores = [], []
    if usuario["perfil"] == "professor":
        condicoes.append("t.docente_id = %s")
        valores.append(usuario["docente_id"])
    for chave, coluna in (("periodo", "mc.periodo_atual"), ("disciplina", "t.disciplina_id"), ("turma", "t.turma_id")):
        if chave in filtros:
            condicoes.append(f"{coluna} = %s")
            valores.append(filtros[chave])
    if "semestre" in filtros:
        condicoes.append("t.ano_letivo = %s AND t.semestre_letivo = %s")
        valores.extend(filtros["semestre"])
    return BASE + (" WHERE " + " AND ".join(condicoes) if condicoes else ""), valores


def opcoes(usuario):
    """O que pode ser escolhido nos filtros da tela, dentro do que o usuário pode ver."""
    base, args = _base({}, usuario)
    periodos = consultar(f"SELECT DISTINCT periodo FROM ({base}) b ORDER BY 1", *args)
    semestres = consultar(f"SELECT DISTINCT semestre FROM ({base}) b ORDER BY 1 DESC", *args)
    filtro = "WHERE t.docente_id = %s" if usuario["perfil"] == "professor" else ""
    args = (usuario["docente_id"],) if filtro else ()
    turmas = consultar(f"""
        SELECT t.turma_id AS id, t.codigo_turma AS codigo, t.disciplina_id,
               d.codigo || ' — ' || d.nome AS disciplina, t.ano_letivo || '.' || t.semestre_letivo AS semestre
          FROM turmas t JOIN disciplinas d USING (disciplina_id) {filtro} ORDER BY t.codigo_turma""", *args)
    disciplinas = {t["disciplina_id"]: t["disciplina"] for t in turmas}
    return {"periodos": [l["periodo"] for l in periodos], "semestres": [l["semestre"] for l in semestres],
            "disciplinas": [{"id": i, "nome": n} for i, n in sorted(disciplinas.items(), key=lambda x: x[1])],
            "turmas": turmas}


# ---------- descritiva e distribuições ----------

def medidas(variavel, filtros, usuario, grupo="geral"):
    """Média, mediana, moda, desvio padrão, mínimo, máximo, quartis e bigodes do boxplot (regra de 1,5 x IQR)."""
    coluna, rotulo = VARIAVEIS[variavel], GRUPOS[grupo]
    base, args = _base(filtros, usuario)
    linhas = consultar(f"""
        WITH v AS (SELECT {rotulo} AS grupo, {coluna} AS valor FROM ({base}) b WHERE {coluna} IS NOT NULL),
        q AS (SELECT grupo, count(*) AS n, avg(valor) AS media, stddev_samp(valor) AS desvio, min(valor) AS minimo,
                     max(valor) AS maximo, mode() WITHIN GROUP (ORDER BY valor) AS moda,
                     percentile_cont(0.25) WITHIN GROUP (ORDER BY valor) AS q1,
                     percentile_cont(0.5) WITHIN GROUP (ORDER BY valor) AS mediana,
                     percentile_cont(0.75) WITHIN GROUP (ORDER BY valor) AS q3
                FROM v GROUP BY grupo)
        SELECT q.grupo, q.n, q.media, q.desvio, q.minimo, q.maximo, q.moda, q.q1, q.mediana, q.q3,
               min(v.valor) FILTER (WHERE v.valor >= q.q1 - 1.5 * (q.q3 - q.q1)) AS bigode_inf,
               max(v.valor) FILTER (WHERE v.valor <= q.q3 + 1.5 * (q.q3 - q.q1)) AS bigode_sup,
               count(*) FILTER (WHERE v.valor < q.q1 - 1.5 * (q.q3 - q.q1)
                                   OR v.valor > q.q3 + 1.5 * (q.q3 - q.q1)) AS atipicos,
               count(*) FILTER (WHERE v.valor = q.moda) AS moda_repeticoes
          FROM q JOIN v USING (grupo)
         GROUP BY q.grupo, q.n, q.media, q.desvio, q.minimo, q.maximo, q.moda, q.q1, q.mediana, q.q3
         ORDER BY q.grupo""", *args)
    saida = [{c: (_r(v) if isinstance(v, float) else v) for c, v in l.items()} for l in linhas]
    for l in saida:
        if l["moda_repeticoes"] < 2:  # nenhum valor se repete: não há moda (o PostgreSQL devolveria o menor valor)
            l["moda"] = None
    return saida


def descritiva(filtros, usuario):
    saida = {}
    for variavel in VARIAVEIS:
        linhas = medidas(variavel, filtros, usuario)
        saida[variavel] = linhas[0] if linhas else None
    return saida


def histogramas(filtros, usuario):
    """Contagem por faixa de 5 pontos. O valor 100 entra na última faixa."""
    base, args = _base(filtros, usuario)
    linhas = consultar(f"""
        WITH b AS ({base})
        SELECT 'nota' AS variavel, least(width_bucket(nota, 0, 100, {FAIXAS}), {FAIXAS}) AS faixa, count(*) AS n
          FROM b WHERE nota IS NOT NULL GROUP BY 2
        UNION ALL
        SELECT 'frequencia', least(width_bucket(freq, 0, 100, {FAIXAS}), {FAIXAS}), count(*)
          FROM b WHERE freq IS NOT NULL GROUP BY 2""", *args)
    largura = 100 // FAIXAS
    saida = {v: [{"de": i * largura, "ate": (i + 1) * largura, "n": 0} for i in range(FAIXAS)] for v in VARIAVEIS}
    for l in linhas:
        saida[l["variavel"]][l["faixa"] - 1]["n"] = l["n"]
    return saida


# ---------- aprovação e reprovação ----------

def aprovacao(recorte, filtros, usuario):
    """Taxas sobre as matrículas concluídas (quem está em curso não conta), da maior reprovação para a menor."""
    base, args = _base(filtros, usuario)
    linhas = consultar(f"""
        SELECT {GRUPOS[recorte]} AS grupo,
               count(*) FILTER (WHERE situacao <> 'EM_CURSO') AS concluidas,
               count(*) FILTER (WHERE situacao = 'APROVADO') AS aprovados,
               count(*) FILTER (WHERE situacao = 'REPROVADO_NOTA') AS reprovados_nota,
               count(*) FILTER (WHERE situacao = 'REPROVADO_FREQUENCIA') AS reprovados_frequencia,
               count(*) FILTER (WHERE situacao = 'EM_CURSO') AS em_curso
          FROM ({base}) b GROUP BY 1""", *args)
    saida = []
    for l in linhas:
        total, reprovados = l["concluidas"], l["reprovados_nota"] + l["reprovados_frequencia"]
        saida.append(l | {"taxa_aprovacao": _r(l["aprovados"] / total, 4) if total else None,
                          "taxa_reprovacao": _r(reprovados / total, 4) if total else None,
                          "taxa_reprovacao_nota": _r(l["reprovados_nota"] / total, 4) if total else None,
                          "taxa_reprovacao_frequencia": _r(l["reprovados_frequencia"] / total, 4) if total else None,
                          "ic_reprovacao": avaliacao.ic_proporcao(reprovados, total)})
    if recorte == "semestre":
        return sorted(saida, key=lambda x: x["grupo"])
    return sorted(saida, key=lambda x: (x["taxa_reprovacao"] is None, -(x["taxa_reprovacao"] or 0), x["grupo"]))


def _ranking_turmas(filtros, usuario):
    linhas = aprovacao("turma", filtros, usuario)
    aptas = [l for l in linhas if l["concluidas"] >= MINIMO_TURMA]
    return {"total": len(linhas), "aptas": len(aptas), "minimo": MINIMO_TURMA, "linhas": aptas[:TOPO_TURMAS]}


# ---------- evolução ----------

def _tendencia(pontos, campo):
    """Inclinação da reta (por semestre), só com semestres concluídos: nota parcial não é comparável à final."""
    validos = [p for p in pontos if not p["parcial"] and p[campo] is not None]
    if len(validos) < 2:
        return None
    return round(modelo_risco._inclinacao([p["ordem"] for p in validos], [p[campo] for p in validos]), 2)


def evolucao(filtros, usuario):
    base, args = _base(filtros, usuario)
    linhas = consultar(f"""
        SELECT semestre, ordem, count(*) AS registros, avg(nota) AS nota, avg(freq) AS frequencia,
               count(*) FILTER (WHERE situacao <> 'EM_CURSO') AS concluidas
          FROM ({base}) b GROUP BY 1, 2 ORDER BY 2""", *args)
    pontos = [{"semestre": l["semestre"], "ordem": l["ordem"], "registros": l["registros"], "nota": _r(l["nota"]),
               "frequencia": _r(l["frequencia"]), "parcial": not l["concluidas"]} for l in linhas]
    return {"pontos": pontos, "tendencia": {"nota": _tendencia(pontos, "nota"),
                                            "frequencia": _tendencia(pontos, "frequencia")}}


def evolucao_aluno(disciplinas):
    """Média por semestre e tendência de um aluno, a partir das linhas de alunos.disciplinas()."""
    semestres = {}
    for d in disciplinas:
        s = semestres.setdefault(d["semestre"], {"notas": [], "freqs": [], "concluidas": 0})
        nota = d["nota_final"] if d["nota_final"] is not None else d["nota_parcial"]
        if nota is not None:
            s["notas"].append(nota)
        if d["frequencia_percentual"] is not None:
            s["freqs"].append(d["frequencia_percentual"])
        s["concluidas"] += d["situacao"] != "EM_CURSO"

    def media(valores):
        return round(sum(valores) / len(valores), 2) if valores else None

    pontos = [{"semestre": sem, "ordem": int(sem[:4]) * 2 + int(sem[5:]), "nota": media(s["notas"]),
               "frequencia": media(s["freqs"]), "parcial": not s["concluidas"]} for sem, s in sorted(semestres.items())]
    return {"pontos": pontos, "tendencia": {"nota": _tendencia(pontos, "nota"),
                                            "frequencia": _tendencia(pontos, "frequencia")}}


def painel(filtros, usuario):
    """Tudo o que a aba Estatística desenha de uma vez."""
    return {"descritiva": descritiva(filtros, usuario), "histogramas": histogramas(filtros, usuario),
            "boxplots": {v: {g: medidas(v, filtros, usuario, g) for g in ("periodo", "disciplina")} for v in VARIAVEIS},
            "aprovacao": {"disciplina": aprovacao("disciplina", filtros, usuario),
                          "semestre": aprovacao("semestre", filtros, usuario),
                          "turma": _ranking_turmas(filtros, usuario)},
            "evolucao": evolucao(filtros, usuario)}


# ---------- fatores ligados à evasão e comparação entre grupos (só secretaria) ----------

def _por_aluno():
    """Uma linha por aluno: indicadores acadêmicos e o perfil mais recente. A unidade de análise é o aluno, para não
    contar a mesma pessoa várias vezes."""
    return consultar("""
        SELECT a.codigo_academico AS matricula, mc.periodo_atual AS periodo, mc.turno, s.trabalha,
               s.horas_trabalho_semana AS horas_trabalho, s.qualidade_internet AS internet,
               s.escola_publica_origem AS escola_publica, ci.distancia_rodoviaria_aprox_km AS distancia,
               EXISTS (SELECT 1 FROM bolsas_alunos b WHERE b.aluno_id = a.aluno_id AND b.status = 'ATIVA') AS bolsista,
               h.nota, h.freq, h.reprovacoes, h.concluidas
          FROM alunos a JOIN matriculas_curso mc ON mc.aluno_id = a.aluno_id
          LEFT JOIN LATERAL (SELECT * FROM perfis_socioeconomicos p WHERE p.aluno_id = a.aluno_id
                              ORDER BY p.data_referencia DESC LIMIT 1) s ON TRUE
          LEFT JOIN enderecos_alunos e ON e.aluno_id = a.aluno_id
          LEFT JOIN cidades ci ON ci.cidade_id = e.cidade_id
          LEFT JOIN (SELECT matricula_curso_id, avg(coalesce(nota_final, nota_parcial)) AS nota,
                            avg(frequencia_percentual) AS freq,
                            count(*) FILTER (WHERE starts_with(situacao, 'REPROVADO')) AS reprovacoes,
                            count(*) FILTER (WHERE situacao <> 'EM_CURSO') AS concluidas
                       FROM registros_academicos GROUP BY 1) h ON h.matricula_curso_id = mc.matricula_curso_id""")


def _sim_nao(campo):
    return lambda a: None if a[campo] is None else "Sim" if a[campo] else "Não"


def _abaixo(campo, corte):
    return lambda a: None if a[campo] is None else "Sim" if a[campo] < corte else "Não"


INTERNET = {"BOA": "Boa", "REGULAR": "Regular", "INSTAVEL": "Instável"}
# chave, nome, níveis (com dois níveis, a razão de chances compara o 1º com o 2º) e como classificar o aluno
FATORES = [
    ("trabalha", "Trabalha", ("Sim", "Não"), _sim_nao("trabalha")),
    ("bolsista", "Tem bolsa ativa", ("Sim", "Não"), _sim_nao("bolsista")),
    ("distancia", "Distância até o campus", (f"Mais de {CORTE_DISTANCIA} km", f"Até {CORTE_DISTANCIA} km"),
     lambda a: None if a["distancia"] is None else
     f"Mais de {CORTE_DISTANCIA} km" if a["distancia"] > CORTE_DISTANCIA else f"Até {CORTE_DISTANCIA} km"),
    ("turno", "Turno", ("Noturno", "Matutino"), lambda a: a["turno"]),
    ("internet", "Qualidade da internet", ("Instável", "Regular", "Boa"), lambda a: INTERNET.get(a["internet"])),
    ("escola_publica", "Veio de escola pública", ("Sim", "Não"), _sim_nao("escola_publica")),
    ("freq_baixa", f"Frequência abaixo de {predicao.FREQ_CORTE}%", ("Sim", "Não"), _abaixo("freq", predicao.FREQ_CORTE)),
    ("nota_baixa", "Nota média abaixo de 60", ("Sim", "Não"), _abaixo("nota", 60)),
    ("reprovou", "Tem reprovação no histórico", ("Sim", "Não"),
     lambda a: None if a["reprovacoes"] is None else "Sim" if a["reprovacoes"] else "Não"),
]
CORRELACOES = [
    ("Nota média", lambda a: a["nota"]), ("Frequência média", lambda a: a["freq"]),
    ("Reprovações", lambda a: a["reprovacoes"]),
    ("Taxa de reprovação", lambda a: a["reprovacoes"] / a["concluidas"] if a["concluidas"] else None),
    ("Distância (km)", lambda a: a["distancia"]), ("Horas de trabalho por semana", lambda a: a["horas_trabalho"]),
    ("Período atual", lambda a: a["periodo"]),
]
COMPARACOES = ("trabalha", "bolsista", "escola_publica", "distancia", "turno")


def _fatores(linhas, evadiu):
    saida = []
    for chave, nome, niveis, classificar in FATORES:
        contagem = {n: [0, 0] for n in niveis}  # [evadiram, ficaram]
        for a in linhas:
            nivel = classificar(a)
            if nivel in contagem:
                contagem[nivel][0 if evadiu[a["matricula"]] else 1] += 1
        grupos = [{"nivel": n, "alunos": sum(c), "evasoes": c[0], "taxa": _r(c[0] / sum(c), 4),
                   "ic": avaliacao.ic_proporcao(c[0], sum(c))} for n, c in contagem.items() if sum(c)]
        teste = inferencia.qui_quadrado([contagem[g["nivel"]] for g in grupos])
        rc = None
        if len(niveis) == 2 and len(grupos) == 2:
            bruta = inferencia.razao_chances(*contagem[niveis[0]], *contagem[niveis[1]])
            rc = {"valor": _r(bruta["valor"], 3), "ic": [_r(v, 3) for v in bruta["ic"]],
                  "comparacao": f"{niveis[0]} x {niveis[1]}"}
        saida.append({"chave": chave, "nome": nome, "grupos": grupos, "razao_chances": rc, "teste": teste})
    ajustados = inferencia.holm([f["teste"] and f["teste"]["p"] for f in saida])
    for fator, p in zip(saida, ajustados):
        if fator["teste"]:
            t = fator["teste"]
            fator["teste"] = {"qui2": _r(t["qui2"]), "gl": t["gl"], "p": t["p"], "p_holm": p,
                              "v_cramer": _r(t["v_cramer"], 3), "valido": t["valido"]}
    return saida


def _correlacoes(linhas, evadiu):
    saida = []
    for nome, valor in CORRELACOES:
        pares = [(valor(a), evadiu[a["matricula"]]) for a in linhas if valor(a) is not None]
        c = inferencia.correlacao([float(x) for x, _ in pares], [float(y) for _, y in pares])
        saida.append({"nome": nome} | c)
    for campo in ("pearson_p", "spearman_p"):
        for linha, p in zip(saida, inferencia.holm([l[campo] for l in saida])):
            linha[campo + "_holm"] = p
    for linha in saida:
        linha["pearson"], linha["spearman"] = _r(linha["pearson"], 3), _r(linha["spearman"], 3)
    return saida


def _comparacoes(linhas):
    definicoes = {chave: (nome, niveis, classificar) for chave, nome, niveis, classificar in FATORES}
    saida = []
    for chave in COMPARACOES:
        nome, (nivel_a, nivel_b), classificar = definicoes[chave]
        for rotulo, campo in (("Nota", "nota"), ("Frequência", "freq")):
            a = [l[campo] for l in linhas if classificar(l) == nivel_a and l[campo] is not None]
            b = [l[campo] for l in linhas if classificar(l) == nivel_b and l[campo] is not None]
            resultado = inferencia.comparar_medias(a, b)
            if resultado:
                saida.append({"fator": nome, "variavel": rotulo, "grupo_a": nivel_a, "grupo_b": nivel_b} | resultado)
    for campo in ("p_welch", "p_mann_whitney"):
        for linha, p in zip(saida, inferencia.holm([l[campo] for l in saida])):
            linha[campo + "_holm"] = p
    for l in saida:
        for campo in ("media_a", "media_b", "diferenca", "t", "gl"):
            l[campo] = _r(l[campo])
        l["ic"] = [_r(v) for v in l["ic"]]
        l["d_cohen"], l["prob_superioridade"] = _r(l["d_cohen"], 3), _r(l["prob_superioridade"], 3)
    return saida


def analise_evasao():
    """Fatores, correlações e comparação entre grupos. Associação não é causa, e os valores-p usam a correção de Holm
    porque vários testes são feitos de uma vez."""
    evadiu = avaliacao.gabarito()
    linhas = [a for a in _por_aluno() if a["matricula"] in evadiu]
    evasoes = sum(evadiu[a["matricula"]] for a in linhas)
    return {"alunos": len(linhas), "evasoes": evasoes, "taxa": _r(evasoes / len(linhas), 4) if linhas else None,
            "fatores": _fatores(linhas, evadiu), "correlacoes": _correlacoes(linhas, evadiu),
            "comparacoes": _comparacoes(linhas)}


# ---------- avaliação do modelo por período e por turma ----------

def _resumo_avaliacao(grupo, itens):
    """Medidas de um grupo. A AUC só sai com eventos suficientes: em grupo pequeno ela oscila demais."""
    real = [i["evadiu"] for i in itens]
    n, evasoes = len(real), sum(real)
    suficiente = min(evasoes, n - evasoes) >= avaliacao.EVENTOS_MINIMOS
    saida = {"grupo": grupo, "alunos": n, "evasoes": evasoes, "taxa": _r(evasoes / n, 4),
             "chance_media": _r(sum(i["chance"] for i in itens) / n, 4), "suficiente": suficiente,
             "auc_modelo": None, "auc_modelo_ic": None, "auc_regras": None, "revocacao": None, "precisao": None}
    if suficiente:
        m = avaliacao.metricas([i["nivel"] != "baixo" for i in itens], real)
        saida.update(auc_modelo=avaliacao.auc([i["chance"] for i in itens], real),
                     auc_modelo_ic=avaliacao.ic_auc([i["chance"] for i in itens], real),
                     auc_regras=avaliacao.auc([i["pontos_regras"] for i in itens], real),
                     revocacao=m["revocacao"], precisao=m["precisao"])
    return saida


def avaliacao_por_grupo():
    """Modelo treinado por período e por turma do semestre em curso, só nos alunos separados para o teste."""
    modelo = modelo_risco.ativo()
    if not modelo:
        return {"disponivel": False, "motivo": "Nenhum modelo treinado ainda."}
    teste = treino.alunos_do_teste(modelo)
    if teste is None:
        return {"disponivel": False, "motivo": "Os dados mudaram desde o treino, e não dá para garantir quais alunos "
                                               "ficaram de fora dele. Treine o modelo de novo."}
    for item in teste:
        item["nivel"] = predicao.aplicar_regras_duras(item["aluno"], modelo_risco.nivel(item["chance"]))[0]
        item["pontos_regras"] = predicao.calcular_risco(item["aluno"])["score"]
    por_periodo = {}
    for item in teste:
        por_periodo.setdefault(item["aluno"]["periodo"], []).append(item)
    por_matricula = {i["aluno"]["matricula"]: i for i in teste}
    por_turma = {}
    for l in consultar("""
        SELECT a.codigo_academico AS matricula, t.codigo_turma || ' — ' || d.nome AS turma
          FROM registros_academicos r JOIN turmas t USING (turma_id) JOIN disciplinas d USING (disciplina_id)
          JOIN matriculas_curso mc USING (matricula_curso_id) JOIN alunos a USING (aluno_id)
         WHERE r.situacao = 'EM_CURSO'"""):
        if l["matricula"] in por_matricula:
            por_turma.setdefault(l["turma"], []).append(por_matricula[l["matricula"]])
    turmas = sorted((_resumo_avaliacao(t, itens) for t, itens in por_turma.items()),
                    key=lambda x: (-x["evasoes"], -x["alunos"], x["grupo"]))
    return {"disponivel": True, "modelo_id": modelo["id"], "alunos_teste": len(teste),
            "eventos_minimos": avaliacao.EVENTOS_MINIMOS,
            "por_periodo": [_resumo_avaliacao(f"{p}º período", por_periodo[p]) for p in sorted(por_periodo)],
            "por_turma": {"total": len(turmas), "suficientes": sum(t["suficiente"] for t in turmas),
                          "maior_turma": max((t["alunos"] for t in turmas), default=0), "linhas": turmas[:10]}}


# ---------- exportação em CSV ----------

def _tabela(nome, filtros, usuario):
    """Linhas (dicts) de cada tabela exportável."""
    if nome == "descritiva":
        return [{"variavel": v, "recorte": g, "grupo": l["grupo"]} | {c: x for c, x in l.items() if c != "grupo"}
                for v in VARIAVEIS for g in ("geral", "periodo", "disciplina", "semestre")
                for l in medidas(v, filtros, usuario, g)]
    if nome == "distribuicao":
        return [{"variavel": v, "de": f["de"], "ate": f["ate"], "registros": f["n"]}
                for v, faixas in histogramas(filtros, usuario).items() for f in faixas]
    if nome == "aprovacao":
        return [{"recorte": r} | {c: x for c, x in l.items() if c != "ic_reprovacao"}
                | {"reprovacao_ic_inf": l["ic_reprovacao"] and l["ic_reprovacao"][0],
                   "reprovacao_ic_sup": l["ic_reprovacao"] and l["ic_reprovacao"][1]}
                for r in ("disciplina", "turma", "semestre") for l in aprovacao(r, filtros, usuario)]
    if nome == "evolucao":
        return evolucao(filtros, usuario)["pontos"]
    analise = analise_evasao()
    if nome == "fatores":
        return [{"fator": f["nome"], "nivel": g["nivel"], "alunos": g["alunos"], "evasoes": g["evasoes"], "taxa": g["taxa"],
                 "ic_inf": g["ic"][0], "ic_sup": g["ic"][1],
                 "razao_chances": f["razao_chances"] and f["razao_chances"]["valor"],
                 "rc_ic_inf": f["razao_chances"] and f["razao_chances"]["ic"][0],
                 "rc_ic_sup": f["razao_chances"] and f["razao_chances"]["ic"][1],
                 "qui2": f["teste"] and f["teste"]["qui2"], "gl": f["teste"] and f["teste"]["gl"],
                 "p": f["teste"] and f["teste"]["p"], "p_holm": f["teste"] and f["teste"]["p_holm"],
                 "v_cramer": f["teste"] and f["teste"]["v_cramer"]} for f in analise["fatores"] for g in f["grupos"]]
    if nome == "correlacoes":
        return analise["correlacoes"]
    return [{c: x for c, x in l.items() if c != "ic"} | {"ic_inf": l["ic"][0], "ic_sup": l["ic"][1]}
            for l in analise["comparacoes"]]


TABELAS = ("descritiva", "distribuicao", "aprovacao", "evolucao", "fatores", "correlacoes", "comparacoes")


def _celula(valor):
    """Número com vírgula (Excel em português). Texto que começa com sinal de fórmula ganha um apóstrofo, para a
    planilha não executar o conteúdo."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, float):
        return str(valor).replace(".", ",")
    texto = str(valor)
    return "'" + texto if not isinstance(valor, int) and texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def exportar_csv(nome, filtros, usuario):
    """CSV da tabela pedida, com ponto e vírgula e BOM para abrir certo no Excel."""
    if nome not in TABELAS:
        raise ErroModelo(404, "tabela de estatística não encontrada")
    linhas = _tabela(nome, filtros, usuario)
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    if linhas:
        colunas = list(linhas[0])
        escritor.writerow(colunas)
        escritor.writerows([_celula(l.get(c)) for c in colunas] for l in linhas)
    return "﻿" + saida.getvalue()
