# Dataset sintético SIMPA - Engenharia de Software

Base inteiramente sintética, criada para ensino de banco de dados, estatística, APIs e predição acadêmica. Nenhum registro representa pessoa real.

## Escopo

- 120 alunos, 8 períodos e exatamente 5 disciplinas curriculares por período (40 disciplinas).
- 8 semestres letivos, de 2023-1 a 2026-2, com histórico e período atual.
- 2949 registros acadêmicos, incluindo tentativas repetidas e 600 matrículas em andamento.
- 57 alunos residentes fora de Anápolis e 53 bolsistas/financiados.
- 20 eventos sintéticos de evasão na janela de 12 meses.
- 12 frequências ausentes intencionais e notas parciais/finais ausentes em situações coerentes com disciplinas em andamento.

## Uso recomendado

1. Importe os arquivos de **csv_normalizados/** na ordem listada abaixo, após executar **schema_sqlite.sql**.
2. Use **simpa_visao_analitica.csv** apenas para exploração inicial, gráficos e protótipos de modelos. Ela é propositalmente desnormalizada.
3. Separe a variável-alvo **evasao_observada** das variáveis preditoras. Não use **score_risco_percentual**, **classificacao_risco** ou **motivos_risco** como preditores de um modelo que pretenda reproduzir o desfecho, pois são indicadores derivados e podem causar vazamento de informação.
4. Faça divisão treino/teste estratificada e avalie precisão, revocação, F1, ROC-AUC e matriz de confusão.
5. Não trate correlação como causalidade. O conjunto contém padrões moderados e ruído intencional.

## Ordem de importação

1. cursos
2. periodos_curriculares
3. disciplinas
4. cidades
5. docentes
6. alunos
7. enderecos_alunos
8. perfis_socioeconomicos
9. tipos_bolsa
10. bolsas_alunos
11. matriculas_curso
12. turmas
13. registros_academicos
14. indicadores_risco
15. desfechos_alunos

## Convenções

- CSV UTF-8, separador vírgula, cabeçalho na primeira linha, ponto como separador decimal e datas ISO 8601 (AAAA-MM-DD).
- Campos vazios representam NULL. Identificadores são inteiros e estáveis.
- Valores monetários estão em reais. Notas e frequências variam de 0 a 100.
- CEPs, nomes e logradouros são fictícios. Distâncias e tempos são aproximações para fins didáticos.
- A visão analítica tem uma linha por aluno; a tabela normalizada de registros acadêmicos tem uma linha por aluno, turma e tentativa.

## Relações principais

- alunos 1:1 enderecos_alunos e 1:N perfis_socioeconomicos
- alunos 1:N matriculas_curso; matriculas_curso 1:N registros_academicos
- cursos 1:N disciplinas; disciplinas 1:N turmas; turmas 1:N registros_academicos
- alunos N:N tipos_bolsa por bolsas_alunos
- matriculas_curso 1:N indicadores_risco e 1:N desfechos_alunos
