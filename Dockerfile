FROM python:3.12-slim

ENV PORT=7860 \
    OLLAMA_HOST=http://127.0.0.1:11434 \
    OLLAMA_MODEL=gemma4:e2b \
    OLLAMA_PULL_MODEL=false \
    CASHBACK_DB_PATH=/app/data/cashback.db \
    CASHBACK_EVIDENCE_DIR=/app/data/evidence \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://ollama.com/install.sh | sh

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x start.sh

EXPOSE 7860
CMD ["./start.sh"]
