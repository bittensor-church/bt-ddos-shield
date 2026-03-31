# Real Contact Integration Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add client-library-owned integration tests for the real `BittensorSubtensorContact` and `TurboBittensorSubtensorContact` implementations, running against a disposable local subtensor environment created by the test suite itself.

**Architecture:** The client test suite gets a dedicated `tests/contacts/` integration layer with session-scoped local-subtensor bootstrap helpers, a `subtensor_integration` pytest mark, and one test module per real contact implementation. The bootstrap logic lives entirely under `bt_ddos_shield_client/tests/contacts/`; it does not depend on `manual_tests/`, and the repo-wide engineering standards are updated to require this pattern for real external-service adapters.

**Tech Stack:** Python 3.11+, `pytest`, `pytest-asyncio`, `testcontainers`, `bittensor`, `bittensor-wallet`, `turbobt`

---

## File Map

- Modify: `bt_ddos_shield_client/pyproject.toml`
  - Add `testcontainers` to test dependencies, register the `subtensor_integration` marker, and exclude it from default local test runs.
- Modify: `docs/engineering-standards.md`
  - Add the rule that real contact implementations need separate real-service tests in dedicated files.
- Create: `bt_ddos_shield_client/tests/contacts/__init__.py`
  - Mark the new folder as a test package.
- Create: `bt_ddos_shield_client/tests/contacts/local_subtensor.py`
  - Own the local subtensor container lifecycle and chain bootstrap logic for client-library tests.
- Create: `bt_ddos_shield_client/tests/contacts/conftest.py`
  - Expose session-scoped fixtures for `subtensor`, `turbobt_bittensor`, wallets, and `netuid`.
- Create: `bt_ddos_shield_client/tests/contacts/test_bittensor_subtensor_contact.py`
  - Real tests for `BittensorSubtensorContact` public methods only.
- Create: `bt_ddos_shield_client/tests/contacts/test_turbo_bittensor_subtensor_contact.py`
  - Real tests for `TurboBittensorSubtensorContact` public methods only.

## Task 1: Add Integration-Test Dependencies and Pytest Configuration

**Files:**
- Modify: `bt_ddos_shield_client/pyproject.toml`

- [ ] **Step 1: Write the failing marker-selection smoke test**

Add this test file first as `bt_ddos_shield_client/tests/contacts/test_marker_configuration.py`:

```python
import pytest


@pytest.mark.subtensor_integration
def test_subtensor_integration_marker_is_registered():
    assert True
```

- [ ] **Step 2: Run the test to verify it fails for the right reason**

Run:

```bash
uv run --project bt_ddos_shield_client --group test pytest \
  bt_ddos_shield_client/tests/contacts/test_marker_configuration.py -q
```

Expected:

- pytest either warns or errors because `subtensor_integration` is not registered
- the test is still discovered because the file exists

- [ ] **Step 3: Add the integration-test dependency and pytest marker configuration**

Modify `bt_ddos_shield_client/pyproject.toml`:

```toml
[dependency-groups]
test = [
    "pytest~=8.3.4",
    "pytest-asyncio~=1.0.0",
    "aioresponses~=0.7.8",
    "freezegun~=1.5.1",
    "testcontainers~=4.9.2",
    "bt_ddos_shield_client[turbobt]",
]

[tool.pytest.ini_options]
addopts = '-s -m "not subtensor_integration"'
asyncio_default_fixture_loop_scope = "function"
markers = [
    "subtensor_integration: real local-subtensor integration tests for contact implementations",
]
testpaths = [
    "tests",
]
```

- [ ] **Step 4: Re-run the marker-selection smoke test**

Run:

```bash
uv sync --project bt_ddos_shield_client --group test
uv run --project bt_ddos_shield_client --group test pytest \
  bt_ddos_shield_client/tests/contacts/test_marker_configuration.py -q -m subtensor_integration
```

Expected:

- dependency sync succeeds
- the test passes without unknown-marker warnings

- [ ] **Step 5: Remove the temporary marker smoke test if you do not want to keep it**

If you prefer not to keep this file in the final suite, delete it after the config is proven:

```bash
rm bt_ddos_shield_client/tests/contacts/test_marker_configuration.py
```

If you keep it, skip this step.

- [ ] **Step 6: Commit the config groundwork**

```bash
git add bt_ddos_shield_client/pyproject.toml \
        bt_ddos_shield_client/tests/contacts/test_marker_configuration.py
git commit -m "test: configure contact integration test marker"
```

If you removed the temporary file, leave it out of the commit.

## Task 2: Add Client-Library-Owned Local Subtensor Bootstrap Helpers

**Files:**
- Create: `bt_ddos_shield_client/tests/contacts/__init__.py`
- Create: `bt_ddos_shield_client/tests/contacts/local_subtensor.py`
- Create: `bt_ddos_shield_client/tests/contacts/conftest.py`

- [ ] **Step 1: Write the first failing bootstrap test**

Create `bt_ddos_shield_client/tests/contacts/test_bootstrap_smoke.py`:

```python
import pytest


@pytest.mark.subtensor_integration
def test_local_subtensor_bootstrap_exposes_registered_test_state(
    subtensor,
    validator_wallet,
    miner_wallet,
    netuid,
):
    validator_hotkey = validator_wallet.hotkey.ss58_address
    miner_hotkey = miner_wallet.hotkey.ss58_address

    assert subtensor.subnet_exists(netuid)
    assert subtensor.is_hotkey_registered_on_subnet(validator_hotkey, netuid=netuid)
    assert subtensor.is_hotkey_registered_on_subnet(miner_hotkey, netuid=netuid)
```

- [ ] **Step 2: Run the bootstrap test to verify it fails**

Run:

```bash
uv run --project bt_ddos_shield_client --group test pytest \
  bt_ddos_shield_client/tests/contacts/test_bootstrap_smoke.py -q -m subtensor_integration
```

Expected:

- FAIL because the `subtensor`, `validator_wallet`, `miner_wallet`, and `netuid` fixtures do not exist yet

- [ ] **Step 3: Add the local subtensor bootstrap helper module**

Create `bt_ddos_shield_client/tests/contacts/local_subtensor.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import time

from bittensor import Subtensor
from bittensor.core.extrinsics.registration import register_extrinsic, register_subnet_extrinsic
from bittensor.core.extrinsics.transfer import transfer_extrinsic
from bittensor.utils.balance import Balance
from bittensor_wallet import Wallet
from testcontainers.core.container import DockerContainer


LOCAL_SUBTENSOR_IMAGE = "ghcr.io/opentensor/subtensor-localnet:devnet-ready"


@dataclass
class LocalSubtensorEnv:
    container: DockerContainer
    ws_endpoint: str
    wallet_root: Path
    subtensor: Subtensor
    alice_wallet: Wallet
    validator_wallet: Wallet
    miner_wallet: Wallet
    netuid: int


def _wait_for_chain_ready(subtensor: Subtensor, *, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            subtensor.get_total_subnets()
            return
        except Exception:
            time.sleep(1.0)
    raise RuntimeError("local subtensor did not become ready in time")


def _make_wallet(wallet_root: Path, name: str, uri: str | None = None) -> Wallet:
    wallet = Wallet(path=str(wallet_root), name=name, hotkey="default")
    if uri is not None:
        wallet.create_coldkey_from_uri(uri, use_password=False, overwrite=True)
        wallet.create_hotkey_from_uri(uri, use_password=False, overwrite=True)
    else:
        wallet.create_new_coldkey(n_words=12, use_password=False, overwrite=True)
        wallet.create_new_hotkey(n_words=12, use_password=False, overwrite=True)
    return wallet


def start_local_subtensor_env() -> LocalSubtensorEnv:
    container = DockerContainer(LOCAL_SUBTENSOR_IMAGE)
    container.with_exposed_ports(9944, 9945)
    container.start()
    ws_port = int(container.get_exposed_port(9945))
    ws_endpoint = f"ws://127.0.0.1:{ws_port}"

    wallet_root = Path(tempfile.mkdtemp(prefix="shield-contact-wallets-"))
    subtensor = Subtensor(network=ws_endpoint)
    _wait_for_chain_ready(subtensor)

    alice_wallet = _make_wallet(wallet_root, "alice", "//Alice")
    validator_wallet = _make_wallet(wallet_root, "validator")
    miner_wallet = _make_wallet(wallet_root, "miner")

    transfer_extrinsic(
        subtensor,
        alice_wallet,
        validator_wallet.coldkeypub.ss58_address,
        Balance.from_tao(50_000),
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )
    transfer_extrinsic(
        subtensor,
        alice_wallet,
        miner_wallet.coldkeypub.ss58_address,
        Balance.from_tao(50_000),
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )

    before = subtensor.get_total_subnets()
    register_subnet_extrinsic(
        subtensor,
        alice_wallet,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )
    after = subtensor.get_total_subnets()
    if after <= before:
        raise RuntimeError("subnet registration did not increase subnet count")
    netuid = after - 1

    register_extrinsic(
        subtensor,
        validator_wallet,
        netuid,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )
    register_extrinsic(
        subtensor,
        miner_wallet,
        netuid,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )

    return LocalSubtensorEnv(
        container=container,
        ws_endpoint=ws_endpoint,
        wallet_root=wallet_root,
        subtensor=subtensor,
        alice_wallet=alice_wallet,
        validator_wallet=validator_wallet,
        miner_wallet=miner_wallet,
        netuid=netuid,
    )
```

- [ ] **Step 4: Add pytest fixtures for the bootstrap environment**

Create `bt_ddos_shield_client/tests/contacts/conftest.py`:

```python
from __future__ import annotations

import shutil

import pytest
import turbobt

from tests.contacts.local_subtensor import start_local_subtensor_env


@pytest.fixture(scope="session")
def local_subtensor_env():
    try:
        env = start_local_subtensor_env()
    except Exception as exc:  # pragma: no cover - environment gate
        pytest.skip(f"local subtensor integration environment unavailable: {exc}")
    try:
        yield env
    finally:
        env.container.stop()
        shutil.rmtree(env.wallet_root, ignore_errors=True)


@pytest.fixture(scope="session")
def subtensor(local_subtensor_env):
    return local_subtensor_env.subtensor


@pytest.fixture(scope="session")
def validator_wallet(local_subtensor_env):
    return local_subtensor_env.validator_wallet


@pytest.fixture(scope="session")
def miner_wallet(local_subtensor_env):
    return local_subtensor_env.miner_wallet


@pytest.fixture(scope="session")
def netuid(local_subtensor_env):
    return local_subtensor_env.netuid


@pytest.fixture(scope="session")
def turbobt_bittensor(local_subtensor_env, validator_wallet):
    return turbobt.Bittensor(local_subtensor_env.ws_endpoint, wallet=validator_wallet)
```

- [ ] **Step 5: Re-run the bootstrap smoke test**

Run:

```bash
uv run --project bt_ddos_shield_client --group test pytest \
  bt_ddos_shield_client/tests/contacts/test_bootstrap_smoke.py -q -m subtensor_integration
```

Expected:

- PASS once the container starts, wallets are funded, the subnet exists, and both hotkeys are registered

- [ ] **Step 6: Commit the bootstrap helper layer**

```bash
git add bt_ddos_shield_client/tests/contacts/__init__.py \
        bt_ddos_shield_client/tests/contacts/local_subtensor.py \
        bt_ddos_shield_client/tests/contacts/conftest.py \
        bt_ddos_shield_client/tests/contacts/test_bootstrap_smoke.py
git commit -m "test: add local subtensor bootstrap for contact integration tests"
```

## Task 3: Add Real Tests for `BittensorSubtensorContact`

**Files:**
- Create: `bt_ddos_shield_client/tests/contacts/test_bittensor_subtensor_contact.py`

- [ ] **Step 1: Write the failing `sync_metagraph(...)` integration test**

Create `bt_ddos_shield_client/tests/contacts/test_bittensor_subtensor_contact.py`:

```python
from __future__ import annotations

import pytest
from bittensor.core.metagraph import Metagraph

from bt_ddos_shield_client.certificates import EDDSACertificateManager
from bt_ddos_shield_client.contacts import BittensorSubtensorContact


@pytest.mark.subtensor_integration
def test_bittensor_contact_sync_metagraph_populates_registered_neurons(subtensor, netuid):
    contact = BittensorSubtensorContact()
    metagraph = Metagraph(netuid=netuid, network="local", lite=True, sync=False, subtensor=subtensor)

    contact.sync_metagraph(metagraph, subtensor=subtensor)

    assert len(metagraph.neurons) >= 2
    assert len(metagraph.axons) >= 2
```

- [ ] **Step 2: Run the first bittensor contact test to verify it fails if the contact path is wrong**

Run:

```bash
uv run --project bt_ddos_shield_client --group test pytest \
  bt_ddos_shield_client/tests/contacts/test_bittensor_subtensor_contact.py::test_bittensor_contact_sync_metagraph_populates_registered_neurons \
  -q -m subtensor_integration
```

Expected:

- FAIL until the local-subtensor bootstrap and test assumptions are correct
- once it passes, move to the next failing public-method tests immediately

- [ ] **Step 3: Add the remaining failing public-method tests**

Extend `bt_ddos_shield_client/tests/contacts/test_bittensor_subtensor_contact.py`:

```python
@pytest.mark.subtensor_integration
@pytest.mark.asyncio
async def test_bittensor_contact_reads_missing_certificate_for_registered_miner(
    subtensor,
    miner_wallet,
    netuid,
):
    contact = BittensorSubtensorContact()

    public_key = await contact.get_own_public_key(
        subtensor=subtensor,
        netuid=netuid,
        hotkey=miner_wallet.hotkey.ss58_address,
    )

    assert public_key is None


@pytest.mark.subtensor_integration
@pytest.mark.asyncio
async def test_bittensor_contact_reads_uploaded_certificate_for_validator(
    subtensor,
    validator_wallet,
    netuid,
):
    contact = BittensorSubtensorContact()
    certificate = EDDSACertificateManager.generate_certificate()
    hotkey = validator_wallet.hotkey.ss58_address

    await contact.upload_public_key(
        certificate.public_key,
        certificate.algorithm,
        subtensor=subtensor,
        wallet=validator_wallet,
        netuid=netuid,
    )

    after = await contact.get_own_public_key(
        subtensor=subtensor,
        netuid=netuid,
        hotkey=hotkey,
    )

    assert after == certificate.public_key
```

- [ ] **Step 4: Run the full real bittensor contact module**

Run:

```bash
uv run --project bt_ddos_shield_client --group test pytest \
  bt_ddos_shield_client/tests/contacts/test_bittensor_subtensor_contact.py \
  -q -m subtensor_integration
```

Expected:

- all tests in that module PASS

- [ ] **Step 5: Refine the assertions to stay strictly on public behavior**

Before committing, verify that the file:

- does not call `_get_own_public_key`
- does not call `_upload_public_key`
- does not call `_get_current_axon_info`
- does not assert trivial helper shapes unrelated to behavior

- [ ] **Step 6: Commit the real bittensor contact tests**

```bash
git add bt_ddos_shield_client/tests/contacts/test_bittensor_subtensor_contact.py
git commit -m "test: add real bittensor contact integration coverage"
```

## Task 4: Add Real Tests for `TurboBittensorSubtensorContact`

**Files:**
- Create: `bt_ddos_shield_client/tests/contacts/test_turbo_bittensor_subtensor_contact.py`

- [ ] **Step 1: Write the failing `list_neurons(...)` integration test**

Create `bt_ddos_shield_client/tests/contacts/test_turbo_bittensor_subtensor_contact.py`:

```python
from __future__ import annotations

import pytest

from bt_ddos_shield_client.certificates import EDDSACertificateManager
from bt_ddos_shield_client.shielded_turbobt.contacts import TurboBittensorSubtensorContact


@pytest.mark.subtensor_integration
@pytest.mark.asyncio
async def test_turbobt_contact_lists_registered_neurons(turbobt_bittensor, netuid):
    contact = TurboBittensorSubtensorContact()

    neurons = await contact.list_neurons(
        bittensor=turbobt_bittensor,
        netuid=netuid,
    )

    assert len(neurons) >= 2
```

- [ ] **Step 2: Run the first turbobt contact test**

Run:

```bash
uv run --project bt_ddos_shield_client --group test pytest \
  bt_ddos_shield_client/tests/contacts/test_turbo_bittensor_subtensor_contact.py::test_turbobt_contact_lists_registered_neurons \
  -q -m subtensor_integration
```

Expected:

- FAIL until the `turbobt_bittensor` fixture and bootstrap assumptions are correct

- [ ] **Step 3: Add the remaining failing public-method tests**

Extend `bt_ddos_shield_client/tests/contacts/test_turbo_bittensor_subtensor_contact.py`:

```python
@pytest.mark.subtensor_integration
@pytest.mark.asyncio
async def test_turbobt_contact_reads_missing_certificate_for_registered_miner(
    turbobt_bittensor,
    miner_wallet,
    netuid,
):
    contact = TurboBittensorSubtensorContact()

    public_key = await contact.get_own_public_key(
        bittensor=turbobt_bittensor,
        netuid=netuid,
        hotkey=miner_wallet.hotkey.ss58_address,
    )

    assert public_key is None


@pytest.mark.subtensor_integration
@pytest.mark.asyncio
async def test_turbobt_contact_reads_uploaded_certificate_for_validator(
    turbobt_bittensor,
    validator_wallet,
    netuid,
):
    contact = TurboBittensorSubtensorContact()
    certificate = EDDSACertificateManager.generate_certificate()
    hotkey = validator_wallet.hotkey.ss58_address

    await contact.upload_public_key(
        certificate.public_key,
        certificate.algorithm,
        bittensor=turbobt_bittensor,
        netuid=netuid,
        wallet=validator_wallet,
    )

    after = await contact.get_own_public_key(
        bittensor=turbobt_bittensor,
        netuid=netuid,
        hotkey=hotkey,
    )

    assert after == certificate.public_key
```

- [ ] **Step 4: Run the full turbobt contact module**

Run:

```bash
uv run --project bt_ddos_shield_client --group test pytest \
  bt_ddos_shield_client/tests/contacts/test_turbo_bittensor_subtensor_contact.py \
  -q -m subtensor_integration
```

Expected:

- all tests in that module PASS

- [ ] **Step 5: Refine the assertions to stay strictly on public behavior**

Before committing, verify that the file:

- does not reach into `turbobt` internals beyond real client construction
- does not mock the contact implementation itself
- does not assert private helper behavior

- [ ] **Step 6: Commit the real turbobt contact tests**

```bash
git add bt_ddos_shield_client/tests/contacts/test_turbo_bittensor_subtensor_contact.py
git commit -m "test: add real turbobt contact integration coverage"
```

## Task 5: Update Engineering Standards for Real Contact Tests

**Files:**
- Modify: `docs/engineering-standards.md`

- [ ] **Step 1: Write the failing documentation expectation as a review checklist item**

Use this checklist when editing the doc:

- real external-service adapters require separate real-service tests
- those tests live in dedicated files
- those tests use public adapter methods only
- they may be heavy and integration-marked
- when practical they create their own disposable environment
- they must not depend on unrelated manual-test directories

- [ ] **Step 2: Add the new repo-wide rules**

Extend `docs/engineering-standards.md` with a new section after `Public API Testing Rules`:

```md
## Real Adapter Integration Testing Rules

### Required

- Every real external-service adapter must have separate tests for the real implementation.
- Those tests must live in dedicated files.
- Those tests must exercise only public adapter methods.
- Those tests may be heavy integration tests.
- Those tests should be opt-in locally and expected in CI.
- When practical, those tests should create their own disposable external-service environment.
- Those tests must not depend on unrelated manual-test directories for runtime dependencies.

### Forbidden

- Do not rely only on mocks for real adapter correctness.
- Do not test private adapter helpers in place of real adapter behavior.
- Do not hide real adapter tests inside unrelated wrapper test modules.
```

- [ ] **Step 3: Verify the standards doc stays aligned with the new test layer**

Run:

```bash
rg -n "Real Adapter Integration Testing Rules|manual-test directories|public adapter methods" \
  docs/engineering-standards.md
```

Expected:

- the new rules are present exactly once

- [ ] **Step 4: Commit the standards update**

```bash
git add docs/engineering-standards.md
git commit -m "docs: require real adapter integration tests"
```

## Task 6: Final Verification and Cleanup

**Files:**
- Modify: `bt_ddos_shield_client/pyproject.toml`
- Modify: `docs/engineering-standards.md`
- Create: `bt_ddos_shield_client/tests/contacts/__init__.py`
- Create: `bt_ddos_shield_client/tests/contacts/local_subtensor.py`
- Create: `bt_ddos_shield_client/tests/contacts/conftest.py`
- Create: `bt_ddos_shield_client/tests/contacts/test_bittensor_subtensor_contact.py`
- Create: `bt_ddos_shield_client/tests/contacts/test_turbo_bittensor_subtensor_contact.py`

- [ ] **Step 1: Run the lightweight default test suite**

Run:

```bash
uv run --project bt_ddos_shield_client --group test pytest bt_ddos_shield_client/tests -q
```

Expected:

- existing lightweight suite still PASS
- the `subtensor_integration` tests are excluded by default

- [ ] **Step 2: Run only the integration-marked contact tests**

Run:

```bash
uv run --project bt_ddos_shield_client --group test pytest \
  bt_ddos_shield_client/tests/contacts \
  -q -m subtensor_integration
```

Expected:

- the local subtensor container starts
- the chain bootstrap completes
- both real contact test modules PASS

- [ ] **Step 3: Run syntax and diff sanity checks**

Run:

```bash
uv run --project bt_ddos_shield_client --group test python3 -m compileall \
  bt_ddos_shield_client/bt_ddos_shield_client \
  bt_ddos_shield_client/tests/contacts
git diff --check
```

Expected:

- `compileall` completes without syntax errors
- `git diff --check` prints nothing

- [ ] **Step 4: Verify the final diff against the spec**

Run:

```bash
git diff -- bt_ddos_shield_client/pyproject.toml \
           docs/engineering-standards.md \
           bt_ddos_shield_client/tests/contacts/__init__.py \
           bt_ddos_shield_client/tests/contacts/local_subtensor.py \
           bt_ddos_shield_client/tests/contacts/conftest.py \
           bt_ddos_shield_client/tests/contacts/test_bittensor_subtensor_contact.py \
           bt_ddos_shield_client/tests/contacts/test_turbo_bittensor_subtensor_contact.py
```

Confirm all of the following:

- integration tests exist only for the client library
- they do not depend on `manual_tests/`
- they are dedicated files for the real contact implementations
- they test only public contact methods
- they create and tear down the local subtensor environment themselves
- they are marked and excluded from default local runs
- engineering standards now require this pattern for real external-service adapters

- [ ] **Step 5: Commit the final integration pass**

```bash
git add bt_ddos_shield_client/pyproject.toml \
        docs/engineering-standards.md \
        bt_ddos_shield_client/tests/contacts/__init__.py \
        bt_ddos_shield_client/tests/contacts/local_subtensor.py \
        bt_ddos_shield_client/tests/contacts/conftest.py \
        bt_ddos_shield_client/tests/contacts/test_bittensor_subtensor_contact.py \
        bt_ddos_shield_client/tests/contacts/test_turbo_bittensor_subtensor_contact.py
git commit -m "test: add real contact integration coverage"
```
