# Engineering Standards

This document defines repository-wide engineering rules for service boundaries, mocks, singletons, and tests.

These rules apply to both humans and agents.

## External Service Boundaries

### Required

- Put communication with external control-plane services behind a thin adapter layer.
- In this repository, Subtensor or Bittensor clients are examples of services that belong behind a `Contact` implementation.
- Keep `Contact` implementations transport-oriented. They should translate calls and data, not own higher-level policy.
- Put reconciliation, caching, orchestration, and business rules above the contact layer.
- Make callers depend on the contact boundary, not on direct SDK calls.

### Forbidden

- Do not scatter direct calls to Subtensor, Bittensor, or similar external services throughout application code.
- Do not put TTL state, reconciliation policy, or business rules inside a contact adapter.
- Do not make a contact responsible for unrelated convenience behavior just because it already talks to the service.

## Contact Layer Rules

### Required

- A contact must expose the smallest interface that still covers all external communication needed by the package.
- If a package feature talks to an external service, that communication must be reachable through the contact boundary.
- Real contacts and test contacts must satisfy the same abstract interface.
- Contact methods should be named in domain terms, but stay close to the underlying service operations.

### Forbidden

- Do not add methods to a contact that are really local application concerns.
- Do not require tests to mock upstream SDK internals when they can mock the contact instead.
- Do not call `super()` implementations directly from high-level wrappers if the same operation is supposed to be mocked through a contact.

## Mock Contact Rules

### Required

- Put reusable mock contacts in production code when downstream projects are expected to use them in their own tests.
- Make mock contacts implement the same abstract contact interface as the real contact.
- Keep mock contacts declarative.
- Allow mock contacts to be mutated during a single test.
- Record calls in a structured way so tests can assert externally visible behavior.
- Drive test scenarios by configuring the mock contact, not by patching internal helpers below the public seam.
- Cover non-happy-path behavior through the mock contact, not only happy paths.
- When a contact method returns collections or other aggregate results, include mixed-scenario tests that combine valid items with invalid, missing, stale, or otherwise problematic items in the same case so the test proves one bad item does not break the whole result.
- Configure mocks in domain terms:
  - current listed items or records
  - current synchronized adapter result
  - current externally stored state
  - upload outcome

### Forbidden

- Do not make downstream tests rebuild low-level transport responses when a mock contact can express the same scenario directly.
- Do not make mocks immutable snapshots if the production behavior depends on changing external state.
- Do not hide call history from tests.
- Do not use ad hoc fakes that bypass the package's abstract contact interface when a production mock contact exists or should exist.

## Singleton Rules

### Required

- Expose contact access through module-level singleton factory functions.
- Depend on the factory function at call sites.
- Patch the factory function in tests.
- Keep singleton services stateless where possible.

### Preferred Pattern

```python
_contact_instance: AbstractContact | None = None


def contact() -> AbstractContact:
    global _contact_instance
    if _contact_instance is None:
        _contact_instance = RealContact()
    return _contact_instance
```

### Forbidden

- Do not instantiate real contacts ad hoc throughout the codebase.
- Do not make tests patch deep internals when patching the singleton factory is enough.

## Public API Testing Rules

### Required

- Test behavior through public APIs.
- Mock only true external boundaries that are expensive or inappropriate to run in-process.
- In this repository, examples usually include:
  - patching contact singleton factory functions
  - stubbing HTTP responses with `aioresponses`
- When a contact boundary exists, patch the contact factory and configure a concrete mock contact instance that implements the abstract contact.
- Keep internal helpers real in public-API tests when practical, including manifest builders, reconciliation helpers, parsers, and crypto helpers.
- Public-API tests that use mock contacts should cover both successful and unsuccessful external data in the same suite, and should prefer mixed-result cases for collection reads when that is how production behavior is exercised.
- Use real certificates, keys, and realistic domain objects in tests when practical.
- Prefer asserting final public outcomes and externally visible side effects.

### Forbidden

- Do not write tests that target private or internal helper methods unless there is no reasonable public path.
- Do not write tests whose only value is checking trivial internal shapes, such as:
  - `assert isinstance(str, some_internal_method(...))`
  - direct testing of parsing helpers that are already covered through public behavior
- Do not mock internal methods just to force code through a branch when a public API test can cover it.
- Do not patch internal helper functions below the selected public seam, such as manifest builders, reconciliation helpers, parsing helpers, or similar domain logic, when a mock contact or other true external-boundary stub can express the scenario.
- Do not replace real domain objects with placeholder objects if constructing the real object is practical.

## Real Adapter Integration Testing Rules

### Required

- Every real external-service adapter must have dedicated real-implementation tests. This is mandatory, not optional polish.
- Every real external-service adapter must have separate tests for the real implementation.
- Those tests must live in dedicated files.
- Those tests must exercise only public adapter methods.
- Those tests may be heavy integration tests.
- Those tests should be opt-in locally and expected in CI.
- When practical, those tests should create their own disposable external-service environment. Follow the setup rules below rather than relying on accidental fixture state.
- Those tests must not depend on unrelated manual-test directories for runtime dependencies.

### Forbidden

- Do not rely only on mocks for real adapter correctness.
- Do not treat mock-contact coverage as a substitute for real adapter integration coverage.
- Do not test private adapter helpers in place of real adapter behavior.
- Do not hide real adapter tests inside unrelated wrapper test modules.

## Real Integration Environment Setup Rules

### Required

- Shape real integration fixtures around explicit domain roles, not around misleading names or incidental chain state.
- Prefer fixtures that make roles concrete and inspectable, for example:
  - validator A
  - validator B
  - registered non-validator
  - owner or subnet bootstrap actor
- Use real artifacts in those environments when practical, including real certificates, keys, wallets, and realistic payloads.
- Assert the intended environment topology during setup against the real service state, not against assumptions. Examples include:
  - which actors are registered
  - which actors have validator permits
  - which actors have stake
  - which actors have no published external record yet
- In collection-oriented real adapter tests, prefer composite scenarios that exercise multiple states in sequence or in one case, including mixed healthy and problematic records.
- When testing collection reads, make expected outputs include unaffected valid records as well as problematic records so the test proves partial failure does not poison the whole result.
- Include concrete assertions for actual returned values, not only presence checks.
- Dump returned objects to stable dict or list-of-dicts forms when that makes the full behavior easier to assert in one comparison.
- If a stateful real environment causes transaction collisions, nonce reuse, or other cross-test interference, isolate the affected test in its own disposable environment instead of weakening assertions.
- If the real service has constraints that make one mixed-state transition impossible in-place, use a second fresh real environment inside the same test or test module rather than replacing the scenario with mocks.

### Forbidden

- Do not rely on fixture names like `miner`, `validator`, or `owner` unless the setup proves those roles through actual external state.
- Do not assume a registered actor is or is not a validator without asserting the real permit or equivalent service-side role bit.
- Do not use semantically misleading fixtures to stand in for a role they do not actually have.
- Do not overfit integration tests to happy-path topologies.
- Do not assert only that a record exists when the actual returned payload can be asserted concretely.
- Do not silently ignore extra actors returned by the real service; either account for them explicitly in assertions or reshape the fixture so the topology is unambiguous.
- Do not keep reusing a shared real environment for stateful write tests once it is clear that prior writes interfere with later assertions.

## Stateful Infrastructure Exception

### Required

- For stateful infrastructure such as PostgreSQL or Redis, prefer running a real test instance over mocking the client protocol.
- Use lightweight real instances when they are cheap to start in tests.
- Reserve mocking for cases where a real instance is not practical.

### Forbidden

- Do not treat databases like HTTP APIs for unit-style response mocking if the test can run a real database instead.
- Do not over-mock persistence boundaries in ways that make behavior diverge from production semantics.

## Good And Bad Patterns

### Good

- High-level code calls a contact factory or adapter accessor instead of reaching into a service SDK directly.
- Tests patch that boundary, return a concrete mock contact implementing the abstract interface, and drive public APIs rather than internal helpers.
- Collection-oriented tests mix healthy and unhealthy external items in one case to prove the component keeps valid results while excluding or handling bad ones correctly.
- HTTP-backed behavior is exercised with realistic stubs and real cryptographic material when practical.
- Mock contacts are reconfigured mid-test to simulate on-chain state changes.
- Real contact implementations have dedicated integration tests in their own test modules.
- Real integration fixtures prove their role topology against actual service state before the assertions that depend on it.

### Bad

- High-level code talks directly to Subtensor or Bittensor SDK objects outside the contact layer.
- Tests patch private helpers instead of the external boundary.
- Tests cover only fully happy-path contact data and never exercise mixed success/failure collection results.
- Tests assert internal helper return types instead of public behavior.
- Tests use placeholder objects when realistic domain objects are easy to build.
- Tests call something a validator or non-validator without proving that role from the real environment.
- Tests depend on shared real-environment write state even after collisions or interference are visible.

## Review Checklist

Before merging, check all of the following:

- External service communication is isolated behind the correct adapter boundary.
- Contacts are thin and transport-focused.
- Policy and caching live above contacts.
- Singleton factory functions are the patch point in tests.
- Mock contacts implement the abstract contact interface and expose structured call history plus scenario configuration methods.
- Public tests mock only external boundaries.
- Public tests do not patch internal helper functions below the chosen public seam.
- Mock-contact tests cover unhappy paths and mixed-result collection scenarios, not only pure happy paths.
- Real adapter integration tests exist in dedicated files for every real external-service adapter.
- Real integration test fixtures prove their intended actor roles and state against the actual external service.
- No test exists only to validate an internal helper's trivial return shape.
- Databases and similar stateful systems are tested with real instances unless there is a strong reason not to.
