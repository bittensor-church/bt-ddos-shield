from __future__ import annotations

from dataclasses import dataclass
import os
import sys
from typing import Any

import bittensor as bittensor_lib

from bt_ddos_shield_client.shield_metagraph import ShieldMetagraph

_TURBOBT_AVAILABLE = not (sys.platform and sys.version_info >= (3, 14))

if _TURBOBT_AVAILABLE:
    # Optional integration import; the turbobt extra is not installed on Python 3.14.
    import turbobt

    from bt_ddos_shield_client.shielded_turbobt import ShieldedNeuronMutator


@dataclass(frozen=True)
class ValidatorConfig:
    wallet_name: str
    wallet_hotkey: str
    wallet_path: str
    netuid: int
    network: str


def _load_config() -> ValidatorConfig:
    return ValidatorConfig(
        wallet_name=os.getenv('VALIDATOR_WALLET_NAME', 'validator'),
        wallet_hotkey=os.getenv('VALIDATOR_WALLET_HOTKEY', 'default'),
        wallet_path=os.getenv('VALIDATOR_WALLET_PATH', '~/.bittensor/wallets'),
        netuid=int(os.getenv('VALIDATOR_NETUID', '7')),
        network=os.getenv('VALIDATOR_NETWORK', 'test'),
    )


_config = _load_config()

wallet = bittensor_lib.wallet(
    name=_config.wallet_name,
    hotkey=_config.wallet_hotkey,
    path=_config.wallet_path,
)

shield_metagraph = ShieldMetagraph(
    wallet=wallet,
    netuid=_config.netuid,
    network=_config.network,
    sync=False,
)


if _TURBOBT_AVAILABLE:
    shielded_neuron_mutator = ShieldedNeuronMutator(
        wallet=wallet,
        netuid=_config.netuid,
    )

    bittensor = turbobt.Bittensor(_config.network, wallet=wallet)
    subnet = bittensor.subnet(_config.netuid)


def list_bittensor_neurons() -> list[Any]:
    shield_metagraph.sync()
    return shield_metagraph.axons


async def list_turbobt_neurons() -> list[Any]:
    if not _TURBOBT_AVAILABLE:
        raise RuntimeError('turbobt is not available on this Python version')
    neurons = await subnet.list_neurons()
    return await shielded_neuron_mutator.mutate_neurons(bittensor, neurons)
