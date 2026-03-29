# Pulumi Backend and Stack Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Pulumi backend URL part of shared required config, move stack name into shared config with a default, and make first-run stack bootstrap automatic.

**Architecture:** The shared Pydantic settings object becomes the only production configuration source for Pulumi backend selection and stack naming. The Pulumi runner logs into the configured backend, selects or creates the configured stack, and then runs `pulumi up`, while README examples document exact local-file and S3 backend usage.

**Tech Stack:** Python 3.14, Pydantic Settings, pytest, Pulumi CLI, Docker

---

## File Map

- Modify: `server_shield/src/server_shield/shared/config.py`
  - Extend `PulumiSettings` with `backend_url` and `stack_name`
- Modify: `server_shield/src/server_shield/pulumi_runner/cli.py`
  - Remove direct environment access, use shared config, add `stack select --create`
- Modify: `server_shield/tests/shared/test_config.py`
  - Cover required backend URL and default stack name
- Modify: `server_shield/tests/pulumi_runner/test_cli.py`
  - Cover login, stack select/create, configured/default stack names
- Modify: `README.md`
  - Document required backend config and exact Docker commands for file and S3 backends

### Task 1: Shared Pulumi Config

**Files:**
- Modify: `server_shield/tests/shared/test_config.py`
- Modify: `server_shield/src/server_shield/shared/config.py`

- [ ] **Step 1: Write the failing config test for backend URL and default stack name**

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from server_shield.shared.config import get_config


def test_get_config_reads_pulumi_backend_and_default_stack_name(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SERVER_SHIELD_ENV", "test")
    monkeypatch.setenv("SERVER_SHIELD_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__BACKEND_URL", "file:///var/lib/server-shield/pulumi-state")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_READER__SUBTENSOR_ADDRESS", "ws://reader")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_READER__NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__SUBTENSOR_ADDRESS", "ws://writer")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")

    get_config.cache_clear()
    config = get_config()

    assert config.pulumi.backend_url == "file:///var/lib/server-shield/pulumi-state"
    assert config.pulumi.stack_name == "server-shield"


def test_get_config_requires_pulumi_backend_url(monkeypatch) -> None:
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__MINER_PORT", "9001")
    monkeypatch.delenv("SERVER_SHIELD_PULUMI__BACKEND_URL", raising=False)

    get_config.cache_clear()

    with pytest.raises(ValidationError):
        get_config()
```

- [ ] **Step 2: Run the config tests to verify the new expectations fail**

Run:
```bash
cd server_shield && uv run pytest tests/shared/test_config.py -v
```

Expected: FAIL because `PulumiSettings` does not yet expose `backend_url` or `stack_name`, and missing backend URL is not yet validated.

- [ ] **Step 3: Implement the minimal shared config change**

```python
from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class PulumiSettings(BaseModel):
    backend_url: str
    stack_name: str = "server-shield"
    aws_region: str
    hosted_zone_id: str
    miner_instance_id: str
    miner_port: int
```

Keep the rest of `AppConfig` unchanged.

- [ ] **Step 4: Run the config tests to verify they pass**

Run:
```bash
cd server_shield && uv run pytest tests/shared/test_config.py -v
```

Expected: PASS for all config tests.

- [ ] **Step 5: Commit the shared config change**

```bash
git add server_shield/src/server_shield/shared/config.py server_shield/tests/shared/test_config.py
git commit -m "feat: require pulumi backend config"
```

### Task 2: Pulumi Runner Bootstrap

**Files:**
- Modify: `server_shield/tests/pulumi_runner/test_cli.py`
- Modify: `server_shield/src/server_shield/pulumi_runner/cli.py`

- [ ] **Step 1: Write the failing Pulumi runner test for config-driven login and stack bootstrap**

```python
from pathlib import Path
from types import SimpleNamespace

from server_shield.pulumi_runner.cli import _invoke_pulumi, main


def test_invoke_pulumi_logs_in_selects_stack_and_runs_up(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0)

    config = SimpleNamespace(
        pulumi=SimpleNamespace(
            backend_url="s3://example-state-bucket/server-shield",
            stack_name="custom-stack",
        )
    )
    monkeypatch.setattr("server_shield.pulumi_runner.cli.get_config", lambda: config)
    monkeypatch.setattr("server_shield.pulumi_runner.cli.subprocess.run", fake_run)

    exit_code = _invoke_pulumi()

    assert exit_code == 0
    assert calls == [
        ["pulumi", "login", "s3://example-state-bucket/server-shield"],
        [
            "pulumi",
            "stack",
            "select",
            "custom-stack",
            "--create",
            "--cwd",
            str(Path(__file__).resolve().parents[2] / "pulumi_project"),
        ],
        [
            "pulumi",
            "up",
            "--yes",
            "--stack",
            "custom-stack",
            "--cwd",
            str(Path(__file__).resolve().parents[2] / "pulumi_project"),
        ],
    ]
```

Also keep a second test that uses `stack_name="server-shield"` to preserve the default behavior expectation.

- [ ] **Step 2: Run the Pulumi runner tests to verify they fail for the right reason**

Run:
```bash
cd server_shield && uv run pytest tests/pulumi_runner/test_cli.py -v
```

Expected: FAIL because the runner still reads `PULUMI_BACKEND_URL` directly and does not call `pulumi stack select --create`.

- [ ] **Step 3: Implement the minimal Pulumi runner change**

```python
import subprocess
from pathlib import Path

from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component


def _invoke_pulumi() -> int:
    config = get_config()
    project_dir = Path(__file__).resolve().parents[3] / "pulumi_project"
    login_result = subprocess.run(
        ["pulumi", "login", config.pulumi.backend_url],
        check=False,
    )
    if login_result.returncode != 0:
        return login_result.returncode

    select_result = subprocess.run(
        [
            "pulumi",
            "stack",
            "select",
            config.pulumi.stack_name,
            "--create",
            "--cwd",
            str(project_dir),
        ],
        check=False,
    )
    if select_result.returncode != 0:
        return select_result.returncode

    return subprocess.run(
        [
            "pulumi",
            "up",
            "--yes",
            "--stack",
            config.pulumi.stack_name,
            "--cwd",
            str(project_dir),
        ],
        check=False,
    ).returncode
```

Do not read `PULUMI_BACKEND_URL` directly in production code after this change.

- [ ] **Step 4: Run the Pulumi runner tests to verify they pass**

Run:
```bash
cd server_shield && uv run pytest tests/pulumi_runner/test_cli.py -v
```

Expected: PASS for all Pulumi runner tests.

- [ ] **Step 5: Commit the runner bootstrap change**

```bash
git add server_shield/src/server_shield/pulumi_runner/cli.py server_shield/tests/pulumi_runner/test_cli.py
git commit -m "feat: bootstrap configured pulumi stack"
```

### Task 3: README Backend and Docker Instructions

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the failing documentation test as a checklist**

Use this checklist while editing `README.md`:

```text
- exact docker build command from repo root is present
- exact docker run command for local file backend is present
- SERVER_SHIELD_PULUMI__BACKEND_URL is documented as mandatory
- local file backend example is present
- S3 backend example is present
- stack name override variable is documented
```

- [ ] **Step 2: Verify the current README is missing one or more required points**

Run:
```bash
grep -n "SERVER_SHIELD_PULUMI__BACKEND_URL\|STACK_NAME\|s3://\|docker run" README.md
```

Expected: output is incomplete or missing at least one of the required doc items.

- [ ] **Step 3: Update the README with exact backend configuration examples**

Add content equivalent to:

```markdown
Build the Docker image from the repository root with:

```bash
docker build -f server_shield/Dockerfile -t server-shield:local .
```

Pulumi backend configuration is mandatory. Set `SERVER_SHIELD_PULUMI__BACKEND_URL` in `.env`.

Local file backend example:

```dotenv
SERVER_SHIELD_PULUMI__BACKEND_URL=file:///var/lib/server-shield/pulumi-state
SERVER_SHIELD_PULUMI__STACK_NAME=server-shield
```

Run with a persistent volume:

```bash
docker run \
  --env-file .env \
  --volume server-shield-pulumi-state:/var/lib/server-shield/pulumi-state \
  server-shield:local
```

S3 backend example:

```dotenv
SERVER_SHIELD_PULUMI__BACKEND_URL=s3://my-pulumi-state-bucket/server-shield
SERVER_SHIELD_PULUMI__STACK_NAME=server-shield
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=eu-north-1
```

Run against S3 backend:

```bash
docker run --env-file .env server-shield:local
```

For S3, the bucket must already exist. `SERVER_SHIELD_PULUMI__STACK_NAME` is optional and defaults to `server-shield`.
```

- [ ] **Step 4: Verify the README now contains every required item**

Run:
```bash
grep -n "SERVER_SHIELD_PULUMI__BACKEND_URL\|SERVER_SHIELD_PULUMI__STACK_NAME\|s3://\|docker run\|docker build" README.md
```

Expected: output includes all required references.

- [ ] **Step 5: Commit the README update**

```bash
git add README.md
git commit -m "docs: explain pulumi backend configuration"
```

### Task 4: Final Verification

**Files:**
- Modify: none
- Verify: `server_shield/tests/shared/test_config.py`
- Verify: `server_shield/tests/pulumi_runner/test_cli.py`
- Verify: `README.md`

- [ ] **Step 1: Run the focused test suite**

Run:
```bash
cd server_shield && uv run pytest tests/shared/test_config.py tests/pulumi_runner/test_cli.py -v
```

Expected: PASS for all focused tests.

- [ ] **Step 2: Run the full test suite**

Run:
```bash
cd server_shield && uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Verify no production code reads `PULUMI_BACKEND_URL` directly**

Run:
```bash
grep -RIn "PULUMI_BACKEND_URL" server_shield/src server_shield/tests | sed -n '1,120p'
```

Expected: direct references remain only in tests or documentation strings, not in production logic.

- [ ] **Step 4: Review the diff before closing**

Run:
```bash
git diff -- README.md server_shield/src/server_shield/shared/config.py server_shield/src/server_shield/pulumi_runner/cli.py server_shield/tests/shared/test_config.py server_shield/tests/pulumi_runner/test_cli.py
```

Expected: diff only covers the planned config, runner, test, and README changes.

- [ ] **Step 5: Commit the final verification state**

```bash
git add README.md server_shield/src/server_shield/shared/config.py server_shield/src/server_shield/pulumi_runner/cli.py server_shield/tests/shared/test_config.py server_shield/tests/pulumi_runner/test_cli.py
git commit -m "refactor: configure pulumi backend and stack selection"
```
