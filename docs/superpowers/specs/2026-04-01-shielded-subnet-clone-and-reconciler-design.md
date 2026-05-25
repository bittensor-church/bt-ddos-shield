# Shielded Subnet Clone And Reconciler Design

## Goal

Add a public `LegacySubnetReference.clone(client)` constructor-style method that returns a new subnet reference with the same configuration and helper objects as the original instance, except for a different `client`.

Make that safe by refactoring `CertificateReconciler` so it no longer captures transport callables that indirectly bind a specific client or subtensor instance.

## Current Problem

`LegacySubnetReference` currently stores a `CertificateReconciler` built from `partial(...)` callables. Those callables capture the original client at construction time. A cloned subnet reference would therefore expose a new `client` attribute while reconciliation still talks to the old client.

`ShieldMetagraph` has the same design smell. It constructs a reconciler from bound callables and later mutates the reconciler if `sync(...)` receives a different `subtensor`.

## Recommended Approach

Refactor `CertificateReconciler` into a state holder for:

- the local certificate
- the disabled flag
- TTL cache state for recently confirmed public-key matches

Move transport-specific work into `ensure_own_certificate_matches(...)`, which will accept runtime context from the caller:

```python
ensure_own_certificate_matches(*, contact, client, netuid: int, hotkey: str, wallet)
```

The `client` parameter is intentionally generic. In `ShieldMetagraph` it will be the current `Subtensor` instance. In `LegacySubnetReference` it will be the current `turbobt.Bittensor` instance.

This keeps the contact interfaces unchanged while removing constructor-time binding of transport state.

## Detailed Changes

### CertificateReconciler

Update `CertificateReconciler` to remove:

- `get_own_public_key`
- `upload_public_key`

Keep:

- `certificate`
- `disabled`
- `match_ttl_seconds`
- `_matched_public_key`
- `_matched_until`

Behavior of `ensure_own_certificate_matches(...)` remains:

1. Return immediately when reconciliation is disabled.
2. Return immediately when the cached match is still valid.
3. Read the current on-chain public key through `contact.get_own_public_key(...)`.
4. If the on-chain key matches the local certificate, refresh the TTL cache and stop.
5. Otherwise call `contact.upload_public_key(...)` with the local certificate data.
6. Refresh the TTL cache after a successful upload.

### ShieldMetagraph

Construct `CertificateReconciler` with certificate and option data only.

Update `sync(...)` to pass runtime context into reconciliation:

```python
self._certificate_reconciler.ensure_own_certificate_matches(
    contact=self._contact,
    client=self.subtensor,
    netuid=self.netuid,
    hotkey=self.wallet.hotkey.ss58_address,
    wallet=self.wallet,
)
```

Delete the current logic that mutates reconciler callables when `subtensor` changes. The reconciler will no longer store transport references.

### LegacySubnetReference

Construct `CertificateReconciler` with certificate and option data only.

Update `list_neurons(...)` to pass runtime context into reconciliation:

```python
await self._certificate_reconciler.ensure_own_certificate_matches(
    contact=self._contact,
    client=self.client,
    netuid=self.netuid,
    hotkey=self.wallet.hotkey.ss58_address,
    wallet=self.wallet,
)
```

Add a new public method:

```python
def clone(self, client: turbobt.Bittensor) -> "LegacySubnetReference":
```

`clone(...)` returns a new `LegacySubnetReference` with:

- the same `netuid`
- the same `wallet` object
- the same `ddos_shield_options` object
- the same `_contact` object
- the same `_shield_client` object
- the same `_certificate_reconciler` object
- a different `client`

Reusing `_certificate_reconciler` is safe after the refactor because it no longer retains a transport-bound client reference.

## Testing

Add one focused public-API test for `LegacySubnetReference.clone(...)` that:

1. Creates an original subnet reference.
2. Creates a distinct client object.
3. Calls `clone(new_client)`.
4. Asserts:
   - `clone is not original`
   - `clone.client is new_client`
   - `clone.client is not original.client`
   - `clone.netuid == original.netuid`
   - `clone.wallet is original.wallet`
   - `clone.ddos_shield_options is original.ddos_shield_options`
   - `clone._contact is original._contact`
   - `clone._shield_client is original._shield_client`
   - `clone._certificate_reconciler is original._certificate_reconciler`

Existing reconciliation tests should continue to pass and will validate that the call-site refactor preserved behavior.

## Risks

- The runtime signature for `ensure_own_certificate_matches(...)` must match both contact families, but both already expose the same keyword names for their transport-specific methods.
- Sharing the reconciler across clones also shares TTL cache state. That is acceptable because the requested clone behavior is to keep all attributes the same except `client`, and the cache now reflects only the local certificate match state, not a bound client reference.

## Non-Goals

- No contact interface redesign.
- No extra clone behavior beyond replacing `client`.
- No unrelated refactors in tests or helper modules.
