import bittensor
import pytest

from .example_validator_code import validator
from bt_ddos_shield_client.testing import ShieldMetagraphTestRig, ShieldedNeuronMutatorTestRig
from tests.library.fixtures import certificate_fixture_path, load_certificate_fixture



def test_metagraph_test_rig_produces_final_public_addresses(tmp_path, validator_wallet: bittensor.wallet):
    rig = ShieldMetagraphTestRig()
    rig.set_validator_certificate_path(certificate_fixture_path('validator_a.pem'))
    rig.set_validator_hotkey(validator_wallet.hotkey.ss58_address)
    rig.set_on_chain_certificate(load_certificate_fixture('validator_a.pem').public_key)
    rig.add_miner('miner-a', '198.51.100.10', 8080, shield_address='203.0.113.10:3030')
    rig.add_miner('miner-b', '198.51.100.11', 8081, shield_address=None)

    with rig.install(tmp_path=tmp_path):
        neurons = validator.list_bittensor_neurons()

    assert [(axon.hotkey, axon.ip, axon.port) for axon in neurons] == [
        ('miner-a', '203.0.113.10', 3030),
        ('miner-b', '198.51.100.11', 8081),
    ]


@pytest.mark.asyncio
async def test_shielded_neuron_mutator_test_rig_produces_final_public_addresses(tmp_path, monkeypatch, validator_wallet):
    pytest.importorskip('turbobt')

    rig = ShieldedNeuronMutatorTestRig()
    rig.set_validator_certificate_path(certificate_fixture_path('validator_a.pem'))
    rig.set_on_chain_certificate(load_certificate_fixture('validator_a.pem').public_key)
    rig.set_validator_hotkey(validator_wallet.hotkey.ss58_address)
    rig.add_miner('miner-a', '198.51.100.20', 8090, shield_address='203.0.113.20:3040')
    rig.add_miner('miner-b', '198.51.100.21', 8091, shield_address=None)

    with rig.install(tmp_path=tmp_path) as context:
        result = await validator.list_turbobt_neurons()

    assert result is context.neurons
    assert [(neuron.hotkey, str(neuron.axon_info.ip), neuron.axon_info.port) for neuron in context.neurons] == [
        ('miner-a', '203.0.113.20', 3040),
        ('miner-b', '198.51.100.21', 8091),
    ]


@pytest.mark.asyncio
async def test_shielded_neuron_mutator_test_rig_patches_default_contact_for_user_code(
        tmp_path, monkeypatch, validator_wallet):

    rig = ShieldedNeuronMutatorTestRig()
    rig.set_validator_certificate_path(certificate_fixture_path('validator_a.pem'))
    rig.set_validator_hotkey(validator_wallet.hotkey.ss58_address)
    rig.set_on_chain_certificate(load_certificate_fixture('validator_a.pem').public_key)
    rig.add_miner('miner-a', '198.51.100.23', 8093, shield_address='203.0.113.23:3043')

    with rig.install(tmp_path=tmp_path) as context:
        result = await validator.list_turbobt_neurons()

    assert result is context.neurons
    assert [(neuron.hotkey, str(neuron.axon_info.ip), neuron.axon_info.port) for neuron in context.neurons] == [
        ('miner-a', '203.0.113.23', 3043),
    ]
