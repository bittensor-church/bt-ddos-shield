# Chain Reader / Writer Engineering Standards Design

## Summary

Refactor `server_shield` chain access so `chain_reader` and `chain_writer` both depend on one shared Subtensor contact boundary that follows [docs/engineering-standards.md](/Users/junie/synced_p/new_bittensor_ddos_shield/docs/engineering-standards.md). The contact must remain transport-focused and expose a singleton factory seam for tests. `bittensor_wallet` remains outside that boundary: `chain_writer` continues to construct and use a real wallet, and only Subtensor communication is abstracted behind the contact.

## Goals

- Move all direct Subtensor communication for `chain_reader` and `chain_writer` behind one shared contact interface.
- Expose the contact through a module-level singleton factory function and patch that factory in tests.
- Keep blacklist filtering, domain reconciliation, manifest generation, wallet handling, and publish-if-needed decisions above the contact layer.
- Rewrite tests to exercise the public component entrypoints while mocking only the shared contact boundary.
- Keep `bittensor_wallet` as a real dependency in `chain_writer` tests and production code.

## Non-Goals

- Abstracting or wrapping `bittensor_wallet`.
- Reworking component responsibilities beyond the boundary changes required by the standards.
- Adding a second service layer above the contact.
- Changing state file formats or supervisor/runtime behavior.

## Current Problems

- `chain_writer` talks directly to `bittensor.subtensor(...)` and performs registration, neuron lookup, and publish operations without a contact boundary.
- `chain_reader` currently uses a direct chain helper path rather than a shared contact seam.
- Existing CLI tests target internal helpers such as `_run_once()` and `_publish_axon_if_needed()` instead of the public `main()` entrypoints.
- Tests currently patch internal helpers and direct functions rather than a singleton contact factory.

## Chosen Approach

Introduce one shared Subtensor contact interface for both components and keep all higher-level behavior above it.

- Add one contact module in `server_shield` that defines the abstract interface, the real implementation, and a module-level singleton factory.
- Let `chain_reader` use the contact for validator/certificate reads.
- Let `chain_writer` use the same contact for registration checks, neuron reads, and axon publish calls.
- Keep `bittensor_wallet.Wallet(...)` in `chain_writer` orchestration code so wallet identity remains outside the contact.
- Keep contact methods close to service operations, with no reconciliation or publish policy hidden inside the adapter.

This is the smallest change that satisfies the standards while keeping component behavior readable and easy to test.

## Architecture

### Shared Contact Boundary

Add a shared contact module with:

- an abstract `SubtensorContact` interface
- a real `BittensorSubtensorContact` implementation
- a module-level singleton factory function, for example `subtensor_contact()`

The singleton factory is the only patch point tests should need for Subtensor interaction.

The contact should stay transport-oriented. It may expose methods such as:

- listing validator hotkeys and raw certificate payloads for a netuid
- checking whether a hotkey is registered on a subnet
- reading the current neuron for a hotkey or UID on a subnet
- publishing axon information

Exact method names may vary, but the interface should remain narrowly scoped to external communication.

### Chain Reader Responsibilities

`chain_reader` should continue to own:

- ensuring state files exist
- reading `root_domain`, `blacklist`, and current desired-domain state
- converting contact results into `ValidatorOnChain` domain objects
- logging blacklist and invalid-certificate exclusions
- reconciling desired domains
- building and writing manifest state
- summary logging

The contact should not own:

- blacklist handling
- domain generation
- cert-validity exclusion policy beyond returning raw chain data
- manifest generation

### Chain Writer Responsibilities

`chain_writer` should continue to own:

- ensuring state files exist
- reading `axon_public_ip`
- loading config
- constructing a real `bittensor_wallet.Wallet`
- deriving the hotkey SS58 address from that wallet
- deciding whether the chain state is already up to date
- translating a failed publish result into a runtime error
- success and skip logging

The shared contact should own only the Subtensor operations needed to support those decisions.

### Wallet Boundary

`bittensor_wallet` is explicitly outside the contact boundary.

- Production code continues to instantiate a real wallet in `chain_writer`.
- Tests should also prefer a real wallet rather than mocking wallet behavior.
- The contact receives plain values derived from the wallet, such as `hotkey_ss58`, rather than owning wallet construction.

This keeps the external-service boundary aligned with the engineering standards while respecting the requested wallet constraint.

## Component Flow And Error Handling

### Chain Reader

`chain_reader.main()` remains the public entrypoint.

Execution flow:

1. Ensure state files exist.
2. Read `root_domain`.
3. If the root domain is null, log the existing skip message and return `0`.
4. Load config.
5. Read blacklist and current desired domains.
6. Use the shared contact to fetch chain validator/certificate data.
7. Convert that data into `ValidatorOnChain` values and log exclusion reasons.
8. Reconcile desired domains and write the updated desired-domain state.
9. Build and write the manifest.
10. Print the existing reconciliation summary and return `0`.

If the contact raises, the exception should bubble to `run_component(...)`, which already converts uncaught failures into exit code `1`.

### Chain Writer

`chain_writer.main()` remains the public entrypoint.

Execution flow:

1. Ensure state files exist.
2. Read `axon_public_ip`.
3. If the IP is null, log the existing skip message and return `0`.
4. Load config.
5. Construct a real wallet and derive `hotkey_ss58`.
6. Use the shared contact to check subnet registration.
7. If unregistered, log the existing skip message and return `0`.
8. Use the shared contact to read the current neuron state.
9. If neuron lookup fails or the returned neuron is null, log the existing skip message and return `0`.
10. Compare current axon info with the desired public IP and configured port.
11. If already current, log the existing up-to-date message and return `0`.
12. Ask the shared contact to publish the desired axon info.
13. If publish returns false, raise `RuntimeError("failed to set axon info")`.
14. Log publish success and return `0`.

As with `chain_reader`, unexpected contact errors should bubble up to `run_component(...)` and become exit code `1`.

## Testing Strategy

Tests should move to public-entrypoint coverage and patch only the shared contact boundary for chain interaction.

### General Rules

- Test `main()` rather than `_run_once()` or `_publish_axon_if_needed()`.
- Use real state-store files in temporary directories.
- Patch the shared singleton contact factory rather than internal helper functions.
- Use a real wallet in `chain_writer` tests and patch as little as possible.
- Keep subprocess module-execution tests only if they still add coverage not already provided by `main()` tests.

### Chain Reader Coverage

Required public tests:

- `main()` returns `0` and leaves desired-domain state unchanged when `root_domain` is null.
- `main()` reconciles desired domains and manifest content correctly when the patched contact returns a mixed validator/certificate view.
- `main()` returns `1` when the contact raises unexpectedly through the runtime wrapper.

These tests should assert final state files and externally visible log output rather than private helper calls.

### Chain Writer Coverage

Required public tests:

- `main()` returns `0` and logs the skip message when `axon_public_ip` is null.
- `main()` returns `0` and logs “already up to date” when the patched contact reports matching axon state.
- `main()` returns `0` and logs publish success when the patched contact reports stale axon state and accepts the publish call.
- `main()` returns `1` when the contact raises or when publish returns false.

These tests should construct a real wallet, derive the real hotkey, and patch only the shared contact factory to provide deterministic chain behavior.

## File-Level Changes

- Add: `server_shield/src/server_shield/subtensor_contact.py`
- Modify: `server_shield/src/server_shield/chain_reader/chain.py`
- Modify: `server_shield/src/server_shield/chain_reader/cli.py`
- Modify: `server_shield/src/server_shield/chain_writer/cli.py`
- Modify: `server_shield/tests/chain_reader/test_cli.py`
- Modify: `server_shield/tests/chain_writer/test_cli.py`

Exact file names may shift slightly if a better local module location is more consistent, but the contact boundary should remain shared and singleton-backed.

## Risks

- A contact interface that is too high-level could accidentally absorb application policy.
- A contact interface that is too low-level could leave direct SDK calls scattered in callers.
- `chain_writer` tests will need a deterministic way to construct a real wallet without overcomplicating fixture setup.
- Public-entrypoint tests may need small adjustments to avoid duplicating subprocess smoke coverage.

## Acceptance Criteria

- No `chain_reader` or `chain_writer` application code talks directly to `bittensor.subtensor(...)`.
- Both components depend on one shared Subtensor contact interface exposed through a singleton factory.
- `bittensor_wallet` remains outside the contact boundary.
- Reconciliation, blacklist handling, manifest generation, and publish-if-needed decisions remain above the contact layer.
- Tests patch the shared contact factory instead of private helpers for chain behavior.
- `chain_writer` tests use a real wallet and keep wallet mocking to a minimum.
- Public tests verify final behavior through `main()` and externally visible side effects.
