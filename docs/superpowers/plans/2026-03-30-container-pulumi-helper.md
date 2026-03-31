# Container Pulumi Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `shield-pulumi` executable to the built container so operators can run arbitrary Pulumi commands inside the container with the same environment and working directory as the scheduled Pulumi runner, while still respecting the supervisor lock, and show a generic recovery hint when the Pulumi runner fails.

**Architecture:** Keep the normal scheduled runner and the manual helper on one shared Pulumi invocation path. Move Pulumi environment construction and project-directory resolution into reusable helpers in `server_shield.pulumi_runner.cli`, add a tiny wrapper entrypoint for arbitrary Pulumi commands, and install a shell helper into the image that routes through `server_shield.shared.supervisor` with the same lock name as the scheduled runner. On non-zero Pulumi runner exits, print a short operator hint that points users at `docker exec ... shield-pulumi ...` and mentions `pulumi refresh` / `pulumi import` as available manual tools.

**Tech Stack:** Python 3.14, Pulumi CLI, Pulumi Automation-adjacent shell invocation, existing supervisor lock wrapper, Docker image scripts, pytest

---

## File Map

- Modify: `server_shield/src/server_shield/pulumi_runner/cli.py`
  - Centralize shared Pulumi env/working-dir helpers.
  - Add an invocation path for arbitrary Pulumi CLI args.
  - Print the generic manual-recovery hint on Pulumi runner errors.
- Create: `server_shield/src/server_shield/pulumi_runner/shell.py`
  - Small CLI wrapper for the manual helper entrypoint.
- Modify: `server_shield/pyproject.toml`
  - Register the Python console script used by the helper.
- Create: `server_shield/docker/shield-pulumi`
  - Installed executable wrapper that uses `server_shield.shared.supervisor`.
- Modify: `server_shield/Dockerfile`
  - Copy/install `shield-pulumi` into the image and mark it executable.
- Modify: `server_shield/tests/pulumi_runner/test_cli.py`
  - Cover shared env-building and the failure hint behavior.
- Modify: `server_shield/tests/docker/test_run_component.py`
  - Cover the new helper script behavior and supervisor routing.
- Modify: `README.md`
  - Document `docker exec ... shield-pulumi ...` for operators.
- Modify: `manual_tests/README.md`
  - Add a manual check for the helper in the built container.

### Task 1: Refactor Pulumi CLI Helpers

**Files:**
- Modify: `server_shield/src/server_shield/pulumi_runner/cli.py`
- Test: `server_shield/tests/pulumi_runner/test_cli.py`

- [ ] **Step 1: Write the failing tests for shared helper behavior**

Add tests that expect:

```python
from pathlib import Path

from server_shield.pulumi_runner.cli import _build_pulumi_env, _project_dir


def test_build_pulumi_env_sets_runtime_env(config_factory):
    config = config_factory()

    env = _build_pulumi_env(config)

    assert env["PULUMI_CONFIG_PASSPHRASE"] == ""
    assert env["AWS_ACCESS_KEY_ID"] == config.pulumi.aws.aws_access_key_id
    assert env["AWS_SECRET_ACCESS_KEY"] == config.pulumi.aws.aws_secret_access_key
    assert env["AWS_REGION"] == config.pulumi.aws.aws_region
    assert env["AWS_DEFAULT_REGION"] == config.pulumi.aws.aws_region


def test_project_dir_points_at_pulumi_project():
    assert _project_dir() == Path(__file__).resolve().parents[2] / "pulumi_project"
```

- [ ] **Step 2: Run the focused test file to verify the new tests fail**

Run: `uv run --project server_shield pytest server_shield/tests/pulumi_runner/test_cli.py -q`
Expected: FAIL because `_build_pulumi_env` currently takes no config argument and `_project_dir` does not exist.

- [ ] **Step 3: Implement the shared helper refactor**

Update `server_shield/src/server_shield/pulumi_runner/cli.py` so the helpers are explicit and reusable:

```python
def _build_pulumi_env(config: Config) -> dict[str, str]:
    env = dict(os.environ)
    env["PULUMI_CONFIG_PASSPHRASE"] = ""
    if config.pulumi.shield_backend == "AWS":
        env["AWS_ACCESS_KEY_ID"] = config.pulumi.aws.aws_access_key_id
        env["AWS_SECRET_ACCESS_KEY"] = config.pulumi.aws.aws_secret_access_key
        env["AWS_REGION"] = config.pulumi.aws.aws_region
        env["AWS_DEFAULT_REGION"] = config.pulumi.aws.aws_region
    return env


def _project_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "pulumi_project"
```

Keep `_invoke_pulumi()` calling these helpers rather than duplicating the logic.

- [ ] **Step 4: Run the focused test file to verify it passes**

Run: `uv run --project server_shield pytest server_shield/tests/pulumi_runner/test_cli.py -q`
Expected: PASS for the helper tests and existing Pulumi CLI tests.

- [ ] **Step 5: Commit the helper refactor**

```bash
git add server_shield/src/server_shield/pulumi_runner/cli.py server_shield/tests/pulumi_runner/test_cli.py
git commit -m "refactor: share pulumi cli helpers"
```

### Task 2: Add Manual `shield-pulumi` Entry Point

**Files:**
- Create: `server_shield/src/server_shield/pulumi_runner/shell.py`
- Modify: `server_shield/src/server_shield/pulumi_runner/cli.py`
- Modify: `server_shield/pyproject.toml`
- Test: `server_shield/tests/pulumi_runner/test_cli.py`

- [ ] **Step 1: Write the failing tests for arbitrary Pulumi CLI invocation**

Add tests that expect a manual wrapper to pass raw Pulumi arguments through:

```python
def test_invoke_pulumi_cli_runs_raw_pulumi_args(monkeypatch, config_factory):
    recorded = []

    def fake_run(command, check, env):
        recorded.append((command, env))
        class Result:
            returncode = 0
        return Result()

    config = config_factory()
    monkeypatch.setattr("server_shield.pulumi_runner.cli.get_config", lambda: config)
    monkeypatch.setattr("server_shield.pulumi_runner.cli.subprocess.run", fake_run)

    exit_code = invoke_pulumi_cli(["refresh", "--clear-pending-creates"])

    assert exit_code == 0
    assert recorded[-1][0] == [
        "pulumi",
        "refresh",
        "--clear-pending-creates",
        "--cwd",
        str(_project_dir()),
    ]
```

Also add a small test for the Python CLI entrypoint:

```python
def test_pulumi_shell_main_passes_arguments(monkeypatch):
    monkeypatch.setattr("server_shield.pulumi_runner.shell.invoke_pulumi_cli", lambda argv: 17)
    assert main(["refresh"]) == 17
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run --project server_shield pytest server_shield/tests/pulumi_runner/test_cli.py -q`
Expected: FAIL because `invoke_pulumi_cli` and `server_shield.pulumi_runner.shell` do not exist.

- [ ] **Step 3: Implement the manual Pulumi entrypoint**

Add `server_shield/src/server_shield/pulumi_runner/shell.py`:

```python
import sys

from server_shield.pulumi_runner.cli import invoke_pulumi_cli


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    return invoke_pulumi_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

Extend `server_shield/src/server_shield/pulumi_runner/cli.py` with a reusable raw-command path:

```python
def invoke_pulumi_cli(args: list[str]) -> int:
    config = get_config()
    pulumi_env = _build_pulumi_env(config)

    login_result = subprocess.run(
        ["pulumi", "login", config.pulumi.backend_url],
        check=False,
        env=pulumi_env,
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
            str(_project_dir()),
        ],
        check=False,
        env=pulumi_env,
    )
    if select_result.returncode != 0:
        return select_result.returncode

    command = ["pulumi", *args, "--cwd", str(_project_dir())]
    return subprocess.run(command, check=False, env=pulumi_env).returncode
```

Register the entrypoint in `server_shield/pyproject.toml`:

```toml
[project.scripts]
server-shield-pulumi = "server_shield.pulumi_runner.cli:main"
server-shield-pulumi-shell = "server_shield.pulumi_runner.shell:main"
server-shield-chain-reader = "server_shield.chain_reader.cli:main"
server-shield-chain-writer = "server_shield.chain_writer.cli:main"
```

- [ ] **Step 4: Run the focused tests to verify the entrypoint passes**

Run: `uv run --project server_shield pytest server_shield/tests/pulumi_runner/test_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Commit the manual entrypoint**

```bash
git add server_shield/src/server_shield/pulumi_runner/cli.py server_shield/src/server_shield/pulumi_runner/shell.py server_shield/pyproject.toml server_shield/tests/pulumi_runner/test_cli.py
git commit -m "feat: add manual pulumi shell entrypoint"
```

### Task 3: Install `shield-pulumi` in the Container

**Files:**
- Create: `server_shield/docker/shield-pulumi`
- Modify: `server_shield/Dockerfile`
- Test: `server_shield/tests/docker/test_run_component.py`

- [ ] **Step 1: Write the failing docker-wrapper tests**

Add a test that expects the helper script to route through the supervisor with the shared Pulumi lock name:

```python
def test_shield_pulumi_routes_through_supervisor(tmp_path):
    script = Path("docker/shield-pulumi")
    result = subprocess.run(
        [script, "refresh", "--clear-pending-creates"],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )

    assert "server_shield.shared.supervisor" in result.args[1]
    assert "pulumi-runner" in " ".join(result.args)
```

If the existing docker tests use a fake `python` shim pattern, follow that same pattern rather than invoking the real interpreter.

- [ ] **Step 2: Run the docker test file to verify it fails**

Run: `uv run --project server_shield pytest server_shield/tests/docker/test_run_component.py -q`
Expected: FAIL because `docker/shield-pulumi` does not exist.

- [ ] **Step 3: Implement the installed helper**

Create `server_shield/docker/shield-pulumi`:

```bash
#!/usr/bin/env bash
set -euo pipefail

exec python -m server_shield.shared.supervisor \
    pulumi-runner \
    server-shield-pulumi-shell \
    "$@"
```

Update `server_shield/Dockerfile` so it installs the helper into the image:

```dockerfile
COPY docker/shield-pulumi /usr/local/bin/shield-pulumi
RUN chmod +x /app/docker/run_component.sh /app/docker/entrypoint.sh /usr/local/bin/shield-pulumi
```

- [ ] **Step 4: Run the docker test file to verify it passes**

Run: `uv run --project server_shield pytest server_shield/tests/docker/test_run_component.py -q`
Expected: PASS.

- [ ] **Step 5: Commit the container helper**

```bash
git add server_shield/docker/shield-pulumi server_shield/Dockerfile server_shield/tests/docker/test_run_component.py
git commit -m "feat: install shield-pulumi container helper"
```

### Task 4: Add Generic Operator Guidance on Pulumi Runner Failure

**Files:**
- Modify: `server_shield/src/server_shield/pulumi_runner/cli.py`
- Test: `server_shield/tests/pulumi_runner/test_cli.py`

- [ ] **Step 1: Write the failing failure-message test**

Add a test that expects the Pulumi runner to print a generic manual-recovery hint when `pulumi up` returns non-zero:

```python
def test_invoke_pulumi_prints_manual_recovery_hint_on_failure(
    monkeypatch,
    capsys,
    config_factory,
):
    responses = iter([0, 0, 1])

    def fake_run(command, check, env):
        class Result:
            returncode = next(responses)
        return Result()

    config = config_factory()
    monkeypatch.setattr("server_shield.pulumi_runner.cli.get_config", lambda: config)
    monkeypatch.setattr("server_shield.pulumi_runner.cli.subprocess.run", fake_run)

    exit_code = invoke_pulumi_cli(["up", "--yes", "--stack", config.pulumi.stack_name])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "shield-pulumi" in captured.err
    assert "pulumi refresh" in captured.err
    assert "pulumi import" in captured.err
```

- [ ] **Step 2: Run the focused test file to verify it fails**

Run: `uv run --project server_shield pytest server_shield/tests/pulumi_runner/test_cli.py -q`
Expected: FAIL because no such message is printed today.

- [ ] **Step 3: Implement the generic recovery hint**

In `server_shield/src/server_shield/pulumi_runner/cli.py`, print a generic stderr hint whenever the final Pulumi command exits non-zero:

```python
def _print_manual_recovery_hint() -> None:
    print(
        "pulumi-runner failed. Operators can run manual Pulumi commands inside the container with "
        "`docker exec <container> shield-pulumi ...` from the Pulumi project directory context. "
        "Useful commands include `shield-pulumi refresh ...` and `shield-pulumi import ...`.",
        file=sys.stderr,
        flush=True,
    )
```

Call it only when the final invocation fails, not on successful runs or earlier login/select success paths.

- [ ] **Step 4: Run the focused tests to verify the hint passes**

Run: `uv run --project server_shield pytest server_shield/tests/pulumi_runner/test_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Commit the failure guidance**

```bash
git add server_shield/src/server_shield/pulumi_runner/cli.py server_shield/tests/pulumi_runner/test_cli.py
git commit -m "docs: hint manual pulumi recovery on failure"
```

### Task 5: Document and Verify the Operator Workflow

**Files:**
- Modify: `README.md`
- Modify: `manual_tests/README.md`

- [ ] **Step 1: Update operator docs**

Document in `README.md`:

```md
If the automated Pulumi runner fails, operators can run manual Pulumi commands inside the container with:

```bash
docker exec <container-name> shield-pulumi refresh --clear-pending-creates
docker exec <container-name> shield-pulumi import ...
```

`shield-pulumi` runs from the Pulumi project directory with the same Pulumi/AWS environment as the scheduled runner and uses the same supervisor lock.
```

Document in `manual_tests/README.md`:

```md
To verify the helper exists in the built image:

```bash
docker exec <container-name> shield-pulumi stack output
```

The command should run under the same lock as the automated Pulumi runner, so it will skip if a scheduled Pulumi run is already active.
```

- [ ] **Step 2: Run the full verification suite**

Run: `uv run --project server_shield pytest`
Expected: PASS with all tests green.

- [ ] **Step 3: Run a manual container-facing check**

Run after rebuilding/running the container:

```bash
docker exec <container-name> shield-pulumi stack output
```

Expected:
- the helper executable exists
- it runs from the Pulumi project context
- it can talk to the same Pulumi backend as the scheduled runner

- [ ] **Step 4: Commit the docs**

```bash
git add README.md manual_tests/README.md
git commit -m "docs: describe shield-pulumi operator helper"
```

## Self-Review

- Spec coverage:
  - helper executable in container: covered by Tasks 2 and 3
  - same Pulumi env/working dir as regular runner: covered by Tasks 1 and 2
  - supervisor route with lock behavior: covered by Task 3
  - generic failure message mentioning manual Pulumi commands: covered by Task 4
  - operator docs: covered by Task 5
- Placeholder scan:
  - no `TODO` / `TBD`
  - each code-changing step includes concrete code or an exact command
- Type consistency:
  - shared helpers named `_build_pulumi_env(config)`, `_project_dir()`, `invoke_pulumi_cli(args)`
  - new entrypoint module consistently named `server_shield.pulumi_runner.shell`

