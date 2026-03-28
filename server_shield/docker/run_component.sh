#!/usr/bin/env bash
set -euo pipefail

component="$1"
shift

python -m server_shield.shared.supervisor "$component" "$@"
