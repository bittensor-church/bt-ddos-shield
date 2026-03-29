#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
env_file="${script_dir}/.env"
project_dir="${repo_root}/server_shield/pulumi_project"

set -a
source "${env_file}"
set +a

export AWS_ACCESS_KEY_ID="$SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY"
export PULUMI_CONFIG_PASSPHRASE=""

pulumi login --cwd "${project_dir}"  "${SERVER_SHIELD_PULUMI__BACKEND_URL}"
pulumi destroy --cwd "${project_dir}"
