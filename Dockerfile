FROM node:22-alpine AS web
ENV SCARF_ANALYTICS=false
WORKDIR /web
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime-base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 healthos && useradd --create-home --uid 10001 --gid 10001 healthos
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts
COPY --from=web /web/dist ./frontend/dist
RUN mkdir -p /data /backups && chown -R healthos:healthos /app /data /backups
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')"
CMD ["python", "scripts/start.py"]

FROM runtime-base AS home-assistant
USER root

FROM runtime-base AS runtime
USER healthos
