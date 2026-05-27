from __future__ import annotations

import base64

import pytest

from bt_ddos_shield_client import ed25519_ecies


RECEIVER_PRIVATE_KEY_HEX = "00" * 32
RECEIVER_PUBLIC_KEY_HEX = "3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048a18b59da29"
SECOND_PRIVATE_KEY_HEX = "01" * 32
SECOND_PUBLIC_KEY_HEX = "8a88e3dd7409f195fd52db2d3cba5d72ca6709bf1d94121bf3748801b40f6f5c"
PLAINTEXT = b"validator-a.shield.example.com:9001"
SERVER_CONTRACT_PAYLOAD_B64 = (
    "iojj3XQJ8ZX9UtstPLpdcspnCb8dlBIb83SIAbQPb1wCAgICAgICAgICAgICAgIC7GnxP0NCwWvPk"
    "VafJ/8lOWa+ll93w315INR2Jz34UyQ/UgyGxcty7En0GY5xs5kNaU30"
)


def test_public_key_from_private_key_matches_existing_eciespy_values() -> None:
    assert ed25519_ecies.public_key_from_private_key(RECEIVER_PRIVATE_KEY_HEX) == RECEIVER_PUBLIC_KEY_HEX
    assert ed25519_ecies.public_key_from_private_key(SECOND_PRIVATE_KEY_HEX) == SECOND_PUBLIC_KEY_HEX
    assert ed25519_ecies.public_key_from_private_key(f"0x{SECOND_PRIVATE_KEY_HEX}") == SECOND_PUBLIC_KEY_HEX


def test_decrypts_server_manifest_contract_vector() -> None:
    payload = base64.b64decode(SERVER_CONTRACT_PAYLOAD_B64)

    assert ed25519_ecies.decrypt(RECEIVER_PRIVATE_KEY_HEX, payload) == PLAINTEXT


def test_encrypt_round_trip_and_wire_layout() -> None:
    encrypted = ed25519_ecies.encrypt(RECEIVER_PUBLIC_KEY_HEX, PLAINTEXT)

    assert ed25519_ecies.decrypt(RECEIVER_PRIVATE_KEY_HEX, encrypted) == PLAINTEXT
    assert len(encrypted) == (
        ed25519_ecies.EPHEMERAL_PUBLIC_KEY_BYTES
        + ed25519_ecies.AES_GCM_NONCE_BYTES
        + ed25519_ecies.AES_GCM_TAG_BYTES
        + len(PLAINTEXT)
    )
    assert encrypted[: ed25519_ecies.EPHEMERAL_PUBLIC_KEY_BYTES] != bytes.fromhex(RECEIVER_PUBLIC_KEY_HEX)


def test_generate_private_key_hex_returns_public_key_derivable_secret() -> None:
    private_key = ed25519_ecies.generate_private_key_hex()

    assert len(private_key) == ed25519_ecies.PRIVATE_KEY_BYTES * 2
    assert len(ed25519_ecies.public_key_from_private_key(private_key)) == ed25519_ecies.PUBLIC_KEY_BYTES * 2


@pytest.mark.parametrize(
    ("private_key", "payload"),
    [
        ("not-hex", b"payload"),
        (RECEIVER_PRIVATE_KEY_HEX, b"too-short"),
    ],
)
def test_decrypt_rejects_invalid_inputs(private_key: str, payload: bytes) -> None:
    with pytest.raises(Exception):
        ed25519_ecies.decrypt(private_key, payload)
