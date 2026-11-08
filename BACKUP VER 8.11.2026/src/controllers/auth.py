"""Login, logout, sessão e cadastro de usuários. Também barra a API para quem não fez login."""
import time

import click
from flask import Blueprint, abort, current_app, jsonify, request, session

from controllers.comum import exige, ler_json
from models import usuario
from models.banco import ErroModelo, criar_banco

bp = Blueprint("auth", __name__, cli_group=None)  # cli_group=None: o comando fica "flask criar-usuario"

MAX_FALHAS, BLOQUEIO_S = 5, 15 * 60
falhas = {}  # login -> horários das últimas senhas erradas (fica em memória, zera ao reiniciar)


@bp.before_app_request
def exige_login():
    if request.path.startswith("/api/") and request.path != "/api/login" and "login" not in session:
        abort(401, "faça login")


@bp.post("/api/login")
def entrar():
    dados = ler_json("login", "senha")
    login = str(dados["login"]).strip().lower()
    agora = time.time()
    recentes = [t for t in falhas.get(login, []) if agora - t < BLOQUEIO_S]
    if len(recentes) >= MAX_FALHAS:
        abort(429, "muitas tentativas erradas; tente de novo em 15 minutos")
    u = usuario.autenticar(login, dados["senha"])
    if not u:
        falhas[login] = recentes + [agora]
        current_app.logger.warning("login falhou: %s (%s)", login, request.remote_addr)
        abort(401, "usuário ou senha inválidos")
    falhas.pop(login, None)
    session.clear()
    session.update(login=u["login"], perfil=u["perfil"], nome=u["nome"],
                   aluno_id=u["aluno_id"], docente_id=u["docente_id"])
    return sessao_atual()


@bp.post("/api/logout")
def sair():
    session.clear()
    return jsonify(ok=True)


@bp.get("/api/sessao")
def sessao_atual():
    return jsonify({k: session[k] for k in ("login", "perfil", "nome")})


@bp.post("/api/usuarios")
def cadastrar_usuario():
    exige("secretaria")  # só a secretaria cadastra perfis
    d = ler_json("login", "perfil", "nome", "senha")
    return jsonify(usuario.criar(d["login"], d["perfil"], d["nome"], d["senha"], d.get("vinculo"))), 201


@bp.cli.command("criar-usuario")
@click.argument("login")
@click.argument("perfil", type=click.Choice(["aluno", "professor", "secretaria"]))
@click.argument("nome")
@click.option("--vinculo", help="matrícula do aluno ou docente_id do professor")
@click.password_option("--senha")
def criar_usuario_cli(login, perfil, nome, vinculo, senha):
    """Cadastra um usuário pelo terminal (o primeiro da secretaria nasce assim)."""
    criar_banco()
    try:
        click.echo(usuario.criar(login, perfil, nome, senha, vinculo))
    except ErroModelo as e:
        raise click.ClickException(e.mensagem)
