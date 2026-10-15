# SIMPA — API

Flask + SQLite (`src/funcionaai.db`). Rotas em `src/Espiada.py` (por enquanto só as rotas, sem lógica).

```bash
cd src
python Espiada.py
```

Abra http://127.0.0.1:5000 — o Flask serve a `interface.html`, que consome as rotas `/api/...`.

## Endpoints

| Método | Rota | Entrada (JSON) | Saída |
|---|---|---|---|
| GET | `/api/cursos` | — | `[Curso]` |
| POST | `/api/cursos` | `CursoIn` | `Curso` (201) |
| GET | `/api/alunos` | — | `[Aluno]` |
| GET | `/api/alunos/{matricula}` | — | `Aluno` |
| POST | `/api/alunos` | `AlunoIn` | `Aluno` (201) |
| PUT | `/api/alunos/{matricula}/desempenho` | `DesempenhoIn` | `Aluno` |
| PUT | `/api/alunos/{matricula}/ava` | `AvaIn` | `Aluno` |
| PUT | `/api/alunos/{matricula}/feedback` | `FeedbackIn` | `Aluno` |
| POST | `/api/alunos/{matricula}/predicao` | — | `Predicao` (201) |
| GET | `/api/alunos/{matricula}/predicao` | — | `Predicao` |

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
