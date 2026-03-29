# Manual Pulumi Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual test helper that loads `manual_tests/.env` and runs `pulumi preview` from the repository's Pulumi project directory.

**Architecture:** Keep the helper as a small shell script under `manual_tests/` so it can be run directly by a developer without touching the Python runtime. Verify it with a focused pytest file that runs the script against a stub `pulumi` binary and checks that `manual_tests/.env` uses the current `SERVER_SHIELD_*` schema.

**Tech Stack:** Bash, pytest, pathlib, subprocess

---

### Task 1: Add coverage for the manual helper

**Files:**
- Create: `server_shield/tests/manual_tests/test_preview_pulumi_script.py`
- Test: `server_shield/tests/manual_tests/test_preview_pulumi_script.py`

- [ ] **Step 1: Write the failing test**

```python
def test_preview_script_runs_pulumi_preview_from_pulumi_project():
    ...


def test_manual_env_uses_current_server_shield_names():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/junie/synced_p/new_bittensor_ddos_shield/server_shield && python -m pytest tests/manual_tests/test_preview_pulumi_script.py -v`
Expected: FAIL because `manual_tests/preview_pulumi.sh` does not exist yet and `manual_tests/.env` still contains legacy variable names.

- [ ] **Step 3: Commit**

```bash
git add server_shield/tests/manual_tests/test_preview_pulumi_script.py
git commit -m "test: cover manual pulumi preview helper"
```

### Task 2: Implement the helper and env update

**Files:**
- Create: `manual_tests/preview_pulumi.sh`
- Modify: `manual_tests/.env`
- Test: `server_shield/tests/manual_tests/test_preview_pulumi_script.py`

- [ ] **Step 1: Write minimal implementation**

```bash
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

exec pulumi preview --cwd "${project_dir}"
```

```dotenv
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
SERVER_SHIELD_PULUMI__AWS_REGION=eu-north-1
SERVER_SHIELD_PULUMI__MINER_INSTANCE_ID=i-...
SERVER_SHIELD_PULUMI__MINER_PORT=9001
SERVER_SHIELD_PULUMI__HOSTED_ZONE_ID=Z...
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /Users/junie/synced_p/new_bittensor_ddos_shield/server_shield && python -m pytest tests/manual_tests/test_preview_pulumi_script.py -v`
Expected: PASS with 2 passed.

- [ ] **Step 3: Commit**

```bash
git add manual_tests/.env manual_tests/preview_pulumi.sh server_shield/tests/manual_tests/test_preview_pulumi_script.py
git commit -m "feat: add manual pulumi preview helper"
```
