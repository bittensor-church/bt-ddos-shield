# Turbobt Neuron Mutator Design

## Goal

Add a new public `shielded_turbobt` class that can take an already fetched list of turbobt neurons, reconcile the caller's validator certificate on chain, and mutate shielded neuron axon endpoints in place.

## Scope

This design adds a reusable public helper for the turbobt client surface. It does not change the manifest format, encryption flow, or the lower-level chain contact behavior.

## Public API

Add a new public class in `bt_ddos_shield_client.bt_ddos_shield_client.shielded_turbobt`:

- `ShieldedNeuronMutator`

Constructor responsibilities:

- store `wallet`
- store `netuid`
- accept `ddos_shield_options: ShieldMetagraphOptions | None = None`
- derive the certificate path through the existing `ShieldMetagraphOptions.certificate_path` mechanism
- allow optional injection of the turbobt contact, `ShieldClient`, and `CertificateReconciler` for tests

Public method:

```python
async def mutate_neurons(
    self,
    bittensor: turbobt.Bittensor,
    neurons: list[turbobt.neuron.Neuron],
) -> list[turbobt.neuron.Neuron]:
    """Mutate shielded neuron axons in place and return the same list."""
```

Behavior:

- accepts any provided neuron list without subnet validation
- reconciles the validator certificate against chain using the passed `bittensor`
- uploads the validator certificate if the chain copy is missing or mismatched
- mutates each shielded neuron's `axon_info.ip` and `axon_info.port` in place
- returns the same list object for convenience
- raises immediately on certificate read or upload failure

## Architecture

`ShieldedNeuronMutator` becomes the reusable implementation for the current turbobt shield rewrite pipeline.

It owns only stable configuration and helper dependencies:

- validator wallet
- target `netuid` for certificate reconciliation
- shield options including certificate location
- contact adapter for chain reads and writes
- `ShieldClient` for manifest fetch and decrypt
- `CertificateReconciler` for cert TTL caching and upload decisions

It does not hold a turbobt `Bittensor` instance. The caller must pass a `bittensor` object on each mutation call so the helper can be used with any active client instance.

## Data Flow

`mutate_neurons(...)` performs work in this order:

1. Call `CertificateReconciler.ensure_own_certificate_matches(...)` with the stored wallet, stored `netuid`, configured contact, and the passed `bittensor`.
2. Build a `dict[str, turbobt.neuron.Neuron]` keyed by miner hotkey from the provided list.
3. Reject duplicate hotkeys in the input list with `ValueError`, because keyed in-place mutation would otherwise be ambiguous.
4. Resolve shield addresses for the current neuron endpoints using the stored validator hotkey.
5. Apply shield results by miner hotkey, not by list position.
6. For each valid parsed shield address, mutate the matching neuron's `axon_info.ip` and `axon_info.port` in place.
7. Leave neurons unchanged when no valid shield address is available.
8. Return the original `neurons` list object.

The shield-address application step must not rely on tuple or list ordering. Internally, results should be associated with miner hotkeys and then applied back to neurons through the hotkey map.

## Integration

`LegacySubnetReference` should delegate to the new helper instead of owning the rewrite loop directly.

Updated `list_neurons()` flow:

1. fetch neurons from the turbobt contact
2. call `await self._neuron_mutator.mutate_neurons(self.client, neurons)`
3. return the same `neurons` list

`LegacyTurbobtWrapper` should construct and pass through a `ShieldedNeuronMutator` instance when creating shielded subnet references so the existing public API keeps working.

## Error Handling

Raise immediately:

- chain certificate read failures
- chain certificate upload failures
- duplicate hotkeys in the provided list

Leave the affected neuron unchanged:

- manifest fetch timeout or transport failure
- non-success manifest HTTP response
- invalid manifest payload
- decryption failure
- manifest entry for a different validator
- malformed shield address
- missing shield mapping for a miner

## Testing

Add public-boundary tests covering:

- the new mutator mutates and returns the same list object
- the new mutator uploads the certificate when the on-chain certificate is missing
- the new mutator uploads the certificate when the on-chain certificate mismatches
- the new mutator skips upload when the certificate matches
- the new mutator leaves neurons unchanged for manifest failures or invalid content
- the new mutator applies rewrites by miner hotkey rather than by returned order
- duplicate hotkeys raise `ValueError`
- `LegacySubnetReference.list_neurons()` delegates through the mutator and preserves existing behavior

## Files Expected To Change

- `legacy_turbobt_wrapper.py`
- `bt_ddos_shield_client/bt_ddos_shield_client/shielded_turbobt/__init__.py`
- `test_legacy_turbobt_wrapper.py`

Adding a new focused module under `shielded_turbobt` for the mutator is preferred if that keeps responsibilities clearer than extending `legacy_turbobt_wrapper.py`.
