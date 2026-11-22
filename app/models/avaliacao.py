"""Avaliação do modelo de risco: compara o risco previsto com quem de fato evadiu (tabela desfechos_alunos, o gabarito).

O gabarito só é lido aqui, para medir o acerto; nunca entra no cálculo do risco (seria vazamento).
Evasão é o caso "positivo": prever risco e o aluno evadir é um acerto (verdadeiro positivo).
As regras e o significado de cada métrica estão no readme.md, seção "Avaliação do modelo de risco".
"""
import math
from collections import Counter

from models import alunos, modelo_risco, predicao
from models.banco import consultar

NIVEIS = predicao.NIVEIS  # ("baixo", "medio", "alto"): a ordem vira a pontuação do nível (0, 1, 2)
CORTES = {"alto": ("alto",), "medio_ou_alto": ("medio", "alto")}  # quais níveis contam como "previu evasão"
EVENTOS_MINIMOS = 10  # LLM x regras precisa de tantos alunos que evadiram e tantos que ficaram; abaixo disso, só aviso
Z_95 = 1.96  # valor da normal padrão para um intervalo de confiança de 95%


def _div(a, b):
    return round(a / b, 3) if b else None


def metricas(previsto, real):
    """Matriz de confusão e métricas de uma previsão sim/não. previsto e real: listas de bool (True = evasão)."""
    vp = sum(p and r for p, r in zip(previsto, real))
    fp = sum(p and not r for p, r in zip(previsto, real))
    fn = sum(r and not p for p, r in zip(previsto, real))
    vn = sum(not p and not r for p, r in zip(previsto, real))
    precisao, revocacao = _div(vp, vp + fp), _div(vp, vp + fn)
    f1 = (round(2 * precisao * revocacao / (precisao + revocacao), 3) if precisao and revocacao
          else 0.0 if precisao is not None and revocacao is not None else None)
    return {"vp": vp, "fp": fp, "fn": fn, "vn": vn, "acuracia": _div(vp + vn, len(real)), "precisao": precisao,
            "revocacao": revocacao, "especificidade": _div(vn, vn + fp), "f1": f1}


def auc(pontos, real):
    """Área sob a curva ROC, pela estatística de Mann-Whitney: a chance de um aluno que evadiu ter pontuação maior
    que um que não evadiu (empate vale meio). 0,5 = sorteio; 1 = separa perfeitamente. None sem os dois grupos."""
    pos, neg = Counter(p for p, r in zip(pontos, real) if r), Counter(p for p, r in zip(pontos, real) if not r)
    total_pos, total_neg = sum(pos.values()), sum(neg.values())
    if not total_pos or not total_neg:
        return None
    ganhos, negativos_abaixo = 0.0, 0
    for p in sorted(set(pos) | set(neg)):  # pontuações são poucas (0 a 7): conta por valor em vez de comparar pares
        ganhos += pos[p] * (negativos_abaixo + neg[p] / 2)
        negativos_abaixo += neg[p]
    return round(ganhos / (total_pos * total_neg), 3)


def ic_proporcao(casos, total):
    """Intervalo de confiança de 95% de uma proporção, pelo método de Wilson (funciona bem perto de 0 e de 1)."""
    if not total:
        return None
    p, z2 = casos / total, Z_95 ** 2
    centro = (p + z2 / (2 * total)) / (1 + z2 / total)
    margem = Z_95 * math.sqrt(p * (1 - p) / total + z2 / (4 * total ** 2)) / (1 + z2 / total)
    return [round(max(centro - margem, 0), 3), round(min(centro + margem, 1), 3)]


def intervalos(m):
    """Intervalos de confiança das proporções de uma matriz de confusão. O F1 não é proporção simples e fica de fora."""
    return {"acuracia": ic_proporcao(m["vp"] + m["vn"], m["vp"] + m["fp"] + m["fn"] + m["vn"]),
            "precisao": ic_proporcao(m["vp"], m["vp"] + m["fp"]), "revocacao": ic_proporcao(m["vp"], m["vp"] + m["fn"]),
            "especificidade": ic_proporcao(m["vn"], m["vn"] + m["fp"])}


def ic_auc(pontos, real):
    """Intervalo de confiança de 95% da AUC pelo método de DeLong, que trata empates. None com menos de 2 por grupo."""
    pos, neg = Counter(p for p, r in zip(pontos, real) if r), Counter(p for p, r in zip(pontos, real) if not r)
    total_pos, total_neg = sum(pos.values()), sum(neg.values())
    if total_pos < 2 or total_neg < 2:
        return None
    nota_pos, nota_neg, pos_abaixo, neg_abaixo = {}, {}, 0, 0  # por pontuação: chance de vencer o outro grupo
    for p in sorted(set(pos) | set(neg)):
        nota_pos[p] = (neg_abaixo + neg[p] / 2) / total_neg
        nota_neg[p] = (total_pos - pos_abaixo - pos[p] / 2) / total_pos
        pos_abaixo += pos[p]
        neg_abaixo += neg[p]
    valor = sum(pos[p] * nota_pos[p] for p in pos) / total_pos
    variancia = (sum(pos[p] * (nota_pos[p] - valor) ** 2 for p in pos) / (total_pos - 1) / total_pos
                 + sum(neg[p] * (nota_neg[p] - valor) ** 2 for p in neg) / (total_neg - 1) / total_neg)
    margem = Z_95 * math.sqrt(variancia)
    return [round(max(valor - margem, 0), 3), round(min(valor + margem, 1), 3)]


def curva_roc(pontos, real):
    """Pontos (taxa de falso positivo, taxa de verdadeiro positivo) para cada corte possível, do mais exigente ao mais
    frouxo. Começa em (0, 0) e termina em (1, 1)."""
    total_pos, total_neg = sum(real), len(real) - sum(real)
    curva = [{"fpr": 0.0, "tpr": 0.0, "corte": None}]
    if not total_pos or not total_neg:
        return curva
    for corte in sorted(set(pontos), reverse=True):
        acima = [r for p, r in zip(pontos, real) if p >= corte]
        curva.append({"fpr": round((len(acima) - sum(acima)) / total_neg, 3),
                      "tpr": round(sum(acima) / total_pos, 3), "corte": corte})
    return curva


def bloco(niveis, real, pontos):
    """Todas as medidas de um conjunto de previsões: evasão real por nível, os dois cortes, AUC e curva ROC."""
    por_nivel = {}
    for nivel in NIVEIS:
        do_nivel = [r for n, r in zip(niveis, real) if n == nivel]
        por_nivel[nivel] = {"alunos": len(do_nivel), "evasoes": sum(do_nivel), "taxa": _div(sum(do_nivel), len(do_nivel)),
                            "ic": ic_proporcao(sum(do_nivel), len(do_nivel))}
    cortes = {nome: metricas([n in quais for n in niveis], real) for nome, quais in CORTES.items()}
    return {"alunos": len(real), "evasoes": sum(real), "por_nivel": por_nivel,
            "cortes": {nome: m | {"ic": intervalos(m)} for nome, m in cortes.items()},
            "auc": auc(pontos, real), "auc_ic": ic_auc(pontos, real), "roc": curva_roc(pontos, real)}


def gabarito():
    """{matricula: evadiu?}. Único ponto que lê desfechos_alunos: serve para medir o acerto e como resposta do treino."""
    return {linha["matricula"]: bool(linha["evasao_observada"]) for linha in consultar("""
        SELECT a.codigo_academico AS matricula, d.evasao_observada FROM desfechos_alunos d
          JOIN matriculas_curso USING (matricula_curso_id) JOIN alunos a USING (aluno_id)""")}


def avaliar():
    """Avalia as regras em todos os alunos com desfecho e, nos que têm predição da LLM, compara a LLM com as regras
    nos mesmos alunos. Também devolve a acurácia de quem "chuta" que ninguém evade, a base para comparar, e as
    métricas do modelo treinado, medidas só nos alunos que ele não viu."""
    evadiu = gabarito()
    ultimas = predicao.ultimas_por_aluno()
    regras, llm = [], []  # (nível, pontuação, evadiu) e (nível da LLM, nível das regras, evadiu)
    for aluno in alunos.listar({"perfil": "secretaria"}):
        if aluno["matricula"] not in evadiu:
            continue
        calculo, real = predicao.calcular_risco(aluno), evadiu[aluno["matricula"]]
        regras.append((calculo["risco"], calculo["score"], real))
        ultima = ultimas.get(aluno["matricula"])
        if ultima and ultima["origem"] == "llm" and ultima["modelo_risco_id"] is None:  # com modelo, a LLM só comenta
            llm.append((ultima["risco"], calculo["risco"], real))
    real = [r for _, _, r in regras]
    resultado = {"alunos": len(real), "evasoes": sum(real), "taxa_evasao": _div(sum(real), len(real)),
                 "acuracia_chute": _div(len(real) - sum(real), len(real)),
                 "regras": bloco([n for n, _, _ in regras], real, [p for _, p, _ in regras])}
    pontos_nivel = [NIVEIS.index(n) for n, _, _ in regras]
    resultado["regras"]["auc_nivel"] = auc(pontos_nivel, real)
    resultado["regras"]["auc_nivel_ic"] = ic_auc(pontos_nivel, real)
    real_llm = [r for _, _, r in llm]
    resultado["llm"] = {
        "alunos": len(llm), "eventos_minimos": EVENTOS_MINIMOS,
        "amostra_pequena": min(sum(real_llm), len(llm) - sum(real_llm)) < EVENTOS_MINIMOS,
        "parcial": len(llm) < len(real),  # quem tem predição da LLM pode não ser uma amostra aleatória dos alunos
        "llm": bloco([n for n, _, _ in llm], real_llm, [NIVEIS.index(n) for n, _, _ in llm]),
        "regras": bloco([n for _, n, _ in llm], real_llm, [NIVEIS.index(n) for _, n, _ in llm]),
    }
    modelo = modelo_risco.ativo()
    resultado["modelo_treinado"] = modelo and {"id": modelo["id"], "criado_em": modelo["criado_em"],
                                               "metricas": modelo["metricas"]}
    return resultado
