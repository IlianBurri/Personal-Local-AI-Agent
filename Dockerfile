# syntax=docker/dockerfile:1

# ---------- Stage 1: build the React/Vite frontend ----------
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY ui/web/package.json ui/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/web/ ./
RUN npm run build

# ---------- Stage 2: Python runtime (Flask server) ----------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARCA_HOST=0.0.0.0 \
    ARCA_PORT=8765

WORKDIR /app

# Install Python dependencies first so this layer caches well.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App sources (venv/node_modules/data/dist are excluded via .dockerignore).
COPY . .

# Fresh frontend bundle from stage 1.
COPY --from=frontend-build /build/dist ui/web/dist

# Run as an unprivileged user; config lives under HOME
# (~/.config/arca/config.json) and the SQLite DB under /app/data.
RUN useradd --create-home --uid 1000 arca && chown -R arca:arca /app
USER arca

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/', timeout=2)"

# server.app.run() honors ARCA_HOST/ARCA_PORT from the env above
# (Flask's own app.run() would ignore them and bind 127.0.0.1:5000).
CMD ["python", "-c", "from server.app import run; run()"]
