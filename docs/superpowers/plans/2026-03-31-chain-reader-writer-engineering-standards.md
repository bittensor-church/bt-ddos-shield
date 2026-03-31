# Chain Reader / Writer Engineering Standards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `server_shield` so `chain_reader` and `chain_writer` depend on one shared singleton-backed Subtensor contact boundary, provide a concrete instrumentable `MockSubtensorContact` in production code, move CLI tests to public `main()` coverage without patching internal helpers, and add dedicated real-contact integration tests for `BittensorSubtensorContact`.

**Architecture:** Add `server_shield/src/server_shield/subtensor_contact.py` with one abstract contact, one real `bittensor.subtensor(...)` adapter, one concrete mutable mock contact, and one singleton factory function. Mirror the `bt_ddos_shield_client` pattern in CLI tests: patch only the factory, configure the mock contact in domain terms, keep manifest generation and reconciliation real, and keep `bittensor_wallet.Wallet(...)` real in `chain_writer` tests. Add a separate `server_shield/tests/contacts/` integration layer so the real contact implementation is tested directly through its public methods.

**Tech Stack:** Python 3.14, `bittensor`, `bittensor-wallet`, `pytest`, `pycryptodome`, existing `server_shield.shared.state_store` helpers

---

## File Map

- Create: `server_shield/src/server_shield/subtensor_contact.py`
  - Shared abstract contact, contact result dataclasses, structured call log type, real adapter, mock adapter, and singleton factory.
- Modify: `server_shield/src/server_shield/chain_reader/chain.py`
  - Convert contact-returned chain records into `ValidatorOnChain` objects and keep certificate decoding above the contact.
- Modify: `server_shield/src/server_shield/chain_reader/cli.py`
  - Use the shared contact factory instead of direct chain access.
- Modify: `server_shield/src/server_shield/chain_writer/cli.py`
  - Use the shared contact factory for registration, neuron lookup, and axon publishing while keeping real wallet construction.
- Modify: `server_shield/pyproject.toml`
  - Add integration-test dependencies and pytest marker config for real contact tests.
- Create: `server_shield/tests/conftest.py`
  - Add one fixture that patches the contact factory in both CLI modules and returns `MockSubtensorContact`.
- Modify: `server_shield/tests/chain_reader/test_cli.py`
  - Rewrite to test `main()` with real state files, a patched contact fixture, real manifest generation, and malformed-cert exclusion.
- Modify: `server_shield/tests/chain_writer/test_cli.py`
  - Rewrite to test `main()` with real state files, a patched contact fixture, and a real wallet created under a temp `HOME`.
- Create: `server_shield/tests/contacts/local_subtensor.py`
  - Local test-owned Subtensor bootstrap helper for real contact integration tests.
- Create: `server_shield/tests/contacts/conftest.py`
  - Fixtures for the local Subtensor env, wallets, and netuid used by contact integration tests.
- Create: `server_shield/tests/contacts/test_subtensor_contact.py`
  - Dedicated tests for the real `BittensorSubtensorContact` public methods.

## Task 1: Add the shared contact module and test fixture

**Files:**
- Create: `server_shield/src/server_shield/subtensor_contact.py`
- Create: `server_shield/tests/conftest.py`

- [ ] **Step 1: Write the failing contact import test**

Add this to `server_shield/tests/chain_reader/test_cli.py` temporarily near the imports:

```python
from server_shield.subtensor_contact import AbstractSubtensorContact, MockSubtensorContact, subtensor_contact


def test_subtensor_contact_types_are_importable() -> None:
    assert callable(subtensor_contact)
    assert issubclass(MockSubtensorContact, AbstractSubtensorContact)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --project server_shield pytest server_shield/tests/chain_reader/test_cli.py::test_subtensor_contact_types_are_importable -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'server_shield.subtensor_contact'`

- [ ] **Step 3: Create the shared contact module**

Create `server_shield/src/server_shield/subtensor_contact.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import bittensor
import bittensor_wallet


@dataclass(frozen=True)
class ValidatorCertificateRecord:
    hotkey: str
    certificate_payload: dict[str, Any] | None


@dataclass(frozen=True)
class NeuronAxonRecord:
    is_null: bool
    is_serving: bool
    ip: str | None
    port: int | None


@dataclass(frozen=True)
class SubtensorContactCall:
    method: str
    netuid: int | None = None
    hotkey_ss58: str | None = None
    ip: str | None = None
    port: int | None = None


class AbstractSubtensorContact(ABC):
    @abstractmethod
    def list_validator_certificates(self, *, netuid: int) -> list[ValidatorCertificateRecord]:
        raise NotImplementedError

    @abstractmethod
    def is_hotkey_registered(self, *, hotkey_ss58: str, netuid: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_neuron_axon(self, *, hotkey_ss58: str, netuid: int) -> NeuronAxonRecord:
        raise NotImplementedError

    @abstractmethod
    def publish_axon(
        self,
        *,
        wallet: bittensor_wallet.Wallet,
        netuid: int,
        ip: str,
        port: int,
    ) -> bool:
        raise NotImplementedError


class BittensorSubtensorContact(AbstractSubtensorContact):
    def __init__(self, subtensor_address: str) -> None:
        self._subtensor = bittensor.subtensor(subtensor_address)

    def list_validator_certificates(self, *, netuid: int) -> list[ValidatorCertificateRecord]:
        metagraph = bittensor.metagraph(netuid=netuid, subtensor=self._subtensor)
        records: list[ValidatorCertificateRecord] = []
        for hotkey, permit in zip(metagraph.hotkeys, metagraph.validator_permit, strict=False):
            if not bool(permit):
                continue
            records.append(
                ValidatorCertificateRecord(
                    hotkey=hotkey,
                    certificate_payload=self._subtensor.query_subtensor(
                        name="NeuronCertificates",
                        params=[netuid, hotkey],
                    ),
                )
            )
        return records

    def is_hotkey_registered(self, *, hotkey_ss58: str, netuid: int) -> bool:
        return self._subtensor.is_hotkey_registered(hotkey_ss58, netuid)

    def get_neuron_axon(self, *, hotkey_ss58: str, netuid: int) -> NeuronAxonRecord:
        uid = self._subtensor.get_uid_for_hotkey_on_subnet(hotkey_ss58, netuid)
        neuron = self._subtensor.neuron_for_uid(uid, netuid)
        return NeuronAxonRecord(
            is_null=bool(neuron.is_null),
            is_serving=bool(neuron.axon_info.is_serving),
            ip=neuron.axon_info.ip,
            port=neuron.axon_info.port,
        )

    def publish_axon(
        self,
        *,
        wallet: bittensor_wallet.Wallet,
        netuid: int,
        ip: str,
        port: int,
    ) -> bool:
        return bool(
            self._subtensor.serve_axon(
                netuid,
                axon=bittensor.Axon(
                    wallet,
                    port=port,
                    ip=ip,
                    external_ip=ip,
                    external_port=port,
                ),
                wait_for_inclusion=True,
                wait_for_finalization=True,
            )
        )


@dataclass
class MockSubtensorContact(AbstractSubtensorContact):
    validator_certificates: list[ValidatorCertificateRecord] = field(default_factory=list)
    validator_certificates_exception: Exception | None = None
    registrations: dict[tuple[str, int], bool] = field(default_factory=dict)
    neuron_axons: dict[tuple[str, int], NeuronAxonRecord] = field(default_factory=dict)
    publish_result: bool = True
    publish_exception: Exception | None = None
    calls: list[SubtensorContactCall] = field(default_factory=list)

    def set_validator_certificates(
        self,
        records: list[ValidatorCertificateRecord],
        *,
        exception: Exception | None = None,
    ) -> None:
        self.validator_certificates = list(records)
        self.validator_certificates_exception = exception

    def set_registration(self, *, hotkey_ss58: str, netuid: int, registered: bool) -> None:
        self.registrations[(hotkey_ss58, netuid)] = registered

    def set_neuron_axon(
        self,
        *,
        hotkey_ss58: str,
        netuid: int,
        neuron_axon: NeuronAxonRecord,
    ) -> None:
        self.neuron_axons[(hotkey_ss58, netuid)] = neuron_axon

    def set_publish_behavior(
        self,
        *,
        result: bool = True,
        exception: Exception | None = None,
    ) -> None:
        self.publish_result = result
        self.publish_exception = exception

    def reset_calls(self) -> None:
        self.calls.clear()

    def list_validator_certificates(self, *, netuid: int) -> list[ValidatorCertificateRecord]:
        self.calls.append(SubtensorContactCall(method="list_validator_certificates", netuid=netuid))
        if self.validator_certificates_exception is not None:
            raise self.validator_certificates_exception
        return list(self.validator_certificates)

    def is_hotkey_registered(self, *, hotkey_ss58: str, netuid: int) -> bool:
        self.calls.append(
            SubtensorContactCall(
                method="is_hotkey_registered",
                netuid=netuid,
                hotkey_ss58=hotkey_ss58,
            )
        )
        return self.registrations.get((hotkey_ss58, netuid), False)

    def get_neuron_axon(self, *, hotkey_ss58: str, netuid: int) -> NeuronAxonRecord:
        self.calls.append(
            SubtensorContactCall(
                method="get_neuron_axon",
                netuid=netuid,
                hotkey_ss58=hotkey_ss58,
            )
        )
        return self.neuron_axons[(hotkey_ss58, netuid)]

    def publish_axon(
        self,
        *,
        wallet: bittensor_wallet.Wallet,
        netuid: int,
        ip: str,
        port: int,
    ) -> bool:
        self.calls.append(
            SubtensorContactCall(
                method="publish_axon",
                netuid=netuid,
                hotkey_ss58=wallet.hotkey.ss58_address,
                ip=ip,
                port=port,
            )
        )
        if self.publish_exception is not None:
            raise self.publish_exception
        return self.publish_result


_contact_instance: AbstractSubtensorContact | None = None


def subtensor_contact(subtensor_address: str) -> AbstractSubtensorContact:
    global _contact_instance
    if _contact_instance is None:
        _contact_instance = BittensorSubtensorContact(subtensor_address)
    return _contact_instance
```

- [ ] **Step 4: Add the patched factory fixture**

Create `server_shield/tests/conftest.py`:

```python
from __future__ import annotations

import pytest

from server_shield.subtensor_contact import MockSubtensorContact


@pytest.fixture
def patched_subtensor_contact(monkeypatch) -> MockSubtensorContact:
    contact = MockSubtensorContact()
    monkeypatch.setattr("server_shield.chain_reader.cli.subtensor_contact", lambda subtensor_address: contact)
    monkeypatch.setattr("server_shield.chain_writer.cli.subtensor_contact", lambda subtensor_address: contact)
    return contact
```

- [ ] **Step 5: Run the import test to verify it passes**

Run: `uv run --project server_shield pytest server_shield/tests/chain_reader/test_cli.py::test_subtensor_contact_types_are_importable -v`

Expected: PASS

- [ ] **Step 6: Commit the contact layer**

```bash
git add server_shield/src/server_shield/subtensor_contact.py \
        server_shield/tests/conftest.py \
        server_shield/tests/chain_reader/test_cli.py
git commit -m "refactor: add shared subtensor contact"
```

## Task 2: Move chain_reader to the shared contact and keep manifest generation real

**Files:**
- Modify: `server_shield/src/server_shield/chain_reader/chain.py`
- Modify: `server_shield/src/server_shield/chain_reader/cli.py`
- Modify: `server_shield/tests/chain_reader/test_cli.py`

- [ ] **Step 1: Write the failing public reconciliation test**

Replace the old helper-oriented reconciliation test in `server_shield/tests/chain_reader/test_cli.py` with:

```python
import base64
from pathlib import Path

from Crypto.PublicKey import ECC

from server_shield.chain_reader.cli import main
from server_shield.shared import state_store
from server_shield.shared.state_store import read_desired_domains, read_manifest, write_root_domain
from server_shield.subtensor_contact import MockSubtensorContact, ValidatorCertificateRecord


def _valid_public_key_hex() -> str:
    return ECC.generate(curve="ed25519").public_key().export_key(format="raw").hex()


def test_chain_reader_main_reconciles_domains_from_contact(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    monkeypatch.setenv("SERVER_SHIELD_MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_SUBTENSOR_ADDRESS", "ws://subtensor")
    monkeypatch.setenv("SERVER_SHIELD_NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__BACKEND_URL", "file:///tmp/server-shield-test-state")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__SHIELD_BACKEND", "AWS")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY", "miner-hotkey")
    write_root_domain(tmp_path, "shield.example.com")
    state_store.write_blacklist(tmp_path, ["blacklisted-validator"])

    existing_cert = _valid_public_key_hex()
    new_cert = _valid_public_key_hex()
    blacklisted_cert = _valid_public_key_hex()
    patched_subtensor_contact.set_validator_certificates(
        [
            ValidatorCertificateRecord(
                hotkey="existing-validator",
                certificate_payload={"public_key": [existing_cert]},
            ),
            ValidatorCertificateRecord(
                hotkey="new-validator",
                certificate_payload={"public_key": [new_cert]},
            ),
            ValidatorCertificateRecord(
                hotkey="blacklisted-validator",
                certificate_payload={"public_key": [blacklisted_cert]},
            ),
            ValidatorCertificateRecord(
                hotkey="missing-cert-validator",
                certificate_payload=None,
            ),
        ]
    )

    exit_code = main()

    desired_domains = read_desired_domains(tmp_path)
    manifest = read_manifest(tmp_path)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert desired_domains.domains["existing-validator"].public_cert == existing_cert
    assert desired_domains.domains["new-validator"].public_cert == new_cert
    assert "blacklisted-validator" not in desired_domains.domains
    assert "missing-cert-validator" not in desired_domains.domains
    assert set(manifest.ddos_shield_manifest.encrypted_url_mapping) == {
        "existing-validator",
        "new-validator",
    }
    assert all(
        base64.b64decode(value)
        for value in manifest.ddos_shield_manifest.encrypted_url_mapping.values()
    )
    assert [call.method for call in patched_subtensor_contact.calls] == ["list_validator_certificates"]
    assert "chain_reader reconciled observed=4 kept=0 created=2" in captured.out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --project server_shield pytest server_shield/tests/chain_reader/test_cli.py::test_chain_reader_main_reconciles_domains_from_contact -v`

Expected: FAIL because `chain_reader` still uses the old direct chain path

- [ ] **Step 3: Refactor `chain_reader/chain.py` to depend on the contact**

Replace `server_shield/src/server_shield/chain_reader/chain.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from server_shield.subtensor_contact import AbstractSubtensorContact


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


def fetch_validators_with_certs(
    *,
    contact: AbstractSubtensorContact,
    netuid: int,
) -> list[ValidatorOnChain]:
    validators: list[ValidatorOnChain] = []
    for record in contact.list_validator_certificates(netuid=netuid):
        public_cert, invalid_reason = _decode_certificate_payload(record.certificate_payload)
        validators.append(
            ValidatorOnChain(
                hotkey=record.hotkey,
                public_cert=public_cert,
                cert_invalid_reason=invalid_reason,
            )
        )
    return validators
```

- [ ] **Step 4: Rewire `chain_reader/cli.py` to use the contact factory**

Update `server_shield/src/server_shield/chain_reader/cli.py`:

```python
from server_shield.chain_reader.chain import fetch_validators_with_certs
from server_shield.chain_reader.manifest import build_manifest_state
from server_shield.chain_reader.reconciliation import reconcile_desired_domains
from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component
from server_shield.shared.state_store import (
    ensure_state_files,
    read_blacklist,
    read_desired_domains,
    read_root_domain,
    write_desired_domains,
    write_manifest,
)
from server_shield.subtensor_contact import subtensor_contact


def _run_once() -> int:
    ensure_state_files()
    root_domain = read_root_domain()
    if root_domain.domain is None:
        print("skipping chain_reader because root_domain is null", flush=True)
        return 0

    config = get_config()
    blacklist = set(read_blacklist().root)
    current_domains = read_desired_domains().domains
    contact = subtensor_contact(config.subtensor_address)
    validators = fetch_validators_with_certs(contact=contact, netuid=config.netuid)
    ...
```

Keep the rest of the file unchanged.

- [ ] **Step 5: Add the failing contact-error public test**

Append to `server_shield/tests/chain_reader/test_cli.py`:

```python
def test_chain_reader_main_returns_one_when_contact_raises(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    monkeypatch.setenv("SERVER_SHIELD_MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_SUBTENSOR_ADDRESS", "ws://subtensor")
    monkeypatch.setenv("SERVER_SHIELD_NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__BACKEND_URL", "file:///tmp/server-shield-test-state")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__SHIELD_BACKEND", "AWS")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY", "miner-hotkey")
    write_root_domain(tmp_path, "shield.example.com")
    patched_subtensor_contact.set_validator_certificates([], exception=RuntimeError("boom"))

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "RuntimeError: boom" in captured.err
```

- [ ] **Step 6: Add a mixed-result public test with malformed data**

Append to `server_shield/tests/chain_reader/test_cli.py`:

```python
def test_chain_reader_main_keeps_valid_results_when_one_certificate_payload_is_malformed(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    monkeypatch.setenv("SERVER_SHIELD_MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_SUBTENSOR_ADDRESS", "ws://subtensor")
    monkeypatch.setenv("SERVER_SHIELD_NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__BACKEND_URL", "file:///tmp/server-shield-test-state")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__SHIELD_BACKEND", "AWS")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY", "miner-hotkey")
    write_root_domain(tmp_path, "shield.example.com")
    good_cert = _valid_public_key_hex()
    patched_subtensor_contact.set_validator_certificates(
        [
            ValidatorCertificateRecord(
                hotkey="good-validator",
                certificate_payload={"public_key": [good_cert]},
            ),
            ValidatorCertificateRecord(
                hotkey="malformed-validator",
                certificate_payload={"public_key": []},
            ),
        ]
    )

    exit_code = main()

    desired_domains = read_desired_domains(tmp_path)
    manifest = read_manifest(tmp_path)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert desired_domains.domains["good-validator"].public_cert == good_cert
    assert "malformed-validator" not in desired_domains.domains
    assert set(manifest.ddos_shield_manifest.encrypted_url_mapping) == {"good-validator"}
    assert "excluding validator malformed-validator: malformed certificate payload" in captured.out
    assert "invalid_cert=1" in captured.out
    assert "observed=2" in captured.out
```

- [ ] **Step 7: Run the chain_reader tests to verify green**

Run: `uv run --project server_shield pytest server_shield/tests/chain_reader/test_cli.py -v`

Expected: PASS

- [ ] **Step 8: Commit the chain_reader refactor**

```bash
git add server_shield/src/server_shield/chain_reader/chain.py \
        server_shield/src/server_shield/chain_reader/cli.py \
        server_shield/tests/chain_reader/test_cli.py
git commit -m "refactor: move chain reader to shared contact"
```

## Task 3: Move chain_writer to the shared contact and keep the wallet real

**Files:**
- Modify: `server_shield/src/server_shield/chain_writer/cli.py`
- Modify: `server_shield/tests/chain_writer/test_cli.py`

- [ ] **Step 1: Write the failing public up-to-date test**

Replace the helper-oriented publish test in `server_shield/tests/chain_writer/test_cli.py` with:

```python
from pathlib import Path

from bittensor_wallet import Wallet

from server_shield.chain_writer.cli import main
from server_shield.shared import state_store
from server_shield.shared.state_store import write_axon_public_ip
from server_shield.subtensor_contact import MockSubtensorContact, NeuronAxonRecord


def _create_real_wallet(home_dir: Path, wallet_name: str, hotkey_name: str) -> str:
    wallet = Wallet(path=str(home_dir / ".bittensor" / "wallets"), name=wallet_name, hotkey=hotkey_name)
    wallet.create_coldkey_from_uri("//Alice", use_password=False, overwrite=True)
    wallet.create_hotkey_from_uri("//Alice", use_password=False, overwrite=True)
    return wallet.hotkey.ss58_address


def test_chain_writer_main_logs_up_to_date_with_real_wallet(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SERVER_SHIELD_MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_SUBTENSOR_ADDRESS", "ws://subtensor")
    monkeypatch.setenv("SERVER_SHIELD_NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__BACKEND_URL", "file:///tmp/server-shield-test-state")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__SHIELD_BACKEND", "AWS")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY", "miner-hotkey")
    hotkey_ss58 = _create_real_wallet(tmp_path, "miner", "miner-hotkey")
    patched_subtensor_contact.set_registration(hotkey_ss58=hotkey_ss58, netuid=12, registered=True)
    patched_subtensor_contact.set_neuron_axon(
        hotkey_ss58=hotkey_ss58,
        netuid=12,
        neuron_axon=NeuronAxonRecord(
            is_null=False,
            is_serving=True,
            ip="1.2.3.4",
            port=9001,
        ),
    )
    write_axon_public_ip(tmp_path, "1.2.3.4")

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert hotkey_ss58 in captured.out
    assert "chain_writer axon already up to date" in captured.out
    assert [call.method for call in patched_subtensor_contact.calls] == [
        "is_hotkey_registered",
        "get_neuron_axon",
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --project server_shield pytest server_shield/tests/chain_writer/test_cli.py::test_chain_writer_main_logs_up_to_date_with_real_wallet -v`

Expected: FAIL because `chain_writer` still uses direct Subtensor SDK calls

- [ ] **Step 3: Rewire `chain_writer/cli.py` to use the contact factory**

Update `server_shield/src/server_shield/chain_writer/cli.py`:

```python
import bittensor_wallet

from server_shield.shared.config import AppConfig, get_config
from server_shield.shared.runtime import run_component
from server_shield.shared.state_store import ensure_state_files, read_axon_public_ip
from server_shield.subtensor_contact import subtensor_contact


def _publish_axon_if_needed(config: AppConfig, axon_public_ip: str) -> int:
    wallet = bittensor_wallet.Wallet(
        config.chain_writer.wallet_name,
        config.chain_writer.wallet_hotkey,
    )
    hotkey_ss58 = wallet.hotkey.ss58_address
    contact = subtensor_contact(config.subtensor_address)
    if not contact.is_hotkey_registered(hotkey_ss58=hotkey_ss58, netuid=config.netuid):
        print(
            f"skipping chain_writer because hotkey {hotkey_ss58} is not registered on netuid {config.netuid}",
            flush=True,
        )
        return 0

    neuron = contact.get_neuron_axon(hotkey_ss58=hotkey_ss58, netuid=config.netuid)
    if neuron.is_null:
        print(
            f"skipping chain_writer because neuron lookup failed for hotkey {hotkey_ss58} on netuid {config.netuid}",
            flush=True,
        )
        return 0

    desired_port = config.miner_port
    if neuron.is_serving and neuron.ip == axon_public_ip and neuron.port == desired_port:
        print(
            f"chain_writer axon already up to date for {hotkey_ss58}: {neuron.ip}:{neuron.port}",
            flush=True,
        )
        return 0

    success = contact.publish_axon(
        wallet=wallet,
        netuid=config.netuid,
        ip=axon_public_ip,
        port=desired_port,
    )
    if not success:
        raise RuntimeError("failed to set axon info")

    print(
        f"published axon info for {hotkey_ss58}: {axon_public_ip}:{desired_port}",
        flush=True,
    )
    return 0
```

- [ ] **Step 4: Add the publish and failure tests**

Append to `server_shield/tests/chain_writer/test_cli.py`:

```python
def test_chain_writer_main_publishes_when_chain_state_is_stale(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SERVER_SHIELD_MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_SUBTENSOR_ADDRESS", "ws://subtensor")
    monkeypatch.setenv("SERVER_SHIELD_NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__BACKEND_URL", "file:///tmp/server-shield-test-state")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__SHIELD_BACKEND", "AWS")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY", "miner-hotkey")
    hotkey_ss58 = _create_real_wallet(tmp_path, "miner", "miner-hotkey")
    patched_subtensor_contact.set_registration(hotkey_ss58=hotkey_ss58, netuid=12, registered=True)
    patched_subtensor_contact.set_neuron_axon(
        hotkey_ss58=hotkey_ss58,
        netuid=12,
        neuron_axon=NeuronAxonRecord(
            is_null=False,
            is_serving=True,
            ip="9.9.9.9",
            port=9001,
        ),
    )
    patched_subtensor_contact.set_publish_behavior(result=True)
    write_axon_public_ip(tmp_path, "1.2.3.4")

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "published axon info for " in captured.out
    assert [call.method for call in patched_subtensor_contact.calls] == [
        "is_hotkey_registered",
        "get_neuron_axon",
        "publish_axon",
    ]
    assert patched_subtensor_contact.calls[-1].ip == "1.2.3.4"
    assert patched_subtensor_contact.calls[-1].port == 9001


def test_chain_writer_main_returns_one_when_publish_fails(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SERVER_SHIELD_MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_SUBTENSOR_ADDRESS", "ws://subtensor")
    monkeypatch.setenv("SERVER_SHIELD_NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__BACKEND_URL", "file:///tmp/server-shield-test-state")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__SHIELD_BACKEND", "AWS")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY", "miner-hotkey")
    hotkey_ss58 = _create_real_wallet(tmp_path, "miner", "miner-hotkey")
    patched_subtensor_contact.set_registration(hotkey_ss58=hotkey_ss58, netuid=12, registered=True)
    patched_subtensor_contact.set_neuron_axon(
        hotkey_ss58=hotkey_ss58,
        netuid=12,
        neuron_axon=NeuronAxonRecord(
            is_null=False,
            is_serving=True,
            ip="9.9.9.9",
            port=9001,
        ),
    )
    patched_subtensor_contact.set_publish_behavior(result=False)
    write_axon_public_ip(tmp_path, "1.2.3.4")

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "RuntimeError: failed to set axon info" in captured.err
```

- [ ] **Step 5: Run the chain_writer tests to verify green**

Run: `uv run --project server_shield pytest server_shield/tests/chain_writer/test_cli.py -v`

Expected: PASS

- [ ] **Step 6: Commit the chain_writer refactor**

```bash
git add server_shield/src/server_shield/chain_writer/cli.py \
        server_shield/tests/chain_writer/test_cli.py
git commit -m "refactor: move chain writer to shared contact"
```

## Task 4: Add dedicated real-contact integration tests

**Files:**
- Modify: `server_shield/pyproject.toml`
- Create: `server_shield/tests/contacts/local_subtensor.py`
- Create: `server_shield/tests/contacts/conftest.py`
- Create: `server_shield/tests/contacts/test_subtensor_contact.py`

- [ ] **Step 1: Add integration-test dependencies and marker config**

Modify `server_shield/pyproject.toml`:

```toml
[dependency-groups]
dev = [
    "pytest>=9,<10",
    "pytest-asyncio>=1.1,<2",
    "testcontainers>=4.13,<5",
]

[tool.pytest.ini_options]
markers = [
    "subtensor_integration: tests that require a disposable local subtensor environment",
]
addopts = "-m 'not subtensor_integration'"
```

- [ ] **Step 2: Add the local Subtensor bootstrap helper**

Create `server_shield/tests/contacts/local_subtensor.py` by adapting the working pattern from `bt_ddos_shield_client/tests/contacts/local_subtensor.py`. Keep the helper test-owned and do not depend on `manual_tests/`.

Required public helper surface:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bittensor import Subtensor
from bittensor_wallet import Wallet


@dataclass
class LocalSubtensorEnv:
    ws_endpoint: str
    wallet_root: Path
    subtensor: Subtensor
    validator_wallet: Wallet
    miner_wallet: Wallet
    netuid: int

    def cleanup(self) -> None:
        ...


def start_local_subtensor_env() -> LocalSubtensorEnv:
    ...
```

- [ ] **Step 3: Add the contact integration fixtures**

Create `server_shield/tests/contacts/conftest.py`:

```python
from __future__ import annotations

import pytest

from tests.contacts.local_subtensor import start_local_subtensor_env


@pytest.fixture(scope="module")
def local_subtensor_env():
    env = start_local_subtensor_env()
    try:
        yield env
    finally:
        env.cleanup()


@pytest.fixture(scope="module")
def subtensor(local_subtensor_env):
    return local_subtensor_env.subtensor


@pytest.fixture(scope="module")
def validator_wallet(local_subtensor_env):
    return local_subtensor_env.validator_wallet


@pytest.fixture(scope="module")
def miner_wallet(local_subtensor_env):
    return local_subtensor_env.miner_wallet


@pytest.fixture(scope="module")
def netuid(local_subtensor_env):
    return local_subtensor_env.netuid


@pytest.fixture(scope="module")
def ws_endpoint(local_subtensor_env):
    return local_subtensor_env.ws_endpoint
```

- [ ] **Step 4: Add the real contact test file**

Create `server_shield/tests/contacts/test_subtensor_contact.py`:

```python
from __future__ import annotations

import pytest

from server_shield.subtensor_contact import BittensorSubtensorContact


@pytest.mark.subtensor_integration
def test_subtensor_contact_lists_registered_validator_certificates(
    ws_endpoint,
    validator_wallet,
    miner_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    records = contact.list_validator_certificates(netuid=netuid)

    hotkeys = {record.hotkey for record in records}
    assert validator_wallet.hotkey.ss58_address in hotkeys
    assert miner_wallet.hotkey.ss58_address not in hotkeys


@pytest.mark.subtensor_integration
def test_subtensor_contact_reports_registration_for_registered_hotkey(
    ws_endpoint,
    validator_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    registered = contact.is_hotkey_registered(
        hotkey_ss58=validator_wallet.hotkey.ss58_address,
        netuid=netuid,
    )

    assert registered is True
```

- [ ] **Step 5: Extend the real contact test file with neuron-read and publish coverage**

Append to `server_shield/tests/contacts/test_subtensor_contact.py`:

```python
@pytest.mark.subtensor_integration
def test_subtensor_contact_reads_registered_neuron_axon(
    ws_endpoint,
    validator_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    neuron = contact.get_neuron_axon(
        hotkey_ss58=validator_wallet.hotkey.ss58_address,
        netuid=netuid,
    )

    assert neuron.is_null is False


@pytest.mark.subtensor_integration
def test_subtensor_contact_publishes_and_reads_back_axon_info(
    ws_endpoint,
    validator_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    published = contact.publish_axon(
        wallet=validator_wallet,
        netuid=netuid,
        ip="203.0.113.77",
        port=19001,
    )
    after = contact.get_neuron_axon(
        hotkey_ss58=validator_wallet.hotkey.ss58_address,
        netuid=netuid,
    )

    assert published is True
    assert after.is_null is False
    assert after.port == 19001
```

- [ ] **Step 6: Run the real contact integration tests**

Run: `uv run --project server_shield pytest -m subtensor_integration server_shield/tests/contacts/test_subtensor_contact.py -v`

Expected: PASS

- [ ] **Step 7: Commit the real contact tests**

```bash
git add server_shield/pyproject.toml \
        server_shield/tests/contacts/local_subtensor.py \
        server_shield/tests/contacts/conftest.py \
        server_shield/tests/contacts/test_subtensor_contact.py
git commit -m "test: add real subtensor contact integration coverage"
```

## Task 5: Run the focused verification suite

**Files:**
- Test: `server_shield/tests/chain_reader/test_cli.py`
- Test: `server_shield/tests/chain_writer/test_cli.py`
- Test: `server_shield/tests/contacts/test_subtensor_contact.py`

- [ ] **Step 1: Run the focused CLI suite**

Run: `uv run --project server_shield pytest server_shield/tests/chain_reader/test_cli.py server_shield/tests/chain_writer/test_cli.py -v`

Expected: PASS

- [ ] **Step 2: Run the dedicated real contact suite**

Run: `uv run --project server_shield pytest -m subtensor_integration server_shield/tests/contacts/test_subtensor_contact.py -v`

Expected: PASS

- [ ] **Step 3: Run a broader smoke suite**

Run: `uv run --project server_shield pytest server_shield/tests/shared/test_state_store.py server_shield/tests/chain_reader/test_cli.py server_shield/tests/chain_writer/test_cli.py -v`

Expected: PASS

- [ ] **Step 4: Commit any follow-up verification fixes**

```bash
git add server_shield/pyproject.toml \
        server_shield/src/server_shield/subtensor_contact.py \
        server_shield/src/server_shield/chain_reader/chain.py \
        server_shield/src/server_shield/chain_reader/cli.py \
        server_shield/src/server_shield/chain_writer/cli.py \
        server_shield/tests/conftest.py \
        server_shield/tests/contacts/local_subtensor.py \
        server_shield/tests/contacts/conftest.py \
        server_shield/tests/contacts/test_subtensor_contact.py \
        server_shield/tests/chain_reader/test_cli.py \
        server_shield/tests/chain_writer/test_cli.py
git commit -m "test: align chain cli coverage with engineering standards"
```

## Self-Review

- Spec coverage:
  - Shared singleton-backed contact boundary: Task 1.
  - Concrete mutable mock contact implementing the abstract interface: Task 1.
  - `chain_reader` on the contact boundary with real manifest generation and malformed-cert coverage: Task 2.
  - `chain_writer` on the contact boundary with a real wallet: Task 3.
  - Dedicated real contact implementation tests: Task 4.
  - Verification before completion: Task 5.
- Placeholder scan:
  - No `TODO`, `TBD`, or “similar to above” references remain.
- Type consistency:
  - `AbstractSubtensorContact`, `MockSubtensorContact`, `ValidatorCertificateRecord`, `NeuronAxonRecord`, `SubtensorContactCall`, and `subtensor_contact(...)` use the same names across the file map, code snippets, and tests.
