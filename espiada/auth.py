"""Autenticação e perfis (RF01, RF11, RN09, RN10, CA01).
Cada perfil faz só o que é dele: quem tenta outra função recebe 403 e a tentativa fica no log.
"""
import re
import time

import click
from flask import abort, current_app, request, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from .banco import consultar, criar_banco, transacao

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
SENHA_FORTE = re.compile(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}")  # RF01
MAX_FALHAS, BLOQUEIO_S = 5, 15 * 60
falhas = {}  # login -> horários das últimas senhas erradas. ponytail: em memória, zera ao reiniciar


def negar(motivo):
    current_app.logger.warning("acesso negado: %s (%s) %s %s - %s", session.get("login"), session.get("perfil"),
                               request.method, request.path, motivo)
    abort(403, "sem permissão: " + motivo)


def exige(*perfis):
    if session["perfil"] not in perfis:
        negar("função exclusiva de " + "/".join(perfis))


def exige_login():
    """Roda antes de toda requisição: a API só abre com login."""
    if request.path.startswith("/api/") and request.path != "/api/login" and "login" not in session:
        abort(401, "faça login")


def autenticar(login, senha):
    """Confere login e senha e devolve o usuário. 5 senhas erradas seguidas bloqueiam por 15 minutos."""
    login = str(login).strip().lower()
    agora = time.time()
    recentes = [t for t in falhas.get(login, []) if agora - t < BLOQUEIO_S]
    if len(recentes) >= MAX_FALHAS:
        abort(429, "muitas tentativas erradas; tente de novo em 15 minutos")
    achado = consultar("SELECT * FROM usuario WHERE login = ?", login)
    if not achado or not check_password_hash(achado[0]["senha_hash"], str(senha)):
        falhas[login] = recentes + [agora]
        current_app.logger.warning("login falhou: %s (%s)", login, request.remote_addr)
        abort(401, "usuário ou senha inválidos")
    falhas.pop(login, None)
    return achado[0]


def visiveis():
    """Filtro SQL dos alunos que o usuário logado pode ver (RN09, RN10)."""
    if session["perfil"] == "secretaria":
        return "1", ()
    if session["perfil"] == "professor":  # alunos que já passaram por alguma turma dele
        return """mc.matricula_curso_id IN (SELECT r.matricula_curso_id FROM registros_academicos r
                  JOIN turmas t USING (turma_id) WHERE t.docente_id = ?)""", (session["docente_id"],)
    return "a.aluno_id = ?", (session["aluno_id"],)


def criar_usuario(login, perfil, nome, senha, vinculo=None):
    """Valida e grava um usuário. vinculo = matrícula do aluno ou docente_id do professor."""
    login = str(login).strip().lower()
    if not EMAIL.fullmatch(login):
        abort(400, "login deve ser um e-mail")
    if not SENHA_FORTE.fullmatch(str(senha)):
        abort(400, "senha precisa de 8+ caracteres com maiúscula, minúscula, número e caractere especial")
    aluno_id = docente_id = None
    if perfil == "aluno":
        achado = consultar("SELECT aluno_id FROM alunos WHERE codigo_academico = ?", vinculo)
        if not achado:
            abort(400, "vinculo deve ser a matrícula de um aluno existente")
        aluno_id = achado[0]["aluno_id"]
    elif perfil == "professor":
        achado = consultar("SELECT docente_id FROM docentes WHERE docente_id = ?", vinculo)
        if not achado:
            abort(400, "vinculo deve ser o docente_id de um docente existente")
        docente_id = achado[0]["docente_id"]
    with transacao() as con:  # perfil inválido ou vínculo/login repetido: o banco recusa
        con.execute("INSERT INTO usuario VALUES (?, ?, ?, ?, ?, ?)",
                    (login, perfil, nome, generate_password_hash(str(senha)), aluno_id, docente_id))
    return {"login": login, "perfil": perfil, "nome": nome, "aluno_id": aluno_id, "docente_id": docente_id}


@click.command("criar-usuario")
@click.argument("login")
@click.argument("perfil", type=click.Choice(["aluno", "professor", "secretaria"]))
@click.argument("nome")
@click.option("--vinculo", help="matrícula do aluno ou docente_id do professor")
@click.password_option("--senha")
def criar_usuario_cli(login, perfil, nome, vinculo, senha):
    """Cadastra um usuário pelo terminal (o primeiro da secretaria nasce assim)."""
    criar_banco()
    try:
        click.echo(criar_usuario(login, perfil, nome, senha, vinculo))
    except HTTPException as e:
        raise click.ClickException(e.description)
