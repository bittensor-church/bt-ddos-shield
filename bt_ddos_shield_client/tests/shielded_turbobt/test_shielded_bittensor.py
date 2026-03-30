from __future__ import annotations

from types import SimpleNamespace

from aioresponses import aioresponses
import pytest

from bt_ddos_shield_client.certificates import EDDSACertificateManager
from bt_ddos_shield_client.shield_metagraph import ShieldMetagraphOptions
from bt_ddos_shield_client.tests.fakes import FakeSubtensorContact, build_manifest_body, make_wallet

pytest.importorskip('turbobt')

from bt_ddos_shield_client.shielded_turbobt import ShieldedBittensor, ShieldedSubnetReference


def _patch_bittensor_base(monkeypatch):
    neuron = SimpleNamespace(
        hotkey='miner-hotkey',
        axon_info=SimpleNamespace(ip='198.51.100.50', port=5050),
    )

    def fake_init(self, *args, wallet=None, **kwargs):
        self.wallet = wallet

    async def fake_aenter(self):
        return self

    async def fake_aexit(self, *args, **kwargs):
        return None

    async def fake_list_neurons(self, *args, **kwargs):
        return [neuron]

    monkeypatch.setattr('bt_ddos_shield_client.turbobt.shielded_bittensor.turbobt.Bittensor.__init__', fake_init)
    monkeypatch.setattr('bt_ddos_shield_client.turbobt.shielded_bittensor.turbobt.Bittensor.__aenter__', fake_aenter)
    monkeypatch.setattr('bt_ddos_shield_client.turbobt.shielded_bittensor.turbobt.Bittensor.__aexit__', fake_aexit)
    monkeypatch.setattr(
        'bt_ddos_shield_client.turbobt.shielded_bittensor.turbobt.subnet.SubnetReference.list_neurons',
        fake_list_neurons,
    )


@pytest.mark.asyncio
async def test_shielded_bittensor_updates_visible_endpoint_when_manifest_resolves(monkeypatch, tmp_path):
    _patch_bittensor_base(monkeypatch)
    contact = FakeSubtensorContact()
    monkeypatch.setattr(
        'bt_ddos_shield_client.turbobt.shielded_bittensor.get_contact_instance',
        lambda **_: contact,
    )

    bittensor = ShieldedBittensor(
        'test',
        wallet=make_wallet(),
        ddos_shield_netuid=7,
        ddos_shield_options=ShieldMetagraphOptions(certificate_path=str(tmp_path / 'validator.pem')),
    )

    async with bittensor:
        certificate = EDDSACertificateManager.load_certificate(str(tmp_path / 'validator.pem'))
        with aioresponses() as mocked:
            mocked.get(
                'http://198.51.100.50:5050/shield_manifest.json',
                status=200,
                body=build_manifest_body(certificate.public_key, '203.0.113.44:4040'),
            )
            neurons = await bittensor.subnet(7).list_neurons()

    assert neurons[0].axon_info.ip == '203.0.113.44'
    assert neurons[0].axon_info.port == 4040


@pytest.mark.asyncio
async def test_shielded_bittensor_keeps_original_endpoint_when_manifest_fails(monkeypatch, tmp_path):
    _patch_bittensor_base(monkeypatch)
    contact = FakeSubtensorContact()
    monkeypatch.setattr(
        'bt_ddos_shield_client.turbobt.shielded_bittensor.get_contact_instance',
        lambda **_: contact,
    )

    bittensor = ShieldedBittensor(
        'test',
        wallet=make_wallet(),
        ddos_shield_netuid=7,
        ddos_shield_options=ShieldMetagraphOptions(certificate_path=str(tmp_path / 'validator.pem')),
    )

    async with bittensor:
        with aioresponses() as mocked:
            mocked.get(
                'http://198.51.100.50:5050/shield_manifest.json',
                status=404,
            )
            neurons = await bittensor.subnet(7).list_neurons()

    assert neurons[0].axon_info.ip == '198.51.100.50'
    assert neurons[0].axon_info.port == 5050


def test_shielded_subnet_reference_is_public():
    assert ShieldedSubnetReference.__name__ == 'ShieldedSubnetReference'
