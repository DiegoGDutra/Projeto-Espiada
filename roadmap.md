# Roadmap — ESPIADA

## Base do sistema

| Funcionalidade | Requisitos | % | Feito | Falta |
|---|---|---|---|---|
| Banco de dados SQLite | RNF01, RN01, RN04 | 100% | `espiada/schema.sql` com as tabelas do dataset e do sistema; matrícula = `codigo_academico`; `CHECK` de nota e frequência entre 0 e 100 | — |
| Importação dos dados acadêmicos | RN11, RN16, CA06 | 100% | `espiada/importar.py` importa o dataset sintético; nenhuma rota escreve nota ou frequência | Os cards do Trello ainda dizem "API do AVA" (a decisão foi usar o dataset) |
| API REST em JSON | RNF02 | 100% | Rotas por recurso em `/api/...`, erros padronizados `{"erro": ...}` | Novas rotas conforme as funcionalidades abaixo |
| Login e sessão | RF01, RNF07, CA01 | 100% | Login por e-mail, senha forte, hash, cookie `HttpOnly`/`SameSite`, bloqueio após 5 erros | — |
| Perfis e permissões | RF11, RN09, RN10, CA01 | 100% | Aluno, professor e secretaria, cada um vê só o seu; `403` registrado no log; cadastro pela aba Config. ou terminal | — |

## Monitoramento e painel

| Funcionalidade | Requisitos | % | Feito | Falta |
|---|---|---|---|---|
| Painel principal (dashboard) | RF03, CA02 | 70% | Cartões com total e contagem por nível de risco, barra de % de alto risco por curso, lista dos alunos críticos | Frequência média e nota média gerais; visão por turma |
| Filtros de alunos | RF05, CA05 | 70% | Busca por nome, filtro por curso e por nível de risco | Filtro por turma |
| Histórico individual do aluno | RF07, CA07 | 80% | Ficha com notas e frequência por semestre e histórico de predições | Gráfico da evolução de notas, frequência e risco |
| Gráficos de desempenho | RF09, CA08 | 25% | Só a barra de risco por curso | Gráficos por turma, por aluno, de frequência e de notas, com o tipo certo para cada dado |
| Aba Turmas | RF04, RF05 | 10% | Rota `GET /api/turmas` existe | A aba é só um aviso de "não implementado" |
| Alunos que mudaram de situação | RF02 | 0% | — | Listar quem mudou de nível de risco, do mais recente para o mais antigo |

## Cálculo de risco e predição

| Funcionalidade | Requisitos | % | Feito | Falta |
|---|---|---|---|---|
| Cálculo de risco por regras | RF08, RN06, CA03 | 60% | `calcular_risco()` com frequência, nota, reprovações, reclamações e distância; níveis baixo/médio/alto | Entrega de atividades; estatísticas (média, mediana, moda, variância, desvio padrão); análise do texto dos feedbacks |
| Frequência < 75% força risco alto | RN08 | 25% | Frequência baixa soma +2 pontos | Forçar "alto" independente da nota (hoje só dá "médio") |
| Alto risco só com histórico mínimo | RN07 | 0% | — | Exigir um mínimo de registros antes de classificar como "alto" |
| Pesos configuráveis | RF06, CA11 | 0% | Pesos fixos na lista `REGRAS` de `espiada/risco.py` | Guardar os pesos no banco, criar rota e tela para editar |
| Predição com LLM (Ollama) | RF16, RNF09, CA04 | 20% | Aba Predições, rota `POST /api/alunos/{matricula}/predicao` e histórico em `predicao_ia` (só com as regras) | Integrar a LLM do Ollama (≥ 7B) com o contexto do aluno |
| Recálculo das predições | RF10, RNF05, CA04 | 10% | Predição gerada à mão, um aluno por vez | Recalcular todos quando chegarem dados novos; 1000 alunos em até 5 min |
| Alteração manual de predição | RN14, RN15 | 20% | Colunas `alterada_por` e `justificativa` com `CHECK` exigindo justificativa | Rota e tela; só secretaria ou o professor da turma pode alterar |

## Relatórios, feedback e notificações

| Funcionalidade | Requisitos | % | Feito | Falta |
|---|---|---|---|---|
| Feedback do aluno | RF04, RN05, CA09 | 50% | Tabela `feedback`, rota `POST /api/alunos/{matricula}/feedback` (só o próprio aluno) e teste | Tela para o aluno enviar; seção "feedbacks dos alunos" para o professor |
| Relatórios exportáveis (PDF/CSV) | RF12, RF13, RF14, CA10 | 0% | A aba Relatórios é só um aviso | Exportar por aluno, por turma e por curso; relatório final de desempenho para o aluno |
| Notificação de alto risco | RN12, RN13, CA13 | 0% | — | Avisar a coordenação por WhatsApp ou Telegram, sem repetir o mesmo aluno em 24 h |
| Configurações da plataforma | RF15 | 30% | Aba Config. com cadastro de usuário | Critérios de risco, perfis de acesso, dados institucionais |

## Segurança, LGPD e qualidade

| Funcionalidade | Requisitos | % | Feito | Falta |
|---|---|---|---|---|
| Validação nos próprios campos | RN03, RN04, CA12 | 70% | `CHECK` no banco; formulário de cadastro valida e-mail e senha no campo | Validar os campos das telas novas (pesos, justificativa, feedback) |
| Logs e auditoria | RNF10, CA14 | 20% | Log no console de acesso negado e login errado | Registro persistente de requisições e alterações |
| Limite de requisições | RNF06 | 15% | Só no login (5 erros = 15 min de bloqueio) | Máximo de 10 chamadas da mesma função a cada 3 h |
| HTTPS / segurança de rede | RNF08, RNF13 | 10% | Cookie de sessão protegido | Servir por HTTPS/TLS; `SECRET_KEY` fixa em produção |
| LGPD | RNF11, RNF12, RNF14, RNF15, RN02 | 15% | Cada perfil só recebe os alunos que pode ver | Criptografar nome e matrícula no banco; anonimizar os dados agregados dos relatórios |
| Interface adaptável a dispositivos | RNF03, CA15 | 30% | Uma regra `@media` no painel | Ajustar o login e testar em celular e tablet |
| Escalabilidade | RNF04, CA15 | 0% | — | Teste com vários usuários ao mesmo tempo |
| Testes | Plano de teste | 40% | `tests/teste_banco.py` e `tests/teste_api.py` passam; modo debug ligado | Testes de segurança, com usuários reais, de carga, de dispositivos e de notificação |

## Próximos passos pelo cronograma

| Semana | Prazo | Foco | Situação |
|---|---|---|---|
| 05 | 22/10 | Regras de negócio, pesos configuráveis, níveis | Em andamento: faltam RN07, RN08 e RF06 |
| 06 | 29/10 | LLM do Ollama e tempo de recálculo | Não começou |
| 07 | 05/11 | Gráficos, filtros por turma, histórico com evolução | Parcial |
| 08 | 12/11 | Feedback na tela, notificações, logs de auditoria, teste de carga | Parcial (só a rota de feedback) |
