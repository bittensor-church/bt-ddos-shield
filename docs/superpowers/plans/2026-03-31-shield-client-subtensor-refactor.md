# Shield Client / Subtensor Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `bt_ddos_shield_client` so `ShieldClient` is a pure local certificate + manifest helper, all bittensor/turbobt I/O flows through contact adapters, certificate reconciliation lives in a separate TTL-backed layer, and both `ShieldMetagraph` and `ShieldedSubnetReference` stop relying on `super()` for chain transport.

**Architecture:** Introduce a dedicated contact module that becomes the only adapter surface for bittensor/turbobt communication, plus a separate `CertificateReconciler` that owns “does on-chain cert match local cert?” TTL state. `ShieldMetagraph` should delegate to a contact that invokes the upstream `Metagraph.sync(...)` implementation on the passed metagraph instance, while `ShieldedSubnetReference` should delegate to a contact that invokes the upstream `SubnetReference.list_neurons(...)` implementation on a wrapped base subnet reference.

**Tech Stack:** Python 3.11+, `bittensor~=9.0`, `turbobt~=0.3.1`, `concurrent.futures.ThreadPoolExecutor`, existing certificate / manifest helpers in `bt_ddos_shield_client`

---

## File Map

- Create: `bt_ddos_shield_client/bt_ddos_shield_client/contacts.py`
  - Home for the reusable adapter layer over bittensor and turbobt.
  - Exposes `BittensorSubtensorContact` and `TurboBittensorSubtensorContact`.
- Create: `bt_ddos_shield_client/bt_ddos_shield_client/certificate_reconciliation.py`
  - Home for `CertificateReconciler` and its TTL-backed “cert matches local cert” cache.
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/client.py`
  - Remove context manager behavior and chain dependencies.
  - Keep only local certificate lifecycle and manifest-based shield address resolution.
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py`
  - Replace inline contact classes and `super().sync(...)` transport usage.
  - Build `ShieldClient`, contact, reconciler, and reusable executor.
  - Delegate base metagraph sync through the contact, then apply shield-address rewriting.
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py`
  - Replace inline contact class and `super().list_neurons(...)` transport usage.
  - Use `CertificateReconciler`.
  - Add `ShieldedSubnetReference.from_bittensor(...)`.
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/internal.py`
  - Let `run_async_in_thread` use a caller-supplied executor.

## Constraints

- Do not add new tests in this change.
- Do not add `get_hotkey()` to the public contact interface.
- Neuron fetching must fail if reading or writing the on-chain certificate fails.
- The TTL cache tracks only whether the on-chain cert matches the current local cert.
- Contact adapters own all bittensor/turbobt communication used by this package.

### Task 1: Create the contact adapter layer

**Files:**
- Create: `bt_ddos_shield_client/bt_ddos_shield_client/contacts.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py`

- [ ] **Step 1: Create the shared contact protocol surface**

Create `bt_ddos_shield_client/bt_ddos_shield_client/contacts.py` with the shared protocol surface:

```python
from __future__ import annotations

import asyncio
from typing import Protocol

import turbobt
from bittensor import Subtensor
from bittensor.core.extrinsics.serving import serve_extrinsic
from bittensor.core.metagraph import Metagraph

from bt_ddos_shield_client.certificates import CertificateAlgorithmEnum
from bt_ddos_shield_client.internal import decode_subtensor_certificate_info
from bt_ddos_shield_client.types import PublicKey


class CertificateContact(Protocol):
    async def get_own_public_key(self) -> PublicKey | None: ...

    async def upload_public_key(
        self,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
    ) -> None: ...


class MetagraphContact(CertificateContact, Protocol):
    def sync_metagraph(
        self,
        metagraph: Metagraph,
        *,
        block: int | None = None,
        lite: bool | None = None,
    ) -> None: ...
```

- [ ] **Step 2: Implement the bittensor contact as the metagraph transport adapter**

Add the bittensor adapter to `contacts.py` so `ShieldMetagraph` no longer calls `super().sync(...)` for transport:

```python
class BittensorSubtensorContact:
    def __init__(self, subtensor: Subtensor, netuid: int, wallet):
        self.subtensor = subtensor
        self.netuid = netuid
        self.wallet = wallet

    def sync_metagraph(
        self,
        metagraph: Metagraph,
        *,
        block: int | None = None,
        lite: bool | None = None,
    ) -> None:
        Metagraph.sync(
            metagraph,
            block=block,
            lite=lite,
            subtensor=self.subtensor,
        )
```

- [ ] **Step 3: Implement the certificate operations on both contacts**

Add the own-certificate read/write methods to `BittensorSubtensorContact` and `TurboBittensorSubtensorContact` in `contacts.py`:

```python
    async def get_own_public_key(self) -> PublicKey | None:
        return await asyncio.to_thread(self._get_own_public_key)

    async def upload_public_key(
        self,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
    ) -> None:
        await asyncio.to_thread(self._upload_public_key, public_key, algorithm)

    def _get_own_public_key(self) -> PublicKey | None:
        certificate = self.subtensor.query_subtensor(
            name="NeuronCertificates",
            params=[self.netuid, self.wallet.hotkey.ss58_address],
        )
        if certificate is None:
            return None
        decoded = decode_subtensor_certificate_info(certificate)
        return None if decoded is None else decoded.hex_data

    def _upload_public_key(
        self,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
    ) -> None:
        neuron = self.subtensor.get_neuron_for_pubkey_and_subnet(
            self.wallet.hotkey.ss58_address,
            netuid=self.netuid,
        )
        axon_info = None if neuron is None else neuron.axon_info
        new_ip = "1.1.1.1" if axon_info is None else str(axon_info.ip)
        new_port = 1 if axon_info is None else axon_info.port
        new_protocol = 0 if axon_info is None else axon_info.protocol
        new_placeholder1 = 0 if axon_info is None else (axon_info.placeholder1 + 1) % 256
        certificate_data = bytes([algorithm]) + bytes.fromhex(public_key)
        serve_extrinsic(
            self.subtensor,
            self.wallet,
            new_ip,
            new_port,
            new_protocol,
            self.netuid,
            certificate=certificate_data,  # type: ignore[arg-type]
            placeholder1=new_placeholder1,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )


class TurboBittensorSubtensorContact:
    def __init__(self, bittensor, netuid: int, wallet):
        self.bittensor = bittensor
        self.netuid = netuid
        self.wallet = wallet
        self.subnet = turbobt.subnet.SubnetReference(netuid, client=bittensor)

    async def list_neurons(self, block_hash: str | None = None) -> list[turbobt.neuron.Neuron]:
        return await self.subnet.list_neurons(block_hash)

    async def get_own_public_key(self) -> PublicKey | None:
        neuron = self.subnet.neuron(hotkey=self.wallet.hotkey.ss58_address)
        certificate = await neuron.get_certificate()
        if not certificate:
            return None
        if isinstance(certificate.get("public_key"), list):
            public_key = certificate["public_key"][0]
            if isinstance(public_key, str):
                certificate = {**certificate, "public_key": [public_key]}
            else:
                certificate = {**certificate, "public_key": [bytes.fromhex(public_key)]}
        decoded = decode_subtensor_certificate_info(certificate)
        return None if decoded is None else decoded.hex_data

    async def upload_public_key(
        self,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
    ) -> None:
        neuron = await self.subnet.get_neuron(self.wallet.hotkey.ss58_address)
        ip = "1.1.1.1"
        port = 1
        if neuron and neuron.axon_info and str(neuron.axon_info.ip) != "0.0.0.0":
            ip = str(neuron.axon_info.ip or ip)
            port = neuron.axon_info.port or port
        certificate_data = bytes([algorithm]) + bytes.fromhex(public_key)
        await self.subnet.neurons.serve(ip, port, certificate=certificate_data, wallet=self.wallet)
```

- [ ] **Step 4: Switch existing modules to import contacts from the new module**

Replace inline contact declarations in `shield_metagraph.py` and `shielded_turbobt/shielded_bittensor.py` with imports from `contacts.py`:

```python
from bt_ddos_shield_client.contacts import (
    BittensorSubtensorContact,
    TurboBittensorSubtensorContact,
)
```

Delete the old inline `BittensorSubtensorContact`, `TurboBittensorSubtensorContact`, and `get_contact_instance(...)` blocks once the imports are in place.

- [ ] **Step 5: Run a syntax smoke check for the new adapter file**

Run: `uv run --project bt_ddos_shield_client python3 -m compileall bt_ddos_shield_client/bt_ddos_shield_client/contacts.py`

Expected: `Compiling 'bt_ddos_shield_client/bt_ddos_shield_client/contacts.py'...`

- [ ] **Step 6: Commit the adapter layer**

```bash
git add bt_ddos_shield_client/bt_ddos_shield_client/contacts.py \
        bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py \
        bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py
git commit -m "refactor: add shield contact adapters"
```

### Task 2: Refactor ShieldClient and add certificate reconciliation

**Files:**
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/client.py`
- Create: `bt_ddos_shield_client/bt_ddos_shield_client/certificate_reconciliation.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py`

- [ ] **Step 1: Remove chain and context-manager behavior from ShieldClient**

Replace `client.py` with a local-only helper:

```python
from __future__ import annotations

import os

from bt_ddos_shield_client.certificates import Certificate, EDDSACertificateManager
from bt_ddos_shield_client.encryption import ECIESEncryptionManager
from bt_ddos_shield_client.manifest import JsonManifestSerializer, fetch_manifest, get_address_for_validator
from bt_ddos_shield_client.types import Hotkey, ShieldAddress


class ShieldClient:
    def __init__(
        self,
        certificate_path: str | None = None,
        manifest_timeout: int = 10,
    ):
        self.certificate_path = certificate_path or os.getenv(
            "VALIDATOR_SHIELD_CERTIFICATE_PATH",
            "./validator_cert.pem",
        )
        self.manifest_timeout = manifest_timeout
        self.certificate_manager = EDDSACertificateManager()
        self.encryption_manager = ECIESEncryptionManager()
        self.manifest_serializer = JsonManifestSerializer()
        self.certificate = self._load_or_create_certificate()

    def _load_or_create_certificate(self) -> Certificate:
        try:
            return self.certificate_manager.load_certificate(self.certificate_path)
        except FileNotFoundError:
            certificate = self.certificate_manager.generate_certificate()
            self.certificate_manager.save_certificate(certificate, self.certificate_path)
            return certificate

    async def resolve_shield_address(
        self,
        validator_hotkey: Hotkey,
        axon_ip: str,
        axon_port: int,
    ) -> ShieldAddress | None:
        manifest = await fetch_manifest(
            axon_ip,
            axon_port,
            timeout=self.manifest_timeout,
            serializer=self.manifest_serializer,
        )
        if manifest is None:
            return None
        return get_address_for_validator(
            manifest,
            validator_hotkey,
            self.certificate.private_key,
            self.encryption_manager,
        )
```

- [ ] **Step 2: Create the TTL-backed reconciler**

Create `bt_ddos_shield_client/bt_ddos_shield_client/certificate_reconciliation.py`:

```python
from __future__ import annotations

import time
from dataclasses import dataclass

from bt_ddos_shield_client.certificates import Certificate
from bt_ddos_shield_client.contacts import CertificateContact


@dataclass
class CertificateReconciler:
    contact: CertificateContact
    certificate: Certificate
    match_ttl_seconds: float = 300.0
    _matched_public_key: str | None = None
    _matched_until: float = 0.0

    def _is_match_cached(self) -> bool:
        return (
            self._matched_public_key == self.certificate.public_key
            and time.monotonic() < self._matched_until
        )

    def _cache_match(self) -> None:
        self._matched_public_key = self.certificate.public_key
        self._matched_until = time.monotonic() + self.match_ttl_seconds

    async def ensure_own_certificate_matches(self) -> None:
        if self._is_match_cached():
            return

        public_key = await self.contact.get_own_public_key()
        if public_key == self.certificate.public_key:
            self._cache_match()
            return

        await self.contact.upload_public_key(
            self.certificate.public_key,
            self.certificate.algorithm,
        )
        self._cache_match()
```

- [ ] **Step 3: Wire the reconciler into the two call sites**

Update `shield_metagraph.py` and `shielded_turbobt/shielded_bittensor.py` to construct:

```python
self._shield_client = ShieldClient(
    certificate_path=resolve_certificate_path(self.options.certificate_path),
)
self._certificate_reconciler = CertificateReconciler(
    contact=self._contact,
    certificate=self._shield_client.certificate,
)
```

There should be no `__aenter__`, `__aexit__`, upload retry, or contact injection remaining in `ShieldClient`.

- [ ] **Step 4: Run a syntax smoke check for the refactored certificate path**

Run: `uv run --project bt_ddos_shield_client python3 -m compileall bt_ddos_shield_client/bt_ddos_shield_client/client.py bt_ddos_shield_client/bt_ddos_shield_client/certificate_reconciliation.py`

Expected:

```text
Compiling 'bt_ddos_shield_client/bt_ddos_shield_client/client.py'...
Compiling 'bt_ddos_shield_client/bt_ddos_shield_client/certificate_reconciliation.py'...
```

- [ ] **Step 5: Commit the client/reconciler split**

```bash
git add bt_ddos_shield_client/bt_ddos_shield_client/client.py \
        bt_ddos_shield_client/bt_ddos_shield_client/certificate_reconciliation.py \
        bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py \
        bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py
git commit -m "refactor: split shield client from certificate reconciliation"
```

### Task 3: Refactor ShieldMetagraph to use contact-driven sync

**Files:**
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/internal.py`

- [ ] **Step 1: Make `run_async_in_thread` executor-aware**

Update `internal.py`:

```python
from concurrent.futures import Executor


def _run_coroutine(async_fn):
    return asyncio.run(async_fn)


def run_async_in_thread(async_fn, *, executor: Executor | None = None) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_fn)

    if executor is not None:
        future = executor.submit(_run_coroutine, async_fn)
        return future.result()

    result = None
    exception = None

    def thread_runner():
        nonlocal result, exception
        try:
            result = asyncio.run(async_fn)
        except Exception as exc:  # pragma: no cover - passthrough
            exception = exc

    thread = threading.Thread(target=thread_runner)
    thread.start()
    thread.join()

    if exception is not None:
        raise exception
    return result
```

- [ ] **Step 2: Build ShieldMetagraph around contact delegation and reusable async bridging**

Update `shield_metagraph.py` so the contact owns the base sync call and `ShieldMetagraph` only orchestrates reconciliation plus shield-address rewriting:

```python
from concurrent.futures import ThreadPoolExecutor

from bt_ddos_shield_client.certificate_reconciliation import CertificateReconciler
from bt_ddos_shield_client.contacts import BittensorSubtensorContact


class ShieldMetagraph(Metagraph):
    def __init__(self, wallet, netuid: int, network: str | None = None, lite: bool = True, sync: bool = True, block: int | None = None, subtensor=None, options: ShieldMetagraphOptions | None = None):
        if subtensor is None:
            subtensor = Subtensor(network=network)
        super().__init__(
            netuid=netuid,
            network=network or "finney",
            lite=lite,
            sync=False,
            subtensor=subtensor,
        )
        self.wallet = wallet
        self.options = options or ShieldMetagraphOptions()
        self._contact = BittensorSubtensorContact(
            subtensor=self.subtensor,
            netuid=netuid,
            wallet=wallet,
        )
        self._shield_client = ShieldClient(
            certificate_path=resolve_certificate_path(self.options.certificate_path),
        )
        self._certificate_reconciler = CertificateReconciler(
            contact=self._contact,
            certificate=self._shield_client.certificate,
        )
        self._async_executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="shield-metagraph",
        )
```

- [ ] **Step 3: Replace `super().sync(...)` with a contact invocation of the upstream sync**

Change `ShieldMetagraph.__init__()` and `sync()` in `shield_metagraph.py`:

```python
    def sync(self, block: int | None = None, lite: bool | None = None, subtensor=None):
        self._contact.sync_metagraph(
            self,
            block=block,
            lite=lite,
        )

        run_async_in_thread(
            self._certificate_reconciler.ensure_own_certificate_matches(),
            executor=self._async_executor,
        )

        validator_hotkey = self.wallet.hotkey.ss58_address
        for axon in self.axons:
            shield_address = run_async_in_thread(
                self._shield_client.resolve_shield_address(
                    validator_hotkey,
                    str(axon.ip),
                    axon.port,
                ),
                executor=self._async_executor,
            )
            if shield_address is None:
                continue
            axon.ip = shield_address
```

Also remove the old `run_async_in_thread(self._shield_client.__aenter__())` call from `__init__()`.

- [ ] **Step 4: Run a syntax smoke check for the metagraph refactor**

Run: `uv run --project bt_ddos_shield_client python3 -m compileall bt_ddos_shield_client/bt_ddos_shield_client/internal.py bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py`

Expected:

```text
Compiling 'bt_ddos_shield_client/bt_ddos_shield_client/internal.py'...
Compiling 'bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py'...
```

- [ ] **Step 5: Commit the metagraph transport rewrite**

```bash
git add bt_ddos_shield_client/bt_ddos_shield_client/internal.py \
        bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py
git commit -m "refactor: move shield metagraph sync behind contacts"
```

### Task 4: Refactor shielded turbobt and expose `from_bittensor`

**Files:**
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/__init__.py`

- [ ] **Step 1: Remove ShieldClient context-manager usage from ShieldedBittensor**

Update the constructor and async lifecycle in `shielded_bittensor.py`:

```python
class ShieldedBittensor(turbobt.Bittensor):
    def __init__(
        self,
        *args,
        wallet,
        ddos_shield_netuid: int,
        ddos_shield_options: ShieldMetagraphOptions | None = None,
        **kwargs,
    ):
        super().__init__(*args, wallet=wallet, **kwargs)
        self.ddos_shield_options = ddos_shield_options or ShieldMetagraphOptions()
        self.ddos_shield_netuid = ddos_shield_netuid
        self._contact = TurboBittensorSubtensorContact(
            bittensor=self,
            netuid=ddos_shield_netuid,
            wallet=wallet,
        )
        self._shield_client = ShieldClient(
            certificate_path=resolve_certificate_path(self.ddos_shield_options.certificate_path),
        )
        self._certificate_reconciler = CertificateReconciler(
            contact=self._contact,
            certificate=self._shield_client.certificate,
        )

    async def __aenter__(self):
        await super().__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs):
        await super().__aexit__(*args, **kwargs)
```

- [ ] **Step 2: Add a reusable public constructor on ShieldedSubnetReference**

Add the classmethod in `shielded_bittensor.py`:

```python
@dataclasses.dataclass
class ShieldedSubnetReference(turbobt.subnet.SubnetReference):
    client: dataclasses.InitVar[turbobt.Bittensor]
    wallet: dataclasses.InitVar[object | None] = None
    ddos_shield_options: dataclasses.InitVar[ShieldMetagraphOptions | None] = None

    def __post_init__(self, client, wallet=None, ddos_shield_options=None):
        super().__post_init__(client)
        self.wallet = wallet or client.wallet
        self.ddos_shield_options = ddos_shield_options or ShieldMetagraphOptions()
        self._contact = TurboBittensorSubtensorContact(
            bittensor=client,
            netuid=self.netuid,
            wallet=self.wallet,
        )
        self._shield_client = ShieldClient(
            certificate_path=resolve_certificate_path(self.ddos_shield_options.certificate_path),
        )
        self._certificate_reconciler = CertificateReconciler(
            contact=self._contact,
            certificate=self._shield_client.certificate,
        )

    @classmethod
    def from_bittensor(
        cls,
        bittensor: turbobt.Bittensor,
        netuid: int,
        *,
        wallet=None,
        ddos_shield_options: ShieldMetagraphOptions | None = None,
    ) -> "ShieldedSubnetReference":
        return cls(
            netuid=netuid,
            client=bittensor,
            wallet=wallet,
            ddos_shield_options=ddos_shield_options,
        )
```

- [ ] **Step 3: Replace `super().list_neurons(...)` with the contact adapter**

Rewrite the listing path in `shielded_bittensor.py`:

```python
    async def list_neurons(self, block_hash: str | None = None) -> list[turbobt.neuron.Neuron]:
        await self._certificate_reconciler.ensure_own_certificate_matches()

        neurons = await self._contact.list_neurons(block_hash=block_hash)
        validator_hotkey = self.wallet.hotkey.ss58_address
        for neuron in neurons:
            shield_address = await self._shield_client.resolve_shield_address(
                validator_hotkey,
                str(neuron.axon_info.ip),
                neuron.axon_info.port,
            )
            if shield_address is None:
                continue
            host, _, port_text = shield_address.rpartition(":")
            if not host or not port_text:
                continue
            neuron.axon_info.ip = host
            neuron.axon_info.port = int(port_text)
        return neurons
```

- [ ] **Step 4: Keep ShieldedBittensor.subnet() routing through the new classmethod**

Update the routing logic in `shielded_bittensor.py`:

```python
    def subnet(self, netuid: int) -> turbobt.subnet.SubnetReference:
        if netuid == self.ddos_shield_netuid:
            return ShieldedSubnetReference.from_bittensor(
                self,
                netuid,
                wallet=self.wallet,
                ddos_shield_options=self.ddos_shield_options,
            )
        return super().subnet(netuid)
```

Keep `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/__init__.py` exporting `ShieldedSubnetReference`.

- [ ] **Step 5: Run a syntax smoke check for the turbobt refactor**

Run: `uv run --project bt_ddos_shield_client python3 -m compileall bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py`

Expected: `Compiling 'bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py'...`

- [ ] **Step 6: Commit the turbobt rewrite**

```bash
git add bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py \
        bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/__init__.py
git commit -m "refactor: route shielded turbobt through contacts"
```

### Task 5: Final package-level sanity pass

**Files:**
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/contacts.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/certificate_reconciliation.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/client.py`
- Modify: `bt_ddos_shield_client/bt_ddos_shield_client/internal.py`

- [ ] **Step 1: Reconcile import cycles and final names**

Make sure the final imports settle on this shape:

```python
from bt_ddos_shield_client.certificate_reconciliation import CertificateReconciler
from bt_ddos_shield_client.client import ShieldClient
from bt_ddos_shield_client.contacts import (
    BittensorSubtensorContact,
    TurboBittensorSubtensorContact,
)
from bt_ddos_shield_client.internal import run_async_in_thread
```

If `contacts.py` importing `turbobt` at module load causes optional-dependency problems, move the `turbobt` import behind `typing.TYPE_CHECKING` plus method-local imports, or split the turbo contact into `shielded_turbobt/shielded_contacts.py` while keeping the public adapter concept unchanged.

- [ ] **Step 2: Run a package-wide syntax smoke check**

Run: `uv run --project bt_ddos_shield_client python3 -m compileall bt_ddos_shield_client/bt_ddos_shield_client`

Expected: compile output for the touched package modules and no syntax errors.

- [ ] **Step 3: Review the diff against the spec**

Run:

```bash
git diff -- bt_ddos_shield_client/bt_ddos_shield_client/client.py \
           bt_ddos_shield_client/bt_ddos_shield_client/contacts.py \
           bt_ddos_shield_client/bt_ddos_shield_client/certificate_reconciliation.py \
           bt_ddos_shield_client/bt_ddos_shield_client/internal.py \
           bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py \
           bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py
```

Confirm all of the following before stopping:

- `ShieldClient` has no context-manager methods.
- `ShieldClient` does not accept `wallet` or `subtensor`.
- contacts own the bittensor/turbobt calls that used to be hidden behind `super().sync()` and `super().list_neurons()`.
- the TTL cache lives in `CertificateReconciler`, not a contact.
- `get_hotkey()` is not part of the contact interface.
- neuron fetching fails if certificate read or write fails.

- [ ] **Step 4: Commit the final integration pass**

```bash
git add bt_ddos_shield_client/bt_ddos_shield_client/client.py \
        bt_ddos_shield_client/bt_ddos_shield_client/contacts.py \
        bt_ddos_shield_client/bt_ddos_shield_client/certificate_reconciliation.py \
        bt_ddos_shield_client/bt_ddos_shield_client/internal.py \
        bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py \
        bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py
git commit -m "refactor: finalize shield contact and reconciliation split"
```
