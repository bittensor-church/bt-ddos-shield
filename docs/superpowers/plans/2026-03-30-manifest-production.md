# Manifest Production and Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change `manifest.json` into the final desired upload payload, make `chain_reader` produce it from reconciled validator domains, and make `pulumi_runner` upload `shield_manifest.json` to S3 only when manifest content changes.

**Architecture:** Keep chain-derived state in `chain_reader` and infrastructure ownership in `pulumi_runner`. The shared state layer becomes responsible for deterministic pretty/sorted JSON output and the new typed manifest contract. `chain_reader` writes `desired_domains.json` and `manifest.json`; `pulumi_runner` reads both and uploads the manifest object using a Pulumi-side content hash instead of storing sync metadata in the file.

**Tech Stack:** Python 3.14, bittensor, ECIES, Pydantic, Pulumi AWS, pytest, Markdown

---

## File Structure

- Modify: `server_shield/src/server_shield/shared/state.py`
  - Replace the current manifest model with the final uploaded manifest payload model.
- Modify: `server_shield/src/server_shield/shared/state_store.py`
  - Update manifest read/write helpers and make all state JSON writes pretty/sorted/deterministic.
- Modify: `server_shield/src/server_shield/shared/state_files/manifest.example.json`
  - Replace the current example with the empty final payload.
- Create: `server_shield/src/server_shield/chain_reader/manifest.py`
  - Build encrypted manifest payloads from desired domains using ECIES and base64 encoding.
- Modify: `server_shield/src/server_shield/chain_reader/cli.py`
  - After reconciliation, write the new manifest payload to state.
- Modify: `server_shield/src/server_shield/pulumi_runner/program.py`
  - Read `manifest.json`, serialize it deterministically, and upload `shield_manifest.json` to S3 with `source_hash`.
- Modify: `server_shield/tests/shared/test_state_store.py`
  - Update existing state-store assertions to the new manifest shape and deterministic formatting.
- Modify: `server_shield/tests/chain_reader/test_cli.py`
  - Update existing chain-reader tests to assert manifest production as part of the run.
- Modify: `server_shield/tests/chain_writer/test_cli.py`
  - Update example manifest fixture payload only, because `chain_writer` still ignores manifest state.
- Modify: `README.md`
  - Document the new `manifest.json` contract and Pulumi upload behavior.
- Modify: `manual_tests/README.md`
  - Add manual verification steps for the uploaded `shield_manifest.json`.

### Task 1: Update the shared manifest state contract and deterministic JSON writing

**Files:**
- Modify: `server_shield/src/server_shield/shared/state.py`
- Modify: `server_shield/src/server_shield/shared/state_store.py`
- Modify: `server_shield/src/server_shield/shared/state_files/manifest.example.json`
- Modify: `server_shield/tests/shared/test_state_store.py`
- Modify: `server_shield/tests/chain_reader/test_cli.py`
- Modify: `server_shield/tests/chain_writer/test_cli.py`

- [ ] **Step 1: Update the typed manifest model**

```python
from pydantic import BaseModel, Field, RootModel


class ManifestPayloadState(BaseModel):
    encrypted_url_mapping: dict[str, str] = Field(default_factory=dict)


class ManifestState(BaseModel):
    ddos_shield_manifest: ManifestPayloadState = Field(default_factory=ManifestPayloadState)
```

- [ ] **Step 2: Update state-store manifest helpers and the shared JSON serializer**

```python
def write_manifest(
    state_dir: Path | None = None,
    encrypted_url_mapping: dict[str, str] | None = None,
) -> None:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    _atomic_write(
        resolved_state_dir / "manifest.json",
        ManifestState(
            ddos_shield_manifest=ManifestPayloadState(
                encrypted_url_mapping=encrypted_url_mapping or {},
            )
        ).model_dump(),
    )


def _atomic_write(path: Path, payload: object) -> None:
    with NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=4, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)
```

- [ ] **Step 3: Replace the manifest example file with the empty final payload**

```json
{
    "ddos_shield_manifest": {
        "encrypted_url_mapping": {}
    }
}
```

- [ ] **Step 4: Update existing tests that codify the old manifest shape**

```python
(example_dir / "manifest.example.json").write_text(
    '{\n'
    '    "ddos_shield_manifest": {\n'
    '        "encrypted_url_mapping": {}\n'
    '    }\n'
    '}\n'
)
```

```python
assert json.loads((runtime_dir / "manifest.json").read_text()) == {
    "ddos_shield_manifest": {
        "encrypted_url_mapping": {},
    }
}
assert (runtime_dir / "desired_domains.json").read_text().startswith("{\n    \"domains\"")
```

- [ ] **Step 5: Run the focused shared-state tests**

Run: `uv run --project server_shield pytest server_shield/tests/shared/test_state_store.py server_shield/tests/chain_writer/test_cli.py -v`

Expected:
- all listed tests pass
- no assertions refer to `manifest_url` or `encrypted_addresses`

- [ ] **Step 6: Commit the shared state contract change**

```bash
git add \
  server_shield/src/server_shield/shared/state.py \
  server_shield/src/server_shield/shared/state_store.py \
  server_shield/src/server_shield/shared/state_files/manifest.example.json \
  server_shield/tests/shared/test_state_store.py \
  server_shield/tests/chain_reader/test_cli.py \
  server_shield/tests/chain_writer/test_cli.py
git commit -m "refactor: update manifest state contract"
```

### Task 2: Build encrypted manifest payloads in chain reader

**Files:**
- Create: `server_shield/src/server_shield/chain_reader/manifest.py`
- Modify: `server_shield/src/server_shield/chain_reader/cli.py`
- Modify: `server_shield/tests/chain_reader/test_cli.py`

- [ ] **Step 1: Add a focused manifest-builder module**

```python
from __future__ import annotations

import base64

import ecies
from ecies.config import Config

from server_shield.shared.state import DesiredDomainEntry, ManifestState, ManifestPayloadState


_ECIES_CONFIG = Config(elliptic_curve="ed25519")


def build_manifest_state(
    desired_domains: dict[str, DesiredDomainEntry],
) -> ManifestState:
    encrypted_url_mapping: dict[str, str] = {}
    for hotkey, entry in sorted(desired_domains.items()):
        encrypted_bytes = ecies.encrypt(
            entry.public_cert,
            entry.domain.encode("utf-8"),
            config=_ECIES_CONFIG,
        )
        encrypted_url_mapping[hotkey] = base64.b64encode(encrypted_bytes).decode("ascii")
    return ManifestState(
        ddos_shield_manifest=ManifestPayloadState(
            encrypted_url_mapping=encrypted_url_mapping,
        )
    )
```

- [ ] **Step 2: Wire chain reader to write `manifest.json` from reconciled domains**

```python
from server_shield.chain_reader.manifest import build_manifest_state
from server_shield.shared.state_store import write_manifest


def _run_once() -> int:
    ensure_state_files()
    root_domain = read_root_domain()
    if root_domain.domain is None:
        print("skipping chain_reader because root_domain is null", flush=True)
        return 0

    ...
    write_desired_domains(
        domains={
            hotkey: entry.model_dump()
            for hotkey, entry in result.desired_domains.items()
        }
    )
    manifest = build_manifest_state(result.desired_domains)
    write_manifest(
        encrypted_url_mapping=manifest.ddos_shield_manifest.encrypted_url_mapping,
    )
    print(
        "chain_reader reconciled "
        f"observed={result.observed} kept={result.kept} created={result.created} "
        f"rotated_for_cert={result.rotated_for_cert} "
        f"rotated_for_root_domain={result.rotated_for_root_domain} "
        f"removed={result.removed} blacklisted={result.blacklisted} "
        f"invalid_cert={result.invalid_cert} "
        f"manifest_entries={len(manifest.ddos_shield_manifest.encrypted_url_mapping)}",
        flush=True,
    )
    return 0
```

- [ ] **Step 3: Update existing chain-reader tests to assert manifest production**

```python
from server_shield.shared.state_store import read_manifest

...
manifest = read_manifest(tmp_path)
assert manifest.ddos_shield_manifest.encrypted_url_mapping == {}
```

```python
manifest = read_manifest(tmp_path)
assert set(manifest.ddos_shield_manifest.encrypted_url_mapping) == {
    "existing-validator",
    "new-validator",
}
assert "blacklisted-validator" not in manifest.ddos_shield_manifest.encrypted_url_mapping
assert "missing-cert-validator" not in manifest.ddos_shield_manifest.encrypted_url_mapping
assert "manifest_entries=2" in captured.out
```

- [ ] **Step 4: Manually verify live manifest generation against Finney subnet 12**

Run:

```bash
tmp_state_dir="$(mktemp -d)"
cp server_shield/src/server_shield/shared/state_files/*.example.json "$tmp_state_dir"/
for file in "$tmp_state_dir"/*.example.json; do mv "$file" "${file%.example.json}.json"; done
printf '{\n    "domain": "shield.example.com"\n}\n' > "$tmp_state_dir/root_domain.json"
printf '[]\n' > "$tmp_state_dir/blacklist.json"
SERVER_SHIELD_STATE_DIR="$tmp_state_dir" \
SERVER_SHIELD_SUBTENSOR_ADDRESS=finney \
SERVER_SHIELD_NETUID=12 \
SERVER_SHIELD_PULUMI__BACKEND_URL=file:///tmp/server-shield-test-state \
SERVER_SHIELD_PULUMI__SHIELD_BACKEND=AWS \
SERVER_SHIELD_MINER_PORT=9001 \
SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID=key \
SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY=secret \
SERVER_SHIELD_PULUMI__AWS__AWS_REGION=eu-north-1 \
SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID=Z123 \
SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID=i-123 \
SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME=miner \
SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY=miner-hotkey \
uv run --project server_shield python -m server_shield.chain_reader.cli
cat "$tmp_state_dir/manifest.json"
```

Expected:
- stdout includes `manifest_entries=` with the number of eligible validators
- `manifest.json` contains `ddos_shield_manifest.encrypted_url_mapping`
- every value is a non-empty base64 string
- the file is indented and keys appear in sorted order

- [ ] **Step 5: Commit chain-reader manifest production**

```bash
git add \
  server_shield/src/server_shield/chain_reader/manifest.py \
  server_shield/src/server_shield/chain_reader/cli.py \
  server_shield/tests/chain_reader/test_cli.py
git commit -m "feat: build manifest payload in chain reader"
```

### Task 3: Upload `shield_manifest.json` from Pulumi state

**Files:**
- Modify: `server_shield/src/server_shield/pulumi_runner/program.py`

- [ ] **Step 1: Read the manifest state and add a stable serializer helper**

```python
import hashlib

from server_shield.shared.state_store import (
    read_desired_domains,
    read_manifest,
    write_axon_public_ip,
    write_root_domain,
)


def serialize_manifest_content(manifest: Mapping[str, object]) -> str:
    return json.dumps(manifest, indent=4, sort_keys=True) + "\n"


def manifest_source_hash(serialized_manifest: str) -> str:
    return hashlib.sha256(serialized_manifest.encode("utf-8")).hexdigest()
```

- [ ] **Step 2: Create the bucket object resource**

```python
def run_program() -> None:
    config = get_config()
    desired_domains = read_desired_domains().domains
    manifest = read_manifest().model_dump()
    serialized_manifest = serialize_manifest_content(manifest)
    ...
    aws.s3.BucketObject(
        "shield-manifest-object",
        bucket=bucket.id,
        key="shield_manifest.json",
        content=serialized_manifest,
        content_type="application/json",
        source_hash=manifest_source_hash(serialized_manifest),
        opts=pulumi.ResourceOptions(
            depends_on=[bucket_public_access, bucket_ownership],
        ),
    )
```

- [ ] **Step 3: Manually verify Pulumi uploads only when content changes**

Run:

```bash
tmp_state_dir="$(mktemp -d)"
cp server_shield/src/server_shield/shared/state_files/*.example.json "$tmp_state_dir"/
for file in "$tmp_state_dir"/*.example.json; do mv "$file" "${file%.example.json}.json"; done
printf '{\n    "domain": "shield.example.com"\n}\n' > "$tmp_state_dir/root_domain.json"
printf '{\n    "ddos_shield_manifest": {\n        "encrypted_url_mapping": {\n            "validator-hotkey-1": "ZXhhbXBsZQ=="\n        }\n    }\n}\n' > "$tmp_state_dir/manifest.json"
SERVER_SHIELD_STATE_DIR="$tmp_state_dir" ./manual_tests/run_pulumi.sh
SERVER_SHIELD_STATE_DIR="$tmp_state_dir" ./manual_tests/run_pulumi.sh
printf '{\n    "ddos_shield_manifest": {\n        "encrypted_url_mapping": {\n            "validator-hotkey-1": "ZXhhbXBsZS0y"\n        }\n    }\n}\n' > "$tmp_state_dir/manifest.json"
SERVER_SHIELD_STATE_DIR="$tmp_state_dir" ./manual_tests/run_pulumi.sh
```

Expected:
- the first run creates or updates `shield_manifest.json`
- the second run reports no manifest-object content change
- the third run updates the manifest object because content changed

- [ ] **Step 4: Commit the Pulumi upload change**

```bash
git add server_shield/src/server_shield/pulumi_runner/program.py
git commit -m "feat: upload manifest from pulumi state"
```

### Task 4: Update docs and complete end-to-end manual verification

**Files:**
- Modify: `README.md`
- Modify: `manual_tests/README.md`

- [ ] **Step 1: Update README state-file descriptions**

~~~md
Current state files:

- `root_domain.json`: `{ "domain": null }`
- `axon_public_ip.json`: `{ "ip": null }`
- `desired_domains.json`: `{ "domains": {} }`
- `blacklist.json`: `[]`
- `manifest.json`:

~~~json
{
    "ddos_shield_manifest": {
        "encrypted_url_mapping": {}
    }
}
~~~

Behavior notes:

- `chain_reader` writes both `desired_domains.json` and `manifest.json`.
- `manifest.json` contains the final JSON that Pulumi uploads to S3 as `shield_manifest.json`.
- All state files are written with stable pretty-printed JSON so diffs and Pulumi content hashes do not churn unnecessarily.
~~~

- [ ] **Step 2: Update manual test docs for manifest verification**

~~~md
After `./run_chain_reader.sh`, inspect:

~~~bash
cat /tmp/server-shield-state/manifest.json
~~~

After `./run_pulumi.sh`, confirm the uploaded object:

~~~bash
aws s3 cp "s3://<bucket-name>/shield_manifest.json" -
~~~

The downloaded object should match `/tmp/server-shield-state/manifest.json`.
~~~

- [ ] **Step 3: Run the full current automated suite once and record the result**

Run: `uv run --project server_shield pytest`

Expected: full suite passes after the manifest-contract updates to existing tests

- [ ] **Step 4: Commit the documentation updates**

```bash
git add README.md manual_tests/README.md
git commit -m "docs: describe manifest production flow"
```
