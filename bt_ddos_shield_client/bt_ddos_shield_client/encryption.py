from __future__ import annotations

from typing import Literal

import ecies
from ecies.config import Config

from bt_ddos_shield_client.types import PrivateKey, PublicKey


class EncryptionManagerException(Exception):
    pass


class EncryptionError(EncryptionManagerException):
    pass


class DecryptionError(EncryptionManagerException):
    pass


class ECIESEncryptionManager:
    _CURVE: Literal['ed25519'] = 'ed25519'
    _ECIES_CONFIG = Config(elliptic_curve=_CURVE)

    def encrypt(self, public_key: PublicKey, data: bytes) -> bytes:
        try:
            return ecies.encrypt(public_key, data, config=self._ECIES_CONFIG)
        except Exception as exc:
            raise EncryptionError(f'Encryption failed: {exc}') from exc

    def decrypt(self, private_key: PrivateKey, data: bytes) -> bytes:
        try:
            return ecies.decrypt(private_key, data, config=self._ECIES_CONFIG)
        except Exception as exc:
            raise DecryptionError(f'Decryption failed: {exc}') from exc
