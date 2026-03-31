# Shield Contact Mocks and Public API Tests Design

## Summary

Add production-package mock implementations for the shield contact abstractions so downstream projects can use them in their own tests, and add public-API-focused tests in this repository that patch only the contact factory functions plus HTTP responses. The mock contacts must be declarative, mutable within a single test, and fully instrumented so tests can assert reconciliation and upload behavior, including on-chain/local public-key desynchronization and TTL behavior. On top of that, provide a higher-level fixture-style helper layer for downstream projects that hides contact mocking and manifest-response setup behind declarative helpers.

## Goals

- Provide production-package mock implementations of `AbstractBittensorSubtensorContact` and `AbstractTurboBittensorSubtensorContact`.
- Make the mocks declarative and easy to configure in domain terms rather than subtensor transport terms.
- Make the mocks mutable during a single test so chain state and upload behavior can change between calls.
- Record all contact calls in a structured way for direct assertions in tests.
- Expand tests to cover public behavior through `ShieldMetagraph`, `ShieldedBittensor`, and `ShieldedSubnetReference.from_bittensor(...)`.
- Provide downstream-facing fixture-style helpers that hide contact patching and manifest mocking under the hood.
- Use committed real certificate/key fixtures and clock control for TTL coverage.

## Non-Goals

- Reworking the production reconciliation semantics beyond what is required to make them testable.
- Adding direct tests for private helpers when the same behavior can be verified through public APIs.
- Replacing HTTP stubbing with a full manifest test server.

## Current Problems

- The production package exposes abstract contact types and real contact implementations, but it does not expose reusable mock contacts for downstream tests.
- The existing tests patch lower-level internals and outdated contact factory names instead of exercising the current public surface.
- There is no committed fixture set of real certificates/keys for deterministic tests.
- TTL behavior is not covered with explicit clock control.
- The current fake contact helper is too narrow for reconciliation and mutable state testing.

## Chosen Approach

Add production-package mock contacts with declarative scenario APIs and structured call recording.

- `MockBittensorSubtensorContact` will implement `AbstractBittensorSubtensorContact`.
- `MockTurboBittensorSubtensorContact` will implement `AbstractTurboBittensorSubtensorContact`.
- Both mock classes will live in the production package beside the existing contact abstractions so downstream projects can import them directly.
- Tests in this repository will patch only `bittensor_subtensor_contact()` / `turbo_bittensor_subtensor_contact()` and HTTP responses.
- A fixture-style helper layer will sit on top of those mocks for downstream consumers that do not want to handcraft HTTP manifest stubs or contact state in every test.
- Tests will use committed fixture certificates and keys from the repository.
- TTL coverage will use `freezegun` or an equivalent time-freezing library.

This keeps the low-level mocking surface aligned with the actual public extension point, while also offering a higher-level ergonomic test layer for downstream projects.

## Architecture

### Mock Contact Semantics

The mock contacts should model domain outcomes, not subtensor protocol details.

They should support declarative setup such as:

- configuring the current metagraph sync result
- configuring the current turbobt neuron listing result
- configuring the currently visible on-chain public key
- configuring upload behavior, including success and failure

The configuration must be mutable during a single test. A test should be able to:

1. set the on-chain cert to a mismatched value
2. call the public API and assert upload happened
3. update the on-chain cert to match
4. call the public API again and assert the changed behavior

This mutable fake-chain behavior is required for reconciliation and TTL testing.

### Mock Contact API

The public mock surface should stay small and explicit.

For the bittensor side, expected methods include:

- `set_metagraph_sync(neurons=[...])`
- `set_own_certificate(public_key=...)`
- `set_upload_behavior(exception=None)`
- `reset_calls()`

For the turbobt side, expected methods include:

- `set_neuron_listing(neurons=[...])`
- `set_own_certificate(public_key=...)`
- `set_upload_behavior(exception=None)`
- `reset_calls()`

Exact method names may vary slightly, but the semantics must remain declarative and mutable.

### Call Recording

Both mock classes should keep a structured call log for assertions.

Each record should contain at least:

- method name
- key arguments relevant to the behavior under test
- an ordering signal, either append order or explicit sequence number

Examples of useful recorded fields:

- `method="sync_metagraph"`
- `method="list_neurons"`
- `hotkey`
- `netuid`
- `public_key`
- listed neuron hotkeys

The call log must be directly accessible to tests without additional patching.

### Factory Integration

Tests should patch:

- `bt_ddos_shield_client.shield_metagraph.bittensor_subtensor_contact`
- `bt_ddos_shield_client.shielded_turbobt.shielded_bittensor.turbo_bittensor_subtensor_contact`

Those patched factory functions should return the mutable production-package mocks.

The tests should not patch:

- reconciliation internals
- `ShieldClient`
- contact instance methods directly
- upstream `Metagraph.sync()` / `SubnetReference.list_neurons()` implementations

### Downstream Fixture-Style Helper Layer

On top of the low-level mock contacts, add a higher-level helper layer intended for downstream project tests.

This layer should:

- expose declarative helpers for preparing validators, miners, shielded endpoints, and on-chain certificate state
- hide direct HTTP manifest mocking from downstream tests
- hide direct contact factory patching from downstream tests
- still avoid any real subtensor communication

The downstream helper API should remain outcome-focused. The caller should be able to express intent like:

- prepare a network where neurons A and C are shielded and B is not
- prepare a validator whose local cert mismatches the on-chain cert
- prepare a manifest response for a given miner without manually crafting encrypted payloads

This helper layer may patch contact factories and install HTTP stubs internally, but that wiring should be invisible to downstream test authors.

### Fixture Layout

Commit real certificate/key fixture material under:

- `bt_ddos_shield_client/tests/fixtures/certs/`

The fixture set should contain multiple deterministic keypairs so tests can cover:

- matching on-chain/local public keys
- mismatched on-chain/local public keys
- encrypted manifests for specific validator keys

Tests should load these fixtures through small helpers rather than duplicating path logic.

### TTL Testing

TTL behavior must be tested with clock control using `freezegun` or an equivalent tool.

The tests should prove:

- a mismatched or missing on-chain cert triggers upload on first public call
- a subsequent public call inside the TTL window skips repeated reconciliation when the local cert is unchanged
- advancing time beyond the TTL causes reconciliation to re-read chain state
- changing the local cert invalidates the cached match state even before TTL expiry

## Test Strategy

All new tests should touch the public API only.

### Public Surfaces Under Test

- `ShieldMetagraph(...)` followed by `sync()`
- `ShieldedBittensor(...).subnet(...).list_neurons()`
- `ShieldedSubnetReference.from_bittensor(...).list_neurons()`

### Allowed Test Seams

- patch the contact factory functions
- stub HTTP manifest responses
- freeze or advance time for TTL checks
- use committed certificate/key fixtures

Repository tests should use mock contacts plus mocked HTTP responses directly. They should not introduce a second declarative “shielded/unshielded neuron” abstraction at the repository test level.

### Required Coverage

For `ShieldMetagraph`:

- missing on-chain cert uploads local cert
- mismatched on-chain cert uploads local cert
- matching on-chain cert skips upload
- mutable mock state changes behavior mid-test
- TTL suppresses repeated reconciliation inside the window
- TTL expiry re-enables reconciliation
- mixed shielded/unshielded miners resolve correctly through concurrent manifest fetching
- read failure surfaces through the public API
- upload failure surfaces through the public API

For the turbobt path:

- missing on-chain cert uploads local cert
- mismatched on-chain cert uploads local cert
- matching on-chain cert skips upload
- mutable mock state changes behavior mid-test
- TTL behavior matches the metagraph path
- mixed shielded/unshielded neurons resolve correctly through concurrent manifest fetching
- `ShieldedSubnetReference.from_bittensor(...)` works end-to-end
- read failure surfaces through the public API
- upload failure surfaces through the public API

For the downstream fixture-style helper layer:

- helper-prepared mixed shielded/unshielded scenarios produce the correct public API results
- helper-prepared certificate mismatch scenarios trigger the expected public API behavior
- helper-prepared TTL scenarios produce the correct public API behavior when time is frozen and advanced

These tests should assert final public behavior only. They should not assert helper internals, call logs, or low-level mocking details.

### Testing Style

- Prefer real certificate fixtures over synthetic placeholder values.
- Prefer asserting observable behavior plus contact call logs over internal state.
- Keep the only external I/O stub as HTTP manifest responses.
- Keep mocking minimal and localized to the contact factory functions.
- For the downstream fixture-style helper layer, assert public outcomes only and avoid granular internal assertions.

## File-Level Changes

- `bt_ddos_shield_client/bt_ddos_shield_client/contacts.py`
  - add `MockBittensorSubtensorContact`
- `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/contacts.py`
  - add `MockTurboBittensorSubtensorContact`
- `bt_ddos_shield_client/bt_ddos_shield_client/testing.py`
  - add downstream-facing fixture-style helpers that wrap mock contacts and manifest setup
- `bt_ddos_shield_client/tests/fixtures/certs/`
  - add committed certificate/key fixtures
- `bt_ddos_shield_client/tests/...`
  - rewrite tests to use public APIs, patched contact factories, HTTP stubs, and time freezing
  - add public-API tests for the fixture-style helper layer
- `bt_ddos_shield_client/pyproject.toml`
  - add `freezegun` to the test dependency group if it is not already present

## Risks

- Over-designing the mock API could create a second abstraction layer that diverges from real usage.
- Reusing mutable mock instances across tests would create state leakage unless tests instantiate fresh mocks.
- Fixture sprawl could make the test corpus hard to read if there are too many committed keypairs.
- TTL tests can become flaky if they depend on real time rather than frozen time.

## Acceptance Criteria

- Production-package mock contacts exist for both abstract contact types.
- Mock contacts can be reconfigured mid-test and expose a structured call log.
- Repository tests patch only the contact factory functions plus HTTP responses.
- Repository tests use mock contacts plus HTTP stubs directly, without a repository-only declarative shielded/unshielded abstraction.
- Downstream-facing fixture-style helpers exist and hide contact patching plus manifest setup internally.
- Tests use committed real certificate/key fixtures.
- TTL behavior is covered with `freezegun` or an equivalent clock-freezing tool.
- Public APIs are the primary test surface for reconciliation and shield-address behavior.
