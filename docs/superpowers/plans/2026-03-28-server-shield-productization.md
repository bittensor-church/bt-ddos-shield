# Server Shield Productization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productize `server_shield` into a single structured Python project with shared typed state/config, refactored Pulumi code, placeholder chain jobs, Sentry integration, and a Docker runtime that safely runs all three components every minute.

**Architecture:** Convert `server_shield` to a `src/`-layout package with shared modules for config, state, runtime, and Sentry. Move Pulumi metadata under `server_shield/pulumi_project/`, keep chain reader/writer as placeholder commands for now, and run all three jobs through a lock-and-timeout supervisor so logs stay visible in `docker logs` and failures are reportable.

**Tech Stack:** Python 3.14, uv, pytest, Pulumi, pulumi-aws, pydantic, pydantic-settings, sentry-sdk, Docker, POSIX shell utilities (`flock`, `timeout`)

---

## File Structure Map

Planned file changes and responsibilities:

- Modify: `server_shield/pyproject.toml`
  - add runtime and test dependencies, console scripts, and package discovery
- Delete or replace: `server_shield/__main__.py`
  - remove the current monolithic Pulumi script after its logic is moved
- Move/replace: `server_shield/Pulumi.yaml`, `server_shield/Pulumi.dev.yaml`
  - relocate under `server_shield/pulumi_project/`
- Create: `server_shield/src/server_shield/shared/config.py`
  - shared `pydantic-settings` config and singleton accessor
- Create: `server_shield/src/server_shield/shared/sentry.py`
  - shared Sentry initialization and failure-report helpers
- Create: `server_shield/src/server_shield/shared/runtime.py`
  - component execution wrapper that standardizes exit handling
- Create: `server_shield/src/server_shield/shared/runtime_report.py`
  - tiny CLI for supervisor-triggered Sentry failure reporting
- Create: `server_shield/src/server_shield/shared/state.py`
  - Pydantic models for all JSON state files
- Create: `server_shield/src/server_shield/shared/state_store.py`
  - typed read/write/bootstrap helpers for state files
- Create: `server_shield/src/server_shield/pulumi_runner/program.py`
  - refactored infrastructure composition helpers
- Create: `server_shield/src/server_shield/pulumi_runner/cli.py`
  - Pulumi runner entrypoint
- Create: `server_shield/src/server_shield/chain_reader/cli.py`
  - placeholder reader entrypoint
- Create: `server_shield/src/server_shield/chain_writer/cli.py`
  - placeholder writer entrypoint
- Create: `server_shield/pulumi_project/Pulumi.yaml`
- Create: `server_shield/pulumi_project/Pulumi.dev.yaml`
- Create: `server_shield/pulumi_project/__main__.py`
  - thin Pulumi program bootstrap importing from `pulumi_runner.program`
- Create: `server_shield/docker/run_component.sh`
  - lock + timeout + log-prefix wrapper per component
- Create: `server_shield/docker/entrypoint.sh`
  - starts the three minute loops
- Create: `server_shield/Dockerfile`
  - builds the one-image runtime with Pulumi CLI installed
- Modify: `.gitignore`
  - ignore runtime state files or state directory
- Modify: `README.md`
  - rewrite `### Miner part internal architecture`
- Create tests:
  - `server_shield/tests/shared/test_config.py`
  - `server_shield/tests/shared/test_state_store.py`
  - `server_shield/tests/shared/test_runtime.py`
  - `server_shield/tests/pulumi_runner/test_program.py`
  - `server_shield/tests/chain_reader/test_cli.py`
  - `server_shield/tests/chain_writer/test_cli.py`
  - `server_shield/tests/docker/test_run_component.py`

### Task 1: Shared Config And Runtime Foundation

**Files:**
- Modify: `server_shield/pyproject.toml`
- Create: `server_shield/src/server_shield/__init__.py`
- Create: `server_shield/src/server_shield/shared/__init__.py`
- Create: `server_shield/src/server_shield/shared/config.py`
- Create: `server_shield/src/server_shield/shared/sentry.py`
- Create: `server_shield/src/server_shield/shared/runtime.py`
- Create: `server_shield/tests/shared/test_config.py`
- Create: `server_shield/tests/shared/test_runtime.py`

- [ ] **Step 1: Write the failing config and runtime tests**

```python
# server_shield/tests/shared/test_config.py
from pathlib import Path

from server_shield.shared.config import get_config


def test_get_config_reads_nested_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SERVER_SHIELD_ENV", "test")
    monkeypatch.setenv("SERVER_SHIELD_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("SERVER_SHIELD_STATE_DIR", str(tmp_path / "state"))
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

    assert config.env == "test"
    assert config.state_dir == tmp_path / "state"
    assert config.pulumi.aws_region == "eu-north-1"
    assert config.chain_reader.netuid == 12
    assert config.chain_writer.wallet_name == "miner"


# server_shield/tests/shared/test_runtime.py
from server_shield.shared.runtime import run_component


def test_run_component_returns_zero_for_success(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "server_shield.shared.runtime.init_sentry",
        lambda component_name: calls.append(component_name),
    )

    exit_code = run_component("chain-reader", lambda: 0)

    assert exit_code == 0
    assert calls == ["chain-reader"]


def test_run_component_reports_non_zero_exit_codes(monkeypatch) -> None:
    reports: list[tuple[str, int, str]] = []
    monkeypatch.setattr("server_shield.shared.runtime.init_sentry", lambda component_name: None)
    monkeypatch.setattr(
        "server_shield.shared.runtime.capture_component_failure",
        lambda component_name, exit_code, detail: reports.append((component_name, exit_code, detail)),
    )

    exit_code = run_component("pulumi-runner", lambda: 7)

    assert exit_code == 7
    assert reports == [("pulumi-runner", 7, "non-zero exit")]


def test_run_component_reports_uncaught_exceptions(monkeypatch) -> None:
    reports: list[tuple[str, int, str]] = []
    monkeypatch.setattr("server_shield.shared.runtime.init_sentry", lambda component_name: None)
    monkeypatch.setattr(
        "server_shield.shared.runtime.capture_component_failure",
        lambda component_name, exit_code, detail: reports.append((component_name, exit_code, detail)),
    )

    def boom() -> int:
        raise RuntimeError("kaboom")

    exit_code = run_component("chain-writer", boom)

    assert exit_code == 1
    assert reports == [("chain-writer", 1, "uncaught exception: kaboom")]
```

- [ ] **Step 2: Run the tests to verify they fail for the right reason**

Run: `cd server_shield && uv run pytest tests/shared/test_config.py tests/shared/test_runtime.py -v`
Expected: FAIL with import errors because `server_shield.shared.config` and `server_shield.shared.runtime` do not exist yet.

- [ ] **Step 3: Write the minimal shared config and runtime implementation**

```toml
# server_shield/pyproject.toml
[project]
name = "server-shield"
version = "0.1.0"
description = "Server-side BT DDoS Shield components"
requires-python = ">=3.14"
dependencies = [
    "pulumi>=3.228.0",
    "pulumi-aws>=7.23.0",
    "pydantic>=2.11.0",
    "pydantic-settings>=2.11.0",
    "sentry-sdk>=2.27.0",
]

[project.scripts]
server-shield-pulumi = "server_shield.pulumi_runner.cli:main"
server-shield-chain-reader = "server_shield.chain_reader.cli:main"
server-shield-chain-writer = "server_shield.chain_writer.cli:main"

[dependency-groups]
dev = [
    "pytest>=8.4.0",
]

[build-system]
requires = ["hatchling>=1.27.0"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/server_shield"]
```

```python
# server_shield/src/server_shield/shared/config.py
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class PulumiSettings(BaseModel):
    aws_region: str
    hosted_zone_id: str
    miner_instance_id: str
    miner_port: int


class ChainReaderSettings(BaseModel):
    subtensor_address: str = ""
    netuid: int = 0


class ChainWriterSettings(BaseModel):
    wallet_name: str = ""
    subtensor_address: str = ""
    netuid: int = 0
    miner_port: int = 0


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SERVER_SHIELD_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    env: str = "dev"
    log_level: str = "INFO"
    sentry_dsn: str | None = None
    state_dir: Path = Path("state")
    pulumi: PulumiSettings
    chain_reader: ChainReaderSettings = ChainReaderSettings()
    chain_writer: ChainWriterSettings = ChainWriterSettings()


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig()
```

```python
# server_shield/src/server_shield/shared/sentry.py
import logging

import sentry_sdk

from server_shield.shared.config import get_config


def init_sentry(component_name: str) -> None:
    config = get_config()
    if not config.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=config.sentry_dsn,
        environment=config.env,
        release="server-shield@0.1.0",
    )
    sentry_sdk.set_tag("component", component_name)


def capture_component_failure(component_name: str, exit_code: int, detail: str) -> None:
    config = get_config()
    if not config.sentry_dsn:
        return

    sentry_sdk.capture_message(
        f"{component_name} exited with code {exit_code}: {detail}",
        level="error",
    )
    logging.error("%s exited with code %s: %s", component_name, exit_code, detail)
```

```python
# server_shield/src/server_shield/shared/runtime.py
import traceback
from collections.abc import Callable

from server_shield.shared.sentry import capture_component_failure, init_sentry


def run_component(component_name: str, fn: Callable[[], int]) -> int:
    init_sentry(component_name)
    try:
        exit_code = fn()
    except Exception as exc:  # noqa: BLE001
        capture_component_failure(component_name, 1, f"uncaught exception: {exc}")
        traceback.print_exc()
        return 1

    if exit_code != 0:
        capture_component_failure(component_name, exit_code, "non-zero exit")
    return exit_code
```

- [ ] **Step 4: Run the tests to verify the new foundation passes**

Run: `cd server_shield && uv sync --group dev && uv run pytest tests/shared/test_config.py tests/shared/test_runtime.py -v`
Expected: PASS with 4 passed.

- [ ] **Step 5: Commit the foundation**

```bash
git add server_shield/pyproject.toml server_shield/src/server_shield server_shield/tests/shared
git commit -m "feat: add shared config and runtime foundation"
```

### Task 2: Typed JSON State Models And Git Ignore Rules

**Files:**
- Modify: `.gitignore`
- Create: `server_shield/src/server_shield/shared/state.py`
- Create: `server_shield/src/server_shield/shared/state_store.py`
- Create: `server_shield/tests/shared/test_state_store.py`

- [ ] **Step 1: Write the failing state-store tests**

```python
# server_shield/tests/shared/test_state_store.py
import json
from pathlib import Path

from server_shield.shared.state_store import (
    ensure_state_files,
    read_desired_domains,
    read_nlb_ip,
    write_desired_domains,
)


def test_ensure_state_files_creates_null_and_empty_defaults(tmp_path: Path) -> None:
    ensure_state_files(tmp_path)

    assert json.loads((tmp_path / "hosted_zone_domain.json").read_text()) == {"domain": None}
    assert json.loads((tmp_path / "nlb_ip.json").read_text()) == {"ip": None}
    assert json.loads((tmp_path / "desired_domains.json").read_text()) == {"domains": []}
    assert json.loads((tmp_path / "blacklist.json").read_text()) == {"domains": []}
    assert json.loads((tmp_path / "manifest.json").read_text()) == {
        "manifest_url": None,
        "encrypted_addresses": [],
    }


def test_round_trip_domain_state_uses_typed_models(tmp_path: Path) -> None:
    ensure_state_files(tmp_path)

    write_desired_domains(tmp_path, ["alpha.example.com", "beta.example.com"])
    desired_domains = read_desired_domains(tmp_path)
    nlb_ip = read_nlb_ip(tmp_path)

    assert desired_domains.domains == ["alpha.example.com", "beta.example.com"]
    assert nlb_ip.ip is None
```

- [ ] **Step 2: Run the state-store tests to verify they fail**

Run: `cd server_shield && uv run pytest tests/shared/test_state_store.py -v`
Expected: FAIL with import errors because `server_shield.shared.state_store` does not exist yet.

- [ ] **Step 3: Implement the Pydantic state models, store helpers, and ignore rules**

```python
# server_shield/src/server_shield/shared/state.py
from pydantic import BaseModel, Field


class HostedZoneDomainState(BaseModel):
    domain: str | None = None


class NlbIpState(BaseModel):
    ip: str | None = None


class DesiredDomainsState(BaseModel):
    domains: list[str] = Field(default_factory=list)


class BlacklistState(BaseModel):
    domains: list[str] = Field(default_factory=list)


class ManifestState(BaseModel):
    manifest_url: str | None = None
    encrypted_addresses: list[str] = Field(default_factory=list)
```

```python
# server_shield/src/server_shield/shared/state_store.py
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from server_shield.shared.state import (
    BlacklistState,
    DesiredDomainsState,
    HostedZoneDomainState,
    ManifestState,
    NlbIpState,
)


DEFAULT_STATE_FILES = {
    "hosted_zone_domain.json": HostedZoneDomainState(),
    "nlb_ip.json": NlbIpState(),
    "desired_domains.json": DesiredDomainsState(),
    "blacklist.json": BlacklistState(),
    "manifest.json": ManifestState(),
}


def ensure_state_files(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    for file_name, model in DEFAULT_STATE_FILES.items():
        path = state_dir / file_name
        if not path.exists():
            _atomic_write(path, model.model_dump())


def read_desired_domains(state_dir: Path) -> DesiredDomainsState:
    ensure_state_files(state_dir)
    return DesiredDomainsState.model_validate_json((state_dir / "desired_domains.json").read_text())


def write_desired_domains(state_dir: Path, domains: list[str]) -> None:
    ensure_state_files(state_dir)
    _atomic_write(state_dir / "desired_domains.json", DesiredDomainsState(domains=domains).model_dump())


def read_nlb_ip(state_dir: Path) -> NlbIpState:
    ensure_state_files(state_dir)
    return NlbIpState.model_validate_json((state_dir / "nlb_ip.json").read_text())


def write_nlb_ip(state_dir: Path, ip: str | None) -> None:
    ensure_state_files(state_dir)
    _atomic_write(state_dir / "nlb_ip.json", NlbIpState(ip=ip).model_dump())


def write_hosted_zone_domain(state_dir: Path, domain: str | None) -> None:
    ensure_state_files(state_dir)
    _atomic_write(state_dir / "hosted_zone_domain.json", HostedZoneDomainState(domain=domain).model_dump())


def read_hosted_zone_domain(state_dir: Path) -> HostedZoneDomainState:
    ensure_state_files(state_dir)
    return HostedZoneDomainState.model_validate_json((state_dir / "hosted_zone_domain.json").read_text())


def read_blacklist(state_dir: Path) -> BlacklistState:
    ensure_state_files(state_dir)
    return BlacklistState.model_validate_json((state_dir / "blacklist.json").read_text())


def write_manifest(state_dir: Path, manifest_url: str | None, encrypted_addresses: list[str]) -> None:
    ensure_state_files(state_dir)
    _atomic_write(
        state_dir / "manifest.json",
        ManifestState(manifest_url=manifest_url, encrypted_addresses=encrypted_addresses).model_dump(),
    )


def read_manifest(state_dir: Path) -> ManifestState:
    ensure_state_files(state_dir)
    return ManifestState.model_validate_json((state_dir / "manifest.json").read_text())


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    with NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)
```

```gitignore
# runtime server shield state
server_shield/state/
server_shield/domains.txt
server_shield/hosted_zone_domain.txt
server_shield/nlb_ip.txt
```

- [ ] **Step 4: Run the state-store tests and inspect the defaults**

Run: `cd server_shield && uv run pytest tests/shared/test_state_store.py -v`
Expected: PASS with 2 passed.

- [ ] **Step 5: Commit the state layer**

```bash
git add .gitignore server_shield/src/server_shield/shared/state.py server_shield/src/server_shield/shared/state_store.py server_shield/tests/shared/test_state_store.py
git commit -m "feat: add typed server shield state files"
```

### Task 3: Refactor Pulumi Into A Testable Runner Package

**Files:**
- Delete: `server_shield/__main__.py`
- Move/Create: `server_shield/pulumi_project/Pulumi.yaml`
- Move/Create: `server_shield/pulumi_project/Pulumi.dev.yaml`
- Create: `server_shield/pulumi_project/__main__.py`
- Create: `server_shield/src/server_shield/pulumi_runner/__init__.py`
- Create: `server_shield/src/server_shield/pulumi_runner/program.py`
- Create: `server_shield/src/server_shield/pulumi_runner/cli.py`
- Create: `server_shield/tests/pulumi_runner/test_program.py`

- [ ] **Step 1: Write the failing Pulumi tests**

```python
# server_shield/tests/pulumi_runner/test_program.py
from server_shield.pulumi_runner.program import build_waf_rule_names, should_create_domain_allow_rule


def test_empty_desired_domains_skip_host_allow_rule() -> None:
    assert should_create_domain_allow_rule([]) is False
    assert build_waf_rule_names([]) == ["allow-manifest"]


def test_non_empty_desired_domains_include_host_allow_rule() -> None:
    assert should_create_domain_allow_rule(["miner.example.com"]) is True
    assert build_waf_rule_names(["miner.example.com"]) == [
        "allow-predefined-domains",
        "allow-manifest",
    ]
```

- [ ] **Step 2: Run the Pulumi tests to verify they fail**

Run: `cd server_shield && uv run pytest tests/pulumi_runner/test_program.py -v`
Expected: FAIL with import errors because `server_shield.pulumi_runner.program` does not exist yet.

- [ ] **Step 3: Implement the Pulumi runner package and move the Pulumi project**

```python
# server_shield/src/server_shield/pulumi_runner/program.py
from pathlib import Path

import pulumi
import pulumi_aws as aws
from pulumi_aws.wafv2 import WebAcl, WebAclAssociation
from pulumi_aws.wafv2._inputs import (
    WebAclDefaultActionArgs,
    WebAclDefaultActionBlockArgs,
    WebAclDefaultActionBlockCustomResponseArgs,
    WebAclRuleActionAllowArgs,
    WebAclRuleActionArgs,
    WebAclRuleArgs,
    WebAclRuleStatementArgs,
    WebAclRuleStatementByteMatchStatementArgs,
    WebAclRuleStatementByteMatchStatementFieldToMatchArgs,
    WebAclRuleStatementByteMatchStatementFieldToMatchSingleHeaderArgs,
    WebAclRuleStatementByteMatchStatementFieldToMatchUriPathArgs,
    WebAclRuleStatementByteMatchStatementTextTransformationArgs,
    WebAclRuleStatementOrStatementArgs,
    WebAclRuleVisibilityConfigArgs,
    WebAclVisibilityConfigArgs,
)

from server_shield.shared.config import get_config
from server_shield.shared.state_store import (
    read_desired_domains,
    write_hosted_zone_domain,
    write_nlb_ip,
)


def should_create_domain_allow_rule(desired_domains: list[str]) -> bool:
    return bool(desired_domains)


def build_waf_rule_names(desired_domains: list[str]) -> list[str]:
    names: list[str] = []
    if should_create_domain_allow_rule(desired_domains):
        names.append("allow-predefined-domains")
    names.append("allow-manifest")
    return names


def run_program() -> None:
    config = get_config()
    desired_domains = read_desired_domains(config.state_dir).domains

    hosted_zone = aws.route53.get_zone(zone_id=config.pulumi.hosted_zone_id)
    zone_domain = hosted_zone.name.rstrip(".")
    write_hosted_zone_domain(config.state_dir, zone_domain)

    waf_rules: list[WebAclRuleArgs] = []
    if should_create_domain_allow_rule(desired_domains):
        waf_rules.append(
            WebAclRuleArgs(
                name="allow-predefined-domains",
                priority=0,
                action=WebAclRuleActionArgs(allow=WebAclRuleActionAllowArgs()),
                visibility_config=WebAclRuleVisibilityConfigArgs(
                    sampled_requests_enabled=True,
                    cloudwatch_metrics_enabled=False,
                    metric_name="allow-predefined-domains",
                ),
                statement=WebAclRuleStatementArgs(
                    or_statement=WebAclRuleStatementOrStatementArgs(
                        statements=[
                            WebAclRuleStatementArgs(
                                byte_match_statement=WebAclRuleStatementByteMatchStatementArgs(
                                    search_string=domain,
                                    positional_constraint="EXACTLY",
                                    field_to_match=WebAclRuleStatementByteMatchStatementFieldToMatchArgs(
                                        single_header=WebAclRuleStatementByteMatchStatementFieldToMatchSingleHeaderArgs(name="host"),
                                    ),
                                    text_transformations=[
                                        WebAclRuleStatementByteMatchStatementTextTransformationArgs(
                                            priority=0,
                                            type="LOWERCASE",
                                        )
                                    ],
                                )
                            )
                            for domain in desired_domains
                        ]
                    )
                ),
            )
        )

    waf_rules.append(
        WebAclRuleArgs(
            name="allow-manifest",
            priority=1,
            action=WebAclRuleActionArgs(allow=WebAclRuleActionAllowArgs()),
            visibility_config=WebAclRuleVisibilityConfigArgs(
                sampled_requests_enabled=True,
                cloudwatch_metrics_enabled=False,
                metric_name="allow-manifest",
            ),
            statement=WebAclRuleStatementArgs(
                byte_match_statement=WebAclRuleStatementByteMatchStatementArgs(
                    search_string="/shield_manifest.json",
                    positional_constraint="EXACTLY",
                    field_to_match=WebAclRuleStatementByteMatchStatementFieldToMatchArgs(
                        uri_path=WebAclRuleStatementByteMatchStatementFieldToMatchUriPathArgs(),
                    ),
                    text_transformations=[
                        WebAclRuleStatementByteMatchStatementTextTransformationArgs(priority=0, type="NONE")
                    ],
                )
            ),
        )
    )

    pulumi.export("waf_rule_names", build_waf_rule_names(desired_domains))
    pulumi.export("hosted_zone_domain", zone_domain)
    write_nlb_ip(config.state_dir, None)

    WebAcl(
        "shield-waf-acl",
        scope="REGIONAL",
        default_action=WebAclDefaultActionArgs(
            block=WebAclDefaultActionBlockArgs(
                custom_response=WebAclDefaultActionBlockCustomResponseArgs(response_code=403)
            )
        ),
        visibility_config=WebAclVisibilityConfigArgs(
            sampled_requests_enabled=True,
            cloudwatch_metrics_enabled=False,
            metric_name="shield-waf",
        ),
        rules=waf_rules,
    )
```

```python
# server_shield/src/server_shield/pulumi_runner/cli.py
import subprocess
from pathlib import Path

from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component


def _invoke_pulumi() -> int:
    project_dir = Path(__file__).resolve().parents[3] / "pulumi_project"
    command = ["pulumi", "up", "--yes", "--cwd", str(project_dir)]
    return subprocess.run(command, check=False).returncode


def main() -> int:
    get_config()
    return run_component("pulumi-runner", _invoke_pulumi)
```

```python
# server_shield/pulumi_project/__main__.py
from server_shield.pulumi_runner.program import run_program

run_program()
```

```yaml
# server_shield/pulumi_project/Pulumi.yaml
name: server-shield
runtime:
  name: python
  options:
    toolchain: uv
main: __main__.py
```

```yaml
# server_shield/pulumi_project/Pulumi.dev.yaml
# Copy the existing stack file content from server_shield/Pulumi.dev.yaml unchanged,
# then update any file-path references so they point at pulumi_project-relative paths.
```

Before deleting the current `server_shield/__main__.py`, copy the existing AWS resource construction logic into `server_shield/src/server_shield/pulumi_runner/program.py` and keep it behaviorally equivalent. The only intentional behavior changes in that move are:
- replace direct `os.environ[...]` access with `get_config().pulumi`
- replace text-file writes with `write_hosted_zone_domain()` and `write_nlb_ip()`
- read desired domains through `read_desired_domains()`
- skip the host-based WAF allow rule when `desired_domains` is empty
- keep the manifest path rule, ALB/NLB setup, DNS record, security groups, and exports otherwise intact

- [ ] **Step 4: Run the Pulumi tests, then add one mock-backed smoke test before moving on**

Run: `cd server_shield && uv run pytest tests/pulumi_runner/test_program.py -v`
Expected: PASS with 2 passed.

Then extend `tests/pulumi_runner/test_program.py` with one `pulumi.runtime.test` smoke test that imports `server_shield.pulumi_runner.program` under mocks and asserts the exported `waf_rule_names` omit `allow-predefined-domains` for empty desired domains. Re-run the same command and expect PASS with 3 passed.

- [ ] **Step 5: Commit the Pulumi refactor**

```bash
git add server_shield/pulumi_project server_shield/src/server_shield/pulumi_runner server_shield/tests/pulumi_runner
git rm server_shield/__main__.py
git commit -m "refactor: move pulumi code into server shield package"
```

### Task 4: Add Placeholder Chain Components And Shared Failure Reporting

**Files:**
- Create: `server_shield/src/server_shield/chain_reader/__init__.py`
- Create: `server_shield/src/server_shield/chain_reader/cli.py`
- Create: `server_shield/src/server_shield/chain_writer/__init__.py`
- Create: `server_shield/src/server_shield/chain_writer/cli.py`
- Modify: `server_shield/src/server_shield/shared/sentry.py`
- Create: `server_shield/tests/chain_reader/test_cli.py`
- Create: `server_shield/tests/chain_writer/test_cli.py`

- [ ] **Step 1: Write the failing chain component tests**

```python
# server_shield/tests/chain_reader/test_cli.py
from pathlib import Path

from server_shield.chain_reader.cli import _run_once


def test_chain_reader_bootstraps_state_and_exits_zero(tmp_path: Path, capsys) -> None:
    exit_code = _run_once(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "hello from chain_reader" in captured.out
    assert (tmp_path / "desired_domains.json").exists()


# server_shield/tests/chain_writer/test_cli.py
from pathlib import Path

from server_shield.chain_writer.cli import _run_once
from server_shield.shared.state_store import ensure_state_files, write_nlb_ip


def test_chain_writer_skips_when_nlb_ip_missing(tmp_path: Path, capsys) -> None:
    ensure_state_files(tmp_path)

    exit_code = _run_once(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "skipping chain_writer because nlb_ip is null" in captured.out


def test_chain_writer_logs_placeholder_when_nlb_ip_present(tmp_path: Path, capsys) -> None:
    ensure_state_files(tmp_path)
    write_nlb_ip(tmp_path, "1.2.3.4")

    exit_code = _run_once(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "hello from chain_writer for 1.2.3.4" in captured.out
```

- [ ] **Step 2: Run the chain component tests to verify they fail**

Run: `cd server_shield && uv run pytest tests/chain_reader/test_cli.py tests/chain_writer/test_cli.py -v`
Expected: FAIL with import errors because the chain component modules do not exist yet.

- [ ] **Step 3: Implement the placeholder chain commands and upgrade Sentry helpers**

```python
# server_shield/src/server_shield/shared/sentry.py
import logging

import sentry_sdk

from server_shield.shared.config import get_config


def init_sentry(component_name: str) -> None:
    config = get_config()
    if not config.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=config.sentry_dsn,
        environment=config.env,
        release="server-shield@0.1.0",
    )
    sentry_sdk.set_tag("component", component_name)
    sentry_sdk.set_tag("environment", config.env)


def capture_component_failure(component_name: str, exit_code: int, detail: str) -> None:
    config = get_config()
    logging.error("%s exited with code %s: %s", component_name, exit_code, detail)
    if not config.sentry_dsn:
        return

    with sentry_sdk.push_scope() as scope:
        scope.set_tag("component", component_name)
        scope.set_extra("exit_code", exit_code)
        scope.set_extra("detail", detail)
        sentry_sdk.capture_message(f"{component_name} failure", level="error")
```

```python
# server_shield/src/server_shield/chain_reader/cli.py
from pathlib import Path

from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component
from server_shield.shared.state_store import (
    ensure_state_files,
    read_blacklist,
    read_hosted_zone_domain,
    write_desired_domains,
    write_manifest,
)


def _run_once(state_dir: Path) -> int:
    ensure_state_files(state_dir)
    hosted_zone = read_hosted_zone_domain(state_dir)
    blacklist = read_blacklist(state_dir)
    write_desired_domains(state_dir, [])
    write_manifest(state_dir, None, [])
    print(
        f"hello from chain_reader hosted_zone={hosted_zone.domain!r} blacklist_size={len(blacklist.domains)}",
        flush=True,
    )
    return 0


def main() -> int:
    config = get_config()
    return run_component("chain-reader", lambda: _run_once(config.state_dir))
```

```python
# server_shield/src/server_shield/chain_writer/cli.py
from pathlib import Path

from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component
from server_shield.shared.state_store import ensure_state_files, read_nlb_ip


def _run_once(state_dir: Path) -> int:
    ensure_state_files(state_dir)
    nlb_ip = read_nlb_ip(state_dir)
    if nlb_ip.ip is None:
        print("skipping chain_writer because nlb_ip is null", flush=True)
        return 0

    print(f"hello from chain_writer for {nlb_ip.ip}", flush=True)
    return 0


def main() -> int:
    config = get_config()
    return run_component("chain-writer", lambda: _run_once(config.state_dir))
```

- [ ] **Step 4: Run the chain component tests and the shared runtime tests together**

Run: `cd server_shield && uv run pytest tests/shared/test_runtime.py tests/chain_reader/test_cli.py tests/chain_writer/test_cli.py -v`
Expected: PASS with 6 passed.

- [ ] **Step 5: Commit the placeholder components**

```bash
git add server_shield/src/server_shield/chain_reader server_shield/src/server_shield/chain_writer server_shield/src/server_shield/shared/sentry.py server_shield/tests/chain_reader server_shield/tests/chain_writer
git commit -m "feat: add placeholder chain server components"
```

### Task 5: Docker Scheduling, Locking, Timeouts, Logs, And Supervisor Reporting

**Files:**
- Create: `server_shield/docker/run_component.sh`
- Create: `server_shield/docker/entrypoint.sh`
- Create: `server_shield/Dockerfile`
- Create: `server_shield/src/server_shield/shared/runtime_report.py`
- Create: `server_shield/tests/docker/test_run_component.py`

- [ ] **Step 1: Write the failing supervisor tests**

```python
# server_shield/tests/docker/test_run_component.py
import os
import subprocess
from pathlib import Path


def test_run_component_prefixes_logs_and_returns_zero(tmp_path: Path) -> None:
    script = Path("docker/run_component.sh")
    component = "chain-reader"
    command = ["bash", str(script), component, "python", "-c", "print('hello')"]

    completed = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "LOCK_DIR": str(tmp_path), "RUN_TIMEOUT": "20m"},
    )

    assert completed.returncode == 0
    assert "[chain-reader] hello" in completed.stdout


def test_run_component_skips_when_lock_exists(tmp_path: Path) -> None:
    script = Path("docker/run_component.sh")
    lock_path = tmp_path / "chain-writer.lock"
    holder = subprocess.Popen(
        [
            "bash",
            "-lc",
            f"exec 9>{lock_path}; flock -n 9; sleep 2",
        ],
        cwd=Path(__file__).resolve().parents[2],
    )
    command = ["bash", str(script), "chain-writer", "python", "-c", "print('ignored')"]

    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "LOCK_DIR": str(tmp_path), "RUN_TIMEOUT": "20m"},
        )
    finally:
        holder.terminate()
        holder.wait(timeout=5)

    assert completed.returncode == 0
    assert "[chain-writer] skipped because previous run is still active" in completed.stdout
```

- [ ] **Step 2: Run the supervisor tests to verify they fail**

Run: `cd server_shield && uv run pytest tests/docker/test_run_component.py -v`
Expected: FAIL because `docker/run_component.sh` does not exist yet.

- [ ] **Step 3: Implement the Docker runtime and supervisor scripts**

```bash
# server_shield/docker/run_component.sh
#!/usr/bin/env bash
set -euo pipefail

component="$1"
shift

lock_dir="${LOCK_DIR:-/tmp/server-shield-locks}"
mkdir -p "$lock_dir"
lock_file="$lock_dir/${component}.lock"

exec 9>"$lock_file"
if ! flock -n 9; then
  printf '[%s] skipped because previous run is still active\n' "$component"
  exit 0
fi

status=0
set +e
timeout "${RUN_TIMEOUT:-20m}" "$@" \
  > >(sed "s/^/[${component}] /") \
  2> >(sed "s/^/[${component}] /" >&2)
status=$?
set -e

if [ "$status" -eq 124 ]; then
  python -m server_shield.shared.runtime_report "$component" "$status" "timed out after ${RUN_TIMEOUT:-20m}"
fi

exit "$status"
```

```bash
# server_shield/docker/entrypoint.sh
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
```

```dockerfile
# server_shield/Dockerfile
FROM python:3.14-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl ca-certificates util-linux coreutils \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://get.pulumi.com | sh
ENV PATH="/root/.pulumi/bin:${PATH}"

COPY server_shield /app
RUN pip install uv && uv sync --frozen --group dev
RUN chmod +x /app/docker/run_component.sh /app/docker/entrypoint.sh

ENTRYPOINT ["/app/docker/entrypoint.sh"]
```

```python
# server_shield/src/server_shield/shared/runtime_report.py
import sys

from server_shield.shared.sentry import capture_component_failure, init_sentry


if __name__ == "__main__":
    component_name = sys.argv[1]
    exit_code = int(sys.argv[2])
    detail = sys.argv[3]
    init_sentry(component_name)
    capture_component_failure(component_name, exit_code, detail)
```

- [ ] **Step 4: Run the supervisor tests, then add one timeout-path test**

Run: `cd server_shield && uv run pytest tests/docker/test_run_component.py -v`
Expected: PASS with 2 passed.

Then extend `tests/docker/test_run_component.py` with a third test that runs `python -c "import time; time.sleep(2)"` under `RUN_TIMEOUT=1s` and asserts a non-zero exit plus a timeout message on stderr or stdout. Re-run the same command and expect PASS with 3 passed.

- [ ] **Step 5: Commit the Docker runtime**

```bash
git add server_shield/docker server_shield/Dockerfile server_shield/src/server_shield/shared/runtime_report.py server_shield/tests/docker
git commit -m "feat: add scheduled docker runtime for server shield"
```

### Task 6: Rewrite README And Run Full Verification

**Files:**
- Modify: `README.md`
- Modify if needed: `docs/superpowers/specs/2026-03-28-server-shield-productization-design.md`

- [ ] **Step 1: Write the failing documentation check and final test target**

Create a checklist note in your working scratchpad before editing docs:

```text
README must mention:
- server_shield has 3 components: pulumi_runner, chain_reader, chain_writer
- state files are JSON with null/empty bootstrap defaults
- desired_domains empty means Pulumi skips host-based WAF rules
- chain_writer exits cleanly when nlb_ip is null
- all components log to stdout/stderr and are visible via docker logs
- scheduler runs every minute, never overlaps, times out after 20 minutes
- config is read from environment variables, not .env loading
```

Run the current suite before the README edit so you know the expected green baseline for final verification:
`cd server_shield && uv run pytest -v`
Expected: PASS for all tests added in Tasks 1-5.

- [ ] **Step 2: Update `README.md` and remove stale architecture details**

Replace the current `### Miner part internal architecture` section with content equivalent to:

```markdown
### Miner part internal architecture

The server shield is split into 3 internal components inside `server_shield`:

- `pulumi_runner`: provisions and updates the AWS infrastructure
- `chain_reader`: placeholder job that will eventually read chain state and prepare local desired-domain / manifest data
- `chain_writer`: placeholder job that will eventually publish miner connection data back to chain

These components communicate through typed JSON state files stored in the server shield state directory. On initial bootstrap the files always exist, but their values may be `null` or empty arrays so downstream components can exit quickly without treating missing upstream data as an error.

Current state files:
- `hosted_zone_domain.json`: `{ "domain": null }`
- `nlb_ip.json`: `{ "ip": null }`
- `desired_domains.json`: `{ "domains": [] }`
- `blacklist.json`: `{ "domains": [] }`
- `manifest.json`: `{ "manifest_url": null, "encrypted_addresses": [] }`

Behavior notes:
- if `desired_domains.json` contains no domains, the Pulumi runner still applies the base infrastructure and skips the host-based WAF allow rules
- if `nlb_ip.json` still contains `null`, the chain writer exits cleanly and does nothing
- all three components run in one Docker image, attempt one run every minute, never overlap with themselves, and each run is capped at 20 minutes
- logs from all three components stay on stdout/stderr, so they are visible through `docker logs`
- configuration is parsed from environment variables via shared Pydantic settings
```

- [ ] **Step 3: Run the full verification commands and inspect the results**

Run:

```bash
cd server_shield
uv run pytest -v
export SERVER_SHIELD_PULUMI__AWS_REGION=eu-north-1
export SERVER_SHIELD_PULUMI__HOSTED_ZONE_ID=Z123
export SERVER_SHIELD_PULUMI__MINER_INSTANCE_ID=i-123
export SERVER_SHIELD_PULUMI__MINER_PORT=9001
uv run python -m server_shield.chain_reader.cli
uv run python -m server_shield.chain_writer.cli
```

Expected:
- all tests PASS
- chain reader prints `hello from chain_reader`
- chain writer prints `skipping chain_writer because nlb_ip is null` on a fresh state directory

- [ ] **Step 4: Build the Docker image and verify the runtime contract**

Run:

```bash
docker build -t server-shield:test -f server_shield/Dockerfile .
docker run --rm \
  -e SERVER_SHIELD_PULUMI__AWS_REGION=eu-north-1 \
  -e SERVER_SHIELD_PULUMI__HOSTED_ZONE_ID=Z123 \
  -e SERVER_SHIELD_PULUMI__MINER_INSTANCE_ID=i-123 \
  -e SERVER_SHIELD_PULUMI__MINER_PORT=9001 \
  server-shield:test
```

Expected:
- container starts the three loops
- `docker logs` shows interleaved component-prefixed lines from `pulumi-runner`, `chain-reader`, and `chain-writer`
- no component overlaps with itself
- any timeout path exits with a non-zero status and emits a supervisor failure event

- [ ] **Step 5: Commit the docs and final verification changes**

```bash
git add README.md .gitignore server_shield docs/superpowers/specs/2026-03-28-server-shield-productization-design.md
git commit -m "docs: document productized server shield architecture"
```
