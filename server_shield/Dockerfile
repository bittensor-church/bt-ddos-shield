FROM python:3.14-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ARG PULUMI_VERSION=3.228.0
ARG PULUMI_AWS_PLUGIN_VERSION=7.23.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://get.pulumi.com | sh -s -- --version "${PULUMI_VERSION}"
ENV PATH="/root/.pulumi/bin:/app/.venv/bin:${PATH}"
RUN pulumi plugin install resource aws "${PULUMI_AWS_PLUGIN_VERSION}" --exact

COPY server_shield /app
RUN pip install uv && uv sync --frozen --group dev
RUN chmod +x /app/docker/run_component.sh /app/docker/entrypoint.sh

ENTRYPOINT ["/app/docker/entrypoint.sh"]
