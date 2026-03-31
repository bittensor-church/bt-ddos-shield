from __future__ import annotations

import pytest
from Crypto.PublicKey import ECC
from bittensor.core.extrinsics.serving import serve_extrinsic

from server_shield.subtensor_contact import BittensorSubtensorContact


def _valid_public_key_hex() -> str:
    return ECC.generate(curve="ed25519").public_key().export_key(format="raw").hex()


def _publish_certificate(subtensor, wallet, netuid: int, public_key_hex: str) -> None:
    serve_extrinsic(
        subtensor,
        wallet,
        "1.1.1.1",
        1,
        0,
        netuid,
        certificate=bytes([1]) + bytes.fromhex(public_key_hex),  # type: ignore[arg-type]
        placeholder1=0,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )


def _record_to_dict(record) -> dict[str, object]:
    payload = record.certificate_payload
    if payload is None:
        public_key = None
    else:
        raw_public_key = payload["public_key"][0]
        if isinstance(raw_public_key, str):
            public_key = raw_public_key.removeprefix("0x")
        else:
            public_key = bytes(raw_public_key).hex()

    return {
        "hotkey": record.hotkey,
        "public_key": public_key,
    }


@pytest.mark.subtensor_integration
def test_subtensor_contact_lists_registered_validator_certificates(
    subtensor,
    ws_endpoint,
    validator_wallet,
    miner_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)
    validator_public_key = _valid_public_key_hex()
    _publish_certificate(subtensor, validator_wallet, netuid, validator_public_key)

    records = contact.list_validator_certificates(netuid=netuid)

    assert [_record_to_dict(record) for record in records] == [
        {
            "hotkey": validator_wallet.hotkey.ss58_address,
            "public_key": validator_public_key,
        }
    ]


@pytest.mark.subtensor_integration
def test_subtensor_contact_reports_registration_for_registered_hotkey(
    ws_endpoint,
    validator_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    registered = contact.is_hotkey_registered(
        hotkey_ss58=validator_wallet.hotkey.ss58_address,
        netuid=netuid,
    )

    assert registered is True


@pytest.mark.subtensor_integration
def test_subtensor_contact_reads_registered_neuron_axon(
    ws_endpoint,
    validator_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    neuron = contact.get_neuron_axon(
        hotkey_ss58=validator_wallet.hotkey.ss58_address,
        netuid=netuid,
    )

    assert neuron.is_null is False


@pytest.mark.subtensor_integration
def test_subtensor_contact_publishes_and_reads_back_axon_info(
    ws_endpoint,
    validator_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    published = contact.publish_axon(
        wallet=validator_wallet,
        netuid=netuid,
        ip="203.0.113.77",
        port=19001,
    )
    after = contact.get_neuron_axon(
        hotkey_ss58=validator_wallet.hotkey.ss58_address,
        netuid=netuid,
    )

    assert {
        "published": published,
        "axon": {
            "is_null": after.is_null,
            "is_serving": after.is_serving,
            "ip": after.ip,
            "port": after.port,
        },
    } == {
        "published": True,
        "axon": {
            "is_null": False,
            "is_serving": True,
            "ip": "203.0.113.77",
            "port": 19001,
        },
    }
