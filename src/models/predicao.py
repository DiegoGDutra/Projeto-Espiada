"""Risco de evasão: regras do cálculo, opinião da LLM e histórico de predições (tabela predicao_ia).

Ordem de uma predição: pontuação por regras -> a LLM (Ollama) opina, sem se afastar muito do nível das regras
-> as regras duras têm a palavra final. Sem LLM disponível vale o nível das regras e a predição fica marcada
com origem 'regras'. O funcionamento completo está no readme.md (seção "Como o risco é calculado").
"""
import hashlib
import json

from models import alunos, llm
from models.banco import ErroModelo, consultar, transacao

NIVEIS = ("baixo", "medio", "alto")
ROTULO = {"baixo": "baixo", "medio": "médio", "alto": "alto"}

FREQ_CORTE = 75          # frequência média abaixo disso força o risco "alto" (regra dura)
HISTORICO_MINIMO = 8     # registros acadêmicos mínimos para o aluno poder ser "alto" (um semestre tem 5)
LLM_PASSO_MAXIMO = 1     # quantos níveis a LLM pode se afastar do nível das regras (2 = sem limite)
FALHAS_SEGUIDAS_MAX = 3  # no recálculo em lote, a LLM falhar tantas vezes seguidas interrompe tudo

# pesos fixos (os do readme); ainda não são configuráveis
REGRAS = [
    ("freq", lambda v: v < FREQ_CORTE, 2, f"Frequência abaixo de {FREQ_CORTE}%"),
    ("nota", lambda v: v < 60, 2, "Nota média abaixo de 60"),
    ("reprovacoes", lambda v: v > 0, 1, "Reprovações no histórico"),
    ("reclamacoes", lambda v: v > 0, 1, "Reclamações no feedback"),
    ("distancia", lambda v: v > 30, 1, "Mora a mais de 30 km do campus"),
]


# ---------- regras ----------

def _limitar(nivel, piso, teto):
    """Mantém o nível entre o piso e o teto."""
    return NIVEIS[min(max(NIVEIS.index(nivel), NIVEIS.index(piso)), NIVEIS.index(teto))]


def limites_duros(aluno):
    """Piso e teto das regras duras, que valem acima da pontuação e da LLM.
    Histórico curto: no máximo "médio" (pouco dado para cravar "alto"). Frequência baixa: no mínimo "alto", ou
    "médio" se o histórico for curto (a regra do histórico vence). Campo sem dado não aplica a regra."""
    historico_curto = aluno.get("registros") is not None and aluno["registros"] < HISTORICO_MINIMO
    freq_baixa = aluno.get("freq") is not None and aluno["freq"] < FREQ_CORTE
    teto = "medio" if historico_curto else "alto"
    return (teto if freq_baixa else "baixo"), teto


def aplicar_regras_duras(aluno, nivel):
    """Devolve (nível final, frases que explicam o ajuste; lista vazia se não houve)."""
    piso, teto = limites_duros(aluno)
    final = _limitar(nivel, piso, teto)
    if final == nivel:
        return final, []
    if NIVEIS.index(final) > NIVEIS.index(nivel):
        return final, [f"Frequência abaixo de {FREQ_CORTE}%: risco no mínimo {ROTULO[final]}"]
    return final, [f"Menos de {HISTORICO_MINIMO} registros no histórico: risco limitado a {ROTULO[final]}"]


def calcular_risco(aluno):
    score, fatores = 0, []
    for campo, ruim, peso, descricao in REGRAS:
        if aluno[campo] is None:
            continue  # sem dado, não conta nem a favor nem contra
        negativo = ruim(aluno[campo])
        score += peso * negativo
        fatores.append({"descricao": descricao, "negativo": negativo})
    pontuacao = "alto" if score >= 4 else "medio" if score >= 2 else "baixo"
    risco, ajustes = aplicar_regras_duras(aluno, pontuacao)
    return {"risco": risco, "score": score, "fatores": fatores, "ajustes": ajustes}


# ---------- LLM ----------

def _por_semestre(matricula):
    """Nota média, frequência média e reprovações de cada semestre: a tendência que a LLM enxerga."""
    semestres = {}
    for d in alunos.disciplinas(matricula):
        s = semestres.setdefault(d["semestre"], {"notas": [], "freqs": [], "reprovacoes": 0})
        nota = d["nota_final"] if d["nota_final"] is not None else d["nota_parcial"]
        if nota is not None:
            s["notas"].append(nota)
        if d["frequencia_percentual"] is not None:
            s["freqs"].append(d["frequencia_percentual"])
        s["reprovacoes"] += d["situacao"].startswith("REPROVADO")

    def media(valores):
        return round(sum(valores) / len(valores), 1) if valores else None

    return [{"semestre": sem, "nota_media": media(s["notas"]), "frequencia_media": media(s["freqs"]),
             "reprovacoes": s["reprovacoes"]} for sem, s in sorted(semestres.items())]


def entrada_llm(aluno, base):
    """Contexto enviado à LLM. Anonimizado: sem nome, matrícula, endereço ou outro identificador; só indicadores,
    resumo por semestre, comentários do aluno (texto livre, tratado como dado) e a pré-análise das regras."""
    return {
        "periodo_atual": aluno["periodo"],
        "indicadores": {
            "frequencia_media": aluno["freq"], "nota_media": aluno["nota"], "reprovacoes": aluno["reprovacoes"],
            "distancia_ate_o_campus_km": aluno["distancia"], "registros_academicos": aluno["registros"],
            "reclamacoes_no_feedback": aluno["reclamacoes"],
        },
        "por_semestre": _por_semestre(aluno["matricula"]),
        "feedback": [{"alvo": f["alvo"], "avaliacao": f["avaliacao"], "comentario": (f["comentario"] or "")[:300]}
                     for f in alunos.comentarios(aluno["matricula"])],
        "pre_analise_regras": {
            "nivel": base["risco"], "pontos": base["score"], "ajustes": base["ajustes"],
            "fatores_negativos": [f["descricao"] for f in base["fatores"] if f["negativo"]],
        },
    }


def hash_entrada(contexto):
    """Resumo da entrada, com modelo e versão do prompt. Igual ao da última predição = nada mudou."""
    bruto = json.dumps({"modelo": llm.MODELO, "prompt": llm.PROMPT_VERSAO, "contexto": contexto},
                       sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _decidir(aluno, base, nivel_llm):
    """Nível final: a LLM opina, mas só se afasta LLM_PASSO_MAXIMO níveis do das regras; depois as regras duras
    são aplicadas de novo. Devolve (nível, ajustes novos)."""
    ancora = NIVEIS.index(base["risco"])
    indice = min(max(NIVEIS.index(nivel_llm), ancora - LLM_PASSO_MAXIMO), ancora + LLM_PASSO_MAXIMO)
    return aplicar_regras_duras(aluno, NIVEIS[indice])


def analisar(matricula, aluno, forcar=True):
    """Gera e guarda a predição do aluno (regras + LLM). aluno: o resumo de alunos.buscar().
    Se a LLM falhar, guarda a das regras e devolve o motivo em "aviso". forcar=False reaproveita a última predição
    da LLM quando a entrada não mudou (é o que o recálculo em lote usa); o botão de gerar predição força."""
    base = calcular_risco(aluno)
    contexto = entrada_llm(aluno, base)
    entrada = hash_entrada(contexto)
    anterior = ultima(matricula)
    if not forcar and anterior and anterior["origem"] == "llm" and anterior["entrada_hash"] == entrada:
        return _como_resultado(anterior) | {"reaproveitada": True}
    resultado = {"risco": base["risco"], "score": base["score"], "fatores": base["fatores"],
                 "ajustes": base["ajustes"], "comentario": None, "origem": "regras", "modelo": None,
                 "nivel_regras": base["risco"], "nivel_llm": None}
    try:
        opiniao = llm.avaliar(contexto)
    except ErroModelo as e:
        resultado["aviso"] = e.mensagem
    else:
        risco, ajustes = _decidir(aluno, base, opiniao["nivel"])
        resultado.update(risco=risco, ajustes=list(dict.fromkeys(base["ajustes"] + ajustes)),
                         comentario=opiniao["comentario"], origem="llm", modelo=opiniao["modelo"],
                         nivel_llm=opiniao["nivel"])
    salvar(matricula, resultado, entrada if resultado["origem"] == "llm" else None)
    return resultado


def recalcular_todos(forcar=False, ao_progredir=None):
    """Analisa todos os alunos. Quem não mudou desde a última análise da LLM é pulado (a não ser com forcar).
    Confere o Ollama antes de começar (503 se estiver fora) e para se a LLM falhar várias vezes seguidas.
    ao_progredir(resumo) é chamada a cada aluno, para mostrar o andamento."""
    llm.verificar()
    todos = alunos.listar({"perfil": "secretaria"})
    resumo = {"total": len(todos), "feitos": 0, "puladas": 0, "falhas": 0, "interrompido": False}
    seguidas = 0
    for aluno in todos:
        resultado = analisar(aluno["matricula"], aluno, forcar=forcar)
        if resultado.get("reaproveitada"):
            resumo["puladas"] += 1
        elif resultado.get("aviso"):
            resumo["falhas"] += 1
            seguidas += 1
        else:
            resumo["feitos"] += 1
            seguidas = 0
        if ao_progredir:
            ao_progredir(dict(resumo))
        if seguidas >= FALHAS_SEGUIDAS_MAX:
            resumo["interrompido"] = True
            break
    return resumo


# ---------- histórico ----------

def salvar(matricula, resultado, entrada_hash=None):
    """Cada cálculo vira uma linha nova no histórico (nada é sobrescrito)."""
    detalhes = json.dumps({c: resultado.get(c) for c in ("fatores", "ajustes", "nivel_regras", "nivel_llm")},
                          ensure_ascii=False)
    with transacao() as con:
        con.execute("""
            INSERT INTO predicao_ia (matricula_curso_id, nivel_risco, score, comentario_predicao,
                                     origem, modelo, entrada_hash, detalhes)
            SELECT matricula_curso_id, ?, ?, ?, ?, ?, ?, ? FROM matriculas_curso JOIN alunos USING (aluno_id)
             WHERE codigo_academico = ?""",
                    (resultado["risco"], resultado["score"], resultado.get("comentario"),
                     resultado.get("origem", "regras"), resultado.get("modelo"), entrada_hash, detalhes, matricula))


def _linhas(matricula, limite=-1):
    linhas = consultar("""
        SELECT p.predicao_id AS id, p.criado_em, p.nivel_risco AS risco, p.score, p.comentario_predicao,
               p.alterada_por, p.justificativa, p.origem, p.modelo, p.entrada_hash, p.detalhes
          FROM predicao_ia p JOIN matriculas_curso USING (matricula_curso_id) JOIN alunos a USING (aluno_id)
         WHERE a.codigo_academico = ? ORDER BY p.predicao_id DESC LIMIT ?""", matricula, limite)
    for linha in linhas:
        linha["detalhes"] = json.loads(linha["detalhes"]) if linha["detalhes"] else None
    return linhas


def historico(matricula):
    return [{c: v for c, v in linha.items() if c != "entrada_hash"} for linha in _linhas(matricula)]


def ultima(matricula):
    """Última predição do aluno (com o hash da entrada) ou None."""
    achadas = _linhas(matricula, 1)
    return achadas[0] if achadas else None


def ultimas_por_aluno():
    """Última predição de cada aluno que já tem alguma: {matricula: {risco, origem, criado_em}}. Uma consulta só."""
    linhas = consultar("""
        SELECT a.codigo_academico AS matricula, p.nivel_risco AS risco, p.origem, p.criado_em
          FROM predicao_ia p JOIN matriculas_curso USING (matricula_curso_id) JOIN alunos a USING (aluno_id)
         WHERE p.predicao_id = (SELECT max(predicao_id) FROM predicao_ia
                                 WHERE matricula_curso_id = p.matricula_curso_id)""")
    return {linha["matricula"]: linha for linha in linhas}


def risco_atual(aluno, ultima_predicao):
    """Risco que as telas mostram: o da última predição guardada; sem nenhuma, o calculado pelas regras."""
    if ultima_predicao:
        return {"risco": ultima_predicao["risco"], "risco_origem": ultima_predicao["origem"]}
    return {"risco": calcular_risco(aluno)["risco"], "risco_origem": "regras"}


def _como_resultado(linha):
    detalhes = linha["detalhes"] or {}
    return {"risco": linha["risco"], "score": linha["score"], "fatores": detalhes.get("fatores", []),
            "ajustes": detalhes.get("ajustes", []), "comentario": linha["comentario_predicao"],
            "origem": linha["origem"], "modelo": linha["modelo"], "nivel_regras": detalhes.get("nivel_regras"),
            "nivel_llm": detalhes.get("nivel_llm")}
