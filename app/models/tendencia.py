"""Tendência de nota e frequência: prevê a média do próximo semestre de cada aluno e de cada período (turma).

Como o acerto é provado: 20% dos alunos ficam de fora do treino e, deles, o último semestre concluído fica escondido
(é o gabarito). O modelo aprende só com os outros 80%, prevê o semestre escondido a partir dos anteriores e só depois
a previsão é comparada com o que aconteceu. A referência é repetir a média do semestre anterior: o modelo só é usado
se errar menos que ela em todo o intervalo de confiança de 95%. Nunca lê indicadores_risco nem desfechos_alunos.
O passo a passo está no readme.md, seção "Tendência de nota e frequência".
"""
import functools
import random

from models import modelo_risco, treino
from models.banco import consultar

ALVOS = ("nota", "frequencia")
VARIAVEIS = ("nota_ultimo", "nota_media", "nota_inclinacao", "freq_ultimo", "freq_media", "freq_inclinacao",
             "reprovacoes_ultimo", "semestres")
REGULARIZACAO = 1.0  # penalidade L2 (ridge), a mesma ideia do modelo de risco
LIMIAR = 2.0         # mudança de até 2 pontos conta como "estável" na direção da tendência
PERTO = 5.0          # "acertou de perto": erro de até 5 pontos
REAMOSTRAGENS = 500


def semestre_rotulo(ordem):
    """ano * 2 + semestre (a ordem usada no banco) de volta para "AAAA.S"."""
    ano = (ordem - 1) // 2
    return f"{ano}.{ordem - ano * 2}"


def _historicos(matriculas=None):
    """{matricula: (periodo, [semestres concluídos em ordem], ordem do semestre em curso ou None)}."""
    saida = {}
    for l in consultar(modelo_risco.POR_SEMESTRE, matriculas, matriculas):
        periodo, feitos, _ = saida.setdefault(l["matricula"], (l["periodo"], [], None))
        if l["nota_atual"] is not None:  # semestre em curso: nota parcial não se compara com a final
            saida[l["matricula"]] = (periodo, feitos, l["semestre"])
        elif l["qtd_nota"] and l["qtd_freq"]:
            feitos.append({"ordem": l["semestre"], "nota": l["soma_nota"] / l["qtd_nota"],
                           "frequencia": l["soma_freq"] / l["qtd_freq"], "reprovacoes": l["reprovadas"]})
    return saida


def calcular_variaveis(feitos):
    """Valores na ordem de VARIAVEIS a partir dos semestres concluídos (pelo menos um)."""
    ordens = [s["ordem"] for s in feitos]
    notas, freqs = [s["nota"] for s in feitos], [s["frequencia"] for s in feitos]
    return [notas[-1], sum(notas) / len(notas), modelo_risco._inclinacao(ordens, notas),
            freqs[-1], sum(freqs) / len(freqs), modelo_risco._inclinacao(ordens, freqs),
            float(feitos[-1]["reprovacoes"]), float(len(feitos))]


def ajustar(valores, real):
    """Regressão linear com regularização (ridge), resolvida de uma vez pelas equações normais."""
    colunas = list(zip(*valores))
    medias = [sum(c) / len(c) for c in colunas]
    desvios = [(sum((v - m) ** 2 for v in c) / len(c)) ** 0.5 or 1.0 for c, m in zip(colunas, medias)]
    linhas = [[1.0] + [(v - m) / d for v, m, d in zip(x, medias, desvios)] for x in valores]
    p = len(linhas[0])
    xtx = [[sum(l[i] * l[j] for l in linhas) + (REGULARIZACAO if i == j and i else 0.0) for j in range(p)] for i in range(p)]
    xty = [sum(l[i] * y for l, y in zip(linhas, real)) for i in range(p)]
    b = treino._resolver(xtx, xty)
    return {"intercepto": b[0], "coeficientes": b[1:], "medias": medias, "desvios": desvios}


def prever_valor(pesos, valores):
    z = [(v - m) / d for v, m, d in zip(valores, pesos["medias"], pesos["desvios"])]
    return max(0.0, min(100.0, pesos["intercepto"] + sum(c * v for c, v in zip(pesos["coeficientes"], z))))


def direcao(antes, depois):
    return "sobe" if depois - antes > LIMIAR else "desce" if antes - depois > LIMIAR else "estável"


def dividir(matriculas):
    """(treino, teste) por aluno, sempre a mesma divisão. Não usa o desfecho: aqui ele não importa."""
    ordem = sorted(matriculas)
    random.Random(treino.SEMENTE).shuffle(ordem)
    corte = round(len(ordem) * treino.PROPORCAO_TESTE)
    return set(ordem[corte:]), set(ordem[:corte])


def _ganho(erros_ref, erros_modelo):
    """Quanto o modelo erra a menos que a referência (em pontos), com IC de 95% por bootstrap pareado."""
    rnd, n, difs = random.Random(treino.SEMENTE), len(erros_ref), []
    for _ in range(REAMOSTRAGENS):
        amostra = [rnd.randrange(n) for _ in range(n)]
        difs.append(sum(erros_ref[i] - erros_modelo[i] for i in amostra) / n)
    difs.sort()
    return {"valor": round(sum(a - b for a, b in zip(erros_ref, erros_modelo)) / n, 3),
            "ic": [round(difs[int(0.025 * REAMOSTRAGENS)], 3), round(difs[int(0.975 * REAMOSTRAGENS)], 3)]}


def _medidas(previsto, real, anterior):
    erros = [abs(p - r) for p, r in zip(previsto, real)]
    n = len(real)
    return {"erro_medio": round(sum(erros) / n, 2), "raiz_erro_quadratico": round((sum(e * e for e in erros) / n) ** 0.5, 2),
            "perto": round(sum(e <= PERTO for e in erros) / n, 4),
            "direcao": round(sum(direcao(a, p) == direcao(a, r) for a, p, r in zip(anterior, previsto, real)) / n, 4)}


@functools.cache  # ponytail: as notas só mudam pelo importador, antes do servidor subir; com dados vivos, limpar o cache
def avaliar():
    """Treina nos 80%, prevê o semestre escondido dos 20% e compara com o gabarito. Um modelo por alvo."""
    historicos = _historicos()
    i_treino, i_teste = dividir(historicos)
    saida = {"alunos_treino": 0, "alunos_teste": 0, "limiar": LIMIAR, "perto": PERTO, "alvos": {}, "por_periodo": []}
    x_treino, y_treino = [], {a: [] for a in ALVOS}
    for m in i_treino:
        feitos = historicos[m][1]
        for k in range(1, len(feitos)):  # cada semestre do aluno de treino vira um exemplo: o que veio antes -> ele
            x_treino.append(calcular_variaveis(feitos[:k]))
            for a in ALVOS:
                y_treino[a].append(feitos[k][a])
        saida["alunos_treino"] += len(feitos) > 1
    teste = sorted(m for m in i_teste if len(historicos[m][1]) > 1)  # precisa de um semestre antes do escondido
    x_teste = [calcular_variaveis(historicos[m][1][:-1]) for m in teste]
    escondido = {m: historicos[m][1][-1] for m in teste}  # o gabarito: só é lido depois da previsão
    saida["alunos_teste"] = len(teste)
    previsoes = {}
    for a in ALVOS:
        pesos = ajustar(x_treino, y_treino[a])
        anterior = [x[VARIAVEIS.index("nota_ultimo" if a == "nota" else "freq_ultimo")] for x in x_teste]
        reta = [x_a + x[VARIAVEIS.index("nota_inclinacao" if a == "nota" else "freq_inclinacao")]
                for x_a, x in zip(anterior, x_teste)]
        modelo = [prever_valor(pesos, x) for x in x_teste]
        real = [escondido[m][a] for m in teste]
        ganho = _ganho([abs(p - r) for p, r in zip(anterior, real)], [abs(p - r) for p, r in zip(modelo, real)])
        saida["alvos"][a] = {"modelo": _medidas(modelo, real, anterior), "repetir_anterior": _medidas(anterior, real, anterior),
                             "reta": _medidas([max(0.0, min(100.0, v)) for v in reta], real, anterior),
                             "ganho": ganho, "aprovado": ganho["ic"][0] > 0, "pesos": pesos}
        previsoes[a] = dict(zip(teste, zip(modelo, real)))
    por_periodo = {}
    for m in teste:
        por_periodo.setdefault(historicos[m][0], []).append(m)
    for periodo in sorted(por_periodo):
        ms, linha = por_periodo[periodo], {"periodo": periodo, "alunos": len(por_periodo[periodo]),
                                          "semestre": semestre_rotulo(max(escondido[m]["ordem"] for m in por_periodo[periodo]))}
        for a in ALVOS:
            prev, real = [previsoes[a][m][0] for m in ms], [previsoes[a][m][1] for m in ms]
            linha[a] = {"previsto": round(sum(prev) / len(ms), 2), "real": round(sum(real) / len(ms), 2)}
        saida["por_periodo"].append(linha)
    return saida


def _previsao(feitos, em_curso):
    """Próximo semestre de um histórico: pelo modelo, se ele foi aprovado, ou repetindo o semestre anterior."""
    av, x = avaliar(), calcular_variaveis(feitos)
    saida = {"semestre": semestre_rotulo(em_curso or feitos[-1]["ordem"] + 1), "em_curso": em_curso is not None}
    for a in ALVOS:
        alvo = av["alvos"][a]
        valor = prever_valor(alvo["pesos"], x) if alvo["aprovado"] else feitos[-1][a]
        metodo = "modelo" if alvo["aprovado"] else "repetir_anterior"
        saida[a] = {"previsto": round(valor, 1), "anterior": round(feitos[-1][a], 1), "direcao": direcao(feitos[-1][a], valor),
                    "metodo": metodo, "erro_medio": alvo[metodo]["erro_medio"]}
    return saida


def prever_aluno(matricula):
    """Previsão do próximo semestre do aluno. None se ele ainda não tem semestre concluído."""
    historico = _historicos([matricula]).get(matricula)
    return _previsao(historico[1], historico[2]) if historico and historico[1] else None


def resumo():
    """O que a aba Avaliação mostra: o acerto no semestre escondido (sem os pesos) e a previsão de cada período."""
    av = avaliar()
    alvos = {a: {c: v for c, v in d.items() if c != "pesos"} for a, d in av["alvos"].items()}
    return av | {"alvos": alvos, "previsao_periodos": prever_periodos()}


def prever_periodos():
    """Média prevista do próximo semestre de cada período (turma), com todos os alunos que têm histórico."""
    grupos = {}
    for periodo, feitos, em_curso in _historicos().values():
        if feitos:
            grupos.setdefault(periodo, []).append(_previsao(feitos, em_curso))
    saida = []
    for periodo in sorted(grupos):
        itens = grupos[periodo]
        linha = {"periodo": periodo, "alunos": len(itens), "semestre": itens[0]["semestre"]}
        for a in ALVOS:
            previsto, anterior = (sum(i[a][c] for i in itens) / len(itens) for c in ("previsto", "anterior"))
            linha[a] = {"previsto": round(previsto, 1), "anterior": round(anterior, 1), "direcao": direcao(anterior, previsto)}
        saida.append(linha)
    return saida
