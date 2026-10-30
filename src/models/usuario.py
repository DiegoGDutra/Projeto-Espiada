"""Usuários do sistema (tabela usuario): cadastro com validação e conferência de senha."""
import re

from werkzeug.security import check_password_hash, generate_password_hash

from models.banco import ErroModelo, consultar, transacao

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
SENHA_FORTE = re.compile(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}")


def autenticar(login, senha):
    """O usuário se login e senha conferem; senão None."""
    achado = consultar("SELECT * FROM usuario WHERE login = ?", login)
    if achado and check_password_hash(achado[0]["senha_hash"], str(senha)):
        return achado[0]
    return None


def criar(login, perfil, nome, senha, vinculo=None):
    """Valida e grava um usuário. vinculo = matrícula do aluno ou docente_id do professor."""
    login = str(login).strip().lower()
    if not EMAIL.fullmatch(login):
        raise ErroModelo(400, "login deve ser um e-mail")
    if not SENHA_FORTE.fullmatch(str(senha)):
        raise ErroModelo(400, "senha precisa de 8+ caracteres com maiúscula, minúscula, número e caractere especial")
    aluno_id = docente_id = None
    if perfil == "aluno":
        achado = consultar("SELECT aluno_id FROM alunos WHERE codigo_academico = ?", vinculo)
        if not achado:
            raise ErroModelo(400, "vinculo deve ser a matrícula de um aluno existente")
        aluno_id = achado[0]["aluno_id"]
    elif perfil == "professor":
        achado = consultar("SELECT docente_id FROM docentes WHERE docente_id = ?", vinculo)
        if not achado:
            raise ErroModelo(400, "vinculo deve ser o docente_id de um docente existente")
        docente_id = achado[0]["docente_id"]
    with transacao() as con:  # perfil inválido ou vínculo/login repetido: o banco recusa
        con.execute("INSERT INTO usuario VALUES (?, ?, ?, ?, ?, ?)",
                    (login, perfil, nome, generate_password_hash(str(senha)), aluno_id, docente_id))
    return {"login": login, "perfil": perfil, "nome": nome, "aluno_id": aluno_id, "docente_id": docente_id}
