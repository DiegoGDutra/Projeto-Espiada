# AGENTS.md — Espiada (SIMPA)

Instruções para agentes de IA (Claude Code, Codex, Cursor...) que trabalham neste repositório.
A documentação para pessoas fica no `readme.md`; aqui ficam só comandos, regras e armadilhas.

## O projeto

Sistema web de monitoramento e predição de risco de evasão acadêmica (projeto de faculdade, Grupo 05).
Flask + PostgreSQL, tudo no Docker, MVC, front em HTML/CSS/JS puro, LLM local pelo Ollama. Dados 100% sintéticos (5000 alunos).

## Comandos (Windows, na raiz do projeto)

- Sistema inteiro: `docker compose up -d --build` → http://127.0.0.1:5000 (containers `web-espiada` e `banco-espiada`, volume `espiada_dados`, portas só em 127.0.0.1). A 1ª subida importa e treina sozinha (`scripts/iniciar.py`). Mudou o código? Rode de novo com `--build`.
- Log: `docker compose logs -f web`
- Treinar o modelo de risco de novo: `docker compose exec web flask --app app/Espiada.py treinar-modelo`
- Recálculo em lote: `docker compose exec web flask --app app/Espiada.py recalcular-predicoes` (`--forcar` reanalisa todos)
- Zerar o banco (apaga os dados): `docker compose down -v` e depois `up -d --build`
- Fora do Docker (desenvolvimento): `docker compose stop web`, `.venv\Scripts\python -m pip install -r requirements.txt` e `.venv\Scripts\python app/Espiada.py`

## Testes

```
docker compose exec web python testes/teste_banco.py        # < 1 s
docker compose exec web python testes/teste_api.py          # ~1 min
docker compose exec web python testes/teste_llm.py          # ~1 min
docker compose exec web python testes/teste_modelo.py       # ~15 s
docker compose exec web python testes/teste_estatistica.py  # ~20 s
```

- Precisam do PostgreSQL no ar; não precisam do Ollama (a LLM é simulada).
- Cada teste usa um esquema próprio (`teste_banco`, `teste_api`, `teste_llm`, `teste_modelo`, `teste_estatistica`), recriado a cada execução. Nunca rode testes no esquema `public`.
- Os testes não usam framework: são scripts com `assert`. Rode os cinco depois de mexer em models, controllers ou `schema.sql`.

## Estrutura

- `app/` — o sistema (MVC): `Espiada.py` (entrada), `schema.sql`, `models/` (SQL e regras), `controllers/` (rotas), `views/` (HTML), `static/`
- `scripts/` — `iniciar.py` (entrada do container), `importar.py` (CSV → banco + logins) e `ampliar_dados.py` (gera o dataset de 5000 alunos, semente fixa)
- `testes/` — os cinco testes
- `dados/` — CSVs do dataset e `LEIA-ME.md` com o dicionário

`scripts/` e `testes/` acham os models colocando `app/` no `sys.path` no topo do arquivo; mantenha esse padrão.

## Regras do sistema (não quebrar)

- Nota e frequência só entram pelo importador. Nenhuma rota ou tela escreve nesses campos.
- Cada perfil vê só o que pode: aluno só ele mesmo, professor só alunos das próprias turmas, secretaria todos (`filtro_visiveis` em `app/models/alunos.py`).
- `indicadores_risco` e `desfechos_alunos` nunca são variáveis de entrada da predição (vazamento: são a resposta pronta / o gabarito). O gabarito só é lido em `gabarito()` de `app/models/avaliacao.py`, para medir o acerto e servir de resposta no treino (`app/models/treino.py`).
- Métrica do modelo treinado vem só dos alunos separados para o teste. Uma versão só entra em uso se o ganho de AUC for positivo em todo o IC 95%.
- Tendência (`app/models/tendencia.py`): o último semestre concluído dos alunos de teste é o gabarito e fica escondido até a comparação. O modelo só prevê se errar menos que repetir o semestre anterior em todo o IC 95%. O treino fica em cache no processo (`functools.cache`): mudou nota ou frequência com o servidor no ar, reinicie.
- Estatística: professor só agrega registros das próprias turmas; fatores e comparações (usam desfecho e perfil socioeconômico) são só da secretaria. Avaliação por grupo usa só os alunos de teste.
- O aluno vê o próprio nível de risco, mas não a porcentagem (`_com_risco` em `app/controllers/alunos.py`).
- A LLM não recebe nome, matrícula, endereço nem outro identificador; o contexto é montado em `entrada_llm()`.
- Regras duras valem acima do modelo e da LLM: frequência < 75% força "alto"; menos de 8 registros limita a "médio". Com modelo treinado, a LLM só comenta; sem ele, só se afasta 1 nível das regras.
- Predições nunca são sobrescritas: cada cálculo é uma linha nova em `predicao_ia`.
- Mudou o `PROMPT` em `app/models/llm.py`? Incremente `PROMPT_VERSAO`.

## Convenções de código

- Nomes, comentários, mensagens de erro e commits em português.
- SQL só em `app/models/`. Controllers conferem login/perfil, chamam o model e devolvem JSON.
- Use `consultar()` e `transacao()` de `app/models/banco.py` (passam pelo pool de conexões). Parâmetros com `%s`, nunca f-string com valor vindo de fora.
- Não escreva `%` literal em SQL com parâmetros (use `starts_with()` em vez de `LIKE 'x%'`).
- Valores numéricos com `round(...::numeric, 1)::float`: `numeric` vira `Decimal` e o Flask devolveria string no JSON.
- `criado_em` é TEXT `AAAA-MM-DD HH:MM:SS` em UTC; a tela depende desse formato.
- Erro de regra de negócio vira `ErroModelo(status, mensagem)`; o app traduz para `{"erro": ...}`.
- Prefira o mais simples: sem dependência nova para o que poucas linhas resolvem; front sem framework (gráficos em SVG/CSS à mão).
- Toda tabela nova ou coluna nova vai em `app/schema.sql` com `IF NOT EXISTS` (o schema roda a cada subida do app).

## Armadilhas conhecidas

- O container `web-espiada` ocupa a porta 5000. Para rodar `app/Espiada.py` direto, pare-o antes (`docker compose stop web`).
- O app roda em um único processo com várias threads, porque o andamento do recálculo e o bloqueio de login ficam em memória. Não aumente o número de processos sem mover esse estado para o banco.
- Dentro do Docker, o banco é `banco:5432` e o Ollama do computador é `host.docker.internal:11434`. Fora dele, o banco é `127.0.0.1:5432`.
- `.dockerignore` é uma lista do que pode entrar na imagem: pasta nova precisa ser liberada nele e copiada no `Dockerfile`.
- Use `127.0.0.1`, não `localhost`, no endereço do banco: `localhost` tenta IPv6 primeiro e trava 8 s com o Docker.
- O importador se recusa a importar num banco que já tem alunos (de propósito). Para reimportar, zere o banco.
- Abrir conexão no PostgreSQL custa ~25 ms; por isso existe o pool. Não use `conectar()` em código chamado por aluno.
- `scripts/ampliar_dados.py` reescreve os CSVs de `dados/` (mantém os 120 alunos originais). Depois dele, é preciso zerar e reimportar.

## Ao terminar uma mudança

- Atualize junto o que ela afeta: `readme.md` (uso e arquitetura), `roadmap.md` (andamento em %), `dados/LEIA-ME.md` (se mexer no dataset) e `app/views/sobre.html` (ficha técnica).
- Não commite `.env`, dumps do banco (`*.sql` de backup) nem os `.pptx`/`.docx` da apresentação (estes já estão no `.gitignore`).
