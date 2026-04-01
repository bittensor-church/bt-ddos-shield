from __future__ import annotations

import asyncio

from aioresponses import aioresponses
from freezegun import freeze_time
import pytest

from bt_ddos_shield_client.shield_metagraph import ShieldMetagraphOptions
from tests.fakes import build_manifest_body, build_manifest_body_from_blob, make_turbobt_neuron, make_wallet
from tests.fixtures import certificate_fixture_path, load_certificate_fixture

pytest.importorskip('turbobt')

from bt_ddos_shield_client.shielded_turbobt import ShieldedBittensor, ShieldedSubnetReference


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


def _manifest_url(ip: str, port: int) -> str:
    return f'http://{ip}:{port}/shield_manifest.json'


@freeze_time('2026-03-31 12:00:00')
@pytest.mark.asyncio
async def test_shielded_bittensor_uploads_when_on_chain_cert_is_missing(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey='miner-hotkey', ip='198.51.100.50', port=5050)]
    )
    patched_turbo_bittensor_contact.set_own_certificate(None)
    bittensor = _make_bittensor(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.50', 5050), status=404)
        await bittensor.subnet(7).list_neurons()

    assert [call.method for call in patched_turbo_bittensor_contact.calls] == [
        'get_own_public_key',
        'upload_public_key',
        'list_neurons',
    ]
    assert patched_turbo_bittensor_contact.calls[1].public_key == certificate.public_key


@freeze_time('2026-03-31 12:00:00')
@pytest.mark.asyncio
async def test_shielded_bittensor_uploads_when_on_chain_cert_mismatches(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    local_certificate = load_certificate_fixture('validator_a.pem')
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey='miner-hotkey', ip='198.51.100.51', port=5051)]
    )
    patched_turbo_bittensor_contact.set_own_certificate(load_certificate_fixture('validator_b.pem').public_key)
    bittensor = _make_bittensor(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.51', 5051), status=404)
        await bittensor.subnet(7).list_neurons()

    assert [call.method for call in patched_turbo_bittensor_contact.calls] == [
        'get_own_public_key',
        'upload_public_key',
        'list_neurons',
    ]
    assert patched_turbo_bittensor_contact.calls[1].public_key == local_certificate.public_key


@freeze_time('2026-03-31 12:00:00')
@pytest.mark.asyncio
async def test_shielded_bittensor_skips_upload_when_on_chain_cert_matches(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey='miner-hotkey', ip='198.51.100.52', port=5052)]
    )
    patched_turbo_bittensor_contact.set_own_certificate(certificate.public_key)
    bittensor = _make_bittensor(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.52', 5052), status=404)
        await bittensor.subnet(7).list_neurons()

    assert [call.method for call in patched_turbo_bittensor_contact.calls] == [
        'get_own_public_key',
        'list_neurons',
    ]


@pytest.mark.asyncio
async def test_shielded_bittensor_uses_mutated_mock_state_after_ttl(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    other_certificate = load_certificate_fixture('validator_b.pem')
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey='miner-hotkey', ip='198.51.100.53', port=5053)]
    )
    bittensor = _make_bittensor(tmp_path)

    with freeze_time('2026-03-31 12:00:00') as frozen:
        patched_turbo_bittensor_contact.set_own_certificate(other_certificate.public_key)
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.53', 5053), status=404)
            await bittensor.subnet(7).list_neurons()

        assert [call.method for call in patched_turbo_bittensor_contact.calls] == [
            'get_own_public_key',
            'upload_public_key',
            'list_neurons',
        ]

        patched_turbo_bittensor_contact.reset_calls()
        patched_turbo_bittensor_contact.set_own_certificate(certificate.public_key)
        frozen.tick(301)
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.53', 5053), status=404)
            await bittensor.subnet(7).list_neurons()

    assert [call.method for call in patched_turbo_bittensor_contact.calls] == [
        'get_own_public_key',
        'list_neurons',
    ]


@pytest.mark.asyncio
async def test_shielded_bittensor_skips_reconciliation_inside_ttl(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey='miner-hotkey', ip='198.51.100.54', port=5054)]
    )
    patched_turbo_bittensor_contact.set_own_certificate(certificate.public_key)
    bittensor = _make_bittensor(tmp_path)

    with freeze_time('2026-03-31 12:00:00'):
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.54', 5054), status=404)
            await bittensor.subnet(7).list_neurons()

        patched_turbo_bittensor_contact.reset_calls()
        patched_turbo_bittensor_contact.set_own_certificate(load_certificate_fixture('validator_b.pem').public_key)
        patched_turbo_bittensor_contact.set_upload_behavior(RuntimeError('upload should not happen inside ttl'))
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.54', 5054), status=404)
            await bittensor.subnet(7).list_neurons()

    assert [call.method for call in patched_turbo_bittensor_contact.calls] == ['list_neurons']


@pytest.mark.asyncio
async def test_shielded_bittensor_rechecks_chain_after_ttl_expires(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey='miner-hotkey', ip='198.51.100.55', port=5055)]
    )
    patched_turbo_bittensor_contact.set_own_certificate(certificate.public_key)
    bittensor = _make_bittensor(tmp_path)

    with freeze_time('2026-03-31 12:00:00') as frozen:
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.55', 5055), status=404)
            await bittensor.subnet(7).list_neurons()

        patched_turbo_bittensor_contact.reset_calls()
        frozen.tick(301)
        with aioresponses() as mocked:
            mocked.get(_manifest_url('198.51.100.55', 5055), status=404)
            await bittensor.subnet(7).list_neurons()

    assert [call.method for call in patched_turbo_bittensor_contact.calls] == [
        'get_own_public_key',
        'list_neurons',
    ]


@pytest.mark.asyncio
async def test_shielded_bittensor_rewrites_mixed_manifest_results(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_turbo_bittensor_contact.set_neuron_listing(
        [
            make_turbobt_neuron(hotkey='miner-a', ip='198.51.100.60', port=5060, uid=0),
            make_turbobt_neuron(hotkey='miner-b', ip='198.51.100.61', port=5061, uid=1),
            make_turbobt_neuron(hotkey='miner-c', ip='198.51.100.62', port=5062, uid=2),
        ]
    )
    patched_turbo_bittensor_contact.set_own_certificate(certificate.public_key)
    bittensor = _make_bittensor(tmp_path)

    with aioresponses() as mocked:
        mocked.get(
            _manifest_url('198.51.100.60', 5060),
            status=200,
            body=build_manifest_body(certificate.public_key, '203.0.113.60:3060'),
        )
        mocked.get(_manifest_url('198.51.100.61', 5061), status=404)
        mocked.get(
            _manifest_url('198.51.100.62', 5062),
            status=200,
            body=build_manifest_body(certificate.public_key, '203.0.113.62:3062'),
        )
        neurons = await bittensor.subnet(7).list_neurons()

    assert [(neuron.hotkey, str(neuron.axon_info.ip), neuron.axon_info.port) for neuron in neurons] == [
        ('miner-a', '203.0.113.60', 3060),
        ('miner-b', '198.51.100.61', 5061),
        ('miner-c', '203.0.113.62', 3062),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'manifest_kwargs',
    [
        {'exception': asyncio.TimeoutError()},
        {'status': 500},
        {'status': 200, 'body': b'not-json'},
    ],
)
async def test_shielded_bittensor_keeps_original_endpoint_on_manifest_failures(
    patched_turbo_bittensor_contact,
    tmp_path,
    manifest_kwargs,
):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey='miner-hotkey', ip='198.51.100.63', port=5063)]
    )
    patched_turbo_bittensor_contact.set_own_certificate(certificate.public_key)
    bittensor = _make_bittensor(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.63', 5063), **manifest_kwargs)
        neurons = await bittensor.subnet(7).list_neurons()

    assert [(str(neurons[0].axon_info.ip), neurons[0].axon_info.port)] == [('198.51.100.63', 5063)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('body',),
    [
        (lambda certificate: build_manifest_body(certificate.public_key, '203.0.113.99:3099', validator_hotkey='other-hotkey'),),
        (lambda _certificate: build_manifest_body_from_blob(b'not-ecies-ciphertext'),),
        (lambda _certificate: build_manifest_body(load_certificate_fixture('validator_b.pem').public_key, '203.0.113.99:3099'),),
        (lambda certificate: build_manifest_body(certificate.public_key, 'not-a-socket-address'),),
    ],
)
async def test_shielded_bittensor_keeps_original_endpoint_on_manifest_content_failures(
    patched_turbo_bittensor_contact,
    tmp_path,
    body,
):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey='miner-hotkey', ip='198.51.100.67', port=5067)]
    )
    patched_turbo_bittensor_contact.set_own_certificate(certificate.public_key)
    bittensor = _make_bittensor(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.67', 5067), status=200, body=body(certificate))
        neurons = await bittensor.subnet(7).list_neurons()

    assert [(str(neurons[0].axon_info.ip), neurons[0].axon_info.port)] == [('198.51.100.67', 5067)]


@pytest.mark.asyncio
async def test_shielded_subnet_reference_from_bittensor_works_end_to_end(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    certificate = load_certificate_fixture('validator_a.pem')
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey='miner-hotkey', ip='198.51.100.64', port=5064)]
    )
    patched_turbo_bittensor_contact.set_own_certificate(certificate.public_key)
    bittensor = _make_bittensor(tmp_path)
    subnet = ShieldedSubnetReference.from_bittensor(
        bittensor,
        7,
        wallet=make_wallet(),
        ddos_shield_options=ShieldMetagraphOptions(certificate_path=_certificate_path(tmp_path)),
    )

    with aioresponses() as mocked:
        mocked.get(
            _manifest_url('198.51.100.64', 5064),
            status=200,
            body=build_manifest_body(certificate.public_key, '203.0.113.64:3064'),
        )
        neurons = await subnet.list_neurons()

    assert [(neuron.hotkey, str(neuron.axon_info.ip), neuron.axon_info.port) for neuron in neurons] == [
        ('miner-hotkey', '203.0.113.64', 3064),
    ]


def test_shielded_subnet_reference_clone_reuses_helpers_and_swaps_client(tmp_path):
    original = ShieldedSubnetReference.from_bittensor(
        _make_bittensor(tmp_path),
        7,
        wallet=make_wallet(),
        ddos_shield_options=ShieldMetagraphOptions(certificate_path=_certificate_path(tmp_path)),
    )
    new_client = _make_bittensor(tmp_path, fixture_name='validator_b.pem')

    cloned = original.clone(new_client)

    assert cloned is not original
    assert cloned.client is new_client
    assert cloned.client is not original.client
    assert cloned.netuid == original.netuid
    assert cloned.wallet is original.wallet
    assert cloned.ddos_shield_options is original.ddos_shield_options
    assert cloned._contact is original._contact
    assert cloned._shield_client is original._shield_client
    assert cloned._certificate_reconciler is original._certificate_reconciler


@pytest.mark.asyncio
async def test_shielded_bittensor_raises_when_reading_on_chain_cert_fails(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey='miner-hotkey', ip='198.51.100.65', port=5065)]
    )
    patched_turbo_bittensor_contact.set_own_certificate(None, exception=RuntimeError('read failed'))
    bittensor = _make_bittensor(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.65', 5065), status=404)
        with pytest.raises(RuntimeError, match='read failed'):
            await bittensor.subnet(7).list_neurons()

    assert [call.method for call in patched_turbo_bittensor_contact.calls] == ['get_own_public_key']


@pytest.mark.asyncio
async def test_shielded_bittensor_raises_when_uploading_cert_fails(
    patched_turbo_bittensor_contact,
    tmp_path,
):
    patched_turbo_bittensor_contact.set_neuron_listing(
        [make_turbobt_neuron(hotkey='miner-hotkey', ip='198.51.100.66', port=5066)]
    )
    patched_turbo_bittensor_contact.set_own_certificate(None)
    patched_turbo_bittensor_contact.set_upload_behavior(RuntimeError('upload failed'))
    bittensor = _make_bittensor(tmp_path)

    with aioresponses() as mocked:
        mocked.get(_manifest_url('198.51.100.66', 5066), status=404)
        with pytest.raises(RuntimeError, match='upload failed'):
            await bittensor.subnet(7).list_neurons()

    assert [call.method for call in patched_turbo_bittensor_contact.calls] == [
        'get_own_public_key',
        'upload_public_key',
    ]
