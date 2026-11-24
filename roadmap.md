# Roadmap — ESPIADA

## Base do sistema

| Funcionalidade | % | Feito | Falta |
|---|---|---|---|
| Banco de dados PostgreSQL | 95% | PostgreSQL 17 no Docker (`docker-compose.yml`, container `banco-espiada`, só aceita conexões do próprio computador); `app/schema.sql` com as tabelas do dataset e do sistema; matrícula = `codigo_academico`; `CHECK` de nota e frequência entre 0 e 100; pool de conexões; testes em esquemas próprios | Senha do banco por variável de ambiente fora do ambiente de desenvolvimento |
| Importação dos dados acadêmicos | 100% | `scripts/importar.py` importa o dataset sintético com `COPY` (5000 alunos em cerca de 6 s) e cria um login para cada aluno e docente; `scripts/ampliar_dados.py` ampliou o dataset de 120 para 5000 alunos e 450 docentes; nenhuma rota escreve nota ou frequência | — |
| API REST em JSON | 100% | Rotas por recurso em `/api/...`, erros padronizados `{"erro": ...}` | Novas rotas conforme as funcionalidades abaixo |
| Login e sessão | 100% | Login por e-mail, senha forte, hash, cookie `HttpOnly`/`SameSite`, bloqueio após 5 erros | — |
| Perfis e permissões | 100% | Aluno, professor e secretaria, cada um vê só o seu; `403` registrado no log; cadastro pelo terminal ou pela API | — |
| Sistema inteiro no Docker | 95% | `docker compose up -d --build` sobe aplicação (imagem própria, usuário sem root, Waitress) e PostgreSQL; a primeira subida importa o dataset e treina o modelo, e as seguintes não mexem nos dados; healthcheck, reinício automático e portas só no próprio computador; LLM pelo Ollama do computador, testada a partir do container; os 5 testes passam dentro do container | Testar o perfil opcional com o Ollama em container (imagem de cerca de 3,4 GB comprimidos) |

## Monitoramento e painel

| Funcionalidade | % | Feito | Falta |
|---|---|---|---|
| Painel principal (dashboard) | 85% | Cartões com total e contagem por nível de risco, nota e frequência (média, mediana, desvio padrão e quartis), lista dos alunos críticos, filtro por período que vale para o painel inteiro e seletor com 4 tipos de gráfico | Polimento de animações |
| Filtros de alunos | 100% | Busca por nome, filtro por período e por nível de risco no Monitoramento; filtro por período no Painel | — |
| Histórico individual do aluno | 100% | Ficha com notas e frequência por semestre e histórico de predições | - |
| Gráficos de desempenho | 100% | Barras, barras empilhadas, rosca e radar no Painel; histograma, boxplot e linha de evolução na aba Estatística; evolução de nota e frequência na ficha do aluno; tudo em CSS e SVG, sem biblioteca; aviso de que o 1º período não chega a risco alto por causa da regra de histórico mínimo | — |
| Aba Turmas | 80% | Tabela com as turmas (disciplina, docente, semestre, turno, modalidade, vagas), busca e filtro por semestre, a partir de `GET /api/turmas`, `/api/disciplinas` e `/api/docentes` | Alunos e risco por turma; professor ver só as próprias turmas |
| Alunos que mudaram de situação | 0% | — | Listar quem mudou de nível de risco, do mais recente para o mais antigo (impossível pois o dados não serão analisados e disponibilizados com o tempo)|

## Cálculo de risco e predição

| Funcionalidade | % | Feito | Falta |
|---|---|---|---|
| Cálculo de risco por regras | 65% | `calcular_risco()` com frequência, nota, reprovações, reclamações e distância; níveis baixo/médio/alto; o texto dos feedbacks é lido pela LLM | Entrega de atividades (o dataset não tem). As regras seguem como explicação dos fatores e reserva quando não há modelo treinado; a análise de 21/11/26 indicou distância sem efeito significativo, reprovação subvalorizada e 3 pontos com evasão próxima à de 4 |
| Modelo de risco treinado | 80% | Regressão logística sem biblioteca nova (`app/models/treino.py` e `modelo_risco.py`), com tendência de nota e frequência; comando `treinar-modelo`; 80% treino e 20% teste, validação cruzada, calibração e aprovação só com ganho de AUC no IC 95%; versão 1 em uso (AUC 0,789 no teste, contra 0,747 das regras); nível com porcentagem para professor e secretaria | Validar com dados reais; medir a tendência com desfecho por semestre (no dataset atual ela não trouxe ganho); confirmar os cortes de 15% e 30% com a coordenação |
| Frequência < 75% força risco alto | 100% | Regra dura em `limites_duros()`: força "alto" independente da nota e da LLM; testada em `teste_api.py` e `teste_llm.py` | — |
| Alto risco só com histórico mínimo | 90% | Teto "médio" com menos de 8 registros (`HISTORICO_MINIMO`), pois pode ser um aluno sem nota ou matriculado recentemente; vence a regra da frequência quando as duas valem | Confirmar o valor do mínimo (no dataset, qualquer valor de 6 a 10 pega os mesmos 625 alunos do 1º período) |
| Pesos configuráveis | 0% | Pesos fixos na lista `REGRAS` de `app/models/predicao.py` | Guardar os pesos no banco, criar rota e tela para editar |
| Predição com LLM (Ollama) | 85% | `qwen3:4b` local via `app/models/llm.py`, usado em testes locais: contexto sem nome nem matrícula, saída em JSON validada, limite de 1 nível sobre as regras, fallback para as regras se o Ollama cair, origem/modelo/comentário no histórico e na tela; explicação na seção "Como o risco é calculado" do `readme.md`; `testes/teste_llm.py` com Ollama simulado | Validar com o Ollama de verdade; tratar os dados enviados de acordo com a LGPD; medir o tempo por aluno e ajustar o prompt com o gabarito (`desfechos_alunos`) |
| Recálculo das predições | 80% | Comando `recalcular-predicoes`, `POST /api/predicoes/recalcular` (segundo plano, só secretaria) e botão na aba Config. com o andamento; pula quem não mudou (hash da entrada) e para se a LLM falhar 3 vezes seguidas | Gatilho automático quando chegarem dados novos (hoje o `importar.py` não importa de novo); medir com a LLM real a meta de 1000 alunos em até 5 min (com a LLM simulada, os 5000 alunos levam cerca de 30 a 40 s) |
| Alteração manual de predição | 20% | Colunas `alterada_por` e `justificativa` com `CHECK` exigindo justificativa | Rota e tela; só secretaria ou o professor da turma pode alterar |

## Estatística

Os professores pediram mais estatística no sistema. A aba **Estatística** (professor vê as próprias turmas; secretaria vê tudo) e a aba Avaliação reúnem o que está abaixo. Tudo sai das tabelas que já existem (`registros_academicos`, `perfis_socioeconomicos`, `bolsas_alunos` e `desfechos_alunos`), sem dado novo. As escolhas de cada cálculo estão na seção "Estatística" do `readme.md`.

| Funcionalidade | % | Feito | Falta |
|---|---|---|---|
| Estatística descritiva de notas e frequência | 100% | Média, mediana, moda, desvio padrão, mínimo, máximo, quartis e valores atípicos, gerais e filtrados por período, semestre, disciplina e turma; cartões no Painel | — |
| Distribuições (histograma e boxplot) | 100% | Histograma de notas e de frequência em faixas de 5 pontos; boxplot por período e por disciplina, em SVG | — |
| Aprovação e reprovação por disciplina | 100% | Taxa de aprovação, de reprovação por nota e por frequência, com IC 95% de Wilson, por disciplina, turma e semestre; ranking das disciplinas e das turmas que mais reprovam | — |
| Evolução ao longo dos semestres | 100% | Gráfico de linha da média por semestre do curso, de cada grupo de ingresso (filtro por período) e do aluno (na ficha), com a inclinação da tendência por regressão linear; o semestre em curso aparece, mas fica fora da tendência porque a nota ainda é parcial | — |
| Fatores ligados à evasão | 100% | Taxa de evasão por grupo (trabalha, bolsista, distância, turno, internet, escola pública e os critérios das regras) com IC 95%, razão de chances, qui-quadrado, V de Cramér e correção de Holm; correlações de Pearson e Spearman; serve de base para calibrar os pesos das regras | — |
| Comparação entre grupos | 100% | Diferença de nota e de frequência entre grupos (trabalha, bolsista, escola pública, distância e turno), com IC 95%, teste t de Welch, Mann-Whitney, d de Cohen e correção de Holm | — |
| Avaliação do modelo de risco | 95% | Aba Avaliação (só secretaria) e `GET /api/avaliacao`, com `app/models/avaliacao.py`: evasão real por nível, matriz de confusão com dois cortes (médio ou alto; só alto), acurácia, precisão, revocação, especificidade, F1, AUC do nível final e da pontuação, curva ROC e intervalos de confiança de 95% (Wilson e DeLong); modelo treinado x regras nos 1000 alunos de teste, com calibração; avaliação por período e por turma só nos alunos de teste, sem AUC em grupo com menos de 10 evasões; LLM x regras nos mesmos alunos, com teste pareado de McNemar; testada em `testes/teste_api.py`, `testes/teste_modelo.py` e `testes/teste_estatistica.py` | Rodar a comparação com o Ollama de verdade nos 5000 alunos: o teste está pronto, mas só considera predições feitas sem modelo treinado em uso |
| Exportar as estatísticas | 100% | CSV de cada tabela (descritiva, distribuição, aprovação, evolução, fatores, correlações e comparações), respeitando filtros e perfil, com separador e decimal do Excel em português | — |

## Relatórios, feedback e notificações

| Funcionalidade | % | Feito | Falta |
|---|---|---|---|
| Feedback do aluno | 100% | Tabela `feedback`, rotas `POST` e `GET /api/alunos/{matricula}/feedback` (enviar só o próprio aluno) e teste; formulário na tela Meu desempenho grava pela API e lista os feedbacks já enviados; professor e secretaria veem os feedbacks na ficha do aluno | — |
| Relatórios exportáveis (PDF/CSV) | 0% | A aba Relatórios é só um aviso | Exportar por aluno, por turma e por curso; relatório final de desempenho para o aluno |
| Notificação de alto risco | 0% | — | Avisar a coordenação por WhatsApp ou Telegram, sem repetir o mesmo aluno em 24 h |
| Configurações da plataforma | 50% | Aba Config. com o cadastro de usuário e o recálculo em lote das predições | Critérios de risco, perfis de acesso, dados institucionais |

## Segurança, LGPD e qualidade

| Funcionalidade | % | Feito | Falta |
|---|---|---|---|
| Validação nos próprios campos | 75% | `CHECK` no banco; formulário de cadastro valida e-mail e senha no campo; feedback exige a avaliação | Validar os campos das telas novas (pesos, justificativa) |
| Logs e auditoria | 20% | Log no console de acesso negado e login errado | Registro persistente de requisições e alterações |
| Limite de requisições | 15% | Só no login (5 erros = 15 min de bloqueio) | Máximo de 10 chamadas da mesma função a cada 3 h |
| HTTPS / segurança de rede | 20% | Cookie de sessão protegido; `SECRET_KEY` fixa pelo `.env`; no Docker, sem modo debug e com portas só no próprio computador | Servir por HTTPS/TLS |
| LGPD | 40% | Cada perfil só recebe os alunos que pode ver; a LLM roda local e não recebe nome nem matrícula, mas os dados enviados a ela não passaram por tratamento de acordo com a LGPD; página `sobre.html` com Termos de Uso, Política de Privacidade, Cookies e Contato; link para a LGPD no rodapé de todas as telas; estatísticas e CSV só com dados agregados, sem nome nem matrícula, e análise socioeconômica só para a secretaria | Tratar os dados enviados à LLM de acordo com a LGPD; definir um tamanho mínimo de grupo nas estatísticas; preencher os placeholders (CNPJ, encarregado, prazo de guarda); criptografar nome e matrícula no banco; anonimizar os dados agregados dos relatórios |
| Interface adaptável a dispositivos | 30% | Uma regra `@media` no painel | Ajustar o login e testar em celular e tablet |
| Escalabilidade | 30% | Testado com 5000 alunos: importação em cerca de 6 s, lista do painel em cerca de 1 s e recálculo em lote com a LLM simulada em cerca de 30 a 40 s; PostgreSQL com pool de conexões | Teste com vários usuários ao mesmo tempo; recálculo com a LLM real |
| Testes | 45% | `testes/teste_banco.py`, `teste_api.py`, `teste_llm.py`, `teste_modelo.py` e `teste_estatistica.py` passam no PostgreSQL com os 5000 alunos, cada um num esquema próprio; modo debug ligado | Testes de segurança, com usuários reais, de carga, de dispositivos e de notificação |

