"""Importa o dataset num banco temporário e confere as rotas e o formato JSON.  Rodar:  python src/teste_api.py"""
import tempfile
from pathlib import Path

import Espiada
from importar import importar

Espiada.BANCO = Path(tempfile.mkdtemp()) / "teste.db"  # não mexe no funcionaai.db
qtd = importar(Espiada.BANCO)
assert (qtd["alunos"], qtd["registros_academicos"], qtd["turmas"]) == (120, 2949, 320), qtd
api = Espiada.app.test_client()


def chama(metodo, url, json=None, status=200):
    r = api.open(url, method=metodo, json=json)
    assert r.status_code == status, f"{metodo} {url}: esperava {status}, veio {r.status_code} {r.get_json()}"
    return r.get_json()


assert chama("GET", "/api/cursos")[0]["nome"] == "Engenharia de Software"
assert len(chama("GET", "/api/disciplinas")) == 40 and len(chama("GET", "/api/docentes")) == 18

alunos = chama("GET", "/api/alunos")
assert len(alunos) == 120 and {a["risco"] for a in alunos} <= {"baixo", "medio", "alto"}
a = chama("GET", "/api/alunos/AES0001")
assert a["matricula"] == "AES0001" and a["curso"] == "Engenharia de Software" and a["reclamacoes"] == 0, a
assert a["disciplinas"] and all(0 <= d["nota_n1"] <= 100 for d in a["disciplinas"])

chama("POST", "/api/alunos/AES0001/feedback", {"alvo": "curso", "avaliacao_curso": 1, "comentarios": "ruim"}, 201)
assert chama("GET", "/api/alunos/AES0001")["reclamacoes"] == 1

p = chama("POST", "/api/alunos/AES0001/predicao", status=201)
assert p == {"matricula": "AES0001"} | Espiada.calcular_risco(chama("GET", "/api/alunos/AES0001")), p
assert chama("GET", "/api/alunos/AES0001/predicao")[0]["risco"] == p["risco"]

# regras de risco: tudo ruim = alto com score 7; sem dado não conta
ruim = {"freq": 50, "nota": 40, "reprovacoes": 2, "reclamacoes": 1, "distancia": 80}
assert Espiada.calcular_risco(ruim)["score"] == 7 and Espiada.calcular_risco(ruim)["risco"] == "alto"
assert Espiada.calcular_risco(dict.fromkeys(ruim))["risco"] == "baixo"

# erros sempre em {"erro": ...}; nota e frequência não têm rota de escrita (RN11)
assert "erro" in chama("GET", "/api/alunos/XYZ", status=404)
assert "erro" in chama("POST", "/api/alunos/XYZ/feedback", {"alvo": "curso"}, 404)
chama("POST", "/api/alunos/AES0001/feedback", {"alvo": "professor"}, 400)  # RN05
chama("POST", "/api/alunos/AES0001/feedback", ["não é objeto"], 400)
chama("PUT", "/api/alunos/AES0001/desempenho", {"nota_n1": 100}, 404)
chama("GET", "/api/inexistente", status=404)
print("ok: todas as rotas da API funcionam")
