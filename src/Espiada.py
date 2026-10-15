"""SIMPA - rotas da API em Flask.

Rodar (dentro de src/):  python Espiada.py   ->  http://127.0.0.1:5000
Só as rotas: cada uma devolve um JSON vazio/eco no formato descrito no readme.md.
A lógica (banco, cálculo de risco) entra dentro de cada função depois.
"""
from pathlib import Path

from flask import Flask, jsonify, request, send_file

app = Flask(__name__)


@app.get("/")
def interface():
    return send_file(Path(__file__).with_name("interface.html"))


@app.get("/api/cursos")
def listar_cursos():
    return jsonify([])


@app.post("/api/cursos")
def criar_curso():
    return jsonify(request.get_json()), 201


@app.get("/api/alunos")
def listar_alunos():
    return jsonify([])


@app.get("/api/alunos/<int:matricula>")
def obter_aluno(matricula):
    return jsonify({"matricula": matricula})


@app.post("/api/alunos")
def criar_aluno():
    return jsonify(request.get_json()), 201


@app.put("/api/alunos/<int:matricula>/desempenho")
def registrar_desempenho(matricula):
    return jsonify({"matricula": matricula})


@app.put("/api/alunos/<int:matricula>/ava")
def registrar_ava(matricula):
    return jsonify({"matricula": matricula})


@app.put("/api/alunos/<int:matricula>/feedback")
def registrar_feedback(matricula):
    return jsonify({"matricula": matricula})


@app.post("/api/alunos/<int:matricula>/predicao")
def gerar_predicao(matricula):
    return jsonify({"matricula": matricula, "risco": "baixo", "score": 0, "fatores": []}), 201


@app.get("/api/alunos/<int:matricula>/predicao")
def obter_predicao(matricula):
    return jsonify({"matricula": matricula, "risco": "baixo", "score": 0, "fatores": []})


if __name__ == "__main__":
    app.run(debug=True)
