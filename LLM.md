# LLM no Espiada: como funciona, instalação e uso

Este guia explica a predição com LLM (Ollama): o que ela faz, como foi implementada, como instalar e como usar.
O resumo geral do projeto está no [`readme.md`](readme.md) e o andamento no [`roadmap.md`](roadmap.md).

## 1. Resumo

- A LLM é o **`qwen3:8b`** (8 bilhões de parâmetros) rodando **local** no Ollama. Nada vai para a nuvem.
- **Não é chat.** Ninguém digita nada para ela. O prompt é fixo, o conteúdo vem do banco e a resposta é um JSON com formato obrigatório (`nivel` e `comentario`).
- Ela **não decide sozinha**: opina sobre o nível de risco, mas o sistema limita o quanto ela pode se afastar das regras, e as **regras duras** têm a palavra final.
- **O sistema funciona sem ela.** Se o Ollama estiver fora do ar, a predição sai só com as regras e fica marcada como `origem = regras`.
- Cada predição vira uma **linha nova** em `predicao_ia`. O histórico nunca é sobrescrito.

## 2. Como uma predição é decidida

1. **Indicadores:** o resumo do aluno (frequência, nota, reprovações, distância, reclamações e número de registros) vem de `models/alunos.py`.
2. **Pontuação por regras** (`calcular_risco`): freq < 75 (+2), nota < 60 (+2), reprovação (+1), reclamação (+1), distância > 30 km (+1). 4 ou mais é alto, 2 ou mais é médio, senão baixo. Indicador sem dado não conta.
3. **A LLM opina** (`models/llm.py`): recebe o contexto anonimizado (seção 3) e devolve um nível e um comentário.
4. **Limite de afastamento:** a LLM só pode se afastar **1 nível** do nível das regras (`LLM_PASSO_MAXIMO`). Se as regras dizem "baixo", ela pode chegar no máximo a "médio".
5. **Regras duras** (valem acima da pontuação e da LLM):

| Situação | Resultado |
|---|---|
| Histórico suficiente e frequência < 75% | **alto**, qualquer que seja a nota ou a opinião da LLM |
| Histórico curto (menos de 8 registros) | no máximo **médio** |
| Histórico curto **e** frequência < 75% | **médio** (a regra do histórico vence) |
| Campo sem dado (`null`) | a regra não se aplica |

6. **Grava** uma linha em `predicao_ia` com o nível final, o comentário, a `origem` (`llm` ou `regras`), o `modelo` e os `detalhes` (fatores, ajustes, nível das regras e nível da LLM).

Por que esse desenho: o PDF do projeto exige que o sistema **explique por que apontou risco**. Por isso a pontuação e os fatores continuam sendo o núcleo explicável, a LLM é uma análise complementar, e tudo o que ela mudou fica registrado em `detalhes`.

## 3. O que a LLM recebe e devolve

**Recebe** (montado em `predicao.entrada_llm`), sem nome, matrícula, endereço ou qualquer identificador:

```json
{
  "periodo_atual": 4,
  "indicadores": {"frequencia_media": 91.7, "nota_media": 94.0, "reprovacoes": 0,
                  "distancia_ate_o_campus_km": 0.0, "registros_academicos": 20, "reclamacoes_no_feedback": 0},
  "por_semestre": [{"semestre": "2025.1", "nota_media": 94.4, "frequencia_media": 94.4, "reprovacoes": 0}, "..."],
  "feedback": [{"alvo": "curso", "avaliacao": 1, "comentario": "texto do aluno, até 300 caracteres"}],
  "pre_analise_regras": {"nivel": "baixo", "pontos": 0, "ajustes": [], "fatores_negativos": []}
}
```

Um contexto típico tem cerca de 220 tokens e o prompt fixo, cerca de 900 caracteres. Cabem folgados na janela de 4096 tokens.

**Devolve** (o Ollama obriga este formato; o sistema confere de novo em `llm._validar`):

```json
{"nivel": "baixo | medio | alto", "comentario": "até 40 palavras, citando os números"}
```

**Cuidados de segurança**

- **Anonimização:** o contexto não tem dado que identifique o aluno. `teste_llm.py` confere isso.
- **Texto do aluno é dado, não ordem:** o feedback entra dentro do JSON, truncado em 300 caracteres, e o prompt manda ignorar instruções escritas nele. Mesmo que a LLM obedecesse, ela só pode devolver um dos 3 níveis, não passa de 1 nível das regras, e as regras duras valem por cima.
- **Saída escapada:** a tela escapa o comentário da LLM antes de mostrá-lo, então um HTML escrito no feedback não executa.
- **Resposta inválida** (JSON quebrado, nível desconhecido, comentário que não é texto) vira erro `502` internamente, e a predição cai nas regras.

## 4. Quando a LLM roda

| Gatilho | O que acontece |
|---|---|
| Botão **Gerar predição** (aba Predições ou ficha do aluno) | Sempre chama a LLM e grava uma linha nova. Leva alguns segundos. |
| **Recálculo em lote** (comando ou rota, seção 6) | Percorre todos os alunos e **pula quem não mudou**. Roda em segundo plano. |

**Como o lote sabe quem mudou:** a cada análise o sistema guarda o `entrada_hash`, um resumo do contexto enviado mais o modelo e a versão do prompt. Se o hash de hoje for igual ao da última análise da LLM, o aluno é pulado. Mudam o hash: nota, frequência ou feedback novo, outro modelo (`OLLAMA_MODEL`) e edição do prompt (`PROMPT_VERSAO` em `llm.py`).

**Antes de começar o lote**, o sistema confere se o Ollama responde e se o modelo foi baixado. Se não, devolve `503` e não grava nada. Se a LLM falhar **3 vezes seguidas** no meio do lote, ele para.

**O que as telas mostram:** a **última predição guardada** de cada aluno (campo `risco_origem` diz se veio da `llm` ou das `regras`). Quem ainda não tem predição mostra o risco calculado pelas regras. Depois de gerar uma predição, o painel e a tabela atualizam sozinhos.

## 5. Instalação

### 5.1 Ollama e o modelo (na máquina que vai rodar a LLM)

1. Baixe e instale o Ollama: https://ollama.com/download (Windows, macOS e Linux). No Linux também serve `curl -fsSL https://ollama.com/install.sh | sh`.
2. Baixe o modelo (cerca de 5 GB, uma vez só):
   ```bash
   ollama pull qwen3:8b
   ```
3. Confira:
   ```bash
   ollama list
   ollama run qwen3:8b "Responda apenas: ok"
   ```

**Hardware:** o alvo é uma máquina com **8 GB de VRAM e 16 GB de RAM**. O modelo cabe, mas no limite. Feche outros programas que usem a placa de vídeo. Se a VRAM não bastar, o Ollama joga parte do modelo na RAM e fica mais lento. Para ver a divisão, rode `ollama ps` com o modelo carregado e olhe a coluna `PROCESSOR`.

### 5.2 Cliente Python

```bash
pip install "ollama>=0.5.1"
```

Acrescente também a linha `ollama>=0.5.1` ao `requirements.txt`. O pacote só é carregado na hora de chamar o Ollama, então o resto do sistema roda mesmo sem ele. O parâmetro `think` usado em `llm.py` exige uma versão recente do pacote.

### 5.3 Banco de dados

Nada a fazer: ao subir o servidor, `criar_banco()` acrescenta as colunas novas (`origem`, `modelo`, `entrada_hash`, `detalhes`) em bancos antigos. As predições antigas ficam com `origem = regras`.

### 5.4 Variáveis de ambiente (opcionais)

| Variável | Padrão | Para quê |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | endereço do Ollama |
| `OLLAMA_MODEL` | `qwen3:8b` | modelo usado |
| `OLLAMA_TIMEOUT` | `120` | segundos de espera por resposta (a 1ª chamada carrega o modelo e demora) |

Windows (PowerShell): `$env:OLLAMA_MODEL = "qwen3:8b"`. Linux e macOS: `export OLLAMA_MODEL=qwen3:8b`.

### 5.5 Ollama em outra máquina (opcional)

Útil quando o computador de desenvolvimento não tem placa de vídeo suficiente.

1. Na máquina com a placa, inicie o Ollama escutando na rede: variável `OLLAMA_HOST=0.0.0.0` antes de subir o servidor dele.
2. Na máquina do Espiada, aponte para ela: `OLLAMA_URL=http://IP_DA_MAQUINA:11434`.

O Ollama **não tem autenticação**: use só em rede confiável. Os dados enviados já são anonimizados, mas viajam sem criptografia.

## 6. Uso

### 6.1 Pela interface

- **Aba Predições** (professor e secretaria): escolha o aluno e clique em **Gerar predição**. A tela mostra o nível, os fatores, o comentário da LLM, o nível que as regras deram, o nível que a LLM deu e qualquer ajuste de regra dura.
- **Ficha do aluno** (Monitoramento → clicar no aluno): o mesmo botão, mais o histórico. Cada linha mostra se veio da LLM ou das regras, com o comentário embaixo.
- Se o Ollama estiver fora, a tela mostra o resultado das regras com o aviso do motivo.

### 6.2 Recálculo em lote

Pelo terminal (na pasta do projeto):

```bash
flask --app src/Espiada.py recalcular-predicoes            # pula quem não mudou
flask --app src/Espiada.py recalcular-predicoes --forcar   # reanalisa todos
```

Pela API (só secretaria), depois de entrar com `POST /api/login`:

```bash
curl -c cookie.txt -H "Content-Type: application/json" -X POST http://127.0.0.1:5000/api/login \
     -d '{"login": "secretaria@simpa.test", "senha": "Secretaria#2026"}'
curl -b cookie.txt -X POST "http://127.0.0.1:5000/api/predicoes/recalcular"      # 202, roda em segundo plano
curl -b cookie.txt http://127.0.0.1:5000/api/predicoes/recalculo                 # andamento
curl -b cookie.txt -X POST http://127.0.0.1:5000/api/alunos/AES0001/predicao    # um aluno só
```

O andamento traz `estado` (`rodando`, `concluido` ou `erro`), `total`, `feitos`, `puladas` e `falhas`. O estado fica em memória: reiniciar o servidor o zera, e o modo `debug` do Flask pode interromper o lote ao recarregar o código.

### 6.3 Receita para a demonstração

1. Na máquina de 8 GB: instale o Ollama, baixe o `qwen3:8b` e rode `recalcular-predicoes` uma vez.
2. Leve o `src/funcionaai.db` **já com as predições gravadas**. A demonstração lê o que está guardado e não depende da LLM.
3. Se for gerar predição ao vivo, faça um clique de aquecimento antes: a primeira chamada carrega o modelo e é a mais lenta.

Cada análise deve levar alguns segundos numa placa de 8 GB. Esse tempo é uma estimativa a **medir na máquina real**: o comando acima mostra o andamento. Para 1000 alunos, a meta de 5 minutos só cabe com as regras para todos e a LLM apenas em quem mudou.

## 7. Problemas comuns

| Mensagem | Causa | O que fazer |
|---|---|---|
| `pacote ollama não instalado (pip install ollama)` | falta o cliente Python | `pip install "ollama>=0.5.1"` |
| `Ollama indisponível em http://localhost:11434: ...` | Ollama não está rodando, ou `OLLAMA_URL` errada | abra o aplicativo do Ollama ou rode `ollama serve`; confira a URL |
| `modelo qwen3:8b não baixado no Ollama (rode: ollama pull qwen3:8b)` | falta baixar o modelo | `ollama pull qwen3:8b` |
| `a LLM respondeu fora do formato esperado` | resposta cortada ou inválida (aparece como aviso, a predição cai nas regras) | tente de novo; se repetir, aumente `num_predict` em `llm.OPCOES` |
| tudo muito lento | modelo não coube na VRAM | `ollama ps`: veja a divisão GPU/CPU; feche outros programas |
| `timeout` | a 1ª chamada carrega o modelo | aumente `OLLAMA_TIMEOUT` |
| `409` ao recalcular | já existe um lote rodando | espere terminar (`GET /api/predicoes/recalculo`) |
| `503` ao recalcular | Ollama fora ou modelo não baixado | veja as linhas acima; o lote nem começa |

## 8. Ajustes

| O quê | Onde | Padrão |
|---|---|---|
| Corte da frequência | `FREQ_CORTE` em `models/predicao.py` | 75 |
| Histórico mínimo para ser "alto" | `HISTORICO_MINIMO` em `models/predicao.py` | 8 registros (um semestre tem 5) |
| Quanto a LLM pode se afastar das regras | `LLM_PASSO_MAXIMO` em `models/predicao.py` | 1 nível (2 = sem limite) |
| Falhas seguidas que interrompem o lote | `FALHAS_SEGUIDAS_MAX` em `models/predicao.py` | 3 |
| Prompt, formato, temperatura, janela, `keep_alive` | `models/llm.py` | `temperature` 0, `seed` 42, `num_ctx` 4096, 30 min carregado |

**Ao editar o prompt, aumente `PROMPT_VERSAO`** em `llm.py`: assim o recálculo em lote reanalisa todo mundo com o prompt novo.

O histórico mínimo vale 8 por escolha provisória. No dataset, qualquer valor de 6 a 10 pega os mesmos 15 alunos do 1º semestre (5 registros cada); só 1 deles evadiu, e nenhum é "alto" pelas regras.

## 9. Limites e cuidados

- **Não validada ainda contra o gabarito.** Compare as predições com `desfechos_alunos` (evasão observada). Essa tabela serve para **avaliar**, nunca como entrada, assim como `indicadores_risco` (vazamento). Nas regras atuais, 9 das 20 evasões do dataset estão em alunos classificados como "baixo": é onde a LLM pode ajudar.
- **Determinismo:** `temperature` 0 e `seed` fixa dão o mesmo resultado para a mesma entrada, mas isso não é garantido entre versões do Ollama ou do modelo.
- **Privacidade:** com o Ollama local nenhum dado sai da máquina. Com `OLLAMA_URL` apontando para outra máquina, o contexto anonimizado trafega pela rede.
- **O dataset não tem "entrega de atividades"**, então essa informação não chega à LLM.
- **Ainda não existe:** notificação de alto risco, pesos configuráveis, limite de 10 chamadas a cada 3 h, alteração manual de predição, gatilho automático de recálculo ao chegar dado novo e botão de recálculo na tela. Estão no [`roadmap.md`](roadmap.md).

## 10. Arquivos desta integração

| Arquivo | O que faz |
|---|---|
| `src/models/llm.py` | cliente do Ollama: prompt, formato da resposta, validação, erros `503` e `502` |
| `src/models/predicao.py` | regras, regras duras, contexto anonimizado, hash, decisão final, recálculo em lote, histórico |
| `src/models/alunos.py` | `registros` no resumo do aluno e `comentarios()` do feedback |
| `src/models/banco.py` | migração das colunas novas em bancos antigos |
| `src/schema.sql` | colunas `origem`, `modelo`, `entrada_hash` e `detalhes` em `predicao_ia` |
| `src/controllers/alunos.py` | lista e ficha mostram a última predição; o `POST` chama regras + LLM |
| `src/controllers/predicoes.py` | recálculo em lote (rota, andamento e comando `recalcular-predicoes`) |
| `src/Espiada.py` | registra o novo controller |
| `src/views/interface.html` | comentário, origem e ajustes na tela; atualização do painel após gerar |
| `src/teste_llm.py` | testa tudo isso com um Ollama simulado (`python src/teste_llm.py`) |

`teste_banco.py` e `teste_api.py` também foram atualizados. Nenhum dos três testes chama um Ollama de verdade: passam com ou sem ele instalado.
