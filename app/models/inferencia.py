"""Testes estatísticos feitos à mão, sem biblioteca nova: qui-quadrado, t de Welch, Mann-Whitney, correlações,
razão de chances, McNemar e a correção de Holm. Aqui só há contas: nenhum SQL e nenhuma regra do sistema.
O significado de cada teste está no readme.md, seção "Estatística".
"""
import math

Z_95 = 1.96
PEQUENO = 1e-300  # evita divisão por zero nas frações continuadas


def _nao_zero(v):
    return v if abs(v) > PEQUENO else PEQUENO


def _gama_superior(a, x):
    """Função gama incompleta superior regularizada Q(a, x): por série se x é pequeno, por fração continuada se não."""
    if x <= 0:
        return 1.0
    frente = math.exp(-x + a * math.log(x) - math.lgamma(a))
    if x < a + 1:
        termo = soma = 1 / a
        n = a
        for _ in range(2000):
            n += 1
            termo *= x / n
            soma += termo
            if abs(termo) < abs(soma) * 1e-14:
                break
        return max(0.0, 1 - soma * frente)
    b = x + 1 - a
    c, d = 1 / PEQUENO, 1 / _nao_zero(b)
    h = d
    for i in range(1, 2000):
        an = -i * (i - a)
        b += 2
        d = 1 / _nao_zero(an * d + b)
        c = _nao_zero(b + an / c)
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-14:
            break
    return min(1.0, frente * h)


def _beta_regularizada(a, b, x):
    """Função beta incompleta regularizada I_x(a, b), por fração continuada."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    if x > (a + 1) / (a + b + 2):  # do outro lado a fração converge mais rápido
        return 1 - _beta_regularizada(b, a, 1 - x)
    frente = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)) / a
    c, d = 1.0, 1 / _nao_zero(1 - (a + b) * x / (a + 1))
    h = d
    for m in range(1, 1000):
        par = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        d = 1 / _nao_zero(1 + par * d)
        c = _nao_zero(1 + par / c)
        h *= d * c
        impar = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1 / _nao_zero(1 + impar * d)
        c = _nao_zero(1 + impar / c)
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-14:
            break
    return frente * h


def p_qui2(x, gl):
    """Valor-p do qui-quadrado (cauda superior)."""
    return _gama_superior(gl / 2, x / 2)


def p_t(t, gl):
    """Valor-p bilateral da distribuição t de Student."""
    return _beta_regularizada(gl / 2, 0.5, gl / (gl + t * t))


def p_normal(z):
    """Valor-p bilateral da normal padrão."""
    return math.erfc(abs(z) / math.sqrt(2))


def t_critico(gl, alfa=0.05):
    """Valor de t com probabilidade alfa nas duas caudas, por bisseção."""
    baixo, alto = 0.0, 1000.0
    for _ in range(80):
        meio = (baixo + alto) / 2
        if p_t(meio, gl) > alfa:
            baixo = meio
        else:
            alto = meio
    return (baixo + alto) / 2


def holm(valores_p):
    """Correção de Holm para vários testes de uma vez. Mantém a ordem da lista; None continua None."""
    ordem = sorted((i for i, p in enumerate(valores_p) if p is not None), key=lambda i: valores_p[i])
    saida, maior = list(valores_p), 0.0
    for posicao, i in enumerate(ordem):
        maior = max(maior, min(1.0, (len(ordem) - posicao) * valores_p[i]))
        saida[i] = maior
    return saida


def postos(valores):
    """Posto de cada valor (1 = menor); valores empatados recebem a média dos postos."""
    ordem = sorted(range(len(valores)), key=lambda i: valores[i])
    saida, i = [0.0] * len(valores), 0
    while i < len(ordem):
        j = i
        while j + 1 < len(ordem) and valores[ordem[j + 1]] == valores[ordem[i]]:
            j += 1
        for k in range(i, j + 1):
            saida[ordem[k]] = (i + j) / 2 + 1
        i = j + 1
    return saida


def pearson(x, y):
    """Correlação de Pearson; None se uma das variáveis for constante ou houver menos de 3 pares."""
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    syy = sum((v - my) ** 2 for v in y)
    if not sxx or not syy:
        return None
    return max(-1.0, min(1.0, sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sxx * syy)))


def _p_correlacao(r, n):
    if r is None:
        return None
    if abs(r) == 1:
        return 0.0
    return p_t(r * math.sqrt((n - 2) / (1 - r * r)), n - 2)


def correlacao(x, y):
    """Pearson (relação linear) e Spearman (relação monótona, pelos postos), com o valor-p de cada uma."""
    r, rho = pearson(x, y), pearson(postos(x), postos(y))
    return {"n": len(x), "pearson": r, "pearson_p": _p_correlacao(r, len(x)),
            "spearman": rho, "spearman_p": _p_correlacao(rho, len(x))}


def qui_quadrado(tabela):
    """Teste de independência numa tabela de contagens. Devolve qui2, gl, p, V de Cramér (tamanho do efeito) e se a
    aproximação é válida (toda contagem esperada >= 5). None se sobrar menos de 2 linhas ou colunas com dados."""
    linhas = [l for l in tabela if sum(l)]
    colunas = [c for c in zip(*linhas) if sum(c)]
    if len(linhas) < 2 or len(colunas) < 2:
        return None
    linhas = [list(l) for l in zip(*colunas)]
    total = sum(map(sum, linhas))
    soma_linhas, soma_colunas = [sum(l) for l in linhas], [sum(c) for c in colunas]
    x2, menor = 0.0, math.inf
    for i, linha in enumerate(linhas):
        for j, observado in enumerate(linha):
            esperado = soma_linhas[i] * soma_colunas[j] / total
            menor = min(menor, esperado)
            x2 += (observado - esperado) ** 2 / esperado
    gl = (len(linhas) - 1) * (len(colunas) - 1)
    return {"qui2": x2, "gl": gl, "p": p_qui2(x2, gl), "v_cramer": math.sqrt(x2 / (total * (min(len(linhas), len(colunas)) - 1))),
            "valido": menor >= 5}


def razao_chances(a, b, c, d):
    """Razão de chances de a/b contra c/d, com IC de 95% (Woolf). Com alguma casela zerada, soma 0,5 em todas."""
    if 0 in (a, b, c, d):
        a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    log_rc, erro = math.log(a * d / (b * c)), math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return {"valor": math.exp(log_rc), "ic": [math.exp(log_rc - Z_95 * erro), math.exp(log_rc + Z_95 * erro)]}


def mann_whitney(a, b):
    """Mann-Whitney com correção de empates e de continuidade. Compara as distribuições sem supor normalidade.
    Devolve o valor-p e a chance de um valor de a superar um de b (empate vale meio)."""
    na, nb = len(a), len(b)
    n = na + nb
    p = postos(list(a) + list(b))
    u = sum(p[:na]) - na * (na + 1) / 2
    grupos = {}
    for v in list(a) + list(b):
        grupos[v] = grupos.get(v, 0) + 1
    empates = sum(t ** 3 - t for t in grupos.values())
    variancia = na * nb / 12 * ((n + 1) - empates / (n * (n - 1)))
    if variancia <= 0:
        return {"p": 1.0, "prob_superioridade": 0.5}
    desvio = u - na * nb / 2
    z = max(abs(desvio) - 0.5, 0) / math.sqrt(variancia)
    return {"p": p_normal(z), "prob_superioridade": u / (na * nb)}


def comparar_medias(a, b):
    """Diferença de médias (a - b) com IC de 95% e teste t de Welch, d de Cohen e Mann-Whitney. None com menos de 2
    valores em algum grupo."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    ma, mb = sum(a) / na, sum(b) / nb
    va, vb = sum((v - ma) ** 2 for v in a) / (na - 1), sum((v - mb) ** 2 for v in b) / (nb - 1)
    erro2 = va / na + vb / nb
    if not erro2:
        return None
    gl = erro2 ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    margem = t_critico(gl) * math.sqrt(erro2)
    dif = ma - mb
    desvio_comum = math.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    mw = mann_whitney(a, b)
    return {"n_a": na, "n_b": nb, "media_a": ma, "media_b": mb, "diferenca": dif, "ic": [dif - margem, dif + margem],
            "t": dif / math.sqrt(erro2), "gl": gl, "p_welch": p_t(dif / math.sqrt(erro2), gl),
            "d_cohen": dif / desvio_comum if desvio_comum else None, "p_mann_whitney": mw["p"],
            "prob_superioridade": mw["prob_superioridade"]}


def mcnemar(b, c):
    """Teste pareado de dois classificadores nos mesmos alunos. b: só o primeiro acertou; c: só o segundo acertou.
    Até 25 discordâncias usa o teste binomial exato; acima disso, o qui-quadrado com correção de continuidade."""
    n = b + c
    if not n:
        return 1.0
    if n <= 25:
        return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)
    return p_qui2((abs(b - c) - 1) ** 2 / n, 1)
