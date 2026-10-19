# ── Build stage ───────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Security: run as non-root user
RUN addgroup --system shoply && adduser --system --group shoply

WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

USER shoply

EXPOSE 8000

# Render supplies PORT at runtime. One worker keeps the free instance within its memory limit.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}"]
