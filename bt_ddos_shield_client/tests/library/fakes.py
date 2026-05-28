from __future__ import annotations

import base64
import json
from ipaddress import ip_address
from pathlib import Path
from types import SimpleNamespace

from bittensor.core.chain_data import AxonInfo, NeuronInfo, PrometheusInfo
from bittensor.utils.balance import Balance

from bt_ddos_shield_client.encryption import ECIESEncryptionManager


def make_wallet(hotkey: str = 'validator-hotkey', hotkey_path: str | Path = '/tmp/wallets/validator/hotkeys/default'):
    return SimpleNamespace(
        hotkey=SimpleNamespace(ss58_address=hotkey),
        hotkey_file=SimpleNamespace(path=str(hotkey_path)),
    )


def make_bittensor_neuron(
    *,
    hotkey: str,
    ip: str,
    port: int,
    uid: int = 0,
    netuid: int = 7,
    coldkey: str = 'miner-coldkey',
) -> NeuronInfo:
    return NeuronInfo(
        hotkey=hotkey,
        coldkey=coldkey,
        uid=uid,
        netuid=netuid,
        active=1,
        stake=Balance.from_tao(0),
        stake_dict={},
        total_stake=Balance.from_tao(0),
        rank=0.0,
        emission=0.0,
        incentive=0.0,
        consensus=0.0,
        trust=0.0,
        validator_trust=0.0,
        dividends=0.0,
        last_update=0,
        validator_permit=False,
        weights=[],
        bonds=[],
        pruning_score=0,
        prometheus_info=PrometheusInfo(block=0, version=1, ip='127.0.0.1', port=9090, ip_type=4),
        axon_info=AxonInfo(version=1, ip=ip, port=port, ip_type=4, hotkey=hotkey, coldkey=coldkey),
    )


def make_turbobt_neuron(
    *,
    hotkey: str,
    ip: str,
    port: int,
    uid: int = 0,
    coldkey: str = 'miner-coldkey',
):
    # Deferred so non-turbobt tests can import shared fakes on unsupported Python.
    import turbobt
    from turbobt.neuron import AxonInfo as TurboAxonInfo
    from turbobt.neuron import AxonProtocolEnum, Neuron as TurboNeuron, PrometheusInfo as TurboPrometheusInfo

    return TurboNeuron(
        subnet=turbobt.Subnet(
            object(),
            netuid=7,
            name='test-subnet',
            symbol='TS',
            tempo=0,
            owner_hotkey='owner-hotkey',
            owner_coldkey='owner-coldkey',
            identity={},
        ),
        uid=uid,
        coldkey=coldkey,
        hotkey=hotkey,
        active=True,
        axon_info=TurboAxonInfo(ip=ip_address(ip), port=port, protocol=AxonProtocolEnum.HTTP),
        prometheus_info=TurboPrometheusInfo(ip=ip_address('127.0.0.1'), port=9090),
        stake=0.0,
        rank=0.0,
        emission=0.0,
        incentive=0.0,
        consensus=0.0,
        trust=0.0,
        validator_trust=0.0,
        dividends=0.0,
        last_update=0,
        validator_permit=False,
        pruning_score=0,
    )


def build_manifest_body(public_key: str, address: str, validator_hotkey: str = 'validator-hotkey') -> bytes:
    encrypted = ECIESEncryptionManager().encrypt(public_key, address.encode())
    return build_manifest_body_from_blob(encrypted, validator_hotkey=validator_hotkey)


def build_manifest_body_from_blob(encrypted_blob: bytes, validator_hotkey: str = 'validator-hotkey') -> bytes:
    return json.dumps(
        {
            'ddos_shield_manifest': {
                'encrypted_url_mapping': {
                    validator_hotkey: base64.b64encode(encrypted_blob).decode(),
                },
            }
        }
    ).encode()
