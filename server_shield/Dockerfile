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

COPY --from=ghcr.io/astral-sh/uv:0.13.4@sha256:9f130421e930bfbdc563c00740466603f8723158e90297d07957c2294640262b /uv /uvx /bin/
# uv installs the Python packages, so pip and the certifi bundle it vendors are not needed.
RUN python -m pip uninstall --yes pip && rm -f /usr/local/bin/pip

COPY server_shield /app
RUN uv sync --frozen --group dev
COPY server_shield/docker/shield-pulumi /usr/local/bin/shield-pulumi
RUN chmod +x /app/docker/run_component.sh /app/docker/entrypoint.sh /usr/local/bin/shield-pulumi

ENTRYPOINT ["/app/docker/entrypoint.sh"]
