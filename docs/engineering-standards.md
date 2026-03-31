# Engineering Standards

This document defines repository-wide engineering rules for service boundaries, mocks, singletons, and tests.

These rules apply to both humans and agents.

## External Service Boundaries

### Required

- Put communication with external control-plane services behind a thin adapter layer.
- In this repository, communication with Subtensor or Bittensor clients belongs in a `Contact` implementation.
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
- Keep mock contacts declarative.
- Allow mock contacts to be mutated during a single test.
- Record calls in a structured way so tests can assert externally visible behavior.
- Configure mocks in domain terms:
  - current listed neurons
  - current synced metagraph result
  - current on-chain certificate
  - upload outcome

### Forbidden

- Do not make downstream tests rebuild low-level transport responses when a mock contact can express the same scenario directly.
- Do not make mocks immutable snapshots if the production behavior depends on changing external state.
- Do not hide call history from tests.

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
- In this repository, that usually means:
  - patching contact singleton factory functions
  - stubbing HTTP responses with `aioresponses`
- Use real certificates, keys, and realistic domain objects in tests when practical.
- Prefer asserting final public outcomes and externally visible side effects.

### Forbidden

- Do not write tests that target private or internal helper methods unless there is no reasonable public path.
- Do not write tests whose only value is checking trivial internal shapes, such as:
  - `assert isinstance(str, some_internal_method(...))`
  - direct testing of parsing helpers that are already covered through public behavior
- Do not mock internal methods just to force code through a branch when a public API test can cover it.
- Do not replace real domain objects with placeholder objects if constructing the real object is practical.

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

- High-level code calls `bittensor_subtensor_contact()` or `turbo_bittensor_subtensor_contact()`.
- Tests patch those factory functions and drive `ShieldMetagraph.sync()` or `ShieldedSubnetReference.list_neurons()`.
- Manifest behavior is exercised with real HTTP stubs and real certificates.
- Mock contacts are reconfigured mid-test to simulate on-chain state changes.

### Bad

- High-level code talks directly to Subtensor or Bittensor SDK objects outside the contact layer.
- Tests patch private helpers instead of the external boundary.
- Tests assert internal helper return types instead of public behavior.
- Tests use placeholder objects when real `Neuron` or `NeuronInfo` instances are easy to build.

## Review Checklist

Before merging, check all of the following:

- External service communication is isolated behind the correct adapter boundary.
- Contacts are thin and transport-focused.
- Policy and caching live above contacts.
- Singleton factory functions are the patch point in tests.
- Public tests mock only external boundaries.
- No test exists only to validate an internal helper's trivial return shape.
- Databases and similar stateful systems are tested with real instances unless there is a strong reason not to.
