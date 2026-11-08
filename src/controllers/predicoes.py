"""Recálculo das predições de todos os alunos (regras + LLM): roda em segundo plano e o andamento fica numa consulta.
Só a secretaria dispara. Também existe como comando de terminal:  flask --app src/Espiada.py recalcular-predicoes"""
import threading

import click
from flask import Blueprint, abort, jsonify, request

from controllers.comum import exige
from models import llm, predicao
from models.banco import ErroModelo, criar_banco

bp = Blueprint("predicoes", __name__, cli_group=None)  # cli_group=None: o comando fica "flask recalcular-predicoes"

trava = threading.Lock()
andamento = {"estado": "ocioso"}  # ocioso | rodando | concluido | erro (fica em memória, zera ao reiniciar)


def _rodar(forcar):
    """Corpo da thread do recálculo: atualiza o andamento a cada aluno e nunca morre calada."""
    try:
        resumo = predicao.recalcular_todos(forcar, ao_progredir=andamento.update)
        if resumo["interrompido"]:
            andamento.update(resumo, estado="erro", erro="a LLM falhou várias vezes seguidas; recálculo interrompido")
        else:
            andamento.update(resumo, estado="concluido")
    except Exception as e:
        andamento.update(estado="erro", erro=str(e))


@bp.post("/api/predicoes/recalcular")
def recalcular():
    """Dispara o recálculo (202). ?forcar=1 reanalisa também quem não mudou desde a última análise da LLM."""
    exige("secretaria")
    with trava:
        if andamento["estado"] == "rodando":
            abort(409, "já existe um recálculo em andamento")
        llm.verificar()  # 503 na hora se o Ollama estiver fora, em vez de falhar dentro da thread
        andamento.clear()
        andamento.update(estado="rodando", total=0, feitos=0, puladas=0, falhas=0)
        threading.Thread(target=_rodar, args=(request.args.get("forcar") == "1",), daemon=True).start()
        return jsonify(dict(andamento)), 202


@bp.get("/api/predicoes/recalculo")
def andamento_do_recalculo():
    exige("secretaria")
    return jsonify(dict(andamento))


@bp.cli.command("recalcular-predicoes")
@click.option("--forcar", is_flag=True, help="reanalisa também quem não mudou desde a última análise")
def recalcular_cli(forcar):
    """Gera a predição (regras + LLM) de todos os alunos; quem não mudou é pulado."""
    criar_banco()

    def mostrar(r):
        click.echo(f"\r{r['feitos'] + r['puladas'] + r['falhas']}/{r['total']}  analisados {r['feitos']}  "
                   f"pulados {r['puladas']}  falhas {r['falhas']}", nl=False)

    try:
        resumo = predicao.recalcular_todos(forcar, ao_progredir=mostrar)
    except ErroModelo as e:
        raise click.ClickException(e.mensagem)
    click.echo()
    if resumo["interrompido"]:
        raise click.ClickException("a LLM falhou várias vezes seguidas; recálculo interrompido")
