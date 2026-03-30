from __future__ import annotations

from dataclasses import dataclass

from aioresponses import aioresponses
import pytest

from bt_ddos_shield_client import ShieldMetagraph
from bt_ddos_shield_client.certificates import EDDSACertificateManager
from bt_ddos_shield_client.shield_metagraph import ShieldMetagraphOptions
from bt_ddos_shield_client.tests.fakes import FakeSubtensorContact, build_manifest_body, make_wallet


@dataclass
class _FakeAxon:
    hotkey: str
    ip: str
    port: int


def _patch_metagraph_base(monkeypatch):
    def fake_init(self, netuid, network='finney', lite=True, sync=True, subtensor=None):
        self.netuid = netuid
        self.network = network
        self.lite = lite
        self.subtensor = subtensor
        self.axons = [_FakeAxon(hotkey='miner-hotkey', ip='198.51.100.20', port=8080)]

    def fake_sync(self, block=None, lite=None, subtensor=None):
        return None

    monkeypatch.setattr('bt_ddos_shield_client.shield_metagraph.Metagraph.__init__', fake_init)
    monkeypatch.setattr('bt_ddos_shield_client.shield_metagraph.Metagraph.sync', fake_sync)


def test_shield_metagraph_uses_option_certificate_path(monkeypatch, tmp_path):
    _patch_metagraph_base(monkeypatch)
    contact = FakeSubtensorContact()
    monkeypatch.setattr(
        'bt_ddos_shield_client.shield_metagraph.get_contact_instance',
        lambda **_: contact,
    )

    certificate_path = tmp_path / 'from-options.pem'
    ShieldMetagraph(
        wallet=make_wallet(),
        netuid=7,
        subtensor=object(),
        sync=False,
        options=ShieldMetagraphOptions(certificate_path=str(certificate_path)),
    )

    assert certificate_path.exists()
    assert len(contact.uploads) == 1


def test_shield_metagraph_uses_env_certificate_path(monkeypatch, tmp_path):
    _patch_metagraph_base(monkeypatch)
    contact = FakeSubtensorContact()
    monkeypatch.setattr(
        'bt_ddos_shield_client.shield_metagraph.get_contact_instance',
        lambda **_: contact,
    )
    env_path = tmp_path / 'from-env.pem'
    monkeypatch.setenv('VALIDATOR_SHIELD_CERTIFICATE_PATH', str(env_path))

    ShieldMetagraph(
        wallet=make_wallet(),
        netuid=7,
        subtensor=object(),
        sync=False,
    )

    assert env_path.exists()
    assert len(contact.uploads) == 1


def test_shield_metagraph_uses_default_certificate_path(monkeypatch, tmp_path):
    _patch_metagraph_base(monkeypatch)
    contact = FakeSubtensorContact()
    monkeypatch.setattr(
        'bt_ddos_shield_client.shield_metagraph.get_contact_instance',
        lambda **_: contact,
    )
    monkeypatch.delenv('VALIDATOR_SHIELD_CERTIFICATE_PATH', raising=False)
    monkeypatch.chdir(tmp_path)

    ShieldMetagraph(
        wallet=make_wallet(),
        netuid=7,
        subtensor=object(),
        sync=False,
    )

    assert (tmp_path / 'validator_cert.pem').exists()
    assert len(contact.uploads) == 1


def test_shield_metagraph_skips_upload_when_chain_key_matches(monkeypatch, tmp_path):
    _patch_metagraph_base(monkeypatch)
    bootstrap = FakeSubtensorContact()
    monkeypatch.setattr(
        'bt_ddos_shield_client.shield_metagraph.get_contact_instance',
        lambda **_: bootstrap,
    )
    certificate_path = tmp_path / 'validator.pem'
    metagraph = ShieldMetagraph(
        wallet=make_wallet(),
        netuid=7,
        subtensor=object(),
        sync=False,
        options=ShieldMetagraphOptions(certificate_path=str(certificate_path)),
    )
    certificate = EDDSACertificateManager.load_certificate(str(certificate_path))
    contact = FakeSubtensorContact(own_public_key=certificate.public_key)
    monkeypatch.setattr(
        'bt_ddos_shield_client.shield_metagraph.get_contact_instance',
        lambda **_: contact,
    )

    ShieldMetagraph(
        wallet=make_wallet(),
        netuid=7,
        subtensor=object(),
        sync=False,
        options=ShieldMetagraphOptions(certificate_path=str(certificate_path)),
    )

    assert contact.uploads == []


def test_shield_metagraph_retries_failed_certificate_upload_once(monkeypatch, tmp_path):
    _patch_metagraph_base(monkeypatch)
    contact = FakeSubtensorContact(upload_failures_remaining=1)
    monkeypatch.setattr(
        'bt_ddos_shield_client.shield_metagraph.get_contact_instance',
        lambda **_: contact,
    )

    ShieldMetagraph(
        wallet=make_wallet(),
        netuid=7,
        subtensor=object(),
        sync=False,
        options=ShieldMetagraphOptions(certificate_path=str(tmp_path / 'validator.pem')),
    )

    assert len(contact.uploads) == 1


def test_shield_metagraph_replaces_visible_endpoint_when_manifest_resolves(monkeypatch, tmp_path):
    _patch_metagraph_base(monkeypatch)
    contact = FakeSubtensorContact()
    monkeypatch.setattr(
        'bt_ddos_shield_client.shield_metagraph.get_contact_instance',
        lambda **_: contact,
    )
    metagraph = ShieldMetagraph(
        wallet=make_wallet(),
        netuid=7,
        subtensor=object(),
        sync=False,
        options=ShieldMetagraphOptions(certificate_path=str(tmp_path / 'validator.pem')),
    )
    certificate = EDDSACertificateManager.load_certificate(str(tmp_path / 'validator.pem'))

    with aioresponses() as mocked:
        mocked.get(
            'http://198.51.100.20:8080/shield_manifest.json',
            status=200,
            body=build_manifest_body(certificate.public_key, '203.0.113.77:3030'),
        )
        metagraph.sync()

    assert metagraph.axons[0].ip == '203.0.113.77'
    assert metagraph.axons[0].port == 3030


@pytest.mark.parametrize(
    ('response_kwargs', 'body'),
    [
        ({'status': 404}, None),
        ({'status': 200}, b'not-json'),
        ({'status': 200}, None),
    ],
)
def test_shield_metagraph_keeps_original_endpoint_on_manifest_failure(
    monkeypatch,
    tmp_path,
    response_kwargs,
    body,
):
    _patch_metagraph_base(monkeypatch)
    contact = FakeSubtensorContact()
    monkeypatch.setattr(
        'bt_ddos_shield_client.shield_metagraph.get_contact_instance',
        lambda **_: contact,
    )
    metagraph = ShieldMetagraph(
        wallet=make_wallet(),
        netuid=7,
        subtensor=object(),
        sync=False,
        options=ShieldMetagraphOptions(certificate_path=str(tmp_path / 'validator.pem')),
    )
    certificate = EDDSACertificateManager.load_certificate(str(tmp_path / 'validator.pem'))

    if body is None and response_kwargs['status'] == 200:
        body = build_manifest_body(
            certificate.public_key,
            '203.0.113.77:3030',
            validator_hotkey='other-hotkey',
        )

    with aioresponses() as mocked:
        mocked.get(
            'http://198.51.100.20:8080/shield_manifest.json',
            body=body,
            **response_kwargs,
        )
        metagraph.sync()

    assert metagraph.axons[0].ip == '198.51.100.20'
    assert metagraph.axons[0].port == 8080
