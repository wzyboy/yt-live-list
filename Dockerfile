FROM ghcr.io/astral-sh/uv:0.11.17 AS uv

FROM python:3.14-slim-bookworm

COPY --from=uv /uv /uvx /bin/

ENV PATH='/app/.venv/bin:/usr/local/bin:/usr/bin:/bin' \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --locked --no-dev --no-editable

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "yt_live_list.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
