from __future__ import annotations

import asyncio

from aioresponses import aioresponses
from freezegun import freeze_time
import pytest

from bt_ddos_shield_client import ShieldMetagraph
from bt_ddos_shield_client.shield_metagraph import ShieldMetagraphOptions
from tests.fakes import build_manifest_body, build_manifest_body_from_blob, make_bittensor_neuron, make_wallet
from tests.fixtures import certificate_fixture_path, load_certificate_fixture


def _certificate_path(tmp_path, fixture_name: str = 'validator_a.pem') -> str:
    destination = tmp_path / 'validator.pem'
    destination.write_text(certificate_fixture_path(fixture_name).read_text())
    return str(destination)


def _make_metagraph(tmp_path, fixture_name: str = 'validator_a.pem') -> ShieldMetagraph:
    return ShieldMetagraph(
        wallet=make_wallet(),
        netuid=7,
        subtensor=object(),
        sync=False,
        options=ShieldMetagraphOptions(certificate_path=_certificate_path(tmp_path, fixture_name)),
    )


def _manifest_url(ip: str, port: int) -> str:
    return f'http://{ip}:{port}/shield_manifest.json'


@freeze_time('2026-03-31 12:00:00')
def test_shield_metagraph_uploads_when_on_chain_cert_is_missing(patched_bittensor_contact, tmp_path):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey='miner-hotkey', ip='198.51.100.20', port=8080)]
    )
    patched_bittensor_contact.set_own_certificate(None)
    metagraph = _make_metagraph(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.20', 8080), status=404)
        metagraph.sync()

    assert [call.method for call in patched_bittensor_contact.calls] == [
        'sync_metagraph',
        'get_own_public_key',
        'upload_public_key',
    ]
    assert patched_bittensor_contact.calls[-1].public_key == certificate.public_key


@freeze_time('2026-03-31 12:00:00')
def test_shield_metagraph_uploads_when_on_chain_cert_mismatches(patched_bittensor_contact, tmp_path):
    local_certificate = load_certificate_fixture('validator_a.pem')
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey='miner-hotkey', ip='198.51.100.21', port=8081)]
    )
    patched_bittensor_contact.set_own_certificate(load_certificate_fixture('validator_b.pem').public_key)
    metagraph = _make_metagraph(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.21', 8081), status=404)
        metagraph.sync()

    assert [call.method for call in patched_bittensor_contact.calls] == [
        'sync_metagraph',
        'get_own_public_key',
        'upload_public_key',
    ]
    assert patched_bittensor_contact.calls[-1].public_key == local_certificate.public_key


@freeze_time('2026-03-31 12:00:00')
def test_shield_metagraph_skips_upload_when_on_chain_cert_matches(patched_bittensor_contact, tmp_path):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey='miner-hotkey', ip='198.51.100.22', port=8082)]
    )
    patched_bittensor_contact.set_own_certificate(certificate.public_key)
    metagraph = _make_metagraph(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.22', 8082), status=404)
        metagraph.sync()

    assert [call.method for call in patched_bittensor_contact.calls] == [
        'sync_metagraph',
        'get_own_public_key',
    ]


def test_shield_metagraph_reconciler_uses_mutated_mock_state_after_ttl(
    patched_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    other_certificate = load_certificate_fixture('validator_b.pem')
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey='miner-hotkey', ip='198.51.100.23', port=8083)]
    )
    metagraph = _make_metagraph(tmp_path)

    with freeze_time('2026-03-31 12:00:00') as frozen:
        patched_bittensor_contact.set_own_certificate(other_certificate.public_key)
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.23', 8083), status=404)
            metagraph.sync()

        assert [call.method for call in patched_bittensor_contact.calls] == [
            'sync_metagraph',
            'get_own_public_key',
            'upload_public_key',
        ]

        patched_bittensor_contact.reset_calls()
        patched_bittensor_contact.set_own_certificate(certificate.public_key)
        frozen.tick(301)
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.23', 8083), status=404)
            metagraph.sync()

    assert [call.method for call in patched_bittensor_contact.calls] == [
        'sync_metagraph',
        'get_own_public_key',
    ]


def test_shield_metagraph_skips_reconciliation_inside_ttl(patched_bittensor_contact, tmp_path):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey='miner-hotkey', ip='198.51.100.24', port=8084)]
    )
    patched_bittensor_contact.set_own_certificate(certificate.public_key)
    metagraph = _make_metagraph(tmp_path)

    with freeze_time('2026-03-31 12:00:00'):
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.24', 8084), status=404)
            metagraph.sync()

        patched_bittensor_contact.reset_calls()
        patched_bittensor_contact.set_own_certificate(load_certificate_fixture('validator_b.pem').public_key)
        patched_bittensor_contact.set_upload_behavior(RuntimeError('upload should not happen inside ttl'))
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.24', 8084), status=404)
            metagraph.sync()

    assert [call.method for call in patched_bittensor_contact.calls] == ['sync_metagraph']


def test_shield_metagraph_rechecks_chain_after_ttl_expires(patched_bittensor_contact, tmp_path):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey='miner-hotkey', ip='198.51.100.25', port=8085)]
    )
    patched_bittensor_contact.set_own_certificate(certificate.public_key)
    metagraph = _make_metagraph(tmp_path)

    with freeze_time('2026-03-31 12:00:00') as frozen:
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.25', 8085), status=404)
            metagraph.sync()

        patched_bittensor_contact.reset_calls()
        frozen.tick(301)
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.25', 8085), status=404)
            metagraph.sync()

    assert [call.method for call in patched_bittensor_contact.calls] == [
        'sync_metagraph',
        'get_own_public_key',
    ]


def test_shield_metagraph_rewrites_mixed_manifest_results(patched_bittensor_contact, tmp_path):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_bittensor_contact.set_metagraph_sync(
        [
            make_bittensor_neuron(hotkey='miner-a', ip='198.51.100.30', port=8030, uid=0),
            make_bittensor_neuron(hotkey='miner-b', ip='198.51.100.31', port=8031, uid=1),
            make_bittensor_neuron(hotkey='miner-c', ip='198.51.100.32', port=8032, uid=2),
        ]
    )
    patched_bittensor_contact.set_own_certificate(certificate.public_key)
    metagraph = _make_metagraph(tmp_path)

    with aioresponses() as mocked:
        mocked.get(
            _manifest_url('198.51.100.30', 8030),
            status=200,
            body=build_manifest_body(certificate.public_key, '203.0.113.30:3030'),
        )
        mocked.get(_manifest_url('198.51.100.31', 8031), status=404)
        mocked.get(
            _manifest_url('198.51.100.32', 8032),
            status=200,
            body=build_manifest_body(certificate.public_key, '203.0.113.32:3032'),
        )
        metagraph.sync()

    assert [(axon.hotkey, axon.ip, axon.port) for axon in metagraph.axons] == [
        ('miner-a', '203.0.113.30', 3030),
        ('miner-b', '198.51.100.31', 8031),
        ('miner-c', '203.0.113.32', 3032),
    ]


@pytest.mark.parametrize(
    'manifest_kwargs',
    [
        {'exception': asyncio.TimeoutError()},
        {'status': 500},
        {'status': 200, 'body': b'not-json'},
    ],
)
def test_shield_metagraph_keeps_original_endpoint_on_manifest_failures(
    patched_bittensor_contact,
    tmp_path,
    manifest_kwargs,
):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey='miner-hotkey', ip='198.51.100.40', port=8040)]
    )
    patched_bittensor_contact.set_own_certificate(certificate.public_key)
    metagraph = _make_metagraph(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.40', 8040), **manifest_kwargs)
        metagraph.sync()

    assert [(axon.ip, axon.port) for axon in metagraph.axons] == [('198.51.100.40', 8040)]


@pytest.mark.parametrize(
    ('body',),
    [
        (lambda certificate: build_manifest_body(certificate.public_key, '203.0.113.99:3099', validator_hotkey='other-hotkey'),),
        (lambda _certificate: build_manifest_body_from_blob(b'not-ecies-ciphertext'),),
        (lambda _certificate: build_manifest_body(load_certificate_fixture('validator_b.pem').public_key, '203.0.113.99:3099'),),
        (lambda certificate: build_manifest_body(certificate.public_key, 'not-a-socket-address'),),
    ],
)
def test_shield_metagraph_keeps_original_endpoint_on_manifest_content_failures(
    patched_bittensor_contact,
    tmp_path,
    body,
):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey='miner-hotkey', ip='198.51.100.43', port=8043)]
    )
    patched_bittensor_contact.set_own_certificate(certificate.public_key)
    metagraph = _make_metagraph(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.43', 8043), status=200, body=body(certificate))
        metagraph.sync()

    assert [(axon.ip, axon.port) for axon in metagraph.axons] == [('198.51.100.43', 8043)]


def test_shield_metagraph_raises_when_reading_on_chain_cert_fails(patched_bittensor_contact, tmp_path):
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey='miner-hotkey', ip='198.51.100.41', port=8041)]
    )
    patched_bittensor_contact.set_own_certificate(None, exception=RuntimeError('read failed'))
    metagraph = _make_metagraph(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.41', 8041), status=404)
        with pytest.raises(RuntimeError, match='read failed'):
            metagraph.sync()

    assert [call.method for call in patched_bittensor_contact.calls] == [
        'sync_metagraph',
        'get_own_public_key',
    ]


def test_shield_metagraph_raises_when_uploading_cert_fails(patched_bittensor_contact, tmp_path):
    patched_bittensor_contact.set_metagraph_sync(
        [make_bittensor_neuron(hotkey='miner-hotkey', ip='198.51.100.42', port=8042)]
    )
    patched_bittensor_contact.set_own_certificate(None)
    patched_bittensor_contact.set_upload_behavior(RuntimeError('upload failed'))
    metagraph = _make_metagraph(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.42', 8042), status=404)
        with pytest.raises(RuntimeError, match='upload failed'):
            metagraph.sync()

    assert [call.method for call in patched_bittensor_contact.calls] == [
        'sync_metagraph',
        'get_own_public_key',
        'upload_public_key',
    ]
