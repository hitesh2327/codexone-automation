# Admin API image (build from the repo root:  docker build -f api/Dockerfile .)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt ./requirements.txt
COPY api/requirements.txt ./api/requirements.txt
RUN pip install -r api/requirements.txt

COPY src ./src
COPY api ./api
COPY brand ./brand
COPY templates ./templates

RUN useradd --create-home app && mkdir -p data logs output && chown -R app /app
USER app
EXPOSE 8000
# Migrations first, then the server. X-Forwarded-For is trusted only from FORWARDED_ALLOW_IPS (default: none but
# localhost), so a visitor can't pick their own IP to dodge or pin rate limits (QA-M-05). Behind a reverse proxy
# set FORWARDED_ALLOW_IPS to its address, or CLIENT_IP_SOURCE=x-forwarded-for (see api/app/clientip.py).
CMD ["sh", "-c", "cd api && python migrate.py && cd .. && uvicorn api.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
