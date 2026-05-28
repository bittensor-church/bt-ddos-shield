# bt_ddos_shield_client

Validator-side client package for BT DDoS Shield.

The package resolves shielded miner endpoints from miner manifests and mutates validator-side neuron or metagraph data only when a miner publishes a valid encrypted entry for the validator hotkey.

## Install

The base client supports Python 3.11 through 3.14.

```bash
pip install bt-ddos-shield-client
```

Install optional `turbobt` support with:

```bash
pip install "bt-ddos-shield-client[turbobt]"
```

The optional `turbobt` extra is currently limited to Python 3.11 through 3.13 because upstream `turbobt` depends on `eciespy`, which pulls `coincurve`.

## Public API

- `bt_ddos_shield_client.ShieldMetagraph`
- `bt_ddos_shield_client.ShieldTestRig`
- `bt_ddos_shield_client.shielded_turbobt.ShieldedNeuronMutator`

## Certificate Handling

The client uses an Ed25519 ECIES-compatible key pair stored as a validator shield certificate. The public key is uploaded to the subnet certificate field when the local certificate does not match the value already stored on chain.

Certificate path resolution:

1. Use `VALIDATOR_SHIELD_CERTIFICATE_PATH` when the environment variable is set.
2. Otherwise store the certificate next to the wallet hotkey file as `<hotkey>.cert.pem`, for example `~/.bittensor/wallets/validator/hotkeys/default.cert.pem`.

When the certificate file does not exist, the client creates it automatically.

## ShieldMetagraph

Use `ShieldMetagraph` as the validator-side replacement for `bittensor.core.metagraph.Metagraph`:

```python
from bt_ddos_shield_client import ShieldMetagraph

metagraph = ShieldMetagraph(wallet, netuid, subtensor=subtensor)
```

Constructor arguments mirror the common Bittensor metagraph flow:

```python
ShieldMetagraph(
    wallet,
    netuid,
    network=None,
    lite=True,
    sync=True,
    block=None,
    subtensor=None,
)
```

On `sync()`, the client:

1. syncs the underlying Bittensor metagraph through the package contact layer;
2. ensures the validator's public certificate is present on chain;
3. fetches each miner manifest from `http://{axon_ip}:{axon_port}/shield_manifest.json`;
4. decrypts the manifest entry for the validator hotkey and miner hotkey;
5. replaces the miner axon IP and port when the shield address is valid.

Fetch failures, redirects that fail, malformed manifests, missing entries, decryption failures, and invalid shield address strings leave that miner's original axon endpoint unchanged.

## turbobt Integration

Use `ShieldedNeuronMutator` when validator code works with `turbobt` neurons:

```python
from bt_ddos_shield_client.shielded_turbobt import ShieldedNeuronMutator

mutator = ShieldedNeuronMutator(
    wallet=wallet,
    netuid=netuid,
)

neurons = await bittensor.subnet(netuid).list_neurons()
await mutator.mutate_neurons(bittensor, neurons)
```

The mutator performs the same certificate reconciliation and manifest resolution as `ShieldMetagraph`, then updates each matching neuron's `axon_info.ip` and `axon_info.port`.

## Testing Helpers

`ShieldTestRig` installs public-boundary fakes for downstream validator tests. It patches the package contact factories and mocks miner manifest HTTP responses while keeping certificate generation, manifest serialization, encryption, and address parsing real.

```python
from bt_ddos_shield_client import ShieldTestRig

rig = ShieldTestRig(wallet=wallet)
rig.add_miner("miner-a", "198.51.100.10", 8080, shield_address="203.0.113.10:3030")
rig.add_miner("miner-b", "198.51.100.11", 8080, shield_address=None)

with rig.install():
    run_validator_code()
```

Enable `turbobt` test support explicitly:

```python
rig = ShieldTestRig(wallet=wallet, with_turbobt=True)
```

`shield_address=None` makes the fixture return a missing manifest for that miner, so downstream tests can cover unshielded miners.

## Tests

Run the default client test suite across every supported Python version from this directory:

```bash
uv tool run nox
```

Run one Python version with:

```bash
uv tool run nox -s tests-3.12
```

Pass pytest arguments after `--`:

```bash
uv tool run nox -s tests-3.12 -- tests/library -v
```

For a quick run against the current uv environment, use:

```bash
uv run --group test pytest tests -v
```

Default tests cover the public package boundary:

- `ShieldMetagraph`
- `ShieldedNeuronMutator`
- certificate upload behavior through contact fakes
- manifest fetching through `aioresponses`
- downstream-facing `ShieldTestRig` behavior

Docker-backed real contact integration tests live under `tests/contacts` and are marked with `subtensor_integration`, so they are excluded by the default pytest configuration.

Run them explicitly with:

```bash
uv run --group test pytest tests/contacts -m subtensor_integration -v
```

The integration tests start a disposable local subtensor container, create test wallets and subnet state, and exercise the real `BittensorSubtensorContact` and `TurboBittensorSubtensorContact` public methods. They do not depend on `manual_tests/`.

The tests follow the active Docker context. SSH-based Docker contexts require `paramiko`, which is included in the `test` dependency group.
