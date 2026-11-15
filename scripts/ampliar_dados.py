"""Amplia o dataset sintético de dados/ para TOTAL_ALUNOS alunos, mantendo a proporção de 18 docentes a cada 200 alunos.

Os registros originais (alunos 1-120, docentes 1-18, turmas 1-320) ficam intactos; o resto é gerado de novo a cada
execução, com semente fixa (mesma saída sempre). Segue as regras do dataset original: nota final = 0,3·N1 + 0,3·N2 +
0,4·projeto, aprovação com nota >= 60 e frequência >= 75, recuperação no semestre seguinte, turmas de 45 vagas
(novas seções B, C... quando a A enche), 2026-2 em curso, indicadores de risco e desfecho na janela de 12 meses.

Rodar:  python scripts/ampliar_dados.py   e depois zerar o banco (docker compose down -v && docker compose up -d) e rodar python scripts/importar.py
"""
import csv
import random
from datetime import date, timedelta
from itertools import cycle
from pathlib import Path

DADOS = Path(__file__).resolve().parent.parent / "dados"
TOTAL_ALUNOS = 5000
TOTAL_DOCENTES = TOTAL_ALUNOS * 18 // 200  # 450
BASE_ALUNOS, BASE_DOCENTES, BASE_TURMAS = 120, 18, 320  # o que veio no dataset original
VAGAS = 45
SEMESTRES = [(a, s) for a in range(2023, 2027) for s in (1, 2)]  # índice 7 = 2026-2, em curso
ATUAL = len(SEMESTRES) - 1
REFERENCIA = "2026-08-01"

rnd = random.Random(2026)


def ler(tabela):
    with open(DADOS / f"{tabela}.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def gravar(tabela, linhas):
    with open(DADOS / f"{tabela}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)


def num(x, casas=1):
    """Número no formato do dataset: 63 em vez de 63.0."""
    if x is None:
        return ""
    x = round(x, casas)
    return str(int(x)) if x == int(x) else str(x)


def limitar(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def sorteio(pesos):
    return rnd.choices(list(pesos), weights=list(pesos.values()))[0]


def data_aleatoria(inicio, fim):
    return (inicio + timedelta(days=rnd.randint(0, (fim - inicio).days))).isoformat()


def docentes_novos():
    nomes = ["Ana", "Bruno", "Camila", "Daniel", "Elisa", "Felipe", "Gabriela", "Heitor", "Isabela", "João", "Karina",
             "Lucas", "Marina", "Nicolas", "Olívia", "Paulo", "Queila", "Rafael", "Sofia", "Tiago", "Úrsula", "Vitor",
             "Yasmin", "Wagner", "Beatriz", "Caio", "Débora", "Eduardo", "Fabiana", "Gustavo"]
    sobrenomes = ["Almeida", "Barros", "Cardoso", "Dias", "Esteves", "Freitas", "Gomes", "Henriques", "Lima", "Moura",
                  "Nogueira", "Oliveira", "Pereira", "Queiroz", "Rocha", "Santos", "Teixeira", "Vieira", "Xavier",
                  "Zanetti"]
    pares = rnd.sample([(n, s) for n in nomes for s in sobrenomes], TOTAL_DOCENTES - BASE_DOCENTES)
    return [{"docente_id": str(i), "nome_sintetico": f"Docente {n} {s}",
             "titulacao": sorteio({"Mestre": 7, "Especialista": 6, "Doutor": 5}),
             "regime_trabalho": sorteio({"Tempo integral": 13, "Tempo parcial": 5})}
            for i, (n, s) in enumerate(pares, BASE_DOCENTES + 1)]


def main():
    disciplinas = ler("disciplinas")
    por_periodo = {}
    for d in disciplinas:
        por_periodo.setdefault(int(d["periodo_id"]), []).append(d)
    cidades = {c["cidade_id"]: float(c["distancia_rodoviaria_aprox_km"]) for c in ler("cidades")}

    alunos = [a for a in ler("alunos") if int(a["aluno_id"]) <= BASE_ALUNOS]
    enderecos = [e for e in ler("enderecos_alunos") if int(e["aluno_id"]) <= BASE_ALUNOS]
    perfis = [p for p in ler("perfis_socioeconomicos") if int(p["aluno_id"]) <= BASE_ALUNOS]
    bolsas = [b for b in ler("bolsas_alunos") if int(b["aluno_id"]) <= BASE_ALUNOS]
    matriculas = [m for m in ler("matriculas_curso") if int(m["aluno_id"]) <= BASE_ALUNOS]
    docentes = [d for d in ler("docentes") if int(d["docente_id"]) <= BASE_DOCENTES] + docentes_novos()
    turmas = [t for t in ler("turmas") if int(t["turma_id"]) <= BASE_TURMAS]
    registros = [r for r in ler("registros_academicos") if int(r["matricula_curso_id"]) <= BASE_ALUNOS]
    indicadores = [i for i in ler("indicadores_risco") if int(i["matricula_curso_id"]) <= BASE_ALUNOS]
    desfechos = [d for d in ler("desfechos_alunos") if int(d["matricula_curso_id"]) <= BASE_ALUNOS]

    # distribuições tiradas dos próprios dados originais
    peso_cidade = {c: 1 for c in cidades}
    for e in enderecos:
        peso_cidade[e["cidade_id"]] += 1
    logradouros = sorted({e["logradouro_sintetico"] for e in enderecos})
    bairros = sorted({e["bairro_sintetico"] for e in enderecos})

    # turmas por (disciplina, semestre) com a ocupação atual; seção nova quando todas estão cheias
    secoes, ocupacao = {}, {}
    for t in turmas:
        sem = SEMESTRES.index((int(t["ano_letivo"]), int(t["semestre_letivo"])))
        secoes.setdefault((t["disciplina_id"], sem), []).append(t)
        ocupacao[t["turma_id"]] = 0
    for r in registros:
        ocupacao[r["turma_id"]] += 1
    proximo_docente = cycle(rnd.sample(range(1, TOTAL_DOCENTES + 1), TOTAL_DOCENTES))

    def turma_com_vaga(disciplina, sem):
        lista = secoes[(disciplina["disciplina_id"], sem)]
        for t in lista:
            if ocupacao[t["turma_id"]] < VAGAS:
                break
        else:
            a = lista[0]
            letra = chr(ord("A") + len(lista))
            t = dict(a, turma_id=str(len(turmas) + 1), docente_id=str(next(proximo_docente)),
                     codigo_turma=a["codigo_turma"][:-1] + letra)
            turmas.append(t)
            lista.append(t)
            ocupacao[t["turma_id"]] = 0
        ocupacao[t["turma_id"]] += 1
        return t

    proximo_bolsa = max(int(b["bolsa_aluno_id"]) for b in bolsas) + 1
    proximo_registro = max(int(r["registro_id"]) for r in registros) + 1

    for i in range(BASE_ALUNOS + 1, TOTAL_ALUNOS + 1):
        sid = str(i)
        periodo = (i - BASE_ALUNOS - 1) % 8 + 1  # coortes do mesmo tamanho, como no original
        sem0 = ATUAL - (periodo - 1)
        ano, semestre = SEMESTRES[sem0]
        ingresso = f"{ano}-{'02' if semestre == 1 else '08'}-01"

        alunos.append({"aluno_id": sid, "codigo_academico": f"AES{i:04d}", "nome_sintetico": f"Estudante Sintético {i:03d}",
                       "data_nascimento": data_aleatoria(date(1988, 1, 1), date(2008, 12, 31)),
                       "genero_autodeclarado": sorteio({"F": 49, "M": 38, "NÃO_INFORMADO": 33}), "origem_dado": "SINTETICO"})

        cidade = sorteio(peso_cidade)
        dist = cidades[cidade]
        tempo = rnd.randint(8, 42) if dist == 0 else round(dist * 1.05 + rnd.uniform(10, 45))
        enderecos.append({"endereco_id": sid, "aluno_id": sid, "cidade_id": cidade,
                          "logradouro_sintetico": rnd.choice(logradouros), "numero_sintetico": str(rnd.randint(24, 1865)),
                          "complemento_sintetico": f"Apto {rnd.randint(1, 12)}{rnd.randint(1, 10):02d}" if rnd.random() < 0.22 else "",
                          "bairro_sintetico": rnd.choice(bairros),
                          "cep_sintetico": f"{rnd.randint(72000, 79999)}-{rnd.randint(0, 999):03d}",
                          "tempo_deslocamento_min": str(tempo)})

        trabalha = rnd.random() < 0.64
        horas = sorteio({20: 20, 30: 16, 40: 31, 44: 10}) if trabalha else 0
        renda_pessoal = rnd.uniform(500, 6500) * (0.5 + horas / 88) if trabalha else 0
        renda_familiar = limitar(rnd.lognormvariate(8.5, 0.6), 900, 26000)
        renda_familiar = max(renda_familiar, renda_pessoal + rnd.uniform(0, 2000))
        pessoas = rnd.randint(1, 6)
        internet = sorteio({"BOA": 63, "REGULAR": 43, "INSTAVEL": 14})
        perfis.append({"perfil_id": sid, "aluno_id": sid, "data_referencia": REFERENCIA,
                       "renda_pessoal_mensal": num(renda_pessoal, 2), "renda_familiar_mensal": num(renda_familiar, 2),
                       "pessoas_domicilio": str(pessoas), "trabalha": str(int(trabalha)), "horas_trabalho_semana": str(horas),
                       "dependentes": sorteio({"0": 91, "1": 20, "2": 9}),
                       "primeira_geracao_superior": str(int(rnd.random() < 0.47)), "qualidade_internet": internet,
                       "escola_publica_origem": str(int(rnd.random() < 0.37))})

        per_capita = renda_familiar / pessoas
        bolsista = rnd.random() < (0.6 if per_capita < 1500 else 0.35)
        if bolsista:
            tipo = sorteio({"1": 35, "2": 55, "4": 10} if per_capita < 1500 else {"2": 50, "3": 20, "4": 30})
            bolsas.append({"bolsa_aluno_id": str(proximo_bolsa), "aluno_id": sid, "tipo_bolsa_id": tipo,
                           "data_inicio": ingresso, "data_fim": "", "status": "ATIVA"})
            proximo_bolsa += 1

        matriculas.append({"matricula_curso_id": sid, "aluno_id": sid, "curso_id": "1", "data_ingresso": ingresso,
                           "ano_ingresso": str(ano), "semestre_ingresso": str(semestre), "periodo_atual": str(periodo),
                           "turno": "Noturno" if rnd.random() < 0.93 else "Matutino", "status": "ATIVO",
                           "forma_ingresso": sorteio({"Transferência": 41, "ENEM": 31, "Segunda graduação": 26, "Vestibular": 22}),
                           "data_referencia": REFERENCIA})

        # perfil acadêmico do aluno: uma parte tem dificuldade (gera as reprovações e a evasão)
        dificuldade = rnd.random() < 0.22
        habilidade = rnd.gauss(61, 8) if dificuldade else rnd.gauss(79, 9)
        freq_base = limitar(rnd.gauss(82 if dificuldade else 90, 5) - 3 * (horas >= 40) - 3 * (dist > 60), 50, 99)
        tendencia = rnd.gauss(-1 if dificuldade else 0.3, 0.8)

        def cursar(disciplina, sem, tentativa, bonus=0):
            nonlocal proximo_registro
            t = turma_com_vaga(disciplina, sem)
            media = habilidade + bonus + tendencia * (sem - sem0) - 25 * (float(disciplina["indice_dificuldade_sintetico"]) - 0.3)
            n1, n2 = (round(limitar(rnd.gauss(media, 9)), 1) for _ in range(2))
            projeto = round(limitar(rnd.gauss(media + 4, 8)), 1)
            freq = round(limitar(rnd.gauss(freq_base, 5), 30), 1)
            ch = int(disciplina["carga_horaria"])
            final = None
            if sem == ATUAL:
                situacao = "EM_CURSO"
                n2, projeto = [None if rnd.random() < falta else v for v, falta in ((n2, 0.45), (projeto, 0.53))]
                notas = [(n, p) for n, p in ((n1, 0.3), (n2, 0.3), (projeto, 0.4)) if n is not None]
                parcial = sum(n * p for n, p in notas) / sum(p for _, p in notas)
            else:
                final = 0.3 * n1 + 0.3 * n2 + 0.4 * projeto
                parcial = (n1 + n2 + projeto) / 3
                situacao = ("REPROVADO_FREQUENCIA" if freq < 75 else "REPROVADO_NOTA" if final < 60 else "APROVADO")
            registros.append({"registro_id": str(proximo_registro), "matricula_curso_id": sid, "turma_id": t["turma_id"],
                              "tentativa": str(tentativa), "situacao": situacao, "nota_n1": num(n1), "nota_n2": num(n2),
                              "nota_projeto": num(projeto), "nota_parcial": num(parcial), "nota_final": num(final),
                              "frequencia_percentual": "" if rnd.random() < 0.004 else num(freq),  # raros nulos, como no original
                              "faltas_horas": str(round(ch * (100 - freq) / 100)), "carga_horaria_cursada": str(ch),
                              "data_atualizacao": f"{SEMESTRES[sem][0]}-{'06-30' if SEMESTRES[sem][1] == 1 else '12-15'}"})
            proximo_registro += 1
            return situacao

        for q in range(1, periodo + 1):
            sem = sem0 + q - 1
            for d in por_periodo[q]:
                # recuperação: refaz no semestre seguinte, se ele já terminou (2026-2 só tem o período normal)
                if cursar(d, sem, 1).startswith("REPROVADO") and sem + 1 < ATUAL and rnd.random() < 0.6:
                    cursar(d, sem + 1, 2, bonus=5)

    # indicadores e desfecho de cada aluno novo
    meus = {}
    for r in registros:
        meus.setdefault(r["matricula_curso_id"], []).append(r)
    turma_sem = {t["turma_id"]: SEMESTRES.index((int(t["ano_letivo"]), int(t["semestre_letivo"]))) for t in turmas}
    perfil_de = {p["aluno_id"]: p for p in perfis}
    bolsistas = {b["aluno_id"] for b in bolsas}
    dist_de = {e["aluno_id"]: cidades[e["cidade_id"]] for e in enderecos}
    chance_evasao = {"BAIXO": 0.04, "MODERADO": 0.18, "ALTO": 0.22, "CRITICO": 0.5}  # taxas do original por classe

    for i in range(BASE_ALUNOS + 1, TOTAL_ALUNOS + 1):
        sid = str(i)
        rs = meus[sid]
        finais = [float(r["nota_final"]) for r in rs if r["nota_final"]]
        parciais = [float(r["nota_parcial"]) for r in rs if r["situacao"] == "EM_CURSO" and r["nota_parcial"]]
        freqs = [float(r["frequencia_percentual"]) for r in rs if r["frequencia_percentual"]]
        atual = sum(parciais) / len(parciais)
        historica = sum(finais) / len(finais) if finais else atual
        freq = sum(freqs) / len(freqs)
        reprovacoes = sum(r["tentativa"] == "1" and r["situacao"].startswith("REPROVADO") for r in rs)
        por_sem = {}
        for r in rs:
            nota = r["nota_final"] or r["nota_parcial"]
            if nota:
                por_sem.setdefault(turma_sem[r["turma_id"]], []).append(float(nota))
        xs = sorted(por_sem)
        ys = [sum(por_sem[x]) / len(por_sem[x]) for x in xs]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        var = sum((x - mx) ** 2 for x in xs)
        inclinacao = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var if var else 0

        p = perfil_de[sid]
        per_capita = float(p["renda_familiar_mensal"]) / int(p["pessoas_domicilio"])
        motivos = {  # heurística explicável: cada motivo soma pontos ao score
            "nota_parcial_baixa": (atual < 65, (65 - atual) * 1.5),
            "frequencia_baixa": (freq < 78, (78 - freq) * 3),
            "reprovacoes_acumuladas": (reprovacoes > 0, min(reprovacoes, 6) * 5),
            "alta_carga_de_trabalho": (int(p["horas_trabalho_semana"]) >= 40, 6),
            "deslocamento_longo": (dist_de[sid] > 60, 6),
            "internet_instavel": (p["qualidade_internet"] == "INSTAVEL", 5),
            "vulnerabilidade_sem_bolsa": (per_capita < 1000 and sid not in bolsistas, 8),
            "tendencia_de_queda": (len(xs) >= 3 and inclinacao < -3, 6),
        }
        ativos = [m for m, (sim, _) in motivos.items() if sim]
        score = limitar(1.5 + sum(pontos for sim, pontos in motivos.values() if sim), 1.5, 98)
        classe = "BAIXO" if score < 21 else "MODERADO" if score < 45 else "ALTO" if score < 70 else "CRITICO"
        indicadores.append({"indicador_id": sid, "matricula_curso_id": sid, "data_referencia": REFERENCIA,
                            "media_historica": num(historica, 2), "media_periodo_atual": num(atual, 2),
                            "frequencia_media": num(freq, 2), "reprovacoes": str(reprovacoes),
                            "tendencia_nota_por_periodo": num(inclinacao, 3), "score_risco_percentual": num(score, 2),
                            "classificacao_risco": classe, "motivos_risco": "|".join(ativos) or "sem_indicador_critico"})
        evadiu = rnd.random() < chance_evasao[classe]
        desfechos.append({"desfecho_id": sid, "matricula_curso_id": sid, "inicio_janela": REFERENCIA,
                          "fim_janela": "2027-07-31", "evasao_observada": str(int(evadiu)),
                          "tipo_desfecho": "EVASAO" if evadiu else "PERMANENCIA",
                          "data_evento_ou_censura": data_aleatoria(date(2027, 1, 1), date(2027, 7, 31)) if evadiu else "2027-07-31"})

    for tabela, linhas in [("docentes", docentes), ("alunos", alunos), ("enderecos_alunos", enderecos),
                           ("perfis_socioeconomicos", perfis), ("bolsas_alunos", bolsas), ("matriculas_curso", matriculas),
                           ("turmas", turmas), ("registros_academicos", registros), ("indicadores_risco", indicadores),
                           ("desfechos_alunos", desfechos)]:
        gravar(tabela, linhas)
        print(f"{tabela:24} {len(linhas)}")


if __name__ == "__main__":
    main()
