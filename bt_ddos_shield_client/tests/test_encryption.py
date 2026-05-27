from __future__ import annotations

import pytest

from bt_ddos_shield_client.encryption import DecryptionError, ECIESEncryptionManager, EncryptionError


PRIVATE_KEY_HEX = "00" * 32
PUBLIC_KEY_HEX = "3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048a18b59da29"


def test_encryption_manager_round_trips_with_local_ed25519_ecies() -> None:
    manager = ECIESEncryptionManager()

    encrypted = manager.encrypt(PUBLIC_KEY_HEX, b"203.0.113.10:3010")

    assert manager.decrypt(PRIVATE_KEY_HEX, encrypted) == b"203.0.113.10:3010"


def test_encryption_manager_wraps_encrypt_errors() -> None:
    manager = ECIESEncryptionManager()

    with pytest.raises(EncryptionError):
        manager.encrypt("not-hex", b"data")


def test_encryption_manager_wraps_decrypt_errors() -> None:
    manager = ECIESEncryptionManager()

    with pytest.raises(DecryptionError):
        manager.decrypt(PRIVATE_KEY_HEX, b"not-ecies-ciphertext")
