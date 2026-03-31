# bt_ddos_shield_client

Standalone validator-side client package for BT DDoS Shield.

## Public API

- `bt_ddos_shield_client.ShieldMetagraph`
- `bt_ddos_shield_client.shielded_turbobt.ShieldedBittensor`
- `bt_ddos_shield_client.shielded_turbobt.ShieldedSubnetReference`
- `bt_ddos_shield_client.MockBittensorSubtensorContact`
- `bt_ddos_shield_client.shielded_turbobt.MockTurboBittensorSubtensorContact`
- `bt_ddos_shield_client.ShieldMetagraphTestRig`

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
