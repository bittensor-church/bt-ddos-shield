#!/usr/bin/env bash
set -euo pipefail

run_loop() {
  local component="$1"
  shift
  while true; do
    if /app/docker/run_component.sh "$component" "$@"; then
      :
    else
      status=$?
      printf '[%s] command exited with status %s\n' "$component" "$status"
    fi
    sleep 60
  done
}

run_loop pulumi-runner server-shield-pulumi &
run_loop chain-reader server-shield-chain-reader &
run_loop chain-writer server-shield-chain-writer &

wait
