# syntax=docker/dockerfile:1.7

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends wget \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 kubo

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

USER kubo
EXPOSE 8084

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD wget -qO- http://localhost:8084/api/v1/health || exit 1

# Malla interna (P-28, ADR-0020): con KUBO_INTERNAL_TLS=true uvicorn sirve
# HTTPS y exige el certificado del cliente (--ssl-cert-reqs 2).
CMD ["sh", "-c", "if [ \"$KUBO_INTERNAL_TLS\" = \"true\" ]; then exec uvicorn app.main:app --host 0.0.0.0 --port 8084 --workers 1 --ssl-keyfile \"$KUBO_TLS_KEY\" --ssl-certfile \"$KUBO_TLS_CERT\" --ssl-ca-certs \"$KUBO_TLS_CA\" --ssl-cert-reqs 2; else exec uvicorn app.main:app --host 0.0.0.0 --port 8084 --workers 1; fi"]
