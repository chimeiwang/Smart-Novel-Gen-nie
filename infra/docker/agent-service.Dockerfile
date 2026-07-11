# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.8.15 AS uv

FROM python:3.12-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock .python-version ./
COPY packages/service-auth/pyproject.toml packages/service-auth/pyproject.toml
COPY packages/service-auth/src packages/service-auth/src
COPY packages/service-contracts/pyproject.toml packages/service-contracts/pyproject.toml
COPY packages/service-contracts/src packages/service-contracts/src
COPY apps/agent-service/pyproject.toml apps/agent-service/pyproject.toml
COPY apps/agent-service/src apps/agent-service/src
RUN uv sync --frozen --no-dev --no-editable --package inkforge-agent-service

FROM python:3.12-slim AS runtime
RUN groupadd --gid 10001 inkforge && useradd --uid 10001 --gid 10001 --no-create-home inkforge
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv
USER 10001:10001
EXPOSE 8001
CMD ["uvicorn", "inkforge_agents.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001", "--workers", "1", "--no-access-log"]
