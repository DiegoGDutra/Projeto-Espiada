# Roadmap — ESPIADA

## Base do sistema

| Funcionalidade | % | Feito | Falta |
|---|---|---|---|
| Banco de dados SQLite | 100% | `src/schema.sql` com as tabelas do dataset e do sistema; matrícula = `codigo_academico`; `CHECK` de nota e frequência entre 0 e 100 | — |
| Importação dos dados acadêmicos | 100% | `src/importar.py` importa o dataset sintético; nenhuma rota escreve nota ou frequência | — |
| API REST em JSON | 100% | Rotas por recurso em `/api/...`, erros padronizados `{"erro": ...}` | Novas rotas conforme as funcionalidades abaixo |
| Login e sessão | 100% | Login por e-mail, senha forte, hash, cookie `HttpOnly`/`SameSite`, bloqueio após 5 erros | — |
| Perfis e permissões | 100% | Aluno, professor e secretaria, cada um vê só o seu; `403` registrado no log; cadastro pelo terminal ou pela API | — |

## Monitoramento e painel

| Funcionalidade | % | Feito | Falta |
|---|---|---|---|
| Painel principal (dashboard) | 85% | Cartões com total e contagem por nível de risco, lista dos alunos críticos, filtro por turma que vale para o painel inteiro e seletor com 4 tipos de gráfico | Frequência média e nota média gerais |
| Filtros de alunos | 100% | Busca por nome, filtro por turma e por nível de risco no Monitoramento; filtro por turma no Painel | — |
| Histórico individual do aluno | 80% | Ficha com notas e frequência por semestre e histórico de predições | Gráfico da evolução de notas, frequência e risco |
| Gráficos de desempenho | 60% | Barras (% de alto risco por turma), barras empilhadas (alto/médio/baixo por turma), rosca (distribuição geral) e rede/radar (alunos com risco por turma), feitos em CSS e SVG sem biblioteca | Gráficos por aluno, de frequência e de notas |
| Aba Turmas | 10% | Rota `GET /api/turmas` existe | A aba é só um aviso de "não implementado" |
| Alunos que mudaram de situação | 0% | — | Listar quem mudou de nível de risco, do mais recente para o mais antigo |

## Cálculo de risco e predição

| Funcionalidade | % | Feito | Falta |
|---|---|---|---|
| Cálculo de risco por regras | 65% | `calcular_risco()` com frequência, nota, reprovações, reclamações e distância; níveis baixo/médio/alto; o texto dos feedbacks é lido pela LLM | Entrega de atividades (o dataset não tem); estatísticas (média, mediana, moda, variância, desvio padrão) |
| Frequência < 75% força risco alto | 100% | Regra dura em `limites_duros()`: força "alto" independente da nota e da LLM; testada em `teste_api.py` e `teste_llm.py` | — |
| Alto risco só com histórico mínimo | 90% | Teto "médio" com menos de 8 registros (`HISTORICO_MINIMO`); vence a regra da frequência quando as duas valem | Confirmar o valor do mínimo (no dataset, qualquer valor de 6 a 10 pega os mesmos 15 alunos do 1º semestre) |
| Pesos configuráveis | 0% | Pesos fixos na lista `REGRAS` de `src/models/predicao.py` | Guardar os pesos no banco, criar rota e tela para editar |
| Predição com LLM (Ollama) | 85% | `qwen3:8b` local via `src/models/llm.py`: contexto anonimizado, saída em JSON validada, limite de 1 nível sobre as regras, fallback para as regras se o Ollama cair, origem/modelo/comentário no histórico e na tela; guia em `LLM.md`; `src/teste_llm.py` com Ollama simulado | Validar com o Ollama de verdade na máquina de 8 GB de VRAM; medir o tempo por aluno e ajustar o prompt com o gabarito (`desfechos_alunos`) |
| Recálculo das predições | 70% | Comando `recalcular-predicoes` e `POST /api/predicoes/recalcular` (segundo plano, só secretaria); pula quem não mudou (hash da entrada) e para se a LLM falhar 3 vezes seguidas | Gatilho automático quando chegarem dados novos (hoje o `importar.py` não importa de novo); botão na aba Config.; medir 1000 alunos em até 5 min (só cabe com a LLM apenas em quem mudou) |
| Alteração manual de predição | 20% | Colunas `alterada_por` e `justificativa` com `CHECK` exigindo justificativa | Rota e tela; só secretaria ou o professor da turma pode alterar |

## Relatórios, feedback e notificações

| Funcionalidade | % | Feito | Falta |
|---|---|---|---|
| Feedback do aluno | 65% | Tabela `feedback`, rota `POST /api/alunos/{matricula}/feedback` (só o próprio aluno) e teste; formulário na tela Meu desempenho (só demonstração, não grava) | Ligar o formulário à rota; seção "feedbacks dos alunos" para o professor |
| Relatórios exportáveis (PDF/CSV) | 0% | A aba Relatórios é só um aviso | Exportar por aluno, por turma e por curso; relatório final de desempenho para o aluno |
| Notificação de alto risco | 0% | — | Avisar a coordenação por WhatsApp ou Telegram, sem repetir o mesmo aluno em 24 h |
| Configurações da plataforma | 30% | Aba Config. com o formulário de cadastro de usuário pronto, mas escondido (marcado como em desenvolvimento) | Critérios de risco, perfis de acesso, dados institucionais |

## Segurança, LGPD e qualidade

| Funcionalidade | % | Feito | Falta |
|---|---|---|---|
| Validação nos próprios campos | 75% | `CHECK` no banco; formulário de cadastro valida e-mail e senha no campo; feedback exige a avaliação | Validar os campos das telas novas (pesos, justificativa) |
| Logs e auditoria | 20% | Log no console de acesso negado e login errado | Registro persistente de requisições e alterações |
| Limite de requisições | 15% | Só no login (5 erros = 15 min de bloqueio) | Máximo de 10 chamadas da mesma função a cada 3 h |
| HTTPS / segurança de rede | 10% | Cookie de sessão protegido | Servir por HTTPS/TLS; `SECRET_KEY` fixa em produção |
| LGPD | 40% | Cada perfil só recebe os alunos que pode ver; a LLM roda local e recebe só indicadores anonimizados (sem nome nem matrícula); página `sobre.html` com Termos de Uso, Política de Privacidade, Cookies e Contato; link para a LGPD no rodapé de todas as telas | Preencher os placeholders (CNPJ, encarregado, prazo de guarda); criptografar nome e matrícula no banco; anonimizar os dados agregados dos relatórios |
| Interface adaptável a dispositivos | 30% | Uma regra `@media` no painel | Ajustar o login e testar em celular e tablet |
| Escalabilidade | 0% | — | Teste com vários usuários ao mesmo tempo |
| Testes | 40% | `src/teste_banco.py`, `src/teste_api.py` e `src/teste_llm.py` passam; modo debug ligado | Testes de segurança, com usuários reais, de carga, de dispositivos e de notificação |

## Próximos passos pelo cronograma

| Semana | Prazo | Foco | Situação |
|---|---|---|---|
| 05 | 22/10 | Regras de negócio, pesos configuráveis, níveis | Em andamento: histórico mínimo e corte de frequência feitos; faltam os pesos configuráveis |
| 06 | 29/10 | LLM do Ollama e tempo de recálculo | Quase pronto: LLM e recálculo em lote integrados e testados com Ollama simulado; falta validar com o Ollama real e medir o tempo |
| 07 | 05/11 | Gráficos, filtros por turma, histórico com evolução | Quase pronto: gráficos e filtros por turma feitos; falta a evolução no histórico do aluno |
| 08 | 12/11 | Feedback na tela, notificações, logs de auditoria, teste de carga | Parcial (rota de feedback e formulário de demonstração) |
