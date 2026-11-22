"""Treinamento do modelo de risco: aprende os pesos com alunos de desfecho conhecido e prova o acerto em alunos à parte.

1. separa 20% dos alunos para o teste (mesma proporção de evasão nos dois grupos);
2. ajusta uma regressão logística nos outros 80% e mede a estabilidade com validação cruzada;
3. compara com a referência (as regras ou o modelo ativo) só nos alunos do teste;
4. aprova o modelo apenas se o ganho de AUC for positivo em todo o intervalo de confiança de 95%.
O passo a passo está no readme.md, seção "Treinamento do modelo de risco".
"""
import math
import random

from models import alunos, avaliacao, modelo_risco, predicao
from models.banco import ErroModelo

SEMENTE = 2026             # mesma divisão a cada treino: o resultado pode ser reproduzido
PROPORCAO_TESTE = 0.2
DOBRAS = 5
REGULARIZACAO = 1.0        # penalidade L2: evita pesos exagerados
ITERACOES = 8              # passos do método de Newton; a regressão logística converge em poucos
REAMOSTRAGENS = 500        # bootstrap do intervalo de confiança do ganho
EVASOES_MINIMAS = 50       # com menos evasões que isso, não há exemplos suficientes para aprender


def _resolver(matriz, vetor):
    """Resolve o sistema linear por eliminação de Gauss com pivotamento."""
    n = len(vetor)
    m = [linha[:] + [v] for linha, v in zip(matriz, vetor)]
    for i in range(n):
        pivo = max(range(i, n), key=lambda l: abs(m[l][i]))
        m[i], m[pivo] = m[pivo], m[i]
        for l in range(i + 1, n):
            fator = m[l][i] / m[i][i]
            for c in range(i, n + 1):
                m[l][c] -= fator * m[i][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][c] * x[c] for c in range(i + 1, n))) / m[i][i]
    return x


def ajustar(valores, real):
    """Regressão logística com regularização, pelo método de Newton. Médias e desvios saem só dos dados recebidos."""
    colunas = list(zip(*valores))
    medias, desvios = [], []
    for coluna in colunas:
        presentes = [v for v in coluna if v is not None]
        media = sum(presentes) / len(presentes) if presentes else 0.0
        medias.append(media)
        desvios.append(math.sqrt(sum((v - media) ** 2 for v in presentes) / len(presentes)) or 1.0 if presentes else 1.0)
    linhas = [[1.0] + [0.0 if v is None else (v - m) / d for v, m, d in zip(x, medias, desvios)] for x in valores]
    p = len(linhas[0])
    b = [0.0] * p
    for _ in range(ITERACOES):
        hess, grad = [[0.0] * p for _ in range(p)], [0.0] * p
        for x, y in zip(linhas, real):
            chance = 1 / (1 + math.exp(-max(min(sum(c * v for c, v in zip(b, x)), 30), -30)))
            peso, erro = chance * (1 - chance), y - chance
            for i in range(p):
                grad[i] += erro * x[i]
                for j in range(i, p):
                    hess[i][j] += peso * x[i] * x[j]
        for i in range(p):
            for j in range(i):
                hess[i][j] = hess[j][i]
            if i:  # o intercepto não é penalizado
                hess[i][i] += REGULARIZACAO
                grad[i] -= REGULARIZACAO * b[i]
        b = [c + d for c, d in zip(b, _resolver(hess, grad))]
    return {"variaveis": list(modelo_risco.VARIAVEIS), "intercepto": b[0], "coeficientes": b[1:],
            "medias": medias, "desvios": desvios}


def dividir(real):
    """(índices do treino, índices do teste), com a mesma proporção de evasão nos dois."""
    rnd = random.Random(SEMENTE)
    treino, teste = [], []
    for classe in (True, False):
        grupo = [i for i, r in enumerate(real) if r == classe]
        rnd.shuffle(grupo)
        corte = round(len(grupo) * PROPORCAO_TESTE)
        teste += grupo[:corte]
        treino += grupo[corte:]
    return sorted(treino), sorted(teste)


def _validacao_cruzada(valores, real):
    """AUC de cada aluno do treino previsto por um modelo que não o viu."""
    ordem = list(range(len(real)))
    random.Random(SEMENTE).shuffle(ordem)
    previsto = [0.0] * len(real)
    for dobra in range(DOBRAS):
        fora = ordem[dobra::DOBRAS]
        separados = set(fora)
        dentro = [i for i in ordem if i not in separados]
        pesos = ajustar([valores[i] for i in dentro], [real[i] for i in dentro])
        for i in fora:
            previsto[i] = modelo_risco.probabilidade(pesos, valores[i])
    return avaliacao.auc(previsto, real)


def _ganho(novo, referencia, real):
    """Diferença de AUC (novo - referência) nos mesmos alunos, com IC de 95% por bootstrap pareado."""
    rnd, n, difs = random.Random(SEMENTE), len(real), []
    while len(difs) < REAMOSTRAGENS:
        amostra = [rnd.randrange(n) for _ in range(n)]
        r = [real[i] for i in amostra]
        if any(r) and not all(r):
            difs.append(avaliacao.auc([novo[i] for i in amostra], r) - avaliacao.auc([referencia[i] for i in amostra], r))
    difs.sort()
    return {"valor": round(avaliacao.auc(novo, real) - avaliacao.auc(referencia, real), 3),
            "ic": [round(difs[int(0.025 * REAMOSTRAGENS)], 3), round(difs[int(0.975 * REAMOSTRAGENS)], 3)]}


def _medidas(niveis, pontos, real):
    bloco = avaliacao.bloco(niveis, real, pontos)
    del bloco["roc"]
    ordem = [predicao.NIVEIS.index(n) for n in niveis]
    return bloco | {"auc_nivel": avaliacao.auc(ordem, real), "auc_nivel_ic": avaliacao.ic_auc(ordem, real)}


def _calibracao(chances, real, grupos=5):
    """Compara a chance prevista com a evasão real em grupos de mesmo tamanho, do menor risco ao maior."""
    ordem = sorted(range(len(real)), key=lambda i: chances[i])
    saida = []
    for g in range(grupos):
        parte = ordem[g * len(ordem) // grupos:(g + 1) * len(ordem) // grupos]
        saida.append({"alunos": len(parte), "previsto": round(sum(chances[i] for i in parte) / len(parte), 3),
                      "real": round(sum(real[i] for i in parte) / len(parte), 3)})
    return saida


def treinar():
    """Treina, testa e guarda uma nova versão. Devolve {id, aprovado, referencia, metricas}."""
    evadiu, dados = avaliacao.gabarito(), modelo_risco.variaveis()
    resumo = {a["matricula"]: a for a in alunos.listar({"perfil": "secretaria"})}
    matriculas = sorted(m for m in evadiu if m in dados and m in resumo)
    real = [evadiu[m] for m in matriculas]
    if min(sum(real), len(real) - sum(real)) < EVASOES_MINIMAS:
        raise ErroModelo(400, f"são necessários pelo menos {EVASOES_MINIMAS} alunos que evadiram e {EVASOES_MINIMAS} que ficaram")
    valores = [dados[m] for m in matriculas]
    i_treino, i_teste = dividir(real)
    x_treino, y_treino = [valores[i] for i in i_treino], [real[i] for i in i_treino]
    pesos = ajustar(x_treino, y_treino)

    y_teste = [real[i] for i in i_teste]
    chances = [modelo_risco.probabilidade(pesos, valores[i]) for i in i_teste]
    do_teste = [resumo[matriculas[i]] for i in i_teste]
    niveis = [predicao.aplicar_regras_duras(a, modelo_risco.nivel(c))[0] for a, c in zip(do_teste, chances)]
    regras = [predicao.calcular_risco(a) for a in do_teste]
    atual = modelo_risco.ativo()
    if atual:
        referencia = f"modelo v{atual['id']}"
        pontos_ref = [modelo_risco.probabilidade(atual["pesos"], valores[i]) for i in i_teste]
    else:
        referencia, pontos_ref = "regras", [r["score"] for r in regras]
    ganho = _ganho(chances, pontos_ref, y_teste)
    aprovado = ganho["ic"][0] > 0
    base = sum(y_teste) / len(y_teste)
    metricas = {
        "treino": {"alunos": len(y_treino), "evasoes": sum(y_treino)},
        "teste": {"alunos": len(y_teste), "evasoes": sum(y_teste)},
        "auc_validacao_cruzada": _validacao_cruzada(x_treino, y_treino),
        "modelo": _medidas(niveis, chances, y_teste),
        "regras": _medidas([r["risco"] for r in regras], [r["score"] for r in regras], y_teste),
        "referencia": referencia, "ganho_auc": ganho,
        "brier": {"modelo": round(sum((c - y) ** 2 for c, y in zip(chances, y_teste)) / len(y_teste), 4),
                  "taxa_geral": round(base * (1 - base), 4)},
        "calibracao": _calibracao(chances, y_teste),
        "cortes": {"medio": modelo_risco.CORTE_MEDIO, "alto": modelo_risco.CORTE_ALTO},
    }
    return {"id": modelo_risco.salvar(pesos, metricas, aprovado), "aprovado": aprovado, "referencia": referencia,
            "metricas": metricas}
