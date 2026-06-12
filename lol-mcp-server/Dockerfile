# LoL MCP server — Streamable HTTP, for Render / Railway / Fly / any container host.
FROM python:3.12-slim

# Streamable HTTP on all interfaces; PORT is injected by the platform at runtime.
ENV PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=http \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Dependency + build metadata first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src

RUN uv sync --no-dev

EXPOSE 8000

# RIOT_API_KEY must be provided as an environment variable by the host —
# never bake secrets into the image.
CMD ["uv", "run", "--no-dev", "lol-mcp-server"]
