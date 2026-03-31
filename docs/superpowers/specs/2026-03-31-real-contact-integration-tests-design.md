# Real Contact Integration Tests Design

## Summary

Add a dedicated pytest integration layer for the real `BittensorSubtensorContact` and `TurboBittensorSubtensorContact` implementations in the client library test suite. These tests will exercise only the public contact methods against a local subtensor environment that the tests themselves create and bootstrap on demand, will live in separate test files, and will be excluded from default local test runs through pytest marks while remaining suitable for CI execution. Update the repository engineering standards so this rule is explicit for all future external-service adapters.

## Goals

- Add real-integration tests for the real contact implementations.
- Limit the test surface to the public methods of the contact classes.
- Keep these tests separate from the lighter public-API tests for wrappers such as `ShieldMetagraph` and `ShieldedBittensor`.
- Make the tests opt-in locally through pytest marks.
- Make the tests practical for CI to run.
- Update the repo-wide engineering standards so real adapter implementations must have separate real-service tests.
- Limit this work to the client library test suite for now.

## Non-Goals

- Re-testing private helper methods of the contact implementations.
- Replacing the existing public-API tests that use mock contacts and HTTP stubs.
- Building a generic integration harness for every service in the repository.
- Changing server-side or non-client test infrastructure as part of this work.
- Turning these tests into full end-to-end product tests beyond the contact boundary.

## Current Problems

- The repository now has strong mock-based public-API tests, but the real contact implementations themselves are not tested against a real local chain.
- There is no repo-standard rule that real external-service adapter implementations must have their own real-service tests.
- Without real-adapter tests, protocol drift in the contact layer could go undetected while mock-based tests still pass.

## Chosen Approach

Add a separate integration-marked pytest layer under the client test package for the real contact implementations.

- Tests will live in dedicated files under `bt_ddos_shield_client/tests/contacts/`.
- The tests will use shared fixtures that create and bootstrap a local subtensor environment on demand.
- The bootstrap sequence may be informed by the existing manual workflow, but the test suite must own its own definitions and must not depend on files under `manual_tests/`.
- The tests will be marked with a dedicated pytest marker such as `subtensor_integration`.
- Local default test runs will exclude that mark.
- CI can opt in and run the marked tests after standing up the local chain environment.

The local chain lifecycle should be managed programmatically from the test suite, using a Docker-management library appropriate for pytest integration. A library in the `testcontainers` family is the preferred default because it keeps environment startup and teardown inside the tests instead of requiring out-of-band orchestration.

This preserves a clean split:

- lightweight public-API tests use mock contacts and HTTP stubs
- real contact integration tests validate the adapter implementation against the actual service

## Architecture

### Test Placement

Create a dedicated folder:

- `bt_ddos_shield_client/tests/contacts/`

Place one file per real contact implementation:

- `test_bittensor_subtensor_contact.py`
- `test_turbo_bittensor_subtensor_contact.py`

This separation is important. These tests are about adapter correctness, not wrapper behavior.

### Marking and Execution

Add a dedicated pytest marker:

- `subtensor_integration`

Behavior:

- excluded from default local test runs
- runnable explicitly with `pytest -m subtensor_integration`
- suitable for a dedicated CI job

The default test configuration should make it hard to run these accidentally during the lightweight local loop, while keeping the command to run them explicit and simple.

### Environment Assumptions

These tests should create a local chain setup inside the client library test suite:

- start a local subtensor container
- create wallets for validator and miner
- create a subnet
- register validator and miner on that subnet
- start the subnet
- ensure the test wallets have sufficient funds for those operations

The tests should not repeat the entire environment bootstrap in every individual test function. That would be too heavy and too slow.

Instead, shared fixtures should:

- create the local subtensor container once for the integration test session
- bootstrap chain state once for the integration test session
- expose the connected clients, wallets, and netuid to the tests
- skip cleanly with a precise message if Docker or the required local tooling is unavailable

The integration tests must not import, shell out to, or otherwise depend on files under `manual_tests/`. Any container definition, bootstrap commands, or helper code needed by the client library tests should live under `bt_ddos_shield_client/tests/contacts/` or another client-library-owned test location.

### Fixture Responsibilities

Shared fixtures should provide:

- a managed local subtensor container lifecycle
- `subtensor`
- `turbobt_bittensor`
- `validator_wallet`
- `miner_wallet`
- `netuid`
- any small helper needed to ensure the validator has an on-chain axon before certificate upload
- any small helper needed to wait for finalization or read-after-write consistency when asserting chain updates

These fixtures should stay narrowly focused on contact-test setup, not become a general-purpose chain testing framework.

The fixture layer should be responsible for:

- starting the chosen subtensor localnet image directly, or from a client-library-owned test definition
- creating wallets and funding them
- creating and starting the test subnet
- registering the validator and miner

The fixtures should prefer a session-scoped bootstrap and function-scoped test assertions on top of that shared environment.

### Test Scope Per Contact

For `BittensorSubtensorContact`:

- `sync_metagraph(...)`
- `get_own_public_key(...)` before upload
- `upload_public_key(...)`
- `get_own_public_key(...)` after upload

For `TurboBittensorSubtensorContact`:

- `list_neurons(...)`
- `get_own_public_key(...)` before upload
- `upload_public_key(...)`
- `get_own_public_key(...)` after upload

The tests should assert meaningful behavior only:

- neuron listing contains expected registered hotkeys
- sync/list calls return or populate real neurons
- missing certificate returns `None`
- uploaded certificate becomes readable afterward

The tests may use the real chain state as their setup mechanism, but they still must not test private methods or internal helper details.

### What Not To Test

These tests must not:

- target private helper methods
- assert trivial internal return shapes
- retest higher-level reconciliation logic already covered through public wrapper tests
- overfit to chain internals beyond what the public contact method promises

## Engineering Standards Update

Update `docs/engineering-standards.md` with an explicit rule:

- every real external-service contact/adapter must have separate tests for the real implementation
- those tests must live in dedicated files
- they must exercise only public adapter methods
- they may be heavy integration tests
- they should be opt-in locally and expected in CI
- when practical, those tests should create their own disposable external-service environment instead of relying on operator-prepared local state
- those tests must not reach into unrelated manual-test directories for runtime dependencies

This complements the existing rule that public wrapper behavior should be tested through public APIs with mocked external boundaries.

Both are needed:

- mock-boundary public tests for application behavior
- real-adapter integration tests for protocol correctness

## Test Strategy

### Bittensor Contact Tests

Expected coverage:

1. `sync_metagraph(...)` populates a passed `Metagraph` with real neurons from the local subnet.
2. `get_own_public_key(...)` returns `None` before the validator cert is uploaded, or returns the currently configured chain value if already present.
3. `upload_public_key(...)` writes the validator certificate to chain.
4. `get_own_public_key(...)` returns the uploaded key after upload.

The test should use a real generated or committed certificate public key value for upload.
The session bootstrap should ensure the validator has an on-chain axon state suitable for `serve_extrinsic`.

### Turbobt Contact Tests

Expected coverage:

1. `list_neurons(...)` returns a real neuron list for the local subnet.
2. `get_own_public_key(...)` returns `None` before upload, or the current chain value if already present.
3. `upload_public_key(...)` writes the validator certificate to chain.
4. `get_own_public_key(...)` returns the uploaded key after upload.

### Isolation and Idempotence

These tests will touch shared disposable local-chain state. The design should therefore prefer:

- reading the current state first
- uploading a known test public key value
- asserting the final readable value

They do not need to restore the previous certificate afterward if the environment is created by the tests and torn down after the session. If CI requires stronger cleanup or per-test isolation, that can be added in implementation.

## File-Level Changes

- `docs/engineering-standards.md`
  - add rules for real contact integration tests
- `bt_ddos_shield_client/pyproject.toml`
  - add pytest marker configuration and default exclusion for heavy integration tests
  - add the Docker-management dependency and any supporting test dependency needed for bootstrap
- `bt_ddos_shield_client/tests/contacts/conftest.py`
  - shared local-chain container/bootstrap fixtures and environment validation
- `bt_ddos_shield_client/tests/contacts/local_subtensor.py`
  - client-library-owned container/bootstrap helpers copied or rewritten for pytest use
- `bt_ddos_shield_client/tests/contacts/test_bittensor_subtensor_contact.py`
  - real tests for `BittensorSubtensorContact`
- `bt_ddos_shield_client/tests/contacts/test_turbo_bittensor_subtensor_contact.py`
  - real tests for `TurboBittensorSubtensorContact`

## Risks

- Docker availability or container startup issues could make these tests fail before any assertions unless fixture errors are precise.
- Local chain bootstrap drift could make these tests fail unclearly if the session setup is not verified step by step.
- Shared mutable chain state can make tests flaky if they assume a pristine environment after another test mutates it.
- Running these by default would slow local development significantly.
- Turbobt and bittensor clients may differ subtly in their view of a recently updated chain state, so tests may need careful sequencing and finalization waits.

## Acceptance Criteria

- Dedicated real-contact test files exist for both contact implementations.
- The tests exercise only public contact methods.
- The tests run against a real local subtensor-backed environment.
- The tests create and tear down that environment themselves.
- The tests do not depend on files under `manual_tests/`.
- The tests are marked and excluded from default local pytest runs.
- The tests can be explicitly selected by mark.
- `docs/engineering-standards.md` explicitly requires this test style for real external-service adapters.
