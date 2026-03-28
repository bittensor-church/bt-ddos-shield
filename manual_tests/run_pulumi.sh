#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
env_file="${script_dir}/.env"
project_dir="${repo_root}/server_shield/pulumi_project"

if [[ ! -f "${env_file}" ]]; then
  echo "Missing env file: ${env_file}" >&2
  exit 1
fi

if [[ ! -d "${project_dir}" ]]; then
  echo "Missing Pulumi project directory: ${project_dir}" >&2
  exit 1
fi

set -a
source "${env_file}"
set +a

PULUMI_CONFIG_PASSPHRASE="" exec pulumi up --cwd "${project_dir}"
