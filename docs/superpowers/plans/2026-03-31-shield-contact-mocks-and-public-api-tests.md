# Shield Contact Mocks and Public API Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add production-package mock contact implementations, downstream-facing testing helpers, committed real certificate fixtures, and public-API tests that cover reconciliation, concurrent manifest resolution, and TTL behavior without any real subtensor communication.

**Architecture:** Keep the low-level test seam aligned with the contact singleton factories: repository tests patch `bittensor_subtensor_contact()` / `turbo_bittensor_subtensor_contact()` and mocked HTTP responses only. Add mutable declarative mock contacts in the production package plus a higher-level `testing.py` helper layer that hides contact patching and manifest setup for downstream users, while all tests continue to exercise `ShieldMetagraph`, `LegacyTurbobtWrapper`, and `LegacySubnetReference.from_bittensor(...)` through public APIs.

**Tech Stack:** Python 3.11+, `pytest`, `pytest-asyncio`, `aioresponses`, `freezegun`, existing certificate/encryption helpers in `bt_ddos_shield_client`

---

## File Map

- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/contacts.py`
  - Add `MockBittensorSubtensorContact` plus structured call recording.
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/contacts.py`
  - Add `MockTurboBittensorSubtensorContact` plus structured call recording.
- Create: `bt_ddos_shield_client/bt_ddos_shield_client/testing.py`
  - Add downstream-facing fixture-style helpers that wrap mock contacts and manifest setup.
- Modify: `bt_ddos_shield_client/pyproject.toml`
  - Add `freezegun` to the test dependency group.
- Create: `bt_ddos_shield_client/tests/fixtures/certs/validator_a.pem`
- Create: `bt_ddos_shield_client/tests/fixtures/certs/validator_b.pem`
- Create: `bt_ddos_shield_client/tests/fixtures/certs/validator_c.pem`
- Create: `bt_ddos_shield_client/tests/fixtures/certs/README.md`
  - Document fixture provenance and purpose.
- Create: `bt_ddos_shield_client/tests/conftest.py`
  - Add patched-contact fixtures that own the `monkeypatch` calls and return mutable mock contacts to tests.
- Create: `bt_ddos_shield_client/tests/fixtures.py`
  - Provide fixture path loaders and certificate readers for tests.
- Modify: `bt_ddos_shield_client/tests/fakes.py`
  - Replace `SimpleNamespace` object builders with real `NeuronInfo` / `turbobt.neuron.Neuron` factory helpers plus manifest helpers.
- Modify: `bt_ddos_shield_client/tests/test_shield_metagraph.py`
  - Rewrite to use public API, patched singleton factory, mocked HTTP responses, and frozen time.
- Modify: `test_legacy_turbobt_wrapper.py`
  - Rewrite to use public API, patched singleton factory, mocked HTTP responses, and frozen time.
- Create: `bt_ddos_shield_client/tests/test_testing_helpers.py`
  - Add public-API tests for the downstream helper layer.

## Task 1: Add Real Certificate Fixtures and Shared Test Helpers

**Files:**
- Modify: `bt_ddos_shield_client/pyproject.toml`
- Create: `bt_ddos_shield_client/tests/fixtures/certs/validator_a.pem`
- Create: `bt_ddos_shield_client/tests/fixtures/certs/validator_b.pem`
- Create: `bt_ddos_shield_client/tests/fixtures/certs/validator_c.pem`
- Create: `bt_ddos_shield_client/tests/fixtures/certs/README.md`
- Create: `bt_ddos_shield_client/tests/fixtures.py`
- Modify: `bt_ddos_shield_client/tests/fakes.py`
- Create: `bt_ddos_shield_client/tests/conftest.py`

- [ ] **Step 1: Add `freezegun` to test dependencies**

Modify `bt_ddos_shield_client/pyproject.toml`:

```toml
[dependency-groups]
test = [
    "pytest~=8.3.4",
    "pytest-asyncio~=1.0.0",
    "aioresponses~=0.7.8",
    "freezegun~=1.5.1",
    "bt_ddos_shield_client[turbobt]",
]
```

- [ ] **Step 2: Add committed certificate fixtures**

Create three committed PEM files under `bt_ddos_shield_client/tests/fixtures/certs/` using the same format already produced by `EDDSACertificateManager.save_certificate(...)`.

Create `bt_ddos_shield_client/tests/fixtures/certs/README.md`:

```md
# Certificate Fixtures

These PEM files were generated with `bt_ddos_shield_client.certificates.EDDSACertificateManager`
and are committed so tests use deterministic real keys.

- `validator_a.pem`
- `validator_b.pem`
- `validator_c.pem`
```

- [ ] **Step 3: Add the fixture loader helper**

Create `bt_ddos_shield_client/tests/fixtures.py`:

```python
from __future__ import annotations

from pathlib import Path

from bt_ddos_shield_client.certificates import Certificate, EDDSACertificateManager


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "certs"


def certificate_fixture_path(filename: str) -> Path:
    return FIXTURES_DIR / filename


def load_certificate_fixture(filename: str) -> Certificate:
    return EDDSACertificateManager().load_certificate(str(certificate_fixture_path(filename)))
```

- [ ] **Step 4: Add real neuron builder helpers**

Modify `bt_ddos_shield_client/tests/fakes.py` so all test examples use real neuron objects with default-filled builders instead of `SimpleNamespace`:

```python
from __future__ import annotations

import base64
import json
from ipaddress import ip_address

from bittensor.core.chain_data import AxonInfo, NeuronInfo, PrometheusInfo
from bittensor.utils.balance import Balance
import turbobt
from turbobt.neuron import AxonInfo as TurboAxonInfo
from turbobt.neuron import AxonProtocolEnum, Neuron as TurboNeuron, PrometheusInfo as TurboPrometheusInfo

from types import SimpleNamespace

from bt_ddos_shield_client.encryption import ECIESEncryptionManager


def make_wallet(hotkey: str = "validator-hotkey"):
    return SimpleNamespace(hotkey=SimpleNamespace(ss58_address=hotkey))


def make_bittensor_neuron(
    *,
    hotkey: str,
    ip: str,
    port: int,
    uid: int = 0,
    netuid: int = 7,
    coldkey: str = "miner-coldkey",
) -> NeuronInfo:
    return NeuronInfo(
        hotkey=hotkey,
        coldkey=coldkey,
        uid=uid,
        netuid=netuid,
        active=1,
        stake=Balance.from_tao(0),
        stake_dict={},
        total_stake=Balance.from_tao(0),
        rank=0.0,
        emission=0.0,
        incentive=0.0,
        consensus=0.0,
        trust=0.0,
        validator_trust=0.0,
        dividends=0.0,
        last_update=0,
        validator_permit=False,
        weights=[],
        bonds=[],
        pruning_score=0,
        prometheus_info=PrometheusInfo(block=0, version=1, ip="127.0.0.1", port=9090, ip_type=4),
        axon_info=AxonInfo(version=1, ip=ip, port=port, ip_type=4, hotkey=hotkey, coldkey=coldkey),
    )


def make_turbobt_neuron(
    *,
    hotkey: str,
    ip: str,
    port: int,
    uid: int = 0,
    coldkey: str = "miner-coldkey",
) -> TurboNeuron:
    return TurboNeuron(
        subnet=turbobt.Subnet(
            object(),
            netuid=7,
            name="test-subnet",
            symbol="TS",
            tempo=0,
            owner_hotkey="owner-hotkey",
            owner_coldkey="owner-coldkey",
            identity={},
        ),
        uid=uid,
        coldkey=coldkey,
        hotkey=hotkey,
        active=True,
        axon_info=TurboAxonInfo(ip=ip_address(ip), port=port, protocol=AxonProtocolEnum.HTTP),
        prometheus_info=TurboPrometheusInfo(ip=ip_address("127.0.0.1"), port=9090),
        stake=0.0,
        rank=0.0,
        emission=0.0,
        incentive=0.0,
        consensus=0.0,
        trust=0.0,
        validator_trust=0.0,
        dividends=0.0,
        last_update=0,
        validator_permit=False,
        pruning_score=0,
    )


def build_manifest_body(public_key: str, address: str, validator_hotkey: str = "validator-hotkey") -> bytes:
    encrypted = ECIESEncryptionManager().encrypt(public_key, address.encode())
    return json.dumps(
        {
            "ddos_shield_manifest": {
                "encrypted_url_mapping": {
                    validator_hotkey: base64.b64encode(encrypted).decode(),
                },
            }
        }
    ).encode()
```

- [ ] **Step 5: Add patched-contact fixtures**

Create `bt_ddos_shield_client/tests/conftest.py`:

```python
from __future__ import annotations

import pytest

from bt_ddos_shield_client.contacts import MockBittensorSubtensorContact
from bt_ddos_shield_client.shielded_turbobt.contacts import MockTurboBittensorSubtensorContact


@pytest.fixture
def patched_bittensor_contact(monkeypatch) -> MockBittensorSubtensorContact:
    contact = MockBittensorSubtensorContact()
    monkeypatch.setattr(
        "bt_ddos_shield_client.shield_metagraph.bittensor_subtensor_contact",
        lambda: contact,
    )
    return contact


@pytest.fixture
def patched_turbo_bittensor_contact(monkeypatch) -> MockTurboBittensorSubtensorContact:
    contact = MockTurboBittensorSubtensorContact()
    monkeypatch.setattr(
        "legacy_turbobt_wrapper.py.turbo_bittensor_subtensor_contact",
        lambda: contact,
    )
    return contact
```

- [ ] **Step 6: Run the helper module smoke tests**

Run:

```bash
uv run --project bt_ddos_shield_client pytest \
  bt_ddos_shield_client/tests/test_shield_metagraph.py::test_shield_metagraph_uses_option_certificate_path \
  test_legacy_turbobt_wrapper.py::test_shielded_subnet_reference_is_public -v
```

Expected: one or both tests FAIL until the rewritten helpers land in the next tasks, but the imports and fixture files are now in place.

- [ ] **Step 7: Commit the fixture groundwork**

```bash
git add bt_ddos_shield_client/pyproject.toml \
        bt_ddos_shield_client/tests/fixtures/certs/validator_a.pem \
        bt_ddos_shield_client/tests/fixtures/certs/validator_b.pem \
        bt_ddos_shield_client/tests/fixtures/certs/validator_c.pem \
        bt_ddos_shield_client/tests/fixtures/certs/README.md \
        bt_ddos_shield_client/tests/fixtures.py \
        bt_ddos_shield_client/tests/fakes.py \
        bt_ddos_shield_client/tests/conftest.py
git commit -m "test: add shield certificate fixtures"
```

## Task 2: Add Mutable Production-Package Mock Contacts

**Files:**
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/contacts.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/contacts.py`

- [ ] **Step 1: Write the failing mock-contact tests**

Add tests to `bt_ddos_shield_client/tests/test_shield_metagraph.py` and `test_legacy_turbobt_wrapper.py` for the public mock classes:

```python
from bt_ddos_shield_client.contacts import MockBittensorSubtensorContact


@pytest.mark.asyncio
async def test_mock_bittensor_contact_records_and_mutates_state():
    contact = MockBittensorSubtensorContact()
    contact.set_own_certificate(public_key="abc123")
    assert await contact.get_own_public_key(subtensor=object(), netuid=7, hotkey="validator") == "abc123"

    contact.set_own_certificate(public_key="def456")
    assert await contact.get_own_public_key(subtensor=object(), netuid=7, hotkey="validator") == "def456"
    assert [call.method for call in contact.calls] == ["get_own_public_key", "get_own_public_key"]
```

```python
from bt_ddos_shield_client.shielded_turbobt.contacts import MockTurboBittensorSubtensorContact
from bt_ddos_shield_client.tests.fakes import make_turbobt_neuron


@pytest.mark.asyncio
async def test_mock_turbobt_contact_records_listing_calls():
    contact = MockTurboBittensorSubtensorContact()
    contact.set_neuron_listing(neurons=[make_turbobt_neuron(hotkey="miner-a", ip="198.51.100.50", port=5050)])

    result = await contact.list_neurons(bittensor=object(), netuid=7)

    assert [neuron.hotkey for neuron in result] == ["miner-a"]
    assert contact.calls[0].method == "list_neurons"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run --project bt_ddos_shield_client pytest \
  bt_ddos_shield_client/tests/test_shield_metagraph.py::test_mock_bittensor_contact_records_and_mutates_state \
  test_legacy_turbobt_wrapper.py::test_mock_turbobt_contact_records_listing_calls -v
```

Expected: FAIL because the mock contact classes do not exist yet.

- [ ] **Step 3: Add structured call-record dataclasses and the bittensor mock**

Extend `bt_ddos_shield_client/bt_ddos_shield_client/contacts.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BittensorContactCall:
    method: str
    netuid: int | None = None
    hotkey: str | None = None
    public_key: PublicKey | None = None


@dataclass
class MockBittensorSubtensorContact(AbstractBittensorSubtensorContact):
    own_public_key: PublicKey | None = None
    upload_exception: Exception | None = None
    sync_neurons: list[NeuronInfo] = field(default_factory=list)
    calls: list[BittensorContactCall] = field(default_factory=list)

    def set_metagraph_sync(self, neurons: list[NeuronInfo]) -> None:
        self.sync_neurons = list(neurons)

    def set_own_certificate(self, public_key: PublicKey | None) -> None:
        self.own_public_key = public_key

    def set_upload_behavior(self, exception: Exception | None = None) -> None:
        self.upload_exception = exception

    def reset_calls(self) -> None:
        self.calls.clear()

    def sync_metagraph(self, metagraph: Metagraph, *, subtensor: Subtensor, block: int | None = None, lite: bool | None = None) -> None:
        self.calls.append(BittensorContactCall(method="sync_metagraph", netuid=metagraph.netuid))
        metagraph.axons = [neuron.axon_info for neuron in self.sync_neurons]
        metagraph.neurons = list(self.sync_neurons)
        metagraph.lite = metagraph.lite if lite is None else lite

    async def get_own_public_key(self, *, subtensor: Subtensor, netuid: int, hotkey: str) -> PublicKey | None:
        self.calls.append(BittensorContactCall(method="get_own_public_key", netuid=netuid, hotkey=hotkey))
        return self.own_public_key

    async def upload_public_key(self, *, subtensor: Subtensor, wallet, netuid: int, public_key: PublicKey, algorithm: CertificateAlgorithmEnum) -> None:
        self.calls.append(BittensorContactCall(method="upload_public_key", netuid=netuid, public_key=public_key))
        if self.upload_exception is not None:
            raise self.upload_exception
        self.own_public_key = public_key
```

- [ ] **Step 4: Add the turbobt mock**

Extend `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/contacts.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TurboBittensorContactCall:
    method: str
    netuid: int | None = None
    hotkey: str | None = None
    public_key: PublicKey | None = None


@dataclass
class MockTurboBittensorSubtensorContact(AbstractTurboBittensorSubtensorContact):
    own_public_key: PublicKey | None = None
    upload_exception: Exception | None = None
    listed_neurons: list[turbobt.neuron.Neuron] = field(default_factory=list)
    calls: list[TurboBittensorContactCall] = field(default_factory=list)

    def set_neuron_listing(self, neurons: list[turbobt.neuron.Neuron]) -> None:
        self.listed_neurons = list(neurons)

    def set_own_certificate(self, public_key: PublicKey | None) -> None:
        self.own_public_key = public_key

    def set_upload_behavior(self, exception: Exception | None = None) -> None:
        self.upload_exception = exception

    def reset_calls(self) -> None:
        self.calls.clear()

    async def list_neurons(self, *, bittensor, netuid: int, block_hash: str | None = None) -> list[turbobt.neuron.Neuron]:
        self.calls.append(TurboBittensorContactCall(method="list_neurons", netuid=netuid))
        return list(self.listed_neurons)

    async def get_own_public_key(self, *, bittensor, netuid: int, hotkey: str) -> PublicKey | None:
        self.calls.append(TurboBittensorContactCall(method="get_own_public_key", netuid=netuid, hotkey=hotkey))
        return self.own_public_key

    async def upload_public_key(self, *, bittensor, netuid: int, wallet, public_key: PublicKey, algorithm: CertificateAlgorithmEnum) -> None:
        self.calls.append(TurboBittensorContactCall(method="upload_public_key", netuid=netuid, public_key=public_key))
        if self.upload_exception is not None:
            raise self.upload_exception
        self.own_public_key = public_key
```

- [ ] **Step 5: Export the new mock classes if needed by downstream imports**

If downstream imports should be short, update package exports such as `bt_ddos_shield_client/bt_ddos_shield_client/__init__.py` or `shielded_turbobt/__init__.py` accordingly:

```python
from .contacts import MockBittensorSubtensorContact as MockBittensorSubtensorContact
```

Do the same for the turbobt mock if you decide the package should expose it from `shielded_turbobt/__init__.py`.

- [ ] **Step 6: Run the mock-contact tests to verify they pass**

Run:

```bash
uv run --project bt_ddos_shield_client pytest \
  bt_ddos_shield_client/tests/test_shield_metagraph.py::test_mock_bittensor_contact_records_and_mutates_state \
  test_legacy_turbobt_wrapper.py::test_mock_turbobt_contact_records_listing_calls -v
```

Expected: PASS

- [ ] **Step 7: Commit the mock contacts**

```bash
git add bt_ddos_shield_client/bt_ddos_shield_client/contacts.py \
        bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/contacts.py \
        bt_ddos_shield_client/bt_ddos_shield_client/__init__.py \
        bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/__init__.py \
        bt_ddos_shield_client/tests/test_shield_metagraph.py \
        test_legacy_turbobt_wrapper.py
git commit -m "feat: add shield contact test mocks"
```

## Task 3: Add Downstream Fixture-Style Test Helpers

**Files:**
- Create: `bt_ddos_shield_client/bt_ddos_shield_client/testing.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/__init__.py`
- Create: `bt_ddos_shield_client/tests/test_testing_helpers.py`

- [ ] **Step 1: Write the failing helper-layer tests**

Create `bt_ddos_shield_client/tests/test_testing_helpers.py`:

```python
from bt_ddos_shield_client.testing import ShieldMetagraphTestRig
from bt_ddos_shield_client.tests.fixtures import certificate_fixture_path


def test_metagraph_test_rig_produces_final_public_addresses(tmp_path):
    rig = ShieldMetagraphTestRig()
    rig.set_validator_certificate_path(certificate_fixture_path("validator_a.pem"))
    rig.add_miner("miner-a", "198.51.100.10", 8080, shield_address="203.0.113.10:3030")
    rig.add_miner("miner-b", "198.51.100.11", 8081, shield_address=None)

    with rig.install(tmp_path=tmp_path) as metagraph:
        metagraph.sync()

    assert [(axon.hotkey, axon.ip, axon.port) for axon in metagraph.axons] == [
        ("miner-a", "203.0.113.10", 3030),
        ("miner-b", "198.51.100.11", 8081),
    ]
```

- [ ] **Step 2: Run the helper-layer test to verify it fails**

Run: `uv run --project bt_ddos_shield_client pytest bt_ddos_shield_client/tests/test_testing_helpers.py::test_metagraph_test_rig_produces_final_public_addresses -v`

Expected: FAIL with `ImportError` because `ShieldMetagraphTestRig` does not exist yet.

- [ ] **Step 3: Add the downstream testing helper module**

Create `bt_ddos_shield_client/bt_ddos_shield_client/testing.py`:

```python
from __future__ import annotations

import base64
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from pathlib import Path

from aioresponses import aioresponses
from bittensor.core.chain_data import AxonInfo, NeuronInfo, PrometheusInfo
from bittensor.utils.balance import Balance

from bt_ddos_shield_client import ShieldMetagraph
from bt_ddos_shield_client.certificates import EDDSACertificateManager
from bt_ddos_shield_client.contacts import MockBittensorSubtensorContact
from bt_ddos_shield_client.encryption import ECIESEncryptionManager
from bt_ddos_shield_client.shield_metagraph import ShieldMetagraphOptions


def _make_wallet(hotkey: str = "validator-hotkey"):
    return SimpleNamespace(hotkey=SimpleNamespace(ss58_address=hotkey))


def _make_bittensor_neuron(*, hotkey: str, ip: str, port: int, uid: int) -> NeuronInfo:
    return NeuronInfo(
        hotkey=hotkey,
        coldkey="miner-coldkey",
        uid=uid,
        netuid=7,
        active=1,
        stake=Balance.from_tao(0),
        stake_dict={},
        total_stake=Balance.from_tao(0),
        rank=0.0,
        emission=0.0,
        incentive=0.0,
        consensus=0.0,
        trust=0.0,
        validator_trust=0.0,
        dividends=0.0,
        last_update=0,
        validator_permit=False,
        weights=[],
        bonds=[],
        pruning_score=0,
        prometheus_info=PrometheusInfo(block=0, version=1, ip="127.0.0.1", port=9090, ip_type=4),
        axon_info=AxonInfo(version=1, ip=ip, port=port, ip_type=4, hotkey=hotkey, coldkey="miner-coldkey"),
    )


def _build_manifest_body(public_key: str, address: str, validator_hotkey: str = "validator-hotkey") -> bytes:
    encrypted = ECIESEncryptionManager().encrypt(public_key, address.encode())
    return json.dumps(
        {
            "ddos_shield_manifest": {
                "encrypted_url_mapping": {
                    validator_hotkey: base64.b64encode(encrypted).decode(),
                },
            }
        }
    ).encode()


@dataclass
class _RigMiner:
    hotkey: str
    ip: str
    port: int
    shield_address: str | None


@dataclass
class ShieldMetagraphTestRig:
    miners: list[_RigMiner] = field(default_factory=list)
    contact: MockBittensorSubtensorContact = field(default_factory=MockBittensorSubtensorContact)
    validator_certificate_path: str | None = None

    def set_validator_certificate_path(self, path) -> None:
        self.validator_certificate_path = str(path)

    def add_miner(self, hotkey: str, ip: str, port: int, shield_address: str | None) -> None:
        self.miners.append(_RigMiner(hotkey, ip, port, shield_address))

    @contextmanager
    def install(self, *, tmp_path):
        if self.validator_certificate_path is None:
            raise ValueError("validator_certificate_path must be configured")
        certificate = EDDSACertificateManager().load_certificate(self.validator_certificate_path)
        destination = tmp_path / "validator.pem"
        destination.write_text(Path(self.validator_certificate_path).read_text())

        self.contact.set_metagraph_sync(
            [
                _make_bittensor_neuron(hotkey=miner.hotkey, ip=miner.ip, port=miner.port, uid=index)
                for index, miner in enumerate(self.miners)
            ]
        )
        self.contact.set_own_certificate(None)

        with self.install_contact_patch(), aioresponses() as mocked:
            for miner in self.miners:
                if miner.shield_address is None:
                    mocked.get(f"http://{miner.ip}:{miner.port}/shield_manifest.json", status=404)
                    continue
                mocked.get(
                    f"http://{miner.ip}:{miner.port}/shield_manifest.json",
                    status=200,
                    body=_build_manifest_body(certificate.public_key, miner.shield_address),
                )

            yield ShieldMetagraph(
                wallet=_make_wallet(),
                netuid=7,
                subtensor=object(),
                sync=False,
                options=ShieldMetagraphOptions(certificate_path=str(destination)),
            )

    @contextmanager
    def install_contact_patch(self):
        from unittest.mock import patch

        with patch(
            "bt_ddos_shield_client.shield_metagraph.bittensor_subtensor_contact",
            return_value=self.contact,
        ):
            yield
```

- [ ] **Step 4: Export the downstream helper**

Modify `bt_ddos_shield_client/bt_ddos_shield_client/__init__.py`:

```python
from .shield_metagraph import ShieldMetagraph as ShieldMetagraph
from .testing import ShieldMetagraphTestRig as ShieldMetagraphTestRig

__all__ = ["ShieldMetagraph", "ShieldMetagraphTestRig"]
```

- [ ] **Step 5: Run the helper-layer test to verify it passes**

Run: `uv run --project bt_ddos_shield_client pytest bt_ddos_shield_client/tests/test_testing_helpers.py::test_metagraph_test_rig_produces_final_public_addresses -v`

Expected: PASS

- [ ] **Step 6: Commit the helper layer**

```bash
git add bt_ddos_shield_client/bt_ddos_shield_client/testing.py \
        bt_ddos_shield_client/bt_ddos_shield_client/__init__.py \
        bt_ddos_shield_client/tests/test_testing_helpers.py
git commit -m "feat: add shield testing helpers"
```

## Task 4: Rewrite ShieldMetagraph Public-API Tests

**Files:**
- Modify: `bt_ddos_shield_client/tests/test_shield_metagraph.py`

- [ ] **Step 1: Write the first failing public-API reconciliation test**

Add this test to `bt_ddos_shield_client/tests/test_shield_metagraph.py`:

```python
from freezegun import freeze_time

from bt_ddos_shield_client.tests.fixtures import certificate_fixture_path
from bt_ddos_shield_client.tests.fakes import make_bittensor_neuron


@freeze_time("2026-03-31 12:00:00")
def test_shield_metagraph_uploads_when_on_chain_cert_is_missing(patched_bittensor_contact, tmp_path):
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey="miner-hotkey", ip="198.51.100.20", port=8080)]
    )
    patched_bittensor_contact.set_own_certificate(None)

    destination = tmp_path / "validator.pem"
    destination.write_text(certificate_fixture_path("validator_a.pem").read_text())

    metagraph = ShieldMetagraph(
        wallet=make_wallet(),
        netuid=7,
        subtensor=object(),
        sync=False,
        options=ShieldMetagraphOptions(certificate_path=str(destination)),
    )

    with aioresponses() as mocked:
        mocked.get("http://198.51.100.20:8080/shield_manifest.json", status=404)
        metagraph.sync()

    assert [call.method for call in patched_bittensor_contact.calls] == [
        "sync_metagraph",
        "get_own_public_key",
        "upload_public_key",
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --project bt_ddos_shield_client pytest bt_ddos_shield_client/tests/test_shield_metagraph.py::test_shield_metagraph_uploads_when_on_chain_cert_is_missing -v`

Expected: FAIL because the current test module still patches old seams and lacks the new fixture utilities.

- [ ] **Step 3: Rewrite the metagraph tests around the new seam**

Rewrite `bt_ddos_shield_client/tests/test_shield_metagraph.py` to include:

```python
from __future__ import annotations

from aioresponses import aioresponses
from freezegun import freeze_time
import pytest

from bt_ddos_shield_client import ShieldMetagraph
from bt_ddos_shield_client.shield_metagraph import ShieldMetagraphOptions
from bt_ddos_shield_client.tests.fixtures import certificate_fixture_path, load_certificate_fixture
from bt_ddos_shield_client.tests.fakes import build_manifest_body, make_bittensor_neuron, make_wallet
```

Include coverage for:

- missing cert upload
- mismatched cert upload
- matching cert skip
- mid-test mutable state change
- TTL freeze/advance behavior
- mixed shielded/unshielded concurrent resolution
- manifest timeout leaves original endpoint intact
- malformed manifest leaves original endpoint intact
- 5xx manifest leaves original endpoint intact
- read failure through public API
- upload failure through public API

For the mixed shielded/unshielded case, use two or three fake neurons and only HTTP responses:

```python
certificate = load_certificate_fixture("validator_a.pem")
with aioresponses() as mocked:
    mocked.get(
        "http://198.51.100.20:8080/shield_manifest.json",
        status=200,
        body=build_manifest_body(certificate.public_key, "203.0.113.70:3070"),
    )
    mocked.get("http://198.51.100.21:8081/shield_manifest.json", status=404)
    mocked.get(
        "http://198.51.100.22:8082/shield_manifest.json",
        status=200,
        body=build_manifest_body(certificate.public_key, "203.0.113.72:3072"),
    )
    metagraph.sync()
```

For manifest failure coverage, drive `aioresponses` directly instead of hiding the failure mode behind helper abstractions:

```python
import asyncio


@pytest.mark.parametrize(
    ("manifest_kwargs", "expected_ip", "expected_port"),
    [
        ({"exception": asyncio.TimeoutError()}, "198.51.100.20", 8080),
        ({"status": 500}, "198.51.100.20", 8080),
        ({"status": 200, "body": b"not-json"}, "198.51.100.20", 8080),
    ],
)
def test_manifest_failures_leave_original_endpoint(
    patched_bittensor_contact,
    tmp_path,
    manifest_kwargs,
    expected_ip,
    expected_port,
):
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey="miner-hotkey", ip="198.51.100.20", port=8080)]
    )
    destination = tmp_path / "validator.pem"
    destination.write_text(certificate_fixture_path("validator_a.pem").read_text())
    metagraph = ShieldMetagraph(
        wallet=make_wallet(),
        netuid=7,
        subtensor=object(),
        sync=False,
        options=ShieldMetagraphOptions(certificate_path=str(destination)),
    )
    with aioresponses() as mocked:
        mocked.get("http://198.51.100.20:8080/shield_manifest.json", **manifest_kwargs)
        metagraph.sync()

    assert metagraph.axons[0].ip == expected_ip
    assert metagraph.axons[0].port == expected_port
```

- [ ] **Step 4: Run the metagraph test module**

Run: `uv run --project bt_ddos_shield_client pytest bt_ddos_shield_client/tests/test_shield_metagraph.py -v`

Expected: all tests in that module PASS

- [ ] **Step 5: Commit the metagraph tests**

```bash
git add bt_ddos_shield_client/tests/test_shield_metagraph.py \
        bt_ddos_shield_client/tests/fixtures.py \
        bt_ddos_shield_client/tests/fixtures/certs/validator_a.pem \
        bt_ddos_shield_client/tests/fixtures/certs/validator_b.pem \
        bt_ddos_shield_client/tests/fixtures/certs/validator_c.pem
git commit -m "test: cover shield metagraph public behavior"
```

## Task 5: Rewrite Turbobt Public-API Tests and Helper-Layer Tests

**Files:**
- Modify: `test_legacy_turbobt_wrapper.py`
- Modify: `bt_ddos_shield_client/tests/test_testing_helpers.py`

- [ ] **Step 1: Write the failing turbobt public-API test**

Add this test:

```python
from freezegun import freeze_time

from bt_ddos_shield_client.tests.fixtures import certificate_fixture_path
from bt_ddos_shield_client.tests.fakes import make_turbobt_neuron


@pytest.mark.asyncio
@freeze_time("2026-03-31 12:00:00")
async def test_shielded_subnet_reference_uploads_when_on_chain_cert_is_missing(patched_turbo_bittensor_contact, tmp_path):
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey="miner-hotkey", ip="198.51.100.50", port=5050)]
    )
    patched_turbo_bittensor_contact.set_own_certificate(None)

    destination = tmp_path / "validator.pem"
    destination.write_text(certificate_fixture_path("validator_a.pem").read_text())

    bittensor = LegacyTurbobtWrapper(
        "test",
        wallet=make_wallet(),
        ddos_shield_netuid=7,
        ddos_shield_options=ShieldMetagraphOptions(certificate_path=str(destination)),
    )

    async with bittensor:
        with aioresponses() as mocked:
            mocked.get("http://198.51.100.50:5050/shield_manifest.json", status=404)
            await bittensor.subnet(7).list_neurons()

    assert [call.method for call in patched_turbo_bittensor_contact.calls] == [
        "get_own_public_key",
        "upload_public_key",
        "list_neurons",
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --project bt_ddos_shield_client pytest test_legacy_turbobt_wrapper.py::test_shielded_subnet_reference_uploads_when_on_chain_cert_is_missing -v`

Expected: FAIL until the module is rewritten against the new seam.

- [ ] **Step 3: Rewrite the turbobt test module**

Rewrite `test_legacy_turbobt_wrapper.py` to cover:

- missing cert upload
- mismatched cert upload
- matching cert skip
- mid-test mutation
- TTL behavior with frozen time
- mixed shielded/unshielded neuron listing
- `LegacySubnetReference.from_bittensor(...)` end-to-end
- manifest timeout leaves original endpoint intact
- malformed manifest leaves original endpoint intact
- 5xx manifest leaves original endpoint intact
- read failure through public API
- upload failure through public API

Use only:

- patched `turbo_bittensor_subtensor_contact()`
- mocked HTTP manifest responses
- committed certificate fixtures

Mirror the metagraph-side adverse manifest cases with `aioresponses`:

```python
import asyncio


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "manifest_kwargs",
    [
        {"exception": asyncio.TimeoutError()},
        {"status": 500},
        {"status": 200, "body": b"not-json"},
    ],
)
async def test_manifest_failures_leave_original_turbobt_endpoint(
    patched_turbo_bittensor_contact,
    tmp_path,
    manifest_kwargs,
):
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey="miner-hotkey", ip="198.51.100.50", port=5050)]
    )
    destination = tmp_path / "validator.pem"
    destination.write_text(certificate_fixture_path("validator_a.pem").read_text())
    bittensor = LegacyTurbobtWrapper(
        "test",
        wallet=make_wallet(),
        ddos_shield_netuid=7,
        ddos_shield_options=ShieldMetagraphOptions(certificate_path=str(destination)),
    )
    async with bittensor:
        with aioresponses() as mocked:
            mocked.get("http://198.51.100.50:5050/shield_manifest.json", **manifest_kwargs)
            neurons = await bittensor.subnet(7).list_neurons()

    assert str(neurons[0].axon_info.ip) == "198.51.100.50"
    assert neurons[0].axon_info.port == 5050
```

- [ ] **Step 4: Add helper-layer public-API tests**

Extend `bt_ddos_shield_client/tests/test_testing_helpers.py` with TTL and mismatch coverage:

```python
from freezegun import freeze_time


@freeze_time("2026-03-31 12:00:00")
def test_metagraph_test_rig_handles_mismatched_certificate_flow(tmp_path):
    rig = ShieldMetagraphTestRig()
    rig.set_validator_certificate_path(certificate_fixture_path("validator_a.pem"))
    rig.add_miner("miner-a", "198.51.100.10", 8080, shield_address="203.0.113.10:3030")
    rig.contact.set_own_certificate("deadbeef")

    with rig.install(tmp_path=tmp_path) as metagraph:
        metagraph.sync()

    assert metagraph.axons[0].ip == "203.0.113.10"
    assert any(call.method == "upload_public_key" for call in rig.contact.calls)
```

Do not assert helper internals beyond what is necessary to show public behavior and the upload side effect exposed by the shared mock call log.

- [ ] **Step 5: Run the turbobt and helper test modules**

Run:

```bash
uv run --project bt_ddos_shield_client pytest \
  test_legacy_turbobt_wrapper.py \
  bt_ddos_shield_client/tests/test_testing_helpers.py -v
```

Expected: all tests in both modules PASS

- [ ] **Step 6: Commit the turbobt and helper tests**

```bash
git add test_legacy_turbobt_wrapper.py \
        bt_ddos_shield_client/tests/test_testing_helpers.py \
        bt_ddos_shield_client/bt_ddos_shield_client/testing.py
git commit -m "test: cover shield turbobt and helper layers"
```

## Task 6: Package-Wide Verification and Cleanup

**Files:**
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/contacts.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/contacts.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/testing.py`
- Modify: `bt_ddos_shield_client/tests/test_shield_metagraph.py`
- Modify: `test_legacy_turbobt_wrapper.py`
- Modify: `bt_ddos_shield_client/tests/test_testing_helpers.py`

- [ ] **Step 1: Reconcile imports and package exports**

Make the final exports explicit where needed:

```python
from .shield_metagraph import ShieldMetagraph as ShieldMetagraph
from .testing import ShieldMetagraphTestRig as ShieldMetagraphTestRig

__all__ = ["ShieldMetagraph", "ShieldMetagraphTestRig"]
```

For turbobt package exports:

```python
from .neuron_mutator import LegacyTurbobtWrapper as LegacyTurbobtWrapper
from .neuron_mutator import LegacySubnetReference as LegacySubnetReference
from .contacts import MockTurboBittensorSubtensorContact as MockTurboBittensorSubtensorContact

__all__ = ["LegacyTurbobtWrapper", "LegacySubnetReference", "MockTurboBittensorSubtensorContact"]
```

- [ ] **Step 2: Run the full library test suite**

Run: `uv run --project bt_ddos_shield_client pytest bt_ddos_shield_client/tests -v`

Expected: all repository tests PASS

- [ ] **Step 3: Run syntax and diff sanity checks**

Run:

```bash
uv run --project bt_ddos_shield_client python3 -m compileall bt_ddos_shield_client/bt_ddos_shield_client bt_ddos_shield_client/tests
git diff --check
```

Expected:

- compileall completes without syntax errors
- `git diff --check` returns no output

- [ ] **Step 4: Verify the spec requirements against the final diff**

Run:

```bash
git diff -- bt_ddos_shield_client/bt_ddos_shield_client/contacts.py \
           bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/contacts.py \
           bt_ddos_shield_client/bt_ddos_shield_client/testing.py \
           bt_ddos_shield_client/tests/fixtures.py \
           bt_ddos_shield_client/tests/test_shield_metagraph.py \
           test_legacy_turbobt_wrapper.py \
           bt_ddos_shield_client/tests/test_testing_helpers.py \
           bt_ddos_shield_client/pyproject.toml
```

Confirm all of the following before stopping:

- production-package mock contacts exist for both abstract contact types
- mock contacts are mutable mid-test and expose structured call logs
- repository tests patch only the contact singleton factory functions plus mocked HTTP responses
- repository tests do not add a repo-only declarative shielded/unshielded abstraction
- downstream-facing helper APIs hide contact patching and manifest setup
- tests use committed real certificate fixtures
- TTL behavior is covered with `freezegun`
- all tests exercise public APIs rather than private helpers

- [ ] **Step 5: Commit the final integration pass**

```bash
git add bt_ddos_shield_client/bt_ddos_shield_client/contacts.py \
        bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/contacts.py \
        bt_ddos_shield_client/bt_ddos_shield_client/testing.py \
        bt_ddos_shield_client/tests/fixtures.py \
        bt_ddos_shield_client/tests/fixtures/certs/validator_a.pem \
        bt_ddos_shield_client/tests/fixtures/certs/validator_b.pem \
        bt_ddos_shield_client/tests/fixtures/certs/validator_c.pem \
        bt_ddos_shield_client/tests/fixtures/certs/README.md \
        bt_ddos_shield_client/tests/test_shield_metagraph.py \
        test_legacy_turbobt_wrapper.py \
        bt_ddos_shield_client/tests/test_testing_helpers.py \
        bt_ddos_shield_client/pyproject.toml
git commit -m "test: add shield contact mocks and public api coverage"
```
