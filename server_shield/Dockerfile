FROM python:3.14-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
# SHA-256 digests of the linux release archives published on GitHub.
ARG PULUMI_VERSION=3.271.0
ARG PULUMI_SHA256_AMD64=48b92e1584cf10649e43add7b4750e8be71231976f0cf25c94148a7ed254a01f
ARG PULUMI_SHA256_ARM64=d8889833c6cfd8e1393e765f85891fd93af47651c1db08c54a11750b5c11df1c
# Keep equal to pulumi-aws in uv.lock, otherwise Pulumi downloads the locked version unverified at runtime.
ARG PULUMI_AWS_PLUGIN_VERSION=7.23.0
ARG PULUMI_AWS_PLUGIN_SHA256_AMD64=f5c585152bbacf11a0c02376ade122b7e74095e9b2f98dd291cbec1d880e7b4c
ARG PULUMI_AWS_PLUGIN_SHA256_ARM64=c6070f8d8ae740e617dd8e7de974b39d9f27d4f9703ec67b5413932572034592

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.pulumi/bin:/app/.venv/bin:${PATH}"
RUN set -eu; \
    arch="$(dpkg --print-architecture)"; \
    case "${arch}" in \
        amd64) pulumi_arch=x64 pulumi_sha256="${PULUMI_SHA256_AMD64}" aws_sha256="${PULUMI_AWS_PLUGIN_SHA256_AMD64}" ;; \
        arm64) pulumi_arch=arm64 pulumi_sha256="${PULUMI_SHA256_ARM64}" aws_sha256="${PULUMI_AWS_PLUGIN_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    download() { curl -fsSL -o "$1" "$2"; echo "$3  $1" | sha256sum -c -; }; \
    download /tmp/pulumi.tar.gz \
        "https://github.com/pulumi/pulumi/releases/download/v${PULUMI_VERSION}/pulumi-v${PULUMI_VERSION}-linux-${pulumi_arch}.tar.gz" \
        "${pulumi_sha256}"; \
    mkdir -p /root/.pulumi/bin; \
    tar -xzf /tmp/pulumi.tar.gz -C /root/.pulumi/bin --strip-components=1; \
    download /tmp/pulumi-resource-aws.tar.gz \
        "https://github.com/pulumi/pulumi-aws/releases/download/v${PULUMI_AWS_PLUGIN_VERSION}/pulumi-resource-aws-v${PULUMI_AWS_PLUGIN_VERSION}-linux-${arch}.tar.gz" \
        "${aws_sha256}"; \
    pulumi plugin install resource aws "${PULUMI_AWS_PLUGIN_VERSION}" --file /tmp/pulumi-resource-aws.tar.gz; \
    rm /tmp/pulumi.tar.gz /tmp/pulumi-resource-aws.tar.gz

COPY --from=ghcr.io/astral-sh/uv:0.13.4@sha256:9f130421e930bfbdc563c00740466603f8723158e90297d07957c2294640262b /uv /uvx /bin/
# uv installs the Python packages, so pip and the certifi bundle it vendors are not needed.
RUN python -m pip uninstall --yes pip && rm -f /usr/local/bin/pip

COPY server_shield /app
RUN uv sync --frozen --group dev
COPY server_shield/docker/shield-pulumi /usr/local/bin/shield-pulumi
RUN chmod +x /app/docker/run_component.sh /app/docker/entrypoint.sh /usr/local/bin/shield-pulumi

ENTRYPOINT ["/app/docker/entrypoint.sh"]
