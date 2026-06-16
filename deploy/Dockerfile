FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app

RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --extra full || uv sync --extra full

COPY . .
RUN chmod +x deploy/entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["deploy/entrypoint.sh"]
