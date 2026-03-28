FROM python:3.14-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://get.pulumi.com | sh
ENV PATH="/root/.pulumi/bin:/app/.venv/bin:${PATH}"

COPY server_shield /app
RUN pip install uv && uv sync --frozen --group dev
RUN chmod +x /app/docker/run_component.sh /app/docker/entrypoint.sh

ENTRYPOINT ["/app/docker/entrypoint.sh"]
