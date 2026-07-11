# Orbit 生产镜像 — 多阶段构建 (S5)
# Stage 1: build — poetry + deps
FROM python:3.11-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir "poetry>=2.0"
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create true \
    && poetry install --only main --no-root --no-interaction

# Stage 2: run — minimal, no poetry, non-root
FROM python:3.11-slim AS runner
WORKDIR /app
COPY --from=builder /root/.cache/pypoetry /root/.cache/pypoetry
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY src/ ./src/
ENV PYTHONPATH=/app/src
RUN useradd -m -s /bin/bash orbit && chown -R orbit:orbit /app
USER orbit
EXPOSE 18888
CMD ["uvicorn", "orbit.api.main:app", "--host", "0.0.0.0", "--port", "18888"]
