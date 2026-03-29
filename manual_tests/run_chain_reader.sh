#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
env_file="${script_dir}/.env"

set -a
source "${env_file}"
set +a

cd "$script_dir"/..
cd server_shield
exec uv run python -m server_shield.shared.supervisor local-dev-chain-reader server-shield-chain-reader
