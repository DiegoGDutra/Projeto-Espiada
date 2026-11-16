"""Importa o dataset num banco temporário e confere as rotas, o formato JSON e as permissões de cada perfil.
A LLM é simulada (nunca chama um Ollama de verdade): o teste vale com ou sem Ollama instalado.
Rodar:  python testes/teste_api.py"""
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "app"), str(RAIZ / "scripts")]  # o sistema fica em app/ e o importador em scripts/

import Espiada
from importar import LOGINS_PADRAO, importar
from models import avaliacao, banco, llm, usuario
from models.banco import ErroModelo
from models.predicao import calcular_risco

banco.usar_esquema_de_teste("teste_api")  # esquema próprio, recriado vazio: não mexe nos dados de verdade
qtd = importar()
assert (qtd["alunos"], qtd["registros_academicos"], qtd["turmas"], qtd["usuario"]) == (5000, 121310, 2902, 5451), qtd
api = Espiada.app.test_client()


def llm_fora(contexto=None):
    raise ErroModelo(503, "Ollama indisponível (simulado no teste)")


llm.avaliar = llm_fora  # por padrão a LLM está fora do ar: a predição sai só com as regras
llm.verificar = llm_fora
SENHA = "Teste#123"
SENHAS = {login: senha for login, _, senha, _ in LOGINS_PADRAO}


def chama(metodo, url, json=None, status=200):
    r = api.open(url, method=metodo, json=json)
    assert r.status_code == status, f"{metodo} {url}: esperava {status}, veio {r.status_code} {r.get_json()}"
    return r.get_json()


def entra(login, senha=None, status=200):
    senha = senha or SENHAS.get(login.lower(), SENHA)
    return chama("POST", "/api/login", {"login": login, "senha": senha}, status)


# ---------- login e cadastro ----------
chama("GET", "/api/alunos", status=401)  # sem login, nada da API abre
assert api.get("/interface.html").status_code == 302
entra("secretaria@simpa.test", "errada", 401)
assert entra("SECRETARIA@simpa.test")["perfil"] == "secretaria"  # login padrão; e-mail sem diferença de maiúscula
assert api.get("/interface.html").status_code == 200
for senha in ["Cur#1a", "SemEspecial1", "SEMMINUSC#1", "semmaiusc#1", "SemNumero#"]:
    chama("POST", "/api/usuarios", {"login": "x@simpa.test", "perfil": "aluno", "nome": "X", "senha": senha,
                                    "vinculo": "AES0001"}, 400)
chama("POST", "/api/usuarios", {"login": "nao-email", "perfil": "secretaria", "nome": "X", "senha": SENHA}, 400)
chama("POST", "/api/usuarios", {"login": "x@simpa.test", "perfil": "aluno", "nome": "X", "senha": SENHA,
                                "vinculo": "XYZ"}, 400)
chama("POST", "/api/usuarios", {"login": "x@simpa.test", "perfil": "admin", "nome": "X", "senha": SENHA}, 400)
chama("POST", "/api/usuarios", {"login": "ana@simpa.test", "perfil": "secretaria", "nome": "Ana", "senha": SENHA}, 201)
chama("POST", "/api/usuarios", {"login": "ada@simpa.test", "perfil": "professor", "nome": "Ada", "senha": SENHA,
                                "vinculo": 2}, 409)  # todo docente já tem login (docente2@simpa.test)
# o importador dá login a todo aluno e docente, com a senha padrão do perfil
assert usuario.autenticar("aes0002@simpa.test", SENHAS["aluno@simpa.test"])["aluno_id"] == 2
assert usuario.autenticar("docente450@simpa.test", SENHAS["professor@simpa.test"])["docente_id"] == 450
assert "já existe" in chama("POST", "/api/usuarios", {"login": "ana@simpa.test", "perfil": "secretaria", "nome": "X", "senha": SENHA}, 409)["erro"]
chama("POST", "/api/usuarios", {"login": "y@simpa.test", "perfil": "aluno", "nome": "Y", "senha": SENHA,
                                "vinculo": "AES0001"}, 409)  # AES0001 já tem login (o padrão)
assert "Teste" not in str(banco.consultar("SELECT senha_hash FROM usuario"))  # só hash

# ---------- secretaria vê tudo ----------
assert chama("GET", "/api/cursos")[0]["nome"] == "Engenharia de Software"
assert len(chama("GET", "/api/disciplinas")) == 40 and len(chama("GET", "/api/docentes")) == 450
alunos = chama("GET", "/api/alunos")
assert len(alunos) == 5000 and {a["risco"] for a in alunos} <= {"baixo", "medio", "alto"}
a = chama("GET", "/api/alunos/AES0001")
assert a["matricula"] == "AES0001" and a["curso"] == "Engenharia de Software" and a["reclamacoes"] == 0, a
assert a["disciplinas"] and all(0 <= d["nota_n1"] <= 100 for d in a["disciplinas"])
p = chama("POST", "/api/alunos/AES0001/predicao", status=201)  # LLM fora: sai só com as regras, com aviso
ficha = chama("GET", "/api/alunos/AES0001")
regras = calcular_risco(ficha)
assert p["matricula"] == "AES0001" and p["origem"] == "regras" and "Ollama" in p["aviso"] and p["comentario"] is None, p
assert (p["risco"], p["score"], p["fatores"]) == (regras["risco"], regras["score"], regras["fatores"]), p
hist = chama("GET", "/api/alunos/AES0001/predicao")
assert hist[0]["risco"] == p["risco"] and hist[0]["origem"] == "regras" and "entrada_hash" not in hist[0], hist
assert ficha["risco_origem"] == "regras" and ficha["registros"] > 0
llm.avaliar = lambda contexto: {"nivel": "alto", "comentario": "Teste da LLM.", "modelo": "fake"}  # LLM no ar
p2 = chama("POST", "/api/alunos/AES0001/predicao", status=201)
assert p2["origem"] == "llm" and p2["comentario"] == "Teste da LLM." and "aviso" not in p2, p2
assert p2["nivel_llm"] == "alto" and p2["risco"] == "medio", p2  # AES0001 é "baixo" pelas regras: a LLM sobe só um nível
assert chama("GET", "/api/alunos/AES0001/predicao")[0]["comentario_predicao"] == "Teste da LLM."
assert chama("GET", "/api/alunos/AES0001")["risco_origem"] == "llm"
llm.avaliar = llm_fora
chama("POST", "/api/alunos/AES0001/feedback", {"alvo": "curso"}, 403)  # feedback é do aluno
assert "erro" in chama("GET", "/api/alunos/XYZ", status=404)
chama("GET", "/api/inexistente", status=404)
chama("PUT", "/api/alunos/AES0001/desempenho", {"nota_n1": 100}, 404)  # nota não tem rota de escrita

# ---------- recálculo em lote: só a secretaria; sem Ollama dá 503; com Ollama roda em segundo plano ----------
chama("POST", "/api/predicoes/recalcular", status=503)  # LLM fora do ar: avisa na hora e nem começa


def recalcula():
    chama("POST", "/api/predicoes/recalcular", status=202)
    for _ in range(1500):  # 5000 alunos: um lote leva perto de 1 minuto
        estado = chama("GET", "/api/predicoes/recalculo")
        if estado["estado"] != "rodando":
            return estado
        time.sleep(0.2)
    raise AssertionError("o recálculo não terminou")


llm.verificar = lambda: None
llm.avaliar = lambda contexto: {"nivel": "medio", "comentario": "Teste em lote.", "modelo": "fake"}
estado = recalcula()
# o AES0001 já tinha uma análise da LLM com a mesma entrada: é pulado
assert estado["estado"] == "concluido" and (estado["total"], estado["feitos"], estado["puladas"]) == (5000, 4999, 1), estado
estado = recalcula()  # nada mudou desde a rodada anterior: todos pulados, nenhuma chamada nova à LLM
assert (estado["feitos"], estado["puladas"], estado["falhas"]) == (0, 5000, 0), estado
assert {x["risco_origem"] for x in chama("GET", "/api/alunos")} == {"llm"}  # as telas passam a mostrar a da LLM
llm.avaliar = llm_fora  # LLM cai no meio do lote: 3 falhas seguidas interrompem
estado = chama("POST", "/api/predicoes/recalcular?forcar=1", status=202)
for _ in range(150):
    estado = chama("GET", "/api/predicoes/recalculo")
    if estado["estado"] != "rodando":
        break
    time.sleep(0.2)
assert estado["estado"] == "erro" and estado["falhas"] == 3 and "interrompido" in estado["erro"], estado
llm.verificar = llm_fora

# ---------- avaliação do modelo: métricas com números conhecidos e a rota com o dataset inteiro ----------
assert avaliacao.metricas([True, True, False, False], [True, False, True, False]) == {
    "vp": 1, "fp": 1, "fn": 1, "vn": 1, "acuracia": 0.5, "precisao": 0.5, "revocacao": 0.5, "especificidade": 0.5,
    "f1": 0.5}
assert avaliacao.metricas([False, False], [True, False])["precisao"] is None  # ninguém apontado: precisão indefinida
assert avaliacao.auc([2, 1, 0], [True, False, False]) == 1.0  # separa perfeitamente
assert avaliacao.auc([1, 1], [True, False]) == 0.5 and avaliacao.auc([0, 2], [True, False]) == 0.0  # empate e invertido
assert avaliacao.auc([1, 2], [True, True]) is None  # sem quem não evadiu, não há o que comparar
av = chama("GET", "/api/avaliacao")
assert (av["alunos"], av["evasoes"]) == (5000, 640) and av["acuracia_chute"] == 0.872, av
regras = av["regras"]
niveis = [calcular_risco(a)["risco"] for a in chama("GET", "/api/alunos")]  # as regras, calculadas por fora
assert {n: d["alunos"] for n, d in regras["por_nivel"].items()} == {n: niveis.count(n) for n in ("baixo", "medio", "alto")}
assert sum(d["evasoes"] for d in regras["por_nivel"].values()) == 640
for m in regras["cortes"].values():
    assert m["vp"] + m["fp"] + m["fn"] + m["vn"] == 5000 and m["vp"] + m["fn"] == 640, m
assert regras["cortes"]["medio_ou_alto"]["revocacao"] >= regras["cortes"]["alto"]["revocacao"]  # corte frouxo pega mais
assert 0.5 < regras["auc"] <= 1 and regras["roc"][0] == {"fpr": 0.0, "tpr": 0.0, "corte": None}
assert (regras["roc"][-1]["fpr"], regras["roc"][-1]["tpr"]) == (1.0, 1.0)
assert av["llm"]["alunos"] > 4900 and not av["llm"]["amostra_pequena"]  # o recálculo acima deu predição de LLM a quase todos
assert av["llm"]["llm"]["alunos"] == av["llm"]["regras"]["alunos"] == av["llm"]["alunos"]  # mesmos alunos nos dois lados

# ---------- aluno: só o próprio ----------
chama("POST", "/api/logout")
chama("GET", "/api/alunos", status=401)
entra("aluno@simpa.test")
assert [x["matricula"] for x in chama("GET", "/api/alunos")] == ["AES0001"]
chama("GET", "/api/alunos/AES0001/predicao")
chama("GET", "/api/alunos/AES0002", status=403)
chama("GET", "/api/alunos/AES0002/predicao", status=403)
chama("POST", "/api/alunos/AES0002/feedback", {"alvo": "curso"}, 403)
chama("POST", "/api/alunos/AES0001/predicao", status=403)
chama("GET", "/api/docentes", status=403)
chama("POST", "/api/predicoes/recalcular", status=403)
chama("GET", "/api/predicoes/recalculo", status=403)
chama("GET", "/api/avaliacao", status=403)  # visão agregada da instituição: só secretaria
chama("POST", "/api/usuarios", {"login": "y@simpa.test", "perfil": "secretaria", "nome": "Y", "senha": SENHA}, 403)
chama("POST", "/api/alunos/AES0001/feedback", {"alvo": "curso", "avaliacao_curso": 1, "comentarios": "ruim"}, 201)
assert chama("GET", "/api/alunos/AES0001")["reclamacoes"] == 1
fb = chama("GET", "/api/alunos/AES0001/feedback")
assert len(fb) == 1 and fb[0]["comentarios"] == "ruim" and fb[0]["avaliacao_curso"] == 1, fb
chama("GET", "/api/alunos/AES0002/feedback", status=403)
chama("POST", "/api/alunos/AES0001/feedback", {"alvo": "professor"}, 400)
chama("POST", "/api/alunos/AES0001/feedback", ["não é objeto"], 400)

# ---------- professor: só alunos das próprias turmas, sem alterar dados ----------
entra("professor@simpa.test")
meus = {r["codigo_academico"] for r in banco.consultar("""
    SELECT DISTINCT a.codigo_academico FROM registros_academicos JOIN turmas t USING (turma_id)
      JOIN matriculas_curso USING (matricula_curso_id) JOIN alunos a USING (aluno_id) WHERE t.docente_id = 1""")}
assert 0 < len(meus) < 5000 and {x["matricula"] for x in chama("GET", "/api/alunos")} == meus
outro = next(f"AES{i:04}" for i in range(1, 5001) if f"AES{i:04}" not in meus)
meu = min(meus)
chama("GET", f"/api/alunos/{meu}")
chama("POST", f"/api/alunos/{meu}/predicao", status=201)
chama("GET", f"/api/alunos/{outro}", status=403)
chama("POST", f"/api/alunos/{outro}/predicao", status=403)
chama("POST", "/api/predicoes/recalcular", status=403)
chama("GET", "/api/avaliacao", status=403)
chama("POST", f"/api/alunos/{meu}/feedback", {"alvo": "curso"}, 403)
chama("POST", "/api/usuarios", {"login": "y@simpa.test", "perfil": "secretaria", "nome": "Y", "senha": SENHA}, 403)

# ---------- força bruta: 5 senhas erradas bloqueiam o login ----------
for _ in range(5):
    entra("ana@simpa.test", "Errada#1", 401)
entra("ana@simpa.test", status=429)

# regras de risco: tudo ruim = alto com score 7; sem dado não conta
ruim = {"freq": 50, "nota": 40, "reprovacoes": 2, "reclamacoes": 1, "distancia": 80}
assert calcular_risco(ruim)["score"] == 7 and calcular_risco(ruim)["risco"] == "alto"
assert calcular_risco(dict.fromkeys(ruim))["risco"] == "baixo"

# regras duras valem acima da pontuação: frequência < 75% força "alto"; histórico curto limita a "médio"
bom = {"freq": 70, "nota": 90, "reprovacoes": 0, "reclamacoes": 0, "distancia": 10, "registros": 25}
assert calcular_risco(bom)["score"] == 2 and calcular_risco(bom)["risco"] == "alto"  # 2 pontos, mas a frequência força
assert calcular_risco(bom | {"registros": 5})["risco"] == "medio"  # calouro com frequência baixa: o histórico vence
assert calcular_risco(bom | {"freq": 80, "nota": 40, "reprovacoes": 1, "reclamacoes": 1, "distancia": 80,
                             "registros": 5})["risco"] == "medio"  # 5 pontos, mas histórico curto: teto "médio"
assert calcular_risco(bom | {"freq": None})["risco"] == "baixo"  # sem dado, a regra não se aplica
assert calcular_risco(bom | {"registros": None})["risco"] == "alto"
print("ok: rotas e permissões da API funcionam")
