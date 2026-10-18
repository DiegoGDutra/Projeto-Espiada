"""Confere as rotas e o formato JSON da API num banco temporário.  Rodar:  python src/test_api.py"""
import tempfile
from pathlib import Path

import Espiada

Espiada.BANCO = Path(tempfile.mkdtemp()) / "teste.db"  # não mexe no funcionaai.db
Espiada.criar_banco()
api = Espiada.app.test_client()


def chama(metodo, url, json=None, status=200):
    r = api.open(url, method=metodo, json=json)
    assert r.status_code == status, f"{metodo} {url}: esperava {status}, veio {r.status_code} {r.get_json()}"
    return r.get_json()


assert chama("POST", "/api/cursos", {"nome_curso": "Engenharia de Software"}, 201) == {"id_curso": 1, "nome_curso": "Engenharia de Software"}
chama("POST", "/api/materias", {"id_curso": 1, "nome_materia": "Cálculo"}, 201)
chama("POST", "/api/turmas", {"id_materia": 1, "semestre": "2026.2"}, 201)
assert len(chama("GET", "/api/cursos")) == 1

aluno = {"matricula": 2024001, "nome": "Ana", "senha": "Segredo#1", "id_curso": 1, "situacao": 1, "distancia_km": 40}
novo = chama("POST", "/api/alunos", aluno, 201)
assert novo["curso"] == "Engenharia de Software" and novo["freq"] is None, "sem dados ainda, indicador é null"
assert "senha" not in novo and "senha_hash" not in novo, "senha nunca sai na resposta"

chama("PUT", "/api/alunos/2024001/desempenho", {"id_turma": 1, "media_final": 50, "total_aulas": 80, "faltas_totais": 40})
chama("PUT", "/api/alunos/2024001/desempenho", {"id_turma": 1, "media_final": 50, "total_aulas": 80, "faltas_totais": 40})  # PUT repetido não duplica
chama("POST", "/api/alunos/2024001/ava", {"data_acesso": "2026-10-01", "min_sessao": 60}, 201)
chama("POST", "/api/alunos/2024001/feedback", {"alvo": "curso", "avaliacao_curso": 1, "comentarios": "ruim"}, 201)

a = chama("GET", "/api/alunos/2024001")
assert (a["freq"], a["nota"], a["ava"], a["reclamacoes"]) == (50.0, 50.0, 10.0, 1), a
assert len(a["disciplinas"]) == 1 and a["risco"] == "alto"

p = chama("POST", "/api/alunos/2024001/predicao", status=201)
assert p["risco"] == "alto" and p["score"] == 7 and all(f["negativo"] for f in p["fatores"])
assert chama("GET", "/api/alunos/2024001/predicao")[0]["risco"] == "alto"
assert chama("GET", "/api/alunos")[0]["risco"] == "alto"

# erros sempre em {"erro": ...}
assert "erro" in chama("POST", "/api/alunos", {"nome": "X"}, 400)
assert "erro" in chama("POST", "/api/alunos", aluno, 409), "matrícula repetida"
assert "erro" in chama("GET", "/api/alunos/999", status=404)
assert "erro" in chama("POST", "/api/alunos/999/ava", {"data_acesso": "x", "min_sessao": 1}, 404)
chama("PUT", "/api/alunos/2024001/desempenho", {"id_turma": 1, "nota_cic1": 101}, 400)  # RN04
chama("POST", "/api/alunos/2024001/feedback", {"alvo": "professor"}, 400)  # RN05
chama("POST", "/api/cursos", ["não é objeto"], 400)
chama("GET", "/api/inexistente", status=404)
print("ok: todas as rotas da API funcionam")
