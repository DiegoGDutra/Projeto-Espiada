"""Confere a estatística: contas com valores conhecidos, totais contra o banco, permissões, CSV e avaliação por grupo.
Rodar:  python testes/teste_estatistica.py"""
import inspect
import math
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "app"), str(RAIZ / "scripts")]  # o sistema fica em app/ e o importador em scripts/

import Espiada
from importar import LOGINS_PADRAO, importar
from models import avaliacao, banco, estatistica, inferencia as inf, modelo_risco, treino
from models.banco import ErroModelo


def perto(a, b, erro=1e-3):
    return abs(a - b) <= erro


# ---------- distribuições: valores críticos das tabelas ----------
assert perto(inf.p_qui2(3.841459, 1), 0.05, 1e-5) and perto(inf.p_qui2(5.991465, 2), 0.05, 1e-5)
assert perto(inf.p_qui2(18.307, 10), 0.05, 1e-4) and inf.p_qui2(0, 3) == 1
assert perto(inf.p_t(2.228139, 10), 0.05, 1e-5) and perto(inf.p_t(12.7062, 1), 0.05, 1e-4) and inf.p_t(0, 5) == 1
assert perto(inf.t_critico(10), 2.228) and perto(inf.t_critico(1), 12.706) and perto(inf.t_critico(10000), 1.960)
assert perto(inf.p_normal(1.959964), 0.05, 1e-5)

# ---------- testes, com contas conhecidas ----------
assert inf.holm([0.01, 0.04, 0.03, None]) == [0.03, 0.06, 0.06, None]  # nunca fica menor que o anterior
assert inf.holm([0.9, 0.8]) == [1.0, 1.0] and inf.holm([]) == []
assert inf.postos([10, 20, 20, 30]) == [1, 2.5, 2.5, 4]
assert perto(inf.pearson([1, 2, 3, 4], [2, 4, 6, 8]), 1) and perto(inf.pearson([1, 2, 3], [3, 2, 1]), -1)
assert inf.pearson([1, 1, 1], [1, 2, 3]) is None and inf.pearson([1, 2], [1, 2]) is None
x, y = [1.0, 2, 3, 4, 5, 6, 7, 8], [2.0, 1, 4, 3, 7, 5, 8, 6]
assert perto(inf.pearson(x, y), statistics.correlation(x, y), 1e-9)
c = inf.correlacao([1.0, 2, 3, 4, 5], [1.0, 4, 9, 16, 25])  # monótona, mas não linear
assert perto(c["spearman"], 1) and c["pearson"] < 1

q = inf.qui_quadrado([[10, 20], [20, 20]])  # conta à mão: 70 * (200 - 400)^2 / (30 * 40 * 30 * 40) = 1,944
assert perto(q["qui2"], 1.9444) and q["gl"] == 1 and perto(q["p"], 0.1632) and q["valido"]
assert perto(q["v_cramer"], math.sqrt(1.9444 / 70))
assert not inf.qui_quadrado([[1, 2], [3, 1]])["valido"]  # esperado abaixo de 5: aproximação fraca
assert inf.qui_quadrado([[5, 0], [3, 0]]) is None  # só uma coluna com dados

rc = inf.razao_chances(20, 80, 10, 90)  # (20 * 90) / (80 * 10) = 2,25
assert perto(rc["valor"], 2.25) and rc["ic"][0] < 2.25 < rc["ic"][1] and perto(rc["ic"][0], 0.9973, 1e-2)
assert inf.razao_chances(0, 10, 5, 5)["valor"] > 0  # casela zerada não quebra a conta

w = inf.comparar_medias([1.0, 2, 3, 4, 5], [2.0, 4, 6, 8, 10])  # t = -3 / raiz(2,5); p conferido por integração numérica
assert perto(w["diferenca"], -3) and perto(w["t"], -1.8974) and perto(w["gl"], 5.8824) and perto(w["p_welch"], 0.10753)
assert w["ic"][0] < -3 < w["ic"][1] and w["ic"][1] > 0  # o IC cruza o zero, coerente com p > 0,05
assert inf.comparar_medias([1.0], [1.0, 2]) is None and inf.comparar_medias([1.0, 1], [1.0, 1]) is None
mw = inf.mann_whitney([1, 2, 3], [4, 5, 6])
assert mw["prob_superioridade"] == 0 and 0 < mw["p"] < 0.15
assert inf.mann_whitney([1, 1], [1, 1]) == {"p": 1.0, "prob_superioridade": 0.5}

assert inf.mcnemar(0, 0) == 1 and perto(inf.mcnemar(1, 9), 0.0215, 1e-4)  # binomial exato: 2 * 11 / 1024
assert perto(inf.mcnemar(30, 10), inf.p_qui2(19 ** 2 / 40, 1), 1e-12)  # acima de 25 discordâncias, qui-quadrado
assert avaliacao.teste_pareado(["alto", "baixo"], ["baixo", "baixo"], [True, True])["alto"] == {
    "so_a": 1, "so_b": 0, "p": 1.0}

# o gabarito só pode entrar pela função oficial; indicadores_risco é a resposta pronta e nunca é lido aqui
codigo = inspect.getsource(estatistica).lower()
assert "desfechos_alunos" not in codigo and "indicadores_risco" not in codigo

# ---------- filtros ----------
assert estatistica.ler_filtros({"periodo": "3", "semestre": "2025.2", "turma": ""}) == {"periodo": 3, "semestre": (2025, 2)}
for ruim in ({"periodo": "abc"}, {"turma": "1;DROP"}, {"semestre": "2025.3"}, {"disciplina": "-1"}, {"periodo": "9" * 12}):
    try:
        estatistica.ler_filtros(ruim)
        raise AssertionError(f"filtro aceito: {ruim}")
    except ErroModelo as e:
        assert e.status == 400
assert estatistica._celula("=SOMA(A1)") == "'=SOMA(A1)" and estatistica._celula(1.5) == "1,5" and estatistica._celula(-2) == "-2"

# ---------- com o dataset inteiro ----------
banco.usar_esquema_de_teste("teste_estatistica")  # esquema próprio, recriado vazio: não mexe nos dados de verdade
importar()
SENHAS = {login: senha for login, _, senha, _ in LOGINS_PADRAO}
api = Espiada.app.test_client()


def entra(login):
    api.post("/api/logout")
    r = api.post("/api/login", json={"login": login, "senha": SENHAS[login]})
    assert r.status_code == 200, r.get_json()


def chama(url, status=200):
    r = api.get(url)
    assert r.status_code == status, f"{url}: esperava {status}, veio {r.status_code} {r.get_data(as_text=True)[:200]}"
    return r.get_json() if r.mimetype == "application/json" else r


assert api.get("/api/estatisticas").status_code == 401
entra("secretaria@simpa.test")
geral = chama("/api/estatisticas")
d = geral["descritiva"]["nota"]
real = banco.consultar("""SELECT count(*) AS n, avg(v) AS media, stddev_samp(v) AS dp, min(v) AS mi, max(v) AS ma FROM
    (SELECT coalesce(nota_final, nota_parcial) AS v FROM registros_academicos) x WHERE v IS NOT NULL""")[0]
assert d["n"] == real["n"] == 121307 and perto(d["media"], real["media"], .01) and perto(d["desvio"], real["dp"], .01), d
assert d["minimo"] <= d["bigode_inf"] <= d["q1"] <= d["mediana"] <= d["q3"] <= d["bigode_sup"] <= d["maximo"], d
for variavel, faixas in geral["histogramas"].items():
    assert len(faixas) == 20 and sum(f["n"] for f in faixas) == geral["descritiva"][variavel]["n"], variavel
assert len(geral["boxplots"]["nota"]["periodo"]) == 8 and len(geral["boxplots"]["frequencia"]["disciplina"]) == 40
assert sum(l["n"] for l in geral["boxplots"]["nota"]["periodo"]) == d["n"]

ap = geral["aprovacao"]["disciplina"]
contagem = {l["situacao"]: l["n"] for l in banco.consultar("SELECT situacao, count(*) AS n FROM registros_academicos GROUP BY 1")}
assert sum(l["aprovados"] for l in ap) == contagem["APROVADO"] and sum(l["em_curso"] for l in ap) == contagem["EM_CURSO"]
assert sum(l["concluidas"] for l in ap) == sum(n for s, n in contagem.items() if s != "EM_CURSO")
com_taxa = [l for l in ap if l["concluidas"]]  # disciplina só com turmas em curso ainda não tem taxa e fica no fim
assert ap[:len(com_taxa)] == com_taxa and all(l["taxa_reprovacao"] is None for l in ap[len(com_taxa):])
assert [l["taxa_reprovacao"] for l in com_taxa] == sorted((l["taxa_reprovacao"] for l in com_taxa), reverse=True)  # ranking
for l in com_taxa:
    assert perto(l["taxa_aprovacao"] + l["taxa_reprovacao"], 1, 2e-4) and l["ic_reprovacao"][0] <= l["taxa_reprovacao"] <= l["ic_reprovacao"][1], l
t = geral["aprovacao"]["turma"]
assert len(t["linhas"]) == 15 and all(l["concluidas"] >= t["minimo"] for l in t["linhas"])

ev = geral["evolucao"]
assert [p["semestre"] for p in ev["pontos"]][0] == "2023.1" and len(ev["pontos"]) == 8 and ev["pontos"][-1]["parcial"]
fechados = [p for p in ev["pontos"] if not p["parcial"]]  # a tendência ignora o semestre em curso
assert perto(ev["tendencia"]["nota"], modelo_risco._inclinacao([p["ordem"] for p in fechados], [p["nota"] for p in fechados]), .01)

filtrado = chama("/api/estatisticas?periodo=3&semestre=2025.2")
assert filtrado["descritiva"]["nota"]["n"] == banco.consultar("""
    SELECT count(*) AS n FROM registros_academicos r JOIN turmas t USING (turma_id) JOIN matriculas_curso mc USING (matricula_curso_id)
     WHERE mc.periodo_atual = 3 AND t.ano_letivo = 2025 AND t.semestre_letivo = 2""")[0]["n"]
assert d["moda"] == 100 and d["moda_repeticoes"] >= 2
for l in estatistica.medidas("nota", {"periodo": 3}, {"perfil": "secretaria"}, "turma"):
    assert (l["moda"] is None) == (l["moda_repeticoes"] < 2), l  # sem valor repetido, não existe moda
assert chama("/api/estatisticas?periodo=99")["descritiva"]["nota"] is None  # filtro sem dados não quebra
chama("/api/estatisticas?periodo=x", 400)
assert chama("/api/estatisticas/descritiva?periodo=3")["nota"]["n"] > 0

a = chama("/api/estatisticas/evasao")
assert (a["alunos"], a["evasoes"]) == (5000, 640)
for f in a["fatores"]:
    assert sum(g["evasoes"] for g in f["grupos"]) == 640 and sum(g["alunos"] for g in f["grupos"]) == 5000, f["nome"]
    assert f["teste"]["p_holm"] >= f["teste"]["p"] and f["teste"]["valido"], f["nome"]
fatores = {f["chave"]: f for f in a["fatores"]}
assert fatores["nota_baixa"]["razao_chances"]["valor"] > 3 and fatores["nota_baixa"]["teste"]["p_holm"] < .001
assert fatores["internet"]["razao_chances"] is None and len(fatores["internet"]["grupos"]) == 3
corr = {c["nome"]: c for c in a["correlacoes"]}
assert corr["Nota média"]["pearson"] < 0 < corr["Reprovações"]["pearson"]
assert len(a["comparacoes"]) == 10 and all(c["ic"][0] <= c["diferenca"] <= c["ic"][1] for c in a["comparacoes"])

# ---------- avaliação por grupo: só alunos do teste ----------
assert chama("/api/estatisticas/avaliacao")["disponivel"] is False  # ainda sem modelo
r = treino.treinar()
g = chama("/api/estatisticas/avaliacao")
assert g["disponivel"] and g["alunos_teste"] == 1000 and sum(p["alunos"] for p in g["por_periodo"]) == 1000
assert sum(p["evasoes"] for p in g["por_periodo"]) == r["metricas"]["teste"]["evasoes"]
primeiro = g["por_periodo"][0]
assert not primeiro["suficiente"] and primeiro["auc_modelo"] is None  # o 1º período tem poucas evasões no teste
assert g["por_turma"]["suficientes"] == 0 and all(t["auc_modelo"] is None for t in g["por_turma"]["linhas"])
modelo = modelo_risco.ativo()
_, y, _, _ = treino._dados_de_treino()
_, teste = treino.dividir(y)
assert len(treino.alunos_do_teste(modelo)) == len(teste)
adulterado = modelo | {"metricas": modelo["metricas"] | {"modelo": modelo["metricas"]["modelo"] | {"auc": 0.1}}}
assert treino.alunos_do_teste(adulterado) is None  # não reproduz o treino: não mede em quem pode ter sido treinado

# ---------- CSV ----------
for tabela in estatistica.TABELAS:
    corpo = chama(f"/api/estatisticas/exportar/{tabela}")
    texto = corpo.get_data(as_text=True)
    assert corpo.mimetype == "text/csv" and texto.startswith("﻿") and texto.count("\r\n") > 1, tabela
    assert "attachment" in corpo.headers["Content-Disposition"], tabela
chama("/api/estatisticas/exportar/inexistente", 404)
linhas = chama("/api/estatisticas/exportar/evolucao?periodo=8").get_data(as_text=True).lstrip("﻿").splitlines()
assert linhas[0].startswith("semestre;ordem;") and len(linhas) == 9 and "," in linhas[1]

# ---------- ficha do aluno ----------
ficha = chama("/api/alunos/AES0001")
assert ficha["evolucao"]["pontos"] and {"nota", "frequencia"} == set(ficha["evolucao"]["tendencia"])

# ---------- professor: só os registros das próprias turmas ----------
entra("professor@simpa.test")
n_prof = banco.consultar("""SELECT count(*) AS n FROM registros_academicos r JOIN turmas t USING (turma_id)
    WHERE t.docente_id = 1 AND coalesce(r.nota_final, r.nota_parcial) IS NOT NULL""")[0]["n"]
prof = chama("/api/estatisticas")
assert prof["descritiva"]["nota"]["n"] == n_prof < 121307
minhas = {l["turma_id"] for l in banco.consultar("SELECT turma_id FROM turmas WHERE docente_id = 1")}
opc = chama("/api/estatisticas/opcoes")
assert {t["id"] for t in opc["turmas"]} == minhas
outra = banco.consultar("SELECT turma_id FROM turmas WHERE docente_id <> 1 LIMIT 1")[0]["turma_id"]
assert chama(f"/api/estatisticas?turma={outra}")["descritiva"]["nota"] is None  # turma de outro docente: nada
assert chama(f"/api/estatisticas/exportar/descritiva?turma={outra}").get_data(as_text=True) == "﻿"
chama("/api/estatisticas/evasao", 403)
chama("/api/estatisticas/avaliacao", 403)
for tabela in estatistica.SO_SECRETARIA:
    chama(f"/api/estatisticas/exportar/{tabela}", 403)

# ---------- aluno: nada de visão agregada; a própria evolução continua na ficha ----------
entra("aluno@simpa.test")
for url in ("", "/opcoes", "/descritiva", "/evasao", "/avaliacao", "/exportar/descritiva", "/exportar/fatores"):
    chama("/api/estatisticas" + url, 403)
meu = chama("/api/alunos/AES0001")
assert meu["evolucao"]["pontos"] and "probabilidade" not in meu
print("ok: estatística funciona")
