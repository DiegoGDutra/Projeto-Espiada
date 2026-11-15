"""Entrega as telas (views/). O painel só abre para quem fez login."""
from pathlib import Path

from flask import Blueprint, redirect, send_file, session

bp = Blueprint("paginas", __name__)
VIEWS = Path(__file__).resolve().parent.parent / "views"


@bp.get("/")
def login():
    return send_file(VIEWS / "login.html")


@bp.get("/interface.html")
def interface():
    if "login" not in session:
        return redirect("/")
    return send_file(VIEWS / "interface.html")


@bp.get("/sobre.html")
def sobre():
    return send_file(VIEWS / "sobre.html")
