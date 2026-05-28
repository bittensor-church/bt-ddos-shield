from __future__ import annotations

import builtins
import sys

import bittensor
import pytest

from bt_ddos_shield_client.testing import ShieldTestRig


def _validator_module():
    # Deferred so test setup can patch validator environment before module load.
    from tests.test_utils.example_validator_code import validator

    return validator


def test_shield_test_rig_rewrites_bittensor_neurons_for_app_code(validator_wallet: bittensor.wallet):
    validator = _validator_module()
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
    if sys.platform and sys.version_info >= (3, 14):
        pytest.importorskip('turbobt', reason='turbobt is not available on this Python version')
    validator = _validator_module()

    rig = ShieldTestRig(wallet=validator_wallet, with_turbobt=True)
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
    # Import here so the test can reset the contact singleton before exercising the guard.
    import bt_ddos_shield_client.contacts as contacts

    monkeypatch.setattr(contacts, '_bittensor_subtensor_contact_instance', None)
    contacts.bittensor_subtensor_contact()

    rig = ShieldTestRig(wallet=validator_wallet)

    with pytest.raises(AssertionError, match='Real subtensor contact was already instantiated'):
        with rig.install():
            pass


def test_shield_test_rig_screams_when_turbobt_mode_needs_missing_dependency(
    validator_wallet: bittensor.wallet,
    monkeypatch,
):
    real_import = builtins.__import__

    def reject_turbobt(name, *args, **kwargs):
        if name == 'turbobt' or name.startswith('turbobt.'):
            raise ImportError('simulated missing turbobt')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', reject_turbobt)
    rig = ShieldTestRig(wallet=validator_wallet, with_turbobt=True)

    with pytest.raises(RuntimeError, match='ShieldTestRig with_turbobt=True requires turbobt'):
        with rig.install():
            pass


def test_shield_test_rig_false_turbobt_mode_does_not_need_turbobt(
    validator_wallet: bittensor.wallet,
    monkeypatch,
):
    real_import = builtins.__import__

    def reject_turbobt(name, *args, **kwargs):
        if name == 'turbobt' or name.startswith('turbobt.'):
            raise ImportError('simulated missing turbobt')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', reject_turbobt)
    rig = ShieldTestRig(wallet=validator_wallet, with_turbobt=False)

    with rig.install() as context:
        assert context.bittensor is None
        assert context.neurons == []
