# Client Ed25519 ECIES Migration Design

## Goal

Make the base `bt_ddos_shield_client` package installable and testable on Python 3.14 by removing its direct dependency on `eciespy`/`coincurve`, while preserving the existing Ed25519 manifest encryption format and validator certificate format.

This design applies to the core client package. The optional `turbobt` extra remains a separate compatibility concern because `turbobt~=0.3.1` currently depends on `eciespy~=0.4.6`, which still pulls `coincurve`.

## Current State

The client currently uses `eciespy` in two places:

- `bt_ddos_shield_client/bt_ddos_shield_client/encryption.py`
  - `ECIESEncryptionManager.encrypt(...)`
  - `ECIESEncryptionManager.decrypt(...)`
  - configured with `Config(elliptic_curve="ed25519")`
- `bt_ddos_shield_client/bt_ddos_shield_client/certificates.py`
  - `EDDSACertificateManager.generate_certificate(...)`
  - `EDDSACertificateManager.load_certificate(...)`
  - uses `ecies.keys.PrivateKey` to generate raw 32-byte Ed25519 private keys and derive raw 32-byte public keys

The miner-side `server_shield` already avoids `eciespy`. It locally implements the same Ed25519 ECIES-compatible wire format using PyCryptodome:

```text
ephemeral_public_key(32) || aes_gcm_nonce(16) || aes_gcm_tag(16) || ciphertext
```

The client fails to install under Python 3.14 because `eciespy` depends on `coincurve`. On Python 3.14, `coincurve==21.0.0` falls back to a source build and fails in this environment. The core client dependencies other than `eciespy` install successfully under Python 3.14.

## Non-Goals

- Do not change the on-chain validator certificate payload format.
- Do not change the manifest JSON shape.
- Do not change the encrypted plaintext format; it remains `<domain>:<port>`.
- Do not add `secp256k1`, `x25519`, compressed-key, XChaCha20, or alternate ECIES modes to the client.
- Do not solve `turbobt` Python 3.14 compatibility in this migration. The optional extra may remain constrained or documented as Python `<3.14` until upstream changes.

## Design

### Core Crypto Module

Add a client-owned Ed25519-only ECIES module, for example:

```text
bt_ddos_shield_client/bt_ddos_shield_client/ed25519_ecies.py
```

This module owns the project-specific cryptographic contract:

- private keys are raw 32-byte Ed25519 seeds encoded as hex strings;
- public keys are raw 32-byte Ed25519 public keys encoded as hex strings;
- encryption generates a fresh 32-byte ephemeral Ed25519 private key;
- the ephemeral public key is derived from that private key;
- the shared point is:

```text
receiver_public_key.pointQ * ephemeral_private_scalar
```

- the AES key is:

```text
HKDF-SHA256(ephemeral_public_key || shared_point, length=32, salt=b"")
```

- AES-GCM uses a 16-byte nonce and 16-byte tag;
- ciphertext bytes are returned as:

```text
ephemeral_public_key || nonce || tag || encrypted
```

Decryption mirrors the same format:

- split the first 32 bytes as `ephemeral_public_key`;
- split the next 16 bytes as `nonce`;
- split the next 16 bytes as `tag`;
- the remaining bytes are ciphertext;
- derive the shared point from the validator private key and ephemeral public key;
- derive the AES key from `ephemeral_public_key || shared_point`;
- verify and decrypt with AES-GCM.

The module should expose small functions rather than a broad compatibility layer:

```python
def public_key_from_private_key(private_key_hex: str) -> str: ...
def generate_private_key_hex() -> str: ...
def encrypt(public_key_hex: str, data: bytes) -> bytes: ...
def decrypt(private_key_hex: str, data: bytes) -> bytes: ...
```

The implementation should accept an optional `0x` prefix on incoming hex keys only where the current client/server behavior already tolerates it.

### Encryption Manager

Keep `ECIESEncryptionManager` as the public wrapper used by the rest of the client, but replace its internals:

- remove imports from `ecies` and `ecies.config`;
- delegate to `ed25519_ecies.encrypt(...)` and `ed25519_ecies.decrypt(...)`;
- keep `EncryptionError` and `DecryptionError` wrapping behavior unchanged.

This avoids changing the rest of the client flow and keeps existing tests meaningful.

### Certificate Manager

Update `EDDSACertificateManager` so it no longer imports `ecies.keys.PrivateKey`.

Certificate generation should:

- generate a random raw 32-byte private key seed;
- derive the raw public key through PyCryptodome Ed25519;
- return the same `Certificate` dataclass shape as today.

Certificate loading should:

- continue reading the existing PEM file format;
- extract the raw private key bytes using `cryptography`;
- derive the public key through the local `public_key_from_private_key(...)` helper;
- return the same private/public hex strings as today.

Certificate saving should remain unchanged except for import cleanup, because it already serializes raw Ed25519 private bytes through `cryptography`.

Existing certificate fixture files must continue to load to the same public keys. This protects existing validator certificates from accidental rotation after upgrade.

### Packaging

Update `bt_ddos_shield_client/pyproject.toml`:

- change core Python support from:

```toml
requires-python = ">=3.11,<3.14"
```

to:

```toml
requires-python = ">=3.11,<3.15"
```

- remove core dependency:

```toml
"eciespy~=0.4"
```

- add or keep explicit core dependency:

```toml
"pycryptodome>=3.21.0,<4"
```

The existing `cryptography` dependency remains because certificate PEM load/save uses it.

The `turbobt` optional extra needs special handling because upstream `turbobt~=0.3.1` depends on `eciespy`. The implementation plan should choose one of these package-level treatments:

- keep `turbobt~=0.3.1` as-is, and document that `bt_ddos_shield_client[turbobt]` is not Python 3.14-compatible yet;
- or add a Python-version marker to the optional extra:

```toml
turbobt = [
    "turbobt~=0.3.1; python_version < '3.14'",
]
```

The recommended first step is the marker, because it prevents users on Python 3.14 from getting a known-broken optional dependency while preserving the extra for Python 3.11-3.13.

### Tests

Add tests at the protocol boundary, not just implementation internals.

Client crypto tests should cover:

- public key derivation from fixed private keys matches known values;
- generated certificates load/save without changing public key derivation;
- local encrypt/decrypt round trip;
- local decrypt of the server golden vector;
- `ECIESEncryptionManager` still wraps errors in `EncryptionError` and `DecryptionError`.

Compatibility tests should cover:

- existing certificate fixtures, especially `validator_a.pem` and `validator_b.pem`, load to their current expected public keys;
- manifest serializer plus `get_address_for_validator(...)` decrypts a server-shaped base64 entry;
- test helper manifest generation still produces decryptable manifests.

Packaging verification should cover:

- base client install or sync on Python 3.14 without `eciespy`;
- base client tests on Python 3.11-3.13 if available;
- base client tests on Python 3.14;
- optional `turbobt` tests remain on a Python version where the extra is installable.

### Documentation

Update client documentation to say:

- base `bt_ddos_shield_client` supports Python 3.11 through 3.14;
- the optional `turbobt` extra is currently limited by upstream dependency compatibility if the marker is used;
- the manifest encryption protocol is project-owned and intentionally compatible with the miner-side manifest producer.

Update the root README if it currently implies one uniform Python range for all client extras.

## Migration Behavior

Existing users should not need to regenerate validator shield certificates.

The local certificate PEM stores the raw Ed25519 private key. The new implementation derives the same raw public key from that private key, so certificate reconciliation should see the same public key already uploaded on chain.

Existing miner manifests remain decryptable because the wire format is unchanged. New client test helpers should continue producing manifests that current server-compatible clients can decrypt.

## Risks

- This replaces a library call with local crypto code. The risk is controlled by using only the narrow Ed25519 mode already required by the project and by pinning server/client golden vectors.
- Optional `turbobt` remains blocked on Python 3.14 unless upstream removes or fixes its `eciespy` dependency.
- If `eciespy` changes its Ed25519 implementation later, this project should not silently follow it. The project-owned contract should remain stable unless both miner and validator sides coordinate a protocol version change.

## Success Criteria

- `bt_ddos_shield_client` base package no longer depends on `eciespy` or `coincurve`.
- Base client installs under Python 3.14.
- Existing validator certificate fixtures derive the same public keys after the migration.
- Client decrypts the server golden vector.
- Server-compatible ciphertext layout remains unchanged.
- Existing client manifest/metagraph tests pass.
- Optional `turbobt` compatibility status is explicit in package metadata or documentation.
