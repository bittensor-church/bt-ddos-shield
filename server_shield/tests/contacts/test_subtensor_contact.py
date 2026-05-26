from __future__ import annotations

from numbers import Integral

import pytest
from bittensor.core.extrinsics.serving import serve_extrinsic

from server_shield.subtensor_contact import BittensorSubtensorContact
from tests.library.contacts import start_local_subtensor_env


VALIDATOR_1_PUBLIC_KEY = "19cbdfa697f07f27af8bb280bcee651697f0423ee2ba8529fb4e4000036cb134"
VALIDATOR_2_PUBLIC_KEY = "23d3a4c67df00c8b65d287f492eed457b4ada91fb8016f9a83077a3db879c2f7"
MALFORMED_CERTIFICATE = bytes([1])


def _publish_certificate_bytes(subtensor, wallet, netuid: int, certificate: bytes) -> None:
    serve_extrinsic(
        subtensor,
        wallet,
        "1.1.1.1",
        1,
        0,
        netuid,
        certificate=certificate,  # type: ignore[arg-type]
        placeholder1=0,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )


def _publish_certificate(subtensor, wallet, netuid: int, public_key_hex: str) -> None:
    _publish_certificate_bytes(
        subtensor,
        wallet,
        netuid,
        bytes([1]) + bytes.fromhex(public_key_hex),
    )


def _normalize_payload_value(value: object) -> object:
    if isinstance(value, bytes | bytearray):
        return bytes(value).hex()
    if isinstance(value, list | tuple) and value and all(isinstance(item, Integral) for item in value):
        return bytes(int(item) for item in value).hex()
    if isinstance(value, list):
        return [_normalize_payload_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_payload_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_payload_value(item) for key, item in value.items()}
    return value


def _record_to_dict(record) -> dict[str, object]:
    if record.certificate_payload is None:
        payload = None
    else:
        payload = _normalize_payload_value(record.certificate_payload)

    return {
        "hotkey": record.hotkey,
        "certificate_payload": payload,
    }


@pytest.mark.subtensor_integration
def test_subtensor_contact_lists_registered_validator_certificates_across_mixed_states(
    subtensor,
    ws_endpoint,
    alice_wallet,
    validator_wallet,
    validator_wallet_2,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    assert sorted(
        (_record_to_dict(record) for record in contact.list_validator_certificates(netuid=netuid)),
        key=lambda record: str(record["hotkey"]),
    ) == sorted(
        [
            {
                "hotkey": alice_wallet.hotkey.ss58_address,
                "certificate_payload": None,
            },
            {
                "hotkey": validator_wallet.hotkey.ss58_address,
                "certificate_payload": None,
            },
            {
                "hotkey": validator_wallet_2.hotkey.ss58_address,
                "certificate_payload": None,
            },
        ],
        key=lambda record: str(record["hotkey"]),
    )

    _publish_certificate(subtensor, validator_wallet, netuid, VALIDATOR_1_PUBLIC_KEY)
    assert sorted(
        (_record_to_dict(record) for record in contact.list_validator_certificates(netuid=netuid)),
        key=lambda record: str(record["hotkey"]),
    ) == sorted(
        [
            {
                "hotkey": alice_wallet.hotkey.ss58_address,
                "certificate_payload": None,
            },
            {
                "hotkey": validator_wallet.hotkey.ss58_address,
                "certificate_payload": {
                    "algorithm": 1,
                    "public_key": [VALIDATOR_1_PUBLIC_KEY],
                },
            },
            {
                "hotkey": validator_wallet_2.hotkey.ss58_address,
                "certificate_payload": None,
            },
        ],
        key=lambda record: str(record["hotkey"]),
    )

    _publish_certificate(subtensor, validator_wallet_2, netuid, VALIDATOR_2_PUBLIC_KEY)
    assert sorted(
        (_record_to_dict(record) for record in contact.list_validator_certificates(netuid=netuid)),
        key=lambda record: str(record["hotkey"]),
    ) == sorted(
        [
            {
                "hotkey": alice_wallet.hotkey.ss58_address,
                "certificate_payload": None,
            },
            {
                "hotkey": validator_wallet.hotkey.ss58_address,
                "certificate_payload": {
                    "algorithm": 1,
                    "public_key": [VALIDATOR_1_PUBLIC_KEY],
                },
            },
            {
                "hotkey": validator_wallet_2.hotkey.ss58_address,
                "certificate_payload": {
                    "algorithm": 1,
                    "public_key": [VALIDATOR_2_PUBLIC_KEY],
                },
            },
        ],
        key=lambda record: str(record["hotkey"]),
    )

    malformed_env = start_local_subtensor_env()
    try:
        malformed_contact = BittensorSubtensorContact(malformed_env.ws_endpoint)
        _publish_certificate(
            malformed_env.subtensor,
            malformed_env.validator_wallet,
            malformed_env.netuid,
            VALIDATOR_1_PUBLIC_KEY,
        )
        _publish_certificate_bytes(
            malformed_env.subtensor,
            malformed_env.validator_wallet_2,
            malformed_env.netuid,
            MALFORMED_CERTIFICATE,
        )

        assert sorted(
            (
                _record_to_dict(record)
                for record in malformed_contact.list_validator_certificates(netuid=malformed_env.netuid)
            ),
            key=lambda record: str(record["hotkey"]),
        ) == sorted(
            [
                {
                    "hotkey": malformed_env.alice_wallet.hotkey.ss58_address,
                    "certificate_payload": None,
                },
                {
                    "hotkey": malformed_env.validator_wallet.hotkey.ss58_address,
                    "certificate_payload": {
                        "algorithm": 1,
                        "public_key": [VALIDATOR_1_PUBLIC_KEY],
                    },
                },
                {
                    "hotkey": malformed_env.validator_wallet_2.hotkey.ss58_address,
                    "certificate_payload": {
                        "algorithm": 1,
                        "public_key": [[]],
                    },
                },
            ],
            key=lambda record: str(record["hotkey"]),
        )
    finally:
        malformed_env.cleanup()


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
):
    axon_env = start_local_subtensor_env()
    try:
        contact = BittensorSubtensorContact(axon_env.ws_endpoint)

        published = contact.publish_axon(
            wallet=axon_env.validator_wallet,
            netuid=axon_env.netuid,
            ip="203.0.113.77",
            port=19001,
        )
        after = contact.get_neuron_axon(
            hotkey_ss58=axon_env.validator_wallet.hotkey.ss58_address,
            netuid=axon_env.netuid,
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
    finally:
        axon_env.cleanup()
