-- Modelagem inicial do banco (SQLite). Regras do Trello citadas entre parênteses.
-- Notas e frequência vêm do AVA (RN11); por isso aqui só ficam os dados brutos.

CREATE TABLE IF NOT EXISTS curso (
    id_curso   INTEGER PRIMARY KEY,
    nome_curso TEXT NOT NULL UNIQUE
);

-- Todo mundo que faz login: aluno, professor ou secretaria (RF11). Matrícula é a chave (RN01).
CREATE TABLE IF NOT EXISTS usuario (
    matricula  INTEGER PRIMARY KEY,
    perfil     TEXT NOT NULL CHECK (perfil IN ('aluno', 'professor', 'secretaria')),
    nome       TEXT NOT NULL,
    email      TEXT UNIQUE,
    senha_hash TEXT NOT NULL                          -- nunca a senha pura (RNF07)
);

CREATE TABLE IF NOT EXISTS aluno (
    matricula     INTEGER PRIMARY KEY REFERENCES usuario (matricula),
    id_curso      INTEGER NOT NULL REFERENCES curso (id_curso),
    periodo       INTEGER CHECK (periodo >= 1),
    situacao      INTEGER NOT NULL,
    data_ingresso TEXT,                               -- 'AAAA-MM-DD'
    distancia_km  REAL CHECK (distancia_km >= 0)
);

CREATE TABLE IF NOT EXISTS materia (
    id_materia   INTEGER PRIMARY KEY,
    id_curso     INTEGER NOT NULL REFERENCES curso (id_curso),
    nome_materia TEXT NOT NULL
);

-- Turma = matéria + professor num semestre. Professor só vê as próprias turmas (RN09).
CREATE TABLE IF NOT EXISTS turma (
    id_turma            INTEGER PRIMARY KEY,
    id_materia          INTEGER NOT NULL REFERENCES materia (id_materia),
    matricula_professor INTEGER REFERENCES usuario (matricula),
    semestre            TEXT NOT NULL                 -- ex.: '2026.2'
);

-- Uma linha por aluno por turma. Notas de 0 a 100 (RN04).
CREATE TABLE IF NOT EXISTS desempenho_aluno (
    matricula        INTEGER NOT NULL REFERENCES aluno (matricula),
    id_turma         INTEGER NOT NULL REFERENCES turma (id_turma),
    situacao_materia TEXT,
    nota_cic1        REAL CHECK (nota_cic1 BETWEEN 0 AND 100),
    nota_cic2        REAL CHECK (nota_cic2 BETWEEN 0 AND 100),
    nota_cic3        REAL CHECK (nota_cic3 BETWEEN 0 AND 100),
    media_final      REAL CHECK (media_final BETWEEN 0 AND 100),
    total_aulas      INTEGER CHECK (total_aulas >= 0),
    faltas_totais    INTEGER CHECK (faltas_totais BETWEEN 0 AND total_aulas),
    PRIMARY KEY (matricula, id_turma)
);

-- Cada acesso ao AVA vira uma linha (antes só cabia um por aluno).
CREATE TABLE IF NOT EXISTS log_ava (
    id          INTEGER PRIMARY KEY,
    matricula   INTEGER NOT NULL REFERENCES aluno (matricula),
    data_acesso TEXT NOT NULL,
    min_sessao  INTEGER CHECK (min_sessao >= 0)
);

CREATE TABLE IF NOT EXISTS financeiro (
    matricula       INTEGER PRIMARY KEY REFERENCES aluno (matricula),
    mensal_atrasada INTEGER CHECK (mensal_atrasada >= 0),
    dias_atrasada   INTEGER CHECK (dias_atrasada >= 0)
);

-- Aluno só comenta sobre o próprio curso ou a instituição (RN05).
CREATE TABLE IF NOT EXISTS feedback (
    id              INTEGER PRIMARY KEY,
    matricula       INTEGER NOT NULL REFERENCES aluno (matricula),
    alvo            TEXT NOT NULL CHECK (alvo IN ('curso', 'instituicao')),
    comentarios     TEXT,
    avaliacao_curso INTEGER CHECK (avaliacao_curso BETWEEN 1 AND 5),
    criado_em       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Histórico de predições (RF07, RF02): uma linha por cálculo, nunca sobrescreve.
-- Risco em níveis (RN06); alteração manual exige quem alterou e justificativa (RN14, RN15).
CREATE TABLE IF NOT EXISTS predicao_ia (
    id                  INTEGER PRIMARY KEY,
    matricula           INTEGER NOT NULL REFERENCES aluno (matricula),
    criado_em           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    nivel_risco         TEXT NOT NULL CHECK (nivel_risco IN ('baixo', 'medio', 'alto')),
    score               INTEGER,
    comentario_predicao TEXT,
    alterada_por        INTEGER REFERENCES usuario (matricula),
    justificativa       TEXT,
    CHECK (alterada_por IS NULL OR justificativa IS NOT NULL)
);
