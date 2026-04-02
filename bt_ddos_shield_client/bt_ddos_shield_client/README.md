# bt_ddos_shield_client

Standalone validator-side client package for BT DDoS Shield.

## Public API

- `bt_ddos_shield_client.ShieldMetagraph`
- `bt_ddos_shield_client.shielded_turbobt.ShieldedBittensor`
- `bt_ddos_shield_client.shielded_turbobt.ShieldedNeuronMutator`
- `bt_ddos_shield_client.shielded_turbobt.ShieldedSubnetReference`
- `bt_ddos_shield_client.MockBittensorSubtensorContact`
- `bt_ddos_shield_client.shielded_turbobt.MockTurboBittensorSubtensorContact`
- `bt_ddos_shield_client.ShieldMetagraphTestRig`
- `bt_ddos_shield_client.ShieldedNeuronMutatorTestRig`

## Behavior

The client no longer reads manifest URLs from knowledge commitments.

For each miner axon, it:

1. builds `http://{axon_ip}:{axon_port}/shield_manifest.json`
2. fetches that endpoint with redirects enabled
3. deserializes the manifest if the response is valid
4. decrypts the validator-specific address entry
5. replaces the miner axon endpoint only when all of the above succeed

If fetch, redirect, deserialization, or decryption fails, that miner is treated as unshielded.

## Install

```bash
pip install bt-ddos-shield-client
```

With turbobt support:

```bash
pip install "bt-ddos-shield-client[turbobt]"
```

## Run Tests

From the repository root:

```bash
uv run --group test pytest bt_ddos_shield_client/tests -v
```

From inside the `bt_ddos_shield_client` directory:

```bash
uv run --project . --python 3.12 --group test pytest tests -v
```

The test suite stays at the public boundary:

- tests patch `bittensor_subtensor_contact()` / `turbo_bittensor_subtensor_contact()`
- production mock contacts drive certificate upload scenarios
- `aioresponses` mocks `shield_manifest.json` responses over HTTP

### Real Contact Integration Tests

The real `BittensorSubtensorContact` and `TurboBittensorSubtensorContact` implementations also have Docker-backed integration tests under `bt_ddos_shield_client/tests/contacts`.

Those tests are marked with `subtensor_integration`, so they are excluded from the default local pytest run.

Run them explicitly from the repository root with:

```bash
uv run --group test pytest bt_ddos_shield_client/tests/contacts -m subtensor_integration -v
```

Or from inside the `bt_ddos_shield_client` directory:

```bash
uv run --project . --python 3.12 --group test pytest tests/contacts -m subtensor_integration -v
```

Behavior:

- the tests start their own disposable local subtensor container
- they create test wallets, create a subnet, register neurons, and then exercise only the public contact methods
- they do not depend on files under `manual_tests/`

Docker notes:

- the tests follow the active Docker context automatically
- if the active context uses an `ssh://...` Docker endpoint, the test environment needs the `paramiko` test dependency, which is already included in the `test` group

## Usage

```python
from bt_ddos_shield_client import ShieldMetagraph

metagraph = ShieldMetagraph(wallet, netuid, subtensor=subtensor)
```

```python
from bt_ddos_shield_client.shielded_turbobt import ShieldedBittensor

async with ShieldedBittensor(
    network,
    wallet=wallet,
    ddos_shield_netuid=netuid,
) as bittensor:
    neurons = await bittensor.subnet(netuid).list_neurons()
```

```python
from bt_ddos_shield_client.shield_metagraph import ShieldMetagraphOptions
from bt_ddos_shield_client.shielded_turbobt import ShieldedNeuronMutator

mutator = ShieldedNeuronMutator(
    wallet=wallet,
    netuid=netuid,
    ddos_shield_options=ShieldMetagraphOptions(certificate_path='./validator_cert.pem'),
)

neurons = await bittensor.subnet(netuid).list_neurons()
await mutator.mutate_neurons(bittensor, neurons)
```
