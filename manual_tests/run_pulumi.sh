#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
env_file="${script_dir}/.env"
project_dir="${repo_root}/server_shield/pulumi_project"

set -a
source "${env_file}"
set +a

exec pulumi up --cwd "${project_dir}"
