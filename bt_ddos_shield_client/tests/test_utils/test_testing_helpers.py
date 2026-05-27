from __future__ import annotations

import bittensor
import pytest

from bt_ddos_shield_client.testing import ShieldTestRig
from tests.test_utils.example_validator_code import validator


def test_shield_test_rig_rewrites_bittensor_neurons_for_app_code(validator_wallet: bittensor.wallet):
    rig = ShieldTestRig(wallet=validator_wallet)
    rig.add_miner('miner-a', '198.51.100.10', 8080, shield_address='203.0.113.10:3030')
    rig.add_miner('miner-b', '198.51.100.11', 8081, shield_address=None)

    with rig.install():
        first = validator.list_bittensor_neurons()
        second = validator.list_bittensor_neurons()

    assert [(axon.hotkey, axon.ip, axon.port) for axon in first] == [
        ('miner-a', '203.0.113.10', 3030),
        ('miner-b', '198.51.100.11', 8081),
    ]
    assert [(axon.hotkey, axon.ip, axon.port) for axon in second] == [
        ('miner-a', '203.0.113.10', 3030),
        ('miner-b', '198.51.100.11', 8081),
    ]


@pytest.mark.asyncio
async def test_shield_test_rig_rewrites_turbobt_neurons_for_app_code(validator_wallet: bittensor.wallet):
    pytest.importorskip('turbobt')

    rig = ShieldTestRig(wallet=validator_wallet)
    rig.add_miner('miner-a', '198.51.100.20', 8090, shield_address='203.0.113.20:3040')
    rig.add_miner('miner-b', '198.51.100.21', 8091, shield_address=None)

    with rig.install() as context:
        result = await validator.list_turbobt_neurons()

    assert result is context.neurons
    assert [(neuron.hotkey, str(neuron.axon_info.ip), neuron.axon_info.port) for neuron in context.neurons] == [
        ('miner-a', '203.0.113.20', 3040),
        ('miner-b', '198.51.100.21', 8091),
    ]


def test_shield_test_rig_rejects_real_contact_created_before_install(validator_wallet: bittensor.wallet, monkeypatch):
    import bt_ddos_shield_client.contacts as contacts

    monkeypatch.setattr(contacts, '_bittensor_subtensor_contact_instance', None)
    contacts.bittensor_subtensor_contact()

    rig = ShieldTestRig(wallet=validator_wallet)

    with pytest.raises(AssertionError, match='Real subtensor contact was already instantiated'):
        with rig.install():
            pass
