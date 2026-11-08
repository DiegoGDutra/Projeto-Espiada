"""Risco de evasão: as regras do cálculo, a avaliação da LLM (Ollama) e o histórico (tabela predicao_ia)."""
import json
import os
import urllib.request

from models.banco import consultar, transacao

# LLM local no Ollama (`ollama serve` + `ollama pull qwen3:4b`): os dados dos alunos não saem da máquina.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODELO = os.environ.get("OLLAMA_MODELO", "qwen3:4b")
OLLAMA_TIMEOUT = 120  # segundos; o primeiro pedido carrega o modelo na memória

# pesos fixos (os do readme)
REGRAS = [
    ("freq", lambda v: v < 75, 2, "Frequência abaixo de 75%"),
    ("nota", lambda v: v < 60, 2, "Nota média abaixo de 60"),
    ("reprovacoes", lambda v: v > 0, 1, "Reprovações no histórico"),
    ("reclamacoes", lambda v: v > 0, 1, "Reclamações no feedback"),
    ("distancia", lambda v: v > 30, 1, "Mora a mais de 30 km do campus"),
]


def calcular_risco(aluno):
    score, fatores = 0, []
    for campo, ruim, peso, descricao in REGRAS:
        if aluno[campo] is None:
            continue  # sem dado, não conta nem a favor nem contra
        negativo = ruim(aluno[campo])
        score += peso * negativo
        fatores.append({"descricao": descricao, "negativo": negativo})
    risco = "alto" if score >= 4 else "medio" if score >= 2 else "baixo"
    return {"risco": risco, "score": score, "fatores": fatores}


INSTRUCOES = """Você avalia o risco de evasão de um aluno de graduação. Recebe os indicadores, as disciplinas \
(notas de 0 a 100, frequência em %), os comentários do aluno e a classificação feita por regras fixas. \
Considere a tendência entre semestres, disciplinas em curso, reprovações repetidas e o tom dos comentários. \
Pode concordar ou discordar das regras. Responda em português, comentário com no máximo 3 frases, \
citando os fatores que pesaram. Responda só com um JSON {"risco": "baixo" | "medio" | "alto", "comentario": "..."}."""

FORMATO = {"type": "object", "required": ["risco", "comentario"], "properties": {
    "risco": {"type": "string", "enum": ["baixo", "medio", "alto"]}, "comentario": {"type": "string"}}}


def contexto(aluno, disciplinas, comentarios, regras):
    """Texto que vai para a LLM. Sem nome nem endereço: só a matrícula e os indicadores (LGPD)."""
    linhas = [f"Matrícula {aluno['matricula']}, {aluno['curso']}, {aluno['periodo']}º período, situação {aluno['situacao']}.",
              f"Frequência média {aluno['freq']}%, nota média {aluno['nota']}, {aluno['reprovacoes']} reprovações, "
              f"distância do campus {aluno['distancia']} km.", "", "Disciplinas (semestre | disciplina | tentativa | "
              "N1 | N2 | projeto | nota | frequência | situação):"]
    linhas += [f"{d['semestre']} | {d['disciplina']} | {d['tentativa']} | {d['nota_n1']} | {d['nota_n2']} | "
               f"{d['nota_projeto']} | {d['nota_final'] if d['nota_final'] is not None else d['nota_parcial']} | "
               f"{d['frequencia_percentual']} | {d['situacao']}" for d in disciplinas] or ["nenhuma"]
    linhas += ["", "Comentários do aluno (alvo, avaliação 1 a 5, texto):"]
    linhas += [f"{c['alvo']}, {c['avaliacao_curso']}, {c['comentarios'] or ''}" for c in comentarios] or ["nenhum"]
    linhas += ["", f"Regras fixas: risco {regras['risco']} (pontuação {regras['score']}). Fatores: "
               + "; ".join(f"{f['descricao']}: {'sim' if f['negativo'] else 'não'}" for f in regras["fatores"])]
    return "\n".join(linhas)


def avaliar_llm(texto):
    """Pede a classificação para a LLM. Devolve {risco, comentario}; erro de rede ou resposta fora do formato
    vira exceção (quem chama decide cair só nas regras)."""
    corpo = {"model": OLLAMA_MODELO, "stream": False, "format": FORMATO, "think": False, "keep_alive": "30m", "options": {"temperature": 0},
             # tudo numa mensagem só: com papel "system" alguns modelos ignoram o format e respondem texto solto
             "messages": [{"role": "user", "content": INSTRUCOES + "\n\n" + texto}]}
    pedido = urllib.request.Request(OLLAMA_HOST.rstrip("/") + "/api/chat", json.dumps(corpo).encode(),
                                    {"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=OLLAMA_TIMEOUT) as r:
        resposta = json.loads(json.loads(r.read())["message"]["content"])
    if resposta.get("risco") not in ("baixo", "medio", "alto"):
        raise ValueError(f"risco inválido na resposta da LLM: {resposta.get('risco')!r}")
    return {"risco": resposta["risco"], "comentario": str(resposta.get("comentario", "")).strip()}


def prever(aluno, disciplinas, comentarios, usar_llm=True):
    """Regras + LLM. risco final é o da LLM; sem LLM (pedido assim, ou fora do ar) fica o das regras.
    Se a LLM foi pedida e não respondeu, vem um aviso."""
    regras = calcular_risco(aluno)
    resultado = regras | {"risco_regras": regras["risco"], "risco_ia": None, "comentario": None,
                          "modelo": None, "aviso": None}
    if not usar_llm:
        return resultado
    try:
        ia = avaliar_llm(contexto(aluno, disciplinas, comentarios, regras))
    except Exception as e:  # LLM é complemento: a predição por regras sai de qualquer jeito
        resultado["aviso"] = f"LLM indisponível ({type(e).__name__}: {e}); risco calculado só pelas regras"
        return resultado
    return resultado | {"risco": ia["risco"], "risco_ia": ia["risco"], "comentario": ia["comentario"],
                        "modelo": OLLAMA_MODELO}


def salvar(matricula, resultado):
    """Cada cálculo vira uma linha nova no histórico (nada é sobrescrito). score é sempre o das regras."""
    with transacao() as con:
        con.execute("""
            INSERT INTO predicao_ia (matricula_curso_id, nivel_risco, score, comentario_predicao)
            SELECT matricula_curso_id, ?, ?, ? FROM matriculas_curso JOIN alunos USING (aluno_id)
             WHERE codigo_academico = ?""",
            (resultado["risco"], resultado["score"], resultado.get("comentario"), matricula))


def historico(matricula):
    return consultar("""
        SELECT p.predicao_id AS id, p.criado_em, p.nivel_risco AS risco, p.score, p.comentario_predicao,
               p.alterada_por, p.justificativa
          FROM predicao_ia p JOIN matriculas_curso USING (matricula_curso_id) JOIN alunos a USING (aluno_id)
         WHERE a.codigo_academico = ? ORDER BY p.predicao_id DESC""", matricula)
