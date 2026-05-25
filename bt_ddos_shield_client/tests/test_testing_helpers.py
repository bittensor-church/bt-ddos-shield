from __future__ import annotations

from freezegun import freeze_time
import pytest

from bt_ddos_shield_client.shielded_turbobt import ShieldedNeuronMutator
from bt_ddos_shield_client.testing import ShieldMetagraphTestRig, ShieldedNeuronMutatorTestRig
from tests.fixtures import certificate_fixture_path, load_certificate_fixture


def test_metagraph_test_rig_produces_final_public_addresses(tmp_path):
    rig = ShieldMetagraphTestRig()
    rig.set_validator_certificate_path(certificate_fixture_path('validator_a.pem'))
    rig.set_on_chain_certificate(load_certificate_fixture('validator_a.pem').public_key)
    rig.add_miner('miner-a', '198.51.100.10', 8080, shield_address='203.0.113.10:3030')
    rig.add_miner('miner-b', '198.51.100.11', 8081, shield_address=None)

    with rig.install(tmp_path=tmp_path) as metagraph:
        metagraph.sync()

    assert [(axon.hotkey, axon.ip, axon.port) for axon in metagraph.axons] == [
        ('miner-a', '203.0.113.10', 3030),
        ('miner-b', '198.51.100.11', 8081),
    ]


def test_metagraph_test_rig_surfaces_mismatched_certificate_upload_failure(tmp_path):
    rig = ShieldMetagraphTestRig()
    rig.set_validator_certificate_path(certificate_fixture_path('validator_a.pem'))
    rig.set_on_chain_certificate(load_certificate_fixture('validator_b.pem').public_key)
    rig.set_upload_behavior(RuntimeError('upload failed'))
    rig.add_miner('miner-a', '198.51.100.12', 8082, shield_address='203.0.113.12:3032')

    with rig.install(tmp_path=tmp_path) as metagraph:
        with pytest.raises(RuntimeError, match='upload failed'):
            metagraph.sync()


def test_metagraph_test_rig_exposes_ttl_behavior_through_public_api(tmp_path):
    rig = ShieldMetagraphTestRig()
    rig.set_validator_certificate_path(certificate_fixture_path('validator_a.pem'))
    rig.set_on_chain_certificate(load_certificate_fixture('validator_a.pem').public_key)
    rig.add_miner('miner-a', '198.51.100.13', 8083, shield_address='203.0.113.13:3033')

    with freeze_time('2026-03-31 12:00:00') as frozen:
        with rig.install(tmp_path=tmp_path) as metagraph:
            metagraph.sync()

            rig.set_on_chain_certificate(load_certificate_fixture('validator_b.pem').public_key)
            rig.set_upload_behavior(RuntimeError('upload failed'))
            metagraph.sync()

            frozen.tick(301)
            with pytest.raises(RuntimeError, match='upload failed'):
                metagraph.sync()


@pytest.mark.asyncio
async def test_shielded_neuron_mutator_test_rig_produces_final_public_addresses(tmp_path):
    pytest.importorskip('turbobt')

    rig = ShieldedNeuronMutatorTestRig()
    rig.set_validator_certificate_path(certificate_fixture_path('validator_a.pem'))
    rig.set_on_chain_certificate(load_certificate_fixture('validator_a.pem').public_key)
    rig.add_miner('miner-a', '198.51.100.20', 8090, shield_address='203.0.113.20:3040')
    rig.add_miner('miner-b', '198.51.100.21', 8091, shield_address=None)

    with rig.install(tmp_path=tmp_path) as context:
        mutator = ShieldedNeuronMutator(
            wallet=context.wallet,
            netuid=context.netuid,
            contact=rig.contact,
        )
        result = await mutator.mutate_neurons(context.bittensor, context.neurons)

    assert result is context.neurons
    assert [(neuron.hotkey, str(neuron.axon_info.ip), neuron.axon_info.port) for neuron in context.neurons] == [
        ('miner-a', '203.0.113.20', 3040),
        ('miner-b', '198.51.100.21', 8091),
    ]


@pytest.mark.asyncio
async def test_shielded_neuron_mutator_test_rig_surfaces_upload_failures(tmp_path):
    pytest.importorskip('turbobt')

    rig = ShieldedNeuronMutatorTestRig()
    rig.set_validator_certificate_path(certificate_fixture_path('validator_a.pem'))
    rig.set_on_chain_certificate(load_certificate_fixture('validator_b.pem').public_key)
    rig.set_upload_behavior(RuntimeError('upload failed'))
    rig.add_miner('miner-a', '198.51.100.22', 8092, shield_address='203.0.113.22:3042')

    with rig.install(tmp_path=tmp_path) as context:
        mutator = ShieldedNeuronMutator(
            wallet=context.wallet,
            netuid=context.netuid,
            contact=rig.contact,
        )
        with pytest.raises(RuntimeError, match='upload failed'):
            await mutator.mutate_neurons(context.bittensor, context.neurons)
