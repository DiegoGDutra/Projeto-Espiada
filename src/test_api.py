import os
import shutil
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp()) / "teste.db"
shutil.copy(Path(__file__).with_name("funcionaai.db"), tmp)
os.environ["SIMPA_DB"] = str(tmp)

from fastapi.testclient import TestClient  # noqa: E402
from Projeto_SIMPA import app  # noqa: E402

c = TestClient(app)


def test_fluxo():
    curso = c.post("/cursos", json={"nome": "Engenharia"}).json()
    r = c.post("/alunos", json={"matricula": 1, "nome": "Ana", "senha": "123456", "id_curso": curso["id"], "distancia": 40})
    assert r.status_code == 201 and r.json()["curso"] == "Engenharia"
    assert c.post("/alunos", json={"matricula": 1, "nome": "X", "senha": "123456", "id_curso": curso["id"]}).status_code == 409

    a = c.put("/alunos/1/desempenho", json={"materia": 1, "total_aulas": 100, "faltas_totais": 30, "nota_cic1": 4, "nota_cic2": 5}).json()
    assert a["freq"] == 70 and a["nota"] == 4.5 and a["risco"] == "alto"  # 2 + 2 + 1 (distância)

    p = c.post("/alunos/1/predicao").json()
    assert p["score"] == 5 and p["risco"] == "alto"
    assert c.get("/alunos/1/predicao").json()["fatores"] == p["fatores"]
    assert c.get("/alunos/999").status_code == 404
    assert len(c.get("/alunos").json()) == 1
