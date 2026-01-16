# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

ENV UV_CACHE_DIR=/root/.cache/uv \
    UV_LINK_MODE=copy

# Prime dependency layer using pyproject metadata
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --extra server --no-install-project

# Copy project sources and install the package
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --extra server --no-editable


FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    UV_CACHE_DIR=/root/.cache/uv

COPY --from=builder /app /app

EXPOSE 8765

CMD ["uv", "run", "sf", "serve", "--host", "0.0.0.0", "--port", "8765"]
