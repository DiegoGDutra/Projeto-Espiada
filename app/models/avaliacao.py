"""Avaliação do modelo de risco: compara o risco previsto com quem de fato evadiu (tabela desfechos_alunos, o gabarito).

O gabarito só é lido aqui, para medir o acerto; nunca entra no cálculo do risco (seria vazamento).
Evasão é o caso "positivo": prever risco e o aluno evadir é um acerto (verdadeiro positivo).
As regras e o significado de cada métrica estão no readme.md, seção "Avaliação do modelo de risco".
"""
from collections import Counter

from models import alunos, predicao
from models.banco import consultar

NIVEIS = predicao.NIVEIS  # ("baixo", "medio", "alto"): a ordem vira a pontuação do nível (0, 1, 2)
CORTES = {"alto": ("alto",), "medio_ou_alto": ("medio", "alto")}  # quais níveis contam como "previu evasão"
AMOSTRA_MINIMA = 30  # abaixo disso a comparação LLM x regras sai com aviso: pouca gente para concluir


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


def _bloco(niveis, real, pontos):
    """Todas as medidas de um conjunto de previsões: evasão real por nível, os dois cortes, AUC e curva ROC."""
    por_nivel = {}
    for nivel in NIVEIS:
        do_nivel = [r for n, r in zip(niveis, real) if n == nivel]
        por_nivel[nivel] = {"alunos": len(do_nivel), "evasoes": sum(do_nivel), "taxa": _div(sum(do_nivel), len(do_nivel))}
    return {"alunos": len(real), "evasoes": sum(real), "por_nivel": por_nivel,
            "cortes": {nome: metricas([n in quais for n in niveis], real) for nome, quais in CORTES.items()},
            "auc": auc(pontos, real), "roc": curva_roc(pontos, real)}


def avaliar():
    """Avalia as regras em todos os alunos com desfecho e, nos que têm predição da LLM, compara a LLM com as regras
    nos mesmos alunos. Também devolve a acurácia de quem "chuta" que ninguém evade, a base para comparar."""
    evadiu = {linha["matricula"]: bool(linha["evasao_observada"]) for linha in consultar("""
        SELECT a.codigo_academico AS matricula, d.evasao_observada FROM desfechos_alunos d
          JOIN matriculas_curso USING (matricula_curso_id) JOIN alunos a USING (aluno_id)""")}
    ultimas = predicao.ultimas_por_aluno()
    regras, llm = [], []  # (nível, pontuação, evadiu) e (nível da LLM, nível das regras, evadiu)
    for aluno in alunos.listar({"perfil": "secretaria"}):
        if aluno["matricula"] not in evadiu:
            continue
        calculo, real = predicao.calcular_risco(aluno), evadiu[aluno["matricula"]]
        regras.append((calculo["risco"], calculo["score"], real))
        ultima = ultimas.get(aluno["matricula"])
        if ultima and ultima["origem"] == "llm":
            llm.append((ultima["risco"], calculo["risco"], real))
    real = [r for _, _, r in regras]
    resultado = {"alunos": len(real), "evasoes": sum(real), "taxa_evasao": _div(sum(real), len(real)),
                 "acuracia_chute": _div(len(real) - sum(real), len(real)),
                 "regras": _bloco([n for n, _, _ in regras], real, [p for _, p, _ in regras])}
    resultado["regras"]["auc_nivel"] = auc([NIVEIS.index(n) for n, _, _ in regras], real)
    real_llm = [r for _, _, r in llm]
    resultado["llm"] = {
        "alunos": len(llm), "amostra_pequena": len(llm) < AMOSTRA_MINIMA,
        "llm": _bloco([n for n, _, _ in llm], real_llm, [NIVEIS.index(n) for n, _, _ in llm]),
        "regras": _bloco([n for _, n, _ in llm], real_llm, [NIVEIS.index(n) for _, n, _ in llm]),
    }
    return resultado
