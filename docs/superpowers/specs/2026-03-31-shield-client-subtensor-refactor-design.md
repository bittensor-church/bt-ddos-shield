# Shield Client / Subtensor Refactor Design

## Summary

Refactor `bt_ddos_shield_client` so certificate reconciliation happens during neuron fetching rather than during `ShieldClient` startup. `ShieldClient` should stop acting as a context manager and stop depending on `subtensor`. The chain contact layer should remain a thin adapter over subtensor communication, while a separate reconciliation layer should keep a TTL-cached answer to a single question: does the on-chain certificate match the current local certificate?

## Goals

- Remove chain-specific responsibilities from `ShieldClient`.
- Move own-certificate comparison and upload orchestration out of `ShieldClient` and into a dedicated reconciliation layer.
- Perform certificate reconciliation on the neuron-fetch path.
- Expose a public `ShieldedSubnetReference.from_bittensor(...)` constructor.
- Reuse a thread pool for `ShieldMetagraph.sync()` async bridging instead of spawning throwaway threads.

## Non-Goals

- Adding or expanding test coverage in this change.
- Changing manifest fetching or shield address resolution behavior beyond the refactor needed for certificate handling.
- Introducing new public upload/sync orchestration objects outside the existing client/contact/metagraph layers.

## Current Problems

- `ShieldClient` owns both local certificate state and chain reconciliation logic.
- `ShieldClient` uploads certificates during async startup, which is detached from the actual neuron-fetching workflow.
- `ShieldClient` needs a `subtensor`-like object even though its core job is manifest resolution.
- `ShieldMetagraph.sync()` bridges async work by creating a fresh thread per `run_async_in_thread` call.
- There is no reusable public constructor for wrapping an existing `turbobt.Bittensor` instance in a `ShieldedSubnetReference`.

## Chosen Approach

Keep the contact layer thin and introduce a dedicated certificate reconciliation layer.

- `ShieldClient` becomes a plain helper that loads or creates the local certificate and resolves shield addresses from manifests.
- `BittensorSubtensorContact` and `TurboBittensorSubtensorContact` remain thin adapters responsible only for fetching the current on-chain certificate and uploading a certificate payload.
- A separate reconciliation object owns TTL state, comparison policy, and the decision to upload when needed.
- `ShieldMetagraph.sync()` and `ShieldedSubnetReference.list_neurons()` trigger certificate reconciliation as part of neuron fetching.
- `ShieldedSubnetReference.from_bittensor(...)` becomes the public construction API for an already-created `turbobt.Bittensor`.

This keeps manifest resolution isolated in `ShieldClient`, keeps chain transport code mockable and minimal, and keeps reconciliation policy in one reusable place.

## Architecture

### ShieldClient

`ShieldClient` should:

- accept only the wallet-independent runtime configuration it actually needs:
  - `certificate_path`
  - manifest timeout / serializer / encryption dependencies
- load the local certificate on construction, creating and persisting one if the file is missing
- expose the local certificate and validator-private-key-backed shield address resolution

`ShieldClient` should not:

- implement `__aenter__` / `__aexit__`
- accept or store a subtensor/contact object
- perform certificate upload or chain reads

### Contact Layer

Each contact implementation should remain a thin async adapter over chain communication. It should expose only the minimum operations needed by higher layers, with behavior equivalent to:

- `get_hotkey() -> str`
- `get_own_public_key() -> PublicKey | None`
- `upload_public_key(public_key: PublicKey, algorithm: CertificateAlgorithmEnum) -> None`

The contact layer should not own:

- TTL state
- certificate comparison policy
- retry / reconciliation orchestration
- neuron-fetch workflow decisions

This keeps it trivial to replace with mock implementations in tests.

### Certificate Reconciliation Layer

Add a separate reconciliation layer, for example a focused helper/service used by `ShieldMetagraph` and the shielded turbobt path.

This layer should expose a public async method with behavior equivalent to:

- `ensure_own_certificate_matches() -> None`

The reconciler owns:

1. Fetching the current on-chain public key through the contact adapter.
2. Comparing it to the current local certificate public key from `ShieldClient`.
3. Returning immediately when a non-expired TTL cache already says the on-chain cert matches this exact local public key.
4. Uploading the local certificate through the contact adapter if the on-chain value is missing or different.
5. Updating the TTL cache after a successful comparison or successful upload.

The TTL cache stores only one semantic fact:

- whether the on-chain certificate matches the current local certificate

The cached match result must be tied to the local public key used to establish it. If the local certificate changes, the cached answer must no longer be treated as valid even if the TTL has not expired.

### Failure Semantics

Certificate reconciliation is part of neuron fetching in this design.

- If reading the current on-chain certificate fails, neuron fetching must fail.
- If uploading the local certificate fails, neuron fetching must fail.
- If the reconciler determines the on-chain certificate already matches the local one, neuron fetching proceeds normally.

There is no best-effort fallback for certificate read/write failures in this refactor.

### ShieldMetagraph

`ShieldMetagraph` should:

- construct a `ShieldClient` without any subtensor/contact dependency
- construct the appropriate contact object separately
- construct the reconciliation layer separately
- call the reconciliation layer during `sync()`
- reuse a dedicated thread pool when calling `run_async_in_thread` from sync-time code

`ShieldMetagraph.__init__()` should stop performing certificate upload work implicitly. The only certificate-related construction work left there should be local certificate loading via `ShieldClient`.

### Shielded TurboBTT

`ShieldedBittensor` should be updated to align with the same split:

- keep a `ShieldClient`
- keep a contact object
- keep a reconciliation object
- have neuron-fetching paths call reconciliation before shield-address rewriting

Add a public constructor:

- `ShieldedSubnetReference.from_bittensor(bittensor, netuid, *, wallet, ddos_shield_options=None)`

This constructor should build a shield-aware subnet reference from an existing `turbobt.Bittensor` instance without requiring callers to instantiate `ShieldedBittensor`.

The constructor should reuse the same underlying pieces as `ShieldedBittensor` so the behavior stays consistent.

## Async Bridging

`run_async_in_thread` should be extended so callers may supply a reusable executor. When there is no running loop, the function can continue to use `asyncio.run(...)` directly. When there is already a running loop, the helper should dispatch the coroutine execution through the provided executor instead of creating a brand-new thread object for every call.

`ShieldMetagraph` should own a reusable thread pool dedicated to sync-time async bridging. `sync()` should use that pool for:

- certificate reconciliation
- manifest fetch / shield address resolution work

The pool should be an internal implementation detail of `ShieldMetagraph`.

## File-Level Changes

- `bt_ddos_shield_client/bt_ddos_shield_client/client.py`
  - remove context manager methods
  - remove subtensor/contact dependency and upload logic
  - keep local certificate lifecycle and manifest resolution
- `bt_ddos_shield_client/bt_ddos_shield_client/shield_metagraph.py`
  - wire contact + reconciliation usage inside `sync()`
  - keep `BittensorSubtensorContact` transport-only
  - add reusable executor ownership for sync-time async bridging
- `bt_ddos_shield_client/bt_ddos_shield_client/certificate_reconciliation.py`
  - add a focused reconciliation module/class that owns TTL state and certificate matching logic
- `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/shielded_bittensor.py`
  - use the new reconciliation layer with `TurboBittensorSubtensorContact`
  - remove `ShieldClient` context-manager usage
  - add `ShieldedSubnetReference.from_bittensor(...)`
- `bt_ddos_shield_client/bt_ddos_shield_client/internal.py`
  - allow `run_async_in_thread` to use a caller-provided executor

## Testing Strategy

No test additions or refactors are planned in this change. Existing tests may need targeted updates only if required to keep the suite passing after the API changes, but new coverage is explicitly out of scope for this task.

## Risks

- Moving certificate reconciliation onto neuron-fetch paths will make certificate read/write failures surface more often and more directly.
- The TTL cache must be keyed tightly enough to avoid stale “match” results after local certificate rotation.
- The reusable executor must not change sync behavior or swallow exceptions from async work.

## Acceptance Criteria

- `ShieldClient` has no context-manager behavior and no subtensor/contact dependency.
- Contact objects remain thin transport adapters.
- Certificate reconciliation lives in a separate reusable layer for both bittensor and turbobt integrations.
- Neuron fetching fails if certificate read or write fails.
- Reconciliation-layer TTL caching tracks whether the on-chain cert matches the current local cert.
- `ShieldedSubnetReference.from_bittensor(...)` is public.
- `ShieldMetagraph.sync()` uses a reusable thread pool for async bridging.
