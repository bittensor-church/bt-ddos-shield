from __future__ import annotations

from bt_ddos_shield_client import ed25519_ecies
from bt_ddos_shield_client.types import PrivateKey, PublicKey


class EncryptionManagerException(Exception):
    pass


class EncryptionError(EncryptionManagerException):
    pass


class DecryptionError(EncryptionManagerException):
    pass


class ECIESEncryptionManager:
    def encrypt(self, public_key: PublicKey, data: bytes) -> bytes:
        try:
            return ed25519_ecies.encrypt(public_key, data)
        except Exception as exc:
            raise EncryptionError(f'Encryption failed: {exc}') from exc

    def decrypt(self, private_key: PrivateKey, data: bytes) -> bytes:
        try:
            return ed25519_ecies.decrypt(private_key, data)
        except Exception as exc:
            raise DecryptionError(f'Decryption failed: {exc}') from exc
