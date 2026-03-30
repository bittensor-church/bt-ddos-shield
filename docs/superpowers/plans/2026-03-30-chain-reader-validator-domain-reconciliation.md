# Chain Reader Validator Domain Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current stub chain reader with a real validator-domain reconciler that reads validators and certificates from chain and writes stable `desired_domains.json` entries, rotating only for new validators, certificate changes, or root-domain changes.

**Architecture:** Keep the component model unchanged: `chain_reader` remains a one-shot batch job coordinated by the existing supervisor and shared JSON state directory. Add one focused module for chain reads and certificate decoding, one focused module for deterministic reconciliation, then wire `cli.py` to orchestrate the flow and log counts. Per the user’s explicit instruction, verification is manual against live chain data and local state files; no new unit tests are added in this plan.

**Tech Stack:** Python 3.14, bittensor 9.12.2, Pydantic state models, uv, Markdown docs

---

## File Structure

- Create: `server_shield/src/server_shield/chain_reader/chain.py`
  - Fetch validator hotkeys from the live metagraph and decode published validator certificates from `NeuronCertificates`.
- Create: `server_shield/src/server_shield/chain_reader/reconciliation.py`
  - Reconcile current chain validator/cert state with the persisted desired-domain mapping and generate unique new domains when needed.
- Modify: `server_shield/src/server_shield/chain_reader/cli.py`
  - Replace the current stub implementation with real orchestration, skip behavior, logging, and state writes.
- Modify: `README.md`
  - Document `blacklist.json` operation and recommend mounting the full state directory in production.
- Modify: `manual_tests/README.md`
  - Add a concrete chain-reader manual verification flow using Finney subnet 12 and the shared state directory.

### Task 1: Add live validator and certificate fetching

**Files:**
- Create: `server_shield/src/server_shield/chain_reader/chain.py`

- [ ] **Step 1: Create the chain-read module with typed results and certificate decoding**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import bittensor

from server_shield.shared.config import AppConfig


@dataclass(frozen=True)
class ValidatorOnChain:
    hotkey: str
    public_cert: str | None
    cert_invalid_reason: str | None = None


def _decode_certificate_payload(payload: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if payload is None:
        return None, "missing certificate"

    try:
        public_key = payload["public_key"][0]
    except (KeyError, TypeError, IndexError):
        return None, "malformed certificate payload"

    if isinstance(public_key, str):
        return public_key, None

    try:
        return bytes(public_key).hex(), None
    except (TypeError, ValueError):
        return None, "malformed certificate payload"


def fetch_validators_with_certs(config: AppConfig) -> list[ValidatorOnChain]:
    network = config.subtensor_address
    subtensor = bittensor.subtensor(network)
    metagraph = bittensor.metagraph(
        netuid=config.netuid,
        network=network,
        subtensor=subtensor,
    )

    validators: list[ValidatorOnChain] = []
    for hotkey, permit in zip(metagraph.hotkeys, metagraph.validator_permit, strict=False):
        if not bool(permit):
            continue
        certificate = subtensor.query_subtensor(
            name="NeuronCertificates",
            params=[config.netuid, hotkey],
        )
        public_cert, invalid_reason = _decode_certificate_payload(certificate)
        validators.append(
            ValidatorOnChain(
                hotkey=hotkey,
                public_cert=public_cert,
                cert_invalid_reason=invalid_reason,
            )
        )
    return validators
```

- [ ] **Step 2: Confirm the live API shape against Finney subnet 12 before wiring the CLI**

Run:

```bash
uv run --project server_shield python - <<'PY'
import bittensor

sub = bittensor.subtensor("finney")
metagraph = bittensor.metagraph(netuid=12, network="finney", subtensor=sub)
validator_hotkeys = [
    hotkey
    for hotkey, permit in zip(metagraph.hotkeys, metagraph.validator_permit, strict=False)
    if bool(permit)
]
print(f"validator_count={len(validator_hotkeys)}")
print(f"first_hotkey={validator_hotkeys[0]}")
print(sub.query_subtensor(name="NeuronCertificates", params=[12, validator_hotkeys[0]]))
PY
```

Expected: a non-zero validator count and a certificate dict with keys including `public_key` and `algorithm`

- [ ] **Step 3: Commit the chain-read helper**

```bash
git add server_shield/src/server_shield/chain_reader/chain.py
git commit -m "feat: add chain reader validator fetcher"
```

### Task 2: Add deterministic domain reconciliation and CLI wiring

**Files:**
- Create: `server_shield/src/server_shield/chain_reader/reconciliation.py`
- Modify: `server_shield/src/server_shield/chain_reader/cli.py`

- [ ] **Step 1: Create the reconciliation module**

```python
from __future__ import annotations

from dataclasses import dataclass
import secrets

from server_shield.chain_reader.chain import ValidatorOnChain
from server_shield.shared.state import DesiredDomainEntry


@dataclass(frozen=True)
class ReconciliationResult:
    desired_domains: dict[str, DesiredDomainEntry]
    kept: int
    created: int
    rotated_for_cert: int
    rotated_for_root_domain: int
    removed: int
    blacklisted: int
    invalid_cert: int
    observed: int


def _generate_domain_label(hotkey: str, used_domains: set[str], root_domain: str) -> str:
    prefix = hotkey[:8]
    while True:
        candidate = f"{prefix}-{secrets.token_hex(6)}.{root_domain}"
        if candidate not in used_domains:
            used_domains.add(candidate)
            return candidate


def reconcile_desired_domains(
    *,
    root_domain: str,
    current_domains: dict[str, DesiredDomainEntry],
    validators: list[ValidatorOnChain],
    blacklist: set[str],
) -> ReconciliationResult:
    next_domains: dict[str, DesiredDomainEntry] = {}
    used_domains: set[str] = set()
    kept = created = rotated_for_cert = rotated_for_root_domain = invalid_cert = blacklisted_count = 0

    eligible_hotkeys: set[str] = set()
    for validator in validators:
        if validator.hotkey in blacklist:
            blacklisted_count += 1
            continue
        if validator.public_cert is None:
            invalid_cert += 1
            continue

        eligible_hotkeys.add(validator.hotkey)
        current_entry = current_domains.get(validator.hotkey)
        if (
            current_entry is not None
            and current_entry.public_cert == validator.public_cert
            and current_entry.domain.endswith(f".{root_domain}")
        ):
            next_domains[validator.hotkey] = current_entry
            used_domains.add(current_entry.domain)
            kept += 1
            continue

        new_domain = _generate_domain_label(validator.hotkey, used_domains, root_domain)
        next_domains[validator.hotkey] = DesiredDomainEntry(
            domain=new_domain,
            public_cert=validator.public_cert,
        )
        if current_entry is None:
            created += 1
        elif current_entry.public_cert != validator.public_cert:
            rotated_for_cert += 1
        else:
            rotated_for_root_domain += 1

    removed = len(set(current_domains) - eligible_hotkeys)
    return ReconciliationResult(
        desired_domains=next_domains,
        kept=kept,
        created=created,
        rotated_for_cert=rotated_for_cert,
        rotated_for_root_domain=rotated_for_root_domain,
        removed=removed,
        blacklisted=blacklisted_count,
        invalid_cert=invalid_cert,
        observed=len(validators),
    )
```

- [ ] **Step 2: Replace the stub CLI flow with real orchestration**

```python
from server_shield.chain_reader.chain import fetch_validators_with_certs
from server_shield.chain_reader.reconciliation import reconcile_desired_domains
from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component
from server_shield.shared.state_store import (
    ensure_state_files,
    read_blacklist,
    read_desired_domains,
    read_root_domain,
    write_desired_domains,
)


def _run_once() -> int:
    ensure_state_files()
    root_domain = read_root_domain()
    if root_domain.domain is None:
        print("skipping chain_reader because root_domain is null", flush=True)
        return 0

    config = get_config()
    blacklist = set(read_blacklist().root)
    current_domains = read_desired_domains().domains
    validators = fetch_validators_with_certs(config)

    for validator in validators:
        if validator.hotkey in blacklist:
            print(f"excluding blacklisted validator {validator.hotkey}", flush=True)
        elif validator.public_cert is None:
            print(
                f"excluding validator {validator.hotkey}: {validator.cert_invalid_reason}",
                flush=True,
            )

    result = reconcile_desired_domains(
        root_domain=root_domain.domain,
        current_domains=current_domains,
        validators=validators,
        blacklist=blacklist,
    )
    write_desired_domains(domains={
        hotkey: entry.model_dump()
        for hotkey, entry in result.desired_domains.items()
    })
    print(
        "chain_reader reconciled "
        f"observed={result.observed} kept={result.kept} created={result.created} "
        f"rotated_for_cert={result.rotated_for_cert} "
        f"rotated_for_root_domain={result.rotated_for_root_domain} "
        f"removed={result.removed} blacklisted={result.blacklisted} "
        f"invalid_cert={result.invalid_cert}",
        flush=True,
    )
    return 0


def main() -> int:
    get_config()
    return run_component("chain-reader", _run_once)
```

- [ ] **Step 3: Run the component with a null root domain and verify the skip path does not rewrite desired domains**

Run:

```bash
tmp_state_dir="$(mktemp -d)"
cp server_shield/src/server_shield/shared/state_files/*.example.json "$tmp_state_dir"/
for file in "$tmp_state_dir"/*.example.json; do mv "$file" "${file%.example.json}.json"; done
python - <<'PY' "$tmp_state_dir"
from pathlib import Path
import json
import sys

state_dir = Path(sys.argv[1])
(state_dir / "desired_domains.json").write_text(
    json.dumps(
        {
            "domains": {
                "keep-me": {
                    "domain": "keep-me.example.com",
                    "public_cert": "cert-a",
                }
            }
        }
    ) + "\n"
)
PY
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
cat "$tmp_state_dir/desired_domains.json"
```

Expected:
- stdout includes `skipping chain_reader because root_domain is null`
- `desired_domains.json` still contains the existing `keep-me` entry unchanged

- [ ] **Step 4: Run the component with a real root domain against Finney subnet 12 and verify stable reconciliation**

Run:

```bash
tmp_state_dir="$(mktemp -d)"
cp server_shield/src/server_shield/shared/state_files/*.example.json "$tmp_state_dir"/
for file in "$tmp_state_dir"/*.example.json; do mv "$file" "${file%.example.json}.json"; done
printf '{\"domain\": \"shield.example.com\"}\n' > "$tmp_state_dir/root_domain.json"
printf '[\"5DoKZ3oPk1T1dedm5E7LrbJBS4ioEJPf3WYgULn2x6NvzNr5\"]\n' > "$tmp_state_dir/blacklist.json"
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
cat "$tmp_state_dir/desired_domains.json"
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
cat "$tmp_state_dir/desired_domains.json"
```

Expected:
- first run creates entries for eligible validators on subnet 12 except the blacklisted hotkey
- second run preserves the exact same domains for unchanged validators
- every created domain matches `<first8hotkey>-<12 lowercase hex chars>.shield.example.com`

- [ ] **Step 5: Commit the reconciliation implementation**

```bash
git add \
  server_shield/src/server_shield/chain_reader/chain.py \
  server_shield/src/server_shield/chain_reader/reconciliation.py \
  server_shield/src/server_shield/chain_reader/cli.py
git commit -m "feat: reconcile validator domains from chain"
```

### Task 3: Document blacklist operations and production mounting

**Files:**
- Modify: `README.md`
- Modify: `manual_tests/README.md`

- [ ] **Step 1: Update the main README state-file and operations section**

~~~md
Current state files:

- `root_domain.json`: `{ "domain": null }`
- `axon_public_ip.json`: `{ "ip": null }`
- `desired_domains.json`: `{ "domains": {} }`
- `blacklist.json`: `[]`
- `manifest.json`: `{ "manifest_url": null, "encrypted_addresses": [] }`

Behavior notes:

- If `root_domain.json` still contains `null`, the chain reader exits cleanly and leaves `desired_domains.json` unchanged.
- The chain reader fetches validators from chain, excludes any hotkeys listed in `blacklist.json`, excludes validators with missing or invalid certs, and reconciles `desired_domains.json` to match the eligible validator set.
- Existing validator domains stay stable across runs unless the validator cert changes or the root domain changes.

Blacklist operations:

- `blacklist.json` is a human-maintained JSON array of validator hotkeys.
- Add a validator hotkey to remove it from `desired_domains.json` on the next chain-reader run.
- Remove a validator hotkey to allow the chain reader to add it back if it is still an eligible validator with a valid cert.
- In production, mount the entire server-shield state directory rather than mounting only `blacklist.json`.
~~~

- [ ] **Step 2: Add a concrete manual-test section for chain reader**

~~~md
### chain_reader

Set these values in `manual_tests/.env`:

- `SERVER_SHIELD_SUBTENSOR_ADDRESS=finney`
- `SERVER_SHIELD_NETUID=12`
- `SERVER_SHIELD_STATE_DIR=/tmp/server-shield-state`

Prepare the state directory:

~~~bash
mkdir -p /tmp/server-shield-state
cp ../server_shield/src/server_shield/shared/state_files/*.example.json /tmp/server-shield-state/
for file in /tmp/server-shield-state/*.example.json; do mv "$file" "${file%.example.json}.json"; done
printf '{\"domain\": \"shield.example.com\"}\n' > /tmp/server-shield-state/root_domain.json
printf '[]\n' > /tmp/server-shield-state/blacklist.json
~~~

Run the reader:

~~~bash
./run_chain_reader.sh
cat /tmp/server-shield-state/desired_domains.json
~~~

To blacklist a validator:

~~~bash
printf '[\"<validator-hotkey>\"]\n' > /tmp/server-shield-state/blacklist.json
./run_chain_reader.sh
cat /tmp/server-shield-state/desired_domains.json
~~~
~~~

- [ ] **Step 3: Verify the docs reflect the implemented behavior**

Run:

```bash
rg -n "blacklist.json|root_domain.json|desired_domains.json|mount the entire|chain reader" README.md manual_tests/README.md
```

Expected: the grep output shows the blacklist workflow, root-domain skip behavior, and the recommendation to mount the whole state directory

- [ ] **Step 4: Commit the documentation changes**

```bash
git add README.md manual_tests/README.md
git commit -m "docs: explain chain reader blacklist workflow"
```
