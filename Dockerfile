# Imagem da aplicação Espiada. Quem monta é o docker compose (ver docker-compose.yml).
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_ROOT_USER_ACTION=ignore
WORKDIR /espiada

# as dependências vêm antes do código: mudar o código não reinstala tudo
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY scripts/ scripts/
COPY dados/ dados/
COPY testes/ testes/

# o servidor não roda como root
RUN useradd --system --no-create-home espiada
USER espiada

EXPOSE 5000
# a primeira subida importa o dataset e treina o modelo, por isso a tolerância inicial é longa
HEALTHCHECK --interval=10s --timeout=3s --start-period=180s --retries=3 \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:5000/sobre.html', timeout=2)"]

CMD ["python", "scripts/iniciar.py"]
