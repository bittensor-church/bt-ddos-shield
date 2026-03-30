# State Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the AWS-specific persisted state filenames and state-store API names to `root_domain` and `axon_public_ip` without changing runtime behavior.

**Architecture:** Keep the rename strictly at the state contract boundary. Update the typed state models, file bootstrap list, read/write helpers, example state files, and in-repo consumers/tests/docs that use those names, while leaving Pulumi exports like `hosted_zone_domain` unchanged.

**Tech Stack:** Python, pytest, Pydantic, Pulumi, Markdown docs

---

## File Structure

- Modify: `server_shield/src/server_shield/shared/state.py`
  - Rename the two typed state models.
- Modify: `server_shield/src/server_shield/shared/state_store.py`
  - Rename filenames in the bootstrap list and rename the read/write helper API.
- Rename: `server_shield/src/server_shield/shared/state_files/hosted_zone_domain.example.json` -> `server_shield/src/server_shield/shared/state_files/root_domain.example.json`
  - Keep payload shape `{ "domain": null }`.
- Rename: `server_shield/src/server_shield/shared/state_files/nlb_ip.example.json` -> `server_shield/src/server_shield/shared/state_files/axon_public_ip.example.json`
  - Keep payload shape `{ "ip": null }`.
- Rename: `server_shield/src/server_shield/shared/state_files/hosted_zone_domain.json` -> `server_shield/src/server_shield/shared/state_files/root_domain.json`
  - Default checked-in runtime state file name changes only.
- Rename: `server_shield/src/server_shield/shared/state_files/nlb_ip.json` -> `server_shield/src/server_shield/shared/state_files/axon_public_ip.json`
  - Default checked-in runtime state file name changes only.
- Modify: `server_shield/src/server_shield/chain_reader/cli.py`
  - Read `root_domain` via the renamed helper.
- Modify: `server_shield/src/server_shield/chain_writer/cli.py`
  - Read `axon_public_ip` via the renamed helper.
- Modify: `server_shield/src/server_shield/pulumi_runner/program.py`
  - Write the renamed state files but keep `pulumi.export("hosted_zone_domain", ...)` intact.
- Modify: `server_shield/tests/shared/test_state_store.py`
  - Update state bootstrap fixtures and assertions for the renamed files/helpers.
- Modify: `server_shield/tests/chain_reader/test_cli.py`
  - Update example state fixture names.
- Modify: `server_shield/tests/chain_writer/test_cli.py`
  - Update example state fixture names, helper imports, and skip-message assertion.
- Modify: `README.md`
  - Update user-facing state filename references.

### Task 1: Rename the state contract at the shared layer

**Files:**
- Modify: `server_shield/tests/shared/test_state_store.py`
- Modify: `server_shield/src/server_shield/shared/state.py`
- Modify: `server_shield/src/server_shield/shared/state_store.py`
- Rename: `server_shield/src/server_shield/shared/state_files/hosted_zone_domain.example.json`
- Rename: `server_shield/src/server_shield/shared/state_files/nlb_ip.example.json`
- Rename: `server_shield/src/server_shield/shared/state_files/hosted_zone_domain.json`
- Rename: `server_shield/src/server_shield/shared/state_files/nlb_ip.json`

- [ ] **Step 1: Write the failing shared-state tests**

```python
from server_shield.shared.state_store import (
    ensure_state_files,
    read_axon_public_ip,
    read_desired_domains,
    write_desired_domains,
)


def _write_example_files(example_dir: Path) -> None:
    example_dir.mkdir(parents=True, exist_ok=True)
    (example_dir / "root_domain.example.json").write_text('{"domain": null}\n')
    (example_dir / "axon_public_ip.example.json").write_text('{"ip": null}\n')
    (example_dir / "desired_domains.example.json").write_text('{"domains": []}\n')
    (example_dir / "blacklist.example.json").write_text('{"domains": []}\n')
    (example_dir / "manifest.example.json").write_text('{"manifest_url": null, "encrypted_addresses": []}\n')


def test_ensure_state_files_creates_null_and_empty_defaults(tmp_path: Path, monkeypatch) -> None:
    ...
    assert json.loads((runtime_dir / "root_domain.json").read_text()) == {"domain": None}
    assert json.loads((runtime_dir / "axon_public_ip.json").read_text()) == {"ip": None}


def test_round_trip_domain_state_uses_typed_models(tmp_path: Path, monkeypatch) -> None:
    ...
    axon_public_ip = read_axon_public_ip(runtime_dir)
    assert axon_public_ip.ip is None


def test_read_copies_example_file_when_runtime_state_missing(tmp_path: Path, monkeypatch) -> None:
    ...
    (example_dir / "axon_public_ip.example.json").write_text('{"ip": "7.7.7.7"}\n')
    axon_public_ip = read_axon_public_ip(runtime_dir)
    assert axon_public_ip.ip == "7.7.7.7"
    assert (runtime_dir / "axon_public_ip.json").read_text() == (
        example_dir / "axon_public_ip.example.json"
    ).read_text()
```

- [ ] **Step 2: Run the shared-state tests to verify red**

Run: `cd server_shield && .venv/bin/pytest tests/shared/test_state_store.py -v`
Expected: `ImportError` for `read_axon_public_ip` or assertion failures referencing missing `root_domain.json` / `axon_public_ip.json`

- [ ] **Step 3: Write the minimal shared-layer implementation**

```python
class RootDomainState(BaseModel):
    domain: str | None = None


class AxonPublicIpState(BaseModel):
    ip: str | None = None
```

```python
from server_shield.shared.state import (
    AxonPublicIpState,
    BlacklistState,
    DesiredDomainsState,
    ManifestState,
    RootDomainState,
)

STATE_FILE_NAMES = (
    "root_domain.json",
    "axon_public_ip.json",
    "desired_domains.json",
    "blacklist.json",
    "manifest.json",
)


def read_axon_public_ip(state_dir: Path | None = None) -> AxonPublicIpState:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    return AxonPublicIpState.model_validate_json((resolved_state_dir / "axon_public_ip.json").read_text())


def write_axon_public_ip(state_dir: Path | None = None, ip: str | None = None) -> None:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    _atomic_write(
        resolved_state_dir / "axon_public_ip.json",
        AxonPublicIpState(ip=ip).model_dump(),
    )


def write_root_domain(state_dir: Path | None = None, domain: str | None = None) -> None:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    _atomic_write(
        resolved_state_dir / "root_domain.json",
        RootDomainState(domain=domain).model_dump(),
    )


def read_root_domain(state_dir: Path | None = None) -> RootDomainState:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    return RootDomainState.model_validate_json((resolved_state_dir / "root_domain.json").read_text())
```

- [ ] **Step 4: Rename the checked-in state files**

Run:

```bash
mv server_shield/src/server_shield/shared/state_files/hosted_zone_domain.example.json \
  server_shield/src/server_shield/shared/state_files/root_domain.example.json
mv server_shield/src/server_shield/shared/state_files/nlb_ip.example.json \
  server_shield/src/server_shield/shared/state_files/axon_public_ip.example.json
mv server_shield/src/server_shield/shared/state_files/hosted_zone_domain.json \
  server_shield/src/server_shield/shared/state_files/root_domain.json
mv server_shield/src/server_shield/shared/state_files/nlb_ip.json \
  server_shield/src/server_shield/shared/state_files/axon_public_ip.json
```

Expected: `ls server_shield/src/server_shield/shared/state_files` shows the renamed files and no old names.

- [ ] **Step 5: Run the shared-state tests to verify green**

Run: `cd server_shield && .venv/bin/pytest tests/shared/test_state_store.py -v`
Expected: all tests in `tests/shared/test_state_store.py` pass

- [ ] **Step 6: Commit the shared-layer rename**

```bash
git add server_shield/src/server_shield/shared/state.py \
  server_shield/src/server_shield/shared/state_store.py \
  server_shield/src/server_shield/shared/state_files \
  server_shield/tests/shared/test_state_store.py
git commit -m "refactor: rename shared state contract"
```

### Task 2: Rename all in-repo consumers, tests, and docs

**Files:**
- Modify: `server_shield/tests/chain_writer/test_cli.py`
- Modify: `server_shield/tests/chain_reader/test_cli.py`
- Modify: `server_shield/src/server_shield/chain_writer/cli.py`
- Modify: `server_shield/src/server_shield/chain_reader/cli.py`
- Modify: `server_shield/src/server_shield/pulumi_runner/program.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing consumer-facing tests**

```python
from server_shield.shared.state_store import ensure_state_files, write_axon_public_ip


def _write_example_files(example_dir: Path) -> None:
    example_dir.mkdir(parents=True, exist_ok=True)
    (example_dir / "root_domain.example.json").write_text('{"domain": null}\n')
    (example_dir / "axon_public_ip.example.json").write_text('{"ip": null}\n')
    ...


def test_chain_writer_skips_when_axon_public_ip_missing(tmp_path: Path, capsys, monkeypatch) -> None:
    ...
    assert "skipping chain_writer because axon_public_ip is null" in captured.out


def test_chain_writer_logs_placeholder_when_axon_public_ip_present(tmp_path: Path, capsys, monkeypatch) -> None:
    ...
    write_axon_public_ip(tmp_path, "1.2.3.4")
    assert "hello from chain_writer for 1.2.3.4" in captured.out
```

```python
from server_shield.shared.state_store import read_root_domain


def test_chain_reader_bootstraps_state_and_exits_zero(tmp_path: Path, capsys, monkeypatch) -> None:
    ...
    root_domain = read_root_domain(tmp_path)
    assert root_domain.domain is None
    assert "hello from chain_reader" in captured.out
```

- [ ] **Step 2: Run the targeted tests to verify red**

Run: `cd server_shield && .venv/bin/pytest tests/chain_writer/test_cli.py tests/chain_reader/test_cli.py -v`
Expected: import/name failures for `write_axon_public_ip` / `read_root_domain`, or assertions still referencing old skip text

- [ ] **Step 3: Write the minimal consumer updates**

```python
from server_shield.shared.state_store import ensure_state_files, read_axon_public_ip


def _run_once() -> int:
    ensure_state_files()
    axon_public_ip = read_axon_public_ip()
    if axon_public_ip.ip is None:
        print("skipping chain_writer because axon_public_ip is null", flush=True)
        return 0

    print(f"hello from chain_writer for {axon_public_ip.ip}", flush=True)
    return 0
```

```python
from server_shield.shared.state_store import (
    ensure_state_files,
    read_blacklist,
    read_root_domain,
    write_desired_domains,
    write_manifest,
)


def _run_once() -> int:
    ensure_state_files()
    root_domain = read_root_domain()
    blacklist = read_blacklist()
    ...
    print(
        f"hello from chain_reader hosted_zone={root_domain.domain!r} blacklist_size={len(blacklist.domains)}",
        flush=True,
    )
```

```python
from server_shield.shared.state_store import (
    read_desired_domains,
    write_axon_public_ip,
    write_root_domain,
)

...
write_root_domain(domain=zone_domain)
...
nlb_eip.public_ip.apply(_write_axon_public_ip)
...
pulumi.export("hosted_zone_domain", zone_domain)


def _write_axon_public_ip(ip: str) -> str:
    write_axon_public_ip(ip=ip)
    return ip
```

- [ ] **Step 4: Update README and fixture names**

```markdown
- `root_domain.json`: `{ "domain": null }`
- `axon_public_ip.json`: `{ "ip": null }`
...
- If `axon_public_ip.json` still contains `null`, the chain writer exits cleanly and does nothing.
```

Also update the test helper fixture files in `tests/chain_reader/test_cli.py` and `tests/chain_writer/test_cli.py` to write `root_domain.example.json` and `axon_public_ip.example.json`.

- [ ] **Step 5: Run the targeted suite to verify green**

Run: `cd server_shield && .venv/bin/pytest tests/shared/test_state_store.py tests/chain_reader/test_cli.py tests/chain_writer/test_cli.py tests/pulumi_runner/test_program.py -v`
Expected: all targeted tests pass

- [ ] **Step 6: Run a final repo-wide search for stale names**

Run: `rg -n "hosted_zone_domain\\.json|nlb_ip\\.json|read_nlb_ip|write_nlb_ip|read_hosted_zone_domain|write_hosted_zone_domain|HostedZoneDomainState|NlbIpState" server_shield README.md`
Expected: no results for stale state-contract names inside app code/tests/docs, while `hosted_zone_domain` may still appear in Pulumi export strings

- [ ] **Step 7: Commit the consumer rename**

```bash
git add server_shield/src/server_shield/chain_reader/cli.py \
  server_shield/src/server_shield/chain_writer/cli.py \
  server_shield/src/server_shield/pulumi_runner/program.py \
  server_shield/tests/chain_reader/test_cli.py \
  server_shield/tests/chain_writer/test_cli.py \
  README.md
git commit -m "refactor: rename state consumers"
```

## Self-Review

- Spec coverage: the plan covers filename renames, helper/model renames, consumer updates, docs, and preserves the Pulumi export key.
- Placeholder scan: no `TODO`, `TBD`, or implicit “write tests” steps remain.
- Type consistency: the plan consistently uses `RootDomainState`, `AxonPublicIpState`, `read_root_domain`, and `write_axon_public_ip`.
