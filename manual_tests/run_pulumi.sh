#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
env_file="${script_dir}/.env"
project_dir="${repo_root}/server_shield/pulumi_project"

set -a
source "${env_file}"
set +a
SERVER_SHIELD_STATE_DIR=$(realpath -- ${SERVER_SHIELD_STATE_DIR})

mkdir -p /tmp/pulumi-state
cd "$script_dir"/..
cd server_shield
exec uv run python -m server_shield.shared.supervisor local-dev-pulumi server-shield-pulumi
