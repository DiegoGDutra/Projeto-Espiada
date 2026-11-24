"""Entrada do container da aplicação: prepara o banco e sobe o servidor.

Na primeira subida, importa o dataset e treina o modelo de risco. Nas seguintes, só confere as tabelas: os dados
existentes não são alterados. O servidor é o Waitress com um único processo e várias threads, porque o andamento do
recálculo e o bloqueio de login ficam na memória do processo.
"""
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))  # o sistema (models) fica em app/

import psycopg
from waitress import serve

from Espiada import app
from importar import importar
from models import alunos, modelo_risco, treino
from models.banco import ErroModelo, criar_banco

TENTATIVAS_BANCO = 30
THREADS = 8


def esperar_banco():
    """Cria as tabelas que faltam, tentando de novo enquanto o PostgreSQL ainda não aceita conexões."""
    for tentativa in range(1, TENTATIVAS_BANCO + 1):
        try:
            return criar_banco()
        except psycopg.OperationalError:
            if tentativa == TENTATIVAS_BANCO:
                raise
            print("Aguardando o banco de dados...", flush=True)
            time.sleep(2)


def preparar():
    esperar_banco()
    if not alunos.total():
        print("Banco vazio: importando o dataset...", flush=True)
        print(f"Importados {importar()['alunos']} alunos.", flush=True)
    if not modelo_risco.ja_treinado():
        print("Nenhum modelo treinado: treinando...", flush=True)
        try:
            r = treino.treinar()
            print(f"Modelo versão {r['id']}: {'aprovado' if r['aprovado'] else 'não aprovado'}.", flush=True)
        except ErroModelo as e:  # sem modelo o sistema continua funcionando só com as regras
            print(f"Treino não realizado: {e.mensagem}", flush=True)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # como processo 1 do container, sem isso o stop demora 10 s
    preparar()
    print("Espiada no ar: http://127.0.0.1:5000", flush=True)
    serve(app, host="0.0.0.0", port=5000, threads=THREADS, ident="espiada")
