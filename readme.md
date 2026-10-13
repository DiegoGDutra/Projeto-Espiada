# SIMPA — API

FastAPI + SQLite (`src/funcionaai.db`). Código em `src/Projeto_SIMPA.py`.

```bash
cd src
uvicorn Projeto_SIMPA:app --reload
```

Documentação interativa (todos os schemas JSON): http://127.0.0.1:8000/docs

## Endpoints

| Método | Rota | Entrada (JSON) | Saída |
|---|---|---|---|
| GET | `/cursos` | — | `[Curso]` |
| POST | `/cursos` | `CursoIn` | `Curso` (201) |
| GET | `/alunos` | — | `[Aluno]` |
| GET | `/alunos/{matricula}` | — | `Aluno` |
| POST | `/alunos` | `AlunoIn` | `Aluno` (201) |
| PUT | `/alunos/{matricula}/desempenho` | `DesempenhoIn` | `Aluno` |
| PUT | `/alunos/{matricula}/ava` | `AvaIn` | `Aluno` |
| PUT | `/alunos/{matricula}/feedback` | `FeedbackIn` | `Aluno` |
| POST | `/alunos/{matricula}/predicao` | — | `Predicao` (201) |
| GET | `/alunos/{matricula}/predicao` | — | `Predicao` |

Erros: `{"detail": "mensagem"}` com `404` (não encontrado), `409` (matrícula/e-mail duplicado), `422` (dados inválidos).

## Formato JSON

**CursoIn** → `{"nome": "Engenharia de Software"}`
**Curso** → `{"id": 1, "nome": "Engenharia de Software"}`

**AlunoIn**
```json
{"matricula": 2024001, "nome": "Ana Souza", "email": "ana@email.com", "senha": "minimo6",
 "id_curso": 1, "periodo": 2, "situacao": 1, "data_ingresso": "2024-02-01", "distancia": 12.5}
```

**Aluno** (mesmos campos que `interface.html` já usa; `null` = sem dado)
```json
{"matricula": 2024001, "nome": "Ana Souza", "curso": "Engenharia de Software", "turma": 3,
 "freq": 82, "nota": 7.1, "ava": 64, "reclamacoes": 0, "distancia": 12.5, "risco": "baixo"}
```

**DesempenhoIn**
```json
{"materia": 10, "turma": 3, "situacao_materia": "cursando", "nota_cic1": 7.0, "nota_cic2": 6.5,
 "nota_cic3": null, "total_aulas": 80, "faltas_totais": 12, "media_final": null}
```

**AvaIn** → `{"data_acesso": "2026-10-10", "min_sessao": 380}`
**FeedbackIn** → `{"comentarios": "Horário ruim", "avaliacao_curso": 3}`  (1 a 5)

**Predicao**
```json
{"matricula": 2024001, "data": "2026-10-13T14:20:00", "risco": "medio", "score": 3,
 "fatores": [{"descricao": "Frequência abaixo de 75%", "negativo": true},
             {"descricao": "Desempenho acadêmico regular", "negativo": false}]}
```

## Como os indicadores são calculados

- `freq` = 100 × (1 − faltas_totais / total_aulas)
- `nota` = media_final, ou média das notas de ciclo
- `ava` = min_sessao / 600 min (limitado a 100%)
- `risco`: a mesma regra do `computeRisk()` da interface: freq < 75 (+2), nota < 6 (+2), ava < 50 (+1), reclamação (+1), distância > 30 km (+1). ≥4 alto, ≥2 médio, senão baixo.
