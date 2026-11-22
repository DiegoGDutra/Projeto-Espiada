"""Confere o treinamento do modelo de risco: variáveis, regressão, divisão treino/teste, aprovação e o que cada perfil vê.
A LLM é simulada.   Rodar:  python testes/teste_modelo.py"""
import inspect
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "app"), str(RAIZ / "scripts")]  # o sistema fica em app/ e o importador em scripts/

import Espiada
from importar import LOGINS_PADRAO, importar
from models import alunos, avaliacao, banco, llm, modelo_risco, predicao, treino

# ---------- contas puras, com números conhecidos ----------
assert modelo_risco._inclinacao([1, 2, 3], [10, 8, 6]) == -2 and modelo_risco._inclinacao([1], [10]) == 0
semestres = [{"semestre": 1, "soma_nota": 400.0, "qtd_nota": 5, "soma_freq": 450.0, "qtd_freq": 5, "nota_atual": None,
              "cursadas": 5, "reprovadas": 1},
             {"semestre": 2, "soma_nota": 300.0, "qtd_nota": 5, "soma_freq": 400.0, "qtd_freq": 5, "nota_atual": 60.0,
              "cursadas": 0, "reprovadas": 0}]
x = dict(zip(modelo_risco.VARIAVEIS, modelo_risco.calcular_variaveis(2, semestres)))
assert (x["nota"], x["frequencia"], x["nota_atual"], x["taxa_reprovacao"]) == (70, 85, 60, 0.2), x
assert (x["tendencia_nota"], x["queda_nota"], x["mudanca_ultimo_semestre"], x["tem_historico"]) == (-20, -20, -20, 1), x
assert modelo_risco.calcular_variaveis(1, [semestres[0] | {"qtd_nota": 0}]) is None  # aluno sem nota não é previsto
assert [modelo_risco.nivel(p) for p in (0.149, 0.15, 0.299, 0.30)] == ["baixo", "medio", "medio", "alto"]

pesos = {"intercepto": 0.0, "coeficientes": [1.0, 0.0], "medias": [10.0, 5.0], "desvios": [2.0, 1.0]}
assert modelo_risco.probabilidade(pesos, [10.0, None]) == 0.5  # valor ausente vale a média do treino
assert 0 < modelo_risco.probabilidade(pesos, [-1e9, 5.0]) < 1e-9  # valor extremo não estoura a conta

X = [[float(i)] for i in range(100)]
y = [i >= 50 for i in range(100)]
ajuste = treino.ajustar(X, y)
assert ajuste["coeficientes"][0] > 0, ajuste
assert modelo_risco.probabilidade(ajuste, [90.0]) > 0.9 > 0.1 > modelo_risco.probabilidade(ajuste, [10.0])
real = [i % 8 == 0 for i in range(1000)]
tr, te = treino.dividir(real)
assert not set(tr) & set(te) and len(tr) + len(te) == 1000 and sum(real[i] for i in te) == 25 and len(te) == 200
assert (tr, te) == treino.dividir(real)  # mesma divisão a cada treino

# as variáveis não podem vir do gabarito nem da resposta pronta do dataset (vazamento)
codigo = inspect.getsource(modelo_risco).lower()
assert "from desfechos_alunos" not in codigo and "join desfechos_alunos" not in codigo and "join indicadores_risco" not in codigo

# ---------- treinamento com o dataset inteiro ----------
banco.usar_esquema_de_teste("teste_modelo")  # esquema próprio, recriado vazio: não mexe nos dados de verdade
importar()
llm.avaliar = lambda contexto: {"nivel": "baixo", "comentario": "Comentário simulado.", "modelo": "fake", "_ctx": contexto}
SENHAS = {login: senha for login, _, senha, _ in LOGINS_PADRAO}
api = Espiada.app.test_client()


def entra(login):
    r = api.post("/api/login", json={"login": login, "senha": SENHAS[login]})
    assert r.status_code == 200, r.get_json()


assert modelo_risco.ativo() is None and modelo_risco.prever() == {}
entra("secretaria@simpa.test")
assert all(a["probabilidade"] is None for a in api.get("/api/alunos").get_json()[:20])  # sem modelo, sem porcentagem
assert api.get("/api/avaliacao").get_json()["modelo_treinado"] is None

r1 = treino.treinar()
m = r1["metricas"]
assert r1["aprovado"] and r1["referencia"] == "regras" and modelo_risco.ativo()["id"] == r1["id"], m["ganho_auc"]
assert (m["treino"]["alunos"], m["teste"]["alunos"]) == (4000, 1000) and (m["treino"]["evasoes"], m["teste"]["evasoes"]) == (512, 128)
assert m["ganho_auc"]["ic"][0] > 0 and m["modelo"]["auc"] > m["regras"]["auc"], m["ganho_auc"]
assert m["brier"]["modelo"] < m["brier"]["taxa_geral"], m["brier"]  # melhor que prever a taxa geral para todos
assert 0.7 < m["auc_validacao_cruzada"] < 0.9 and len(m["calibracao"]) == 5
assert [g["previsto"] for g in m["calibracao"]] == sorted(g["previsto"] for g in m["calibracao"])

r2 = treino.treinar()  # mesmos dados: não há ganho, então a versão em uso continua a mesma
assert not r2["aprovado"] and r2["referencia"] == f"modelo v{r1['id']}" and modelo_risco.ativo()["id"] == r1["id"], r2["metricas"]["ganho_auc"]

# ---------- nível, porcentagem e regras duras ----------
previsoes = modelo_risco.prever()
lista = api.get("/api/alunos").get_json()
assert len(previsoes) == 5000 and len(lista) == 5000
for a in lista:
    p = previsoes[a["matricula"]]
    assert a["probabilidade"] == p["probabilidade"] and a["risco_origem"] == "modelo", a
    assert a["risco"] == predicao.aplicar_regras_duras(a, p["nivel"])[0], a
    if a["freq"] < predicao.FREQ_CORTE and a["registros"] >= predicao.HISTORICO_MINIMO:
        assert a["risco"] == "alto", a  # frequência baixa força alto, seja qual for a porcentagem
    if a["registros"] < predicao.HISTORICO_MINIMO:
        assert a["risco"] != "alto", a  # histórico curto nunca chega a alto

# a LLM só comenta: com modelo, o nível dela não muda o resultado
matricula = next(a["matricula"] for a in lista if a["risco"] == "alto" and a["freq"] >= predicao.FREQ_CORTE)
r = api.post(f"/api/alunos/{matricula}/predicao")
d = r.get_json()
assert r.status_code == 201 and d["risco"] == "alto" and d["nivel_llm"] == "baixo" and d["comentario"] == "Comentário simulado.", d
assert d["probabilidade"] == previsoes[matricula]["probabilidade"] and d["modelo_risco_id"] == r1["id"], d
h = api.get(f"/api/alunos/{matricula}/predicao").get_json()[0]
assert h["probabilidade"] == d["probabilidade"] and h["modelo_risco_id"] == r1["id"], h
av = api.get("/api/avaliacao").get_json()
assert av["modelo_treinado"]["id"] == r1["id"] and av["llm"]["alunos"] == 0  # comentário não conta como predição da LLM

# ---------- contexto da LLM: anonimizado e com o resultado do modelo ----------
aluno = alunos.buscar(matricula, {"perfil": "secretaria"})
estatistica = {"nivel": "alto", "chance_de_evasao_percentual": 40}
contexto = predicao.entrada_llm(aluno, predicao.calcular_risco(aluno), estatistica)
assert contexto["modelo_estatistico"] == estatistica and matricula not in str(contexto) and aluno["nome"] not in str(contexto)

# ---------- quem vê a porcentagem ----------
api.post("/api/logout")
entra("aluno@simpa.test")
meu = api.get("/api/alunos").get_json()
assert len(meu) == 1 and "probabilidade" not in meu[0] and meu[0]["risco"] in predicao.NIVEIS, meu
assert "probabilidade" not in api.get(f"/api/alunos/{meu[0]['matricula']}").get_json()
api.post(f"/api/logout")
entra("secretaria@simpa.test")
api.post(f"/api/alunos/{meu[0]['matricula']}/predicao")
api.post("/api/logout")
entra("aluno@simpa.test")
assert all("probabilidade" not in h for h in api.get(f"/api/alunos/{meu[0]['matricula']}/predicao").get_json())
api.post("/api/logout")
entra("professor@simpa.test")
assert all(a["probabilidade"] is not None for a in api.get("/api/alunos").get_json())
assert api.get("/api/avaliacao").status_code == 403
print("ok: treinamento do modelo funciona")
