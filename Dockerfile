FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

# torch so CPU: o wheel padrao do PyPI traz bibliotecas CUDA (varios GB) que uma VPS sem GPU nunca usa.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip install .

# O modelo de embeddings vai dentro da imagem: o primeiro start nao depende da internet.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"
ENV HF_HUB_OFFLINE=1

RUN useradd --system --uid 10001 --no-create-home app && chmod -R a+rX /opt/hf-cache
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

# So o proxy alcanca esta porta (ver docker-compose.yml), entao o X-Forwarded-For dele e confiavel.
# Sem isso o limite de requisicoes veria todos os visitantes como o IP do proxy.
CMD ["uvicorn", "piscinow.web.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
