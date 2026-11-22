-- Banco do SIMPA (PostgreSQL). Roda inteiro a cada subida do app: tudo aqui é IF NOT EXISTS.
-- Parte 1: tabelas do dataset sintético (pasta dados/), com a mesma estrutura dele,
-- mais os CHECK de notas/frequência. Os dados entram só pelo scripts/importar.py, ninguém edita à mão.
-- Parte 2: tabelas do próprio sistema (login, feedback, histórico de predições).

CREATE TABLE IF NOT EXISTS cursos (
  curso_id INTEGER PRIMARY KEY,
  nome TEXT NOT NULL,
  grau TEXT NOT NULL,
  total_periodos INTEGER NOT NULL,
  disciplinas_por_periodo INTEGER NOT NULL,
  modalidade TEXT NOT NULL,
  cidade_sede TEXT NOT NULL,
  uf_sede TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS periodos_curriculares (
  periodo_id INTEGER PRIMARY KEY,
  curso_id INTEGER NOT NULL REFERENCES cursos(curso_id),
  numero_periodo INTEGER NOT NULL,
  quantidade_disciplinas INTEGER NOT NULL,
  carga_horaria_prevista INTEGER NOT NULL,
  UNIQUE (curso_id, numero_periodo)
);

CREATE TABLE IF NOT EXISTS disciplinas (
  disciplina_id INTEGER PRIMARY KEY,
  periodo_id INTEGER NOT NULL REFERENCES periodos_curriculares(periodo_id),
  codigo TEXT NOT NULL,
  nome TEXT NOT NULL,
  carga_horaria INTEGER NOT NULL,
  tipo TEXT NOT NULL,
  indice_dificuldade_sintetico DOUBLE PRECISION NOT NULL,
  UNIQUE (codigo)
);

CREATE TABLE IF NOT EXISTS cidades (
  cidade_id INTEGER PRIMARY KEY,
  nome TEXT NOT NULL,
  uf TEXT NOT NULL,
  distancia_rodoviaria_aprox_km DOUBLE PRECISION NOT NULL,
  UNIQUE (nome, uf)
);

CREATE TABLE IF NOT EXISTS docentes (
  docente_id INTEGER PRIMARY KEY,
  nome_sintetico TEXT NOT NULL,
  titulacao TEXT NOT NULL,
  regime_trabalho TEXT NOT NULL
);

-- codigo_academico é a matrícula do aluno e é o que a API usa nas rotas.
CREATE TABLE IF NOT EXISTS alunos (
  aluno_id INTEGER PRIMARY KEY,
  codigo_academico TEXT NOT NULL,
  nome_sintetico TEXT NOT NULL,
  data_nascimento TEXT NOT NULL,
  genero_autodeclarado TEXT NOT NULL,
  origem_dado TEXT NOT NULL,
  UNIQUE (codigo_academico)
);

CREATE TABLE IF NOT EXISTS enderecos_alunos (
  endereco_id INTEGER PRIMARY KEY,
  aluno_id INTEGER NOT NULL REFERENCES alunos(aluno_id),
  cidade_id INTEGER NOT NULL REFERENCES cidades(cidade_id),
  logradouro_sintetico TEXT NOT NULL,
  numero_sintetico INTEGER NOT NULL,
  complemento_sintetico TEXT,
  bairro_sintetico TEXT NOT NULL,
  cep_sintetico TEXT NOT NULL,
  tempo_deslocamento_min INTEGER NOT NULL,
  UNIQUE (aluno_id)
);

CREATE TABLE IF NOT EXISTS perfis_socioeconomicos (
  perfil_id INTEGER PRIMARY KEY,
  aluno_id INTEGER NOT NULL REFERENCES alunos(aluno_id),
  data_referencia TEXT NOT NULL,
  renda_pessoal_mensal DOUBLE PRECISION NOT NULL,
  renda_familiar_mensal DOUBLE PRECISION NOT NULL,
  pessoas_domicilio INTEGER NOT NULL,
  trabalha INTEGER NOT NULL,
  horas_trabalho_semana INTEGER NOT NULL,
  dependentes INTEGER NOT NULL,
  primeira_geracao_superior INTEGER NOT NULL,
  qualidade_internet TEXT NOT NULL,
  escola_publica_origem INTEGER NOT NULL,
  UNIQUE (aluno_id, data_referencia)
);

CREATE TABLE IF NOT EXISTS tipos_bolsa (
  tipo_bolsa_id INTEGER PRIMARY KEY,
  nome TEXT NOT NULL,
  categoria TEXT NOT NULL,
  percentual DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS bolsas_alunos (
  bolsa_aluno_id INTEGER PRIMARY KEY,
  aluno_id INTEGER NOT NULL REFERENCES alunos(aluno_id),
  tipo_bolsa_id INTEGER NOT NULL REFERENCES tipos_bolsa(tipo_bolsa_id),
  data_inicio TEXT NOT NULL,
  data_fim TEXT,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matriculas_curso (
  matricula_curso_id INTEGER PRIMARY KEY,
  aluno_id INTEGER NOT NULL REFERENCES alunos(aluno_id),
  curso_id INTEGER NOT NULL REFERENCES cursos(curso_id),
  data_ingresso TEXT NOT NULL,
  ano_ingresso INTEGER NOT NULL,
  semestre_ingresso INTEGER NOT NULL,
  periodo_atual INTEGER NOT NULL,
  turno TEXT NOT NULL,
  status TEXT NOT NULL,
  forma_ingresso TEXT NOT NULL,
  data_referencia TEXT NOT NULL,
  UNIQUE (aluno_id, curso_id)
);

-- Professor só vê as próprias turmas.
CREATE TABLE IF NOT EXISTS turmas (
  turma_id INTEGER PRIMARY KEY,
  disciplina_id INTEGER NOT NULL REFERENCES disciplinas(disciplina_id),
  docente_id INTEGER NOT NULL REFERENCES docentes(docente_id),
  ano_letivo INTEGER NOT NULL,
  semestre_letivo INTEGER NOT NULL,
  codigo_turma TEXT NOT NULL,
  turno TEXT NOT NULL,
  modalidade TEXT NOT NULL,
  vagas INTEGER NOT NULL,
  carga_horaria INTEGER NOT NULL,
  UNIQUE (codigo_turma)
);

-- Uma linha por aluno, turma e tentativa. Notas e frequência de 0 a 100.
CREATE TABLE IF NOT EXISTS registros_academicos (
  registro_id INTEGER PRIMARY KEY,
  matricula_curso_id INTEGER NOT NULL REFERENCES matriculas_curso(matricula_curso_id),
  turma_id INTEGER NOT NULL REFERENCES turmas(turma_id),
  tentativa INTEGER NOT NULL,
  situacao TEXT NOT NULL,
  nota_n1 DOUBLE PRECISION NOT NULL CHECK (nota_n1 BETWEEN 0 AND 100),
  nota_n2 DOUBLE PRECISION CHECK (nota_n2 BETWEEN 0 AND 100),
  nota_projeto DOUBLE PRECISION CHECK (nota_projeto BETWEEN 0 AND 100),
  nota_parcial DOUBLE PRECISION CHECK (nota_parcial BETWEEN 0 AND 100),
  nota_final DOUBLE PRECISION CHECK (nota_final BETWEEN 0 AND 100),
  frequencia_percentual DOUBLE PRECISION CHECK (frequencia_percentual BETWEEN 0 AND 100),
  faltas_horas INTEGER NOT NULL,
  carga_horaria_cursada INTEGER NOT NULL,
  data_atualizacao TEXT NOT NULL,
  UNIQUE (matricula_curso_id, turma_id, tentativa)
);

-- Risco já calculado pelo dataset. Não usar como entrada da predição (vazamento: é a resposta pronta).
CREATE TABLE IF NOT EXISTS indicadores_risco (
  indicador_id INTEGER PRIMARY KEY,
  matricula_curso_id INTEGER NOT NULL REFERENCES matriculas_curso(matricula_curso_id),
  data_referencia TEXT NOT NULL,
  media_historica DOUBLE PRECISION NOT NULL,
  media_periodo_atual DOUBLE PRECISION NOT NULL,
  frequencia_media DOUBLE PRECISION NOT NULL,
  reprovacoes INTEGER NOT NULL,
  tendencia_nota_por_periodo DOUBLE PRECISION NOT NULL,
  score_risco_percentual DOUBLE PRECISION NOT NULL,
  classificacao_risco TEXT NOT NULL,
  motivos_risco TEXT NOT NULL,
  UNIQUE (matricula_curso_id, data_referencia)
);

-- Gabarito: evasão que de fato aconteceu na janela de 12 meses.
CREATE TABLE IF NOT EXISTS desfechos_alunos (
  desfecho_id INTEGER PRIMARY KEY,
  matricula_curso_id INTEGER NOT NULL REFERENCES matriculas_curso(matricula_curso_id),
  inicio_janela TEXT NOT NULL,
  fim_janela TEXT NOT NULL,
  evasao_observada INTEGER NOT NULL,
  tipo_desfecho TEXT NOT NULL,
  data_evento_ou_censura TEXT NOT NULL,
  UNIQUE (matricula_curso_id, inicio_janela)
);

-- ---------- Parte 2: tabelas do sistema ----------

-- Quem faz login: aluno, professor ou secretaria. Senha só em hash.
CREATE TABLE IF NOT EXISTS usuario (
  login      TEXT PRIMARY KEY,                       -- e-mail
  perfil     TEXT NOT NULL CHECK (perfil IN ('aluno', 'professor', 'secretaria')),
  nome       TEXT NOT NULL,
  senha_hash TEXT NOT NULL,
  aluno_id   INTEGER UNIQUE REFERENCES alunos(aluno_id),
  docente_id INTEGER UNIQUE REFERENCES docentes(docente_id),
  CHECK ((perfil = 'aluno') = (aluno_id IS NOT NULL) AND (perfil = 'professor') = (docente_id IS NOT NULL))
);

-- Aluno só comenta sobre o próprio curso ou a instituição.
CREATE TABLE IF NOT EXISTS feedback (
  feedback_id     INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  aluno_id        INTEGER NOT NULL REFERENCES alunos(aluno_id),
  alvo            TEXT NOT NULL CHECK (alvo IN ('curso', 'instituicao')),
  comentarios     TEXT,
  avaliacao_curso INTEGER CHECK (avaliacao_curso BETWEEN 1 AND 5),
  criado_em       TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
);

-- Cada treinamento do modelo estatístico (treinar-modelo). Vale o último aprovado; os reprovados ficam como registro.
-- pesos e metricas são JSON. As métricas vêm só dos alunos separados para o teste.
CREATE TABLE IF NOT EXISTS modelo_risco (
  modelo_id  INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  criado_em  TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),  -- UTC
  pesos      TEXT NOT NULL,
  metricas   TEXT NOT NULL,
  aprovado   BOOLEAN NOT NULL
);

-- Histórico de predições do sistema: uma linha por cálculo, nunca sobrescreve.
-- Risco em níveis; alteração manual exige quem alterou e justificativa.
-- origem: 'llm' (regras + Ollama) ou 'regras' (LLM fora do ar). entrada_hash: resumo do que a LLM recebeu;
-- se for igual ao da última predição, nada mudou e o recálculo em lote pula o aluno.
CREATE TABLE IF NOT EXISTS predicao_ia (
  predicao_id         INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  matricula_curso_id  INTEGER NOT NULL REFERENCES matriculas_curso(matricula_curso_id),
  criado_em           TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),  -- UTC
  nivel_risco         TEXT NOT NULL CHECK (nivel_risco IN ('baixo', 'medio', 'alto')),
  score               INTEGER,
  comentario_predicao TEXT,
  alterada_por        TEXT REFERENCES usuario(login),
  justificativa       TEXT,
  origem              TEXT NOT NULL DEFAULT 'regras' CHECK (origem IN ('regras', 'llm')),
  modelo              TEXT,
  entrada_hash        TEXT,
  detalhes            TEXT,  -- JSON: fatores, ajustes das regras duras, nível das regras e nível da LLM
  CHECK (alterada_por IS NULL OR justificativa IS NOT NULL)
);

-- chance de evasão (0 a 1) e versão do modelo estatístico; nulas nas predições feitas sem modelo treinado
ALTER TABLE predicao_ia ADD COLUMN IF NOT EXISTS probabilidade DOUBLE PRECISION CHECK (probabilidade BETWEEN 0 AND 1);
ALTER TABLE predicao_ia ADD COLUMN IF NOT EXISTS modelo_risco_id INTEGER REFERENCES modelo_risco(modelo_id);

-- o histórico cresce a cada recálculo em lote; a última predição de cada aluno é buscada por matrícula
CREATE INDEX IF NOT EXISTS predicao_ia_matricula ON predicao_ia (matricula_curso_id, predicao_id);
