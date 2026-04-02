from __future__ import annotations

from dataclasses import dataclass

from aioresponses import aioresponses
from freezegun import freeze_time
import pytest

from bt_ddos_shield_client.shield_metagraph import ShieldMetagraphOptions
from tests.fakes import build_manifest_body, make_turbobt_neuron, make_wallet
from tests.fixtures import certificate_fixture_path, load_certificate_fixture

pytest.importorskip('turbobt')

from bt_ddos_shield_client.shielded_turbobt import ShieldedBittensor, ShieldedNeuronMutator


def _certificate_path(tmp_path, fixture_name: str = 'validator_a.pem') -> str:
    destination = tmp_path / 'validator.pem'
    destination.write_text(certificate_fixture_path(fixture_name).read_text())
    return str(destination)


def _make_bittensor(tmp_path, fixture_name: str = 'validator_a.pem') -> ShieldedBittensor:
    return ShieldedBittensor(
        'test',
        wallet=make_wallet(),
        ddos_shield_netuid=7,
        ddos_shield_options=ShieldMetagraphOptions(certificate_path=_certificate_path(tmp_path, fixture_name)),
    )


def _make_mutator(tmp_path, fixture_name: str = 'validator_a.pem') -> ShieldedNeuronMutator:
    return ShieldedNeuronMutator(
        wallet=make_wallet(),
        netuid=7,
        ddos_shield_options=ShieldMetagraphOptions(certificate_path=_certificate_path(tmp_path, fixture_name)),
    )


def _manifest_url(ip: str, port: int) -> str:
    return f'http://{ip}:{port}/shield_manifest.json'


@freeze_time('2026-04-02 12:00:00')
@pytest.mark.asyncio
async def test_mutate_neurons_returns_same_list_and_uploads_cert_when_missing(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    neurons = [make_turbobt_neuron(hotkey='miner-a', ip='198.51.100.70', port=5070)]
    patched_turbo_bittensor_contact.set_own_certificate(None)
    mutator = _make_mutator(tmp_path)
    bittensor = _make_bittensor(tmp_path)

    with aioresponses() as mocked:
        mocked.get(
            _manifest_url('198.51.100.70', 5070),
            status=200,
            body=build_manifest_body(certificate.public_key, '203.0.113.70:3070'),
        )
        result = await mutator.mutate_neurons(bittensor, neurons)

    assert result is neurons
    assert (str(neurons[0].axon_info.ip), neurons[0].axon_info.port) == ('203.0.113.70', 3070)
    assert [call.method for call in patched_turbo_bittensor_contact.calls] == [
        'get_own_public_key',
        'upload_public_key',
    ]
    assert patched_turbo_bittensor_contact.calls[1].public_key == certificate.public_key


@pytest.mark.asyncio
async def test_mutate_neurons_leaves_unshielded_neurons_unchanged(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    neurons = [make_turbobt_neuron(hotkey='miner-a', ip='198.51.100.71', port=5071)]
    patched_turbo_bittensor_contact.set_own_certificate(certificate.public_key)
    mutator = _make_mutator(tmp_path)
    bittensor = _make_bittensor(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.71', 5071), status=404)
        result = await mutator.mutate_neurons(bittensor, neurons)

    assert result is neurons
    assert (str(neurons[0].axon_info.ip), neurons[0].axon_info.port) == ('198.51.100.71', 5071)


@dataclass
class _OutOfOrderShieldClient:
    certificate: object
    shield_addresses_by_hotkey: dict[str, str | None]

    async def resolve_shield_addresses_by_hotkey(self, validator_hotkey: str, miners):
        assert validator_hotkey == 'validator-hotkey'
        assert set(miners) == {'miner-a', 'miner-b'}
        return self.shield_addresses_by_hotkey


@pytest.mark.asyncio
async def test_mutate_neurons_applies_results_by_hotkey_not_result_order(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    neurons = [
        make_turbobt_neuron(hotkey='miner-a', ip='198.51.100.72', port=5072, uid=0),
        make_turbobt_neuron(hotkey='miner-b', ip='198.51.100.73', port=5073, uid=1),
    ]
    patched_turbo_bittensor_contact.set_own_certificate(certificate.public_key)
    mutator = ShieldedNeuronMutator(
        wallet=make_wallet(),
        netuid=7,
        ddos_shield_options=ShieldMetagraphOptions(certificate_path=_certificate_path(tmp_path)),
        shield_client=_OutOfOrderShieldClient(
            certificate=load_certificate_fixture('validator_a.pem'),
            shield_addresses_by_hotkey={
                'miner-b': '203.0.113.173:3173',
                'miner-a': '203.0.113.172:3172',
            },
        ),
    )
    bittensor = _make_bittensor(tmp_path)

    result = await mutator.mutate_neurons(bittensor, neurons)

    assert result is neurons
    assert [(neuron.hotkey, str(neuron.axon_info.ip), neuron.axon_info.port) for neuron in neurons] == [
        ('miner-a', '203.0.113.172', 3172),
        ('miner-b', '203.0.113.173', 3173),
    ]


@pytest.mark.asyncio
async def test_mutate_neurons_raises_for_duplicate_hotkeys(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    neurons = [
        make_turbobt_neuron(hotkey='miner-a', ip='198.51.100.74', port=5074, uid=0),
        make_turbobt_neuron(hotkey='miner-a', ip='198.51.100.75', port=5075, uid=1),
    ]
    patched_turbo_bittensor_contact.set_own_certificate(certificate.public_key)
    mutator = _make_mutator(tmp_path)
    bittensor = _make_bittensor(tmp_path)

    with pytest.raises(ValueError, match='duplicate neuron hotkey: miner-a'):
        await mutator.mutate_neurons(bittensor, neurons)
