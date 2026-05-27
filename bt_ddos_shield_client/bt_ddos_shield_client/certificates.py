from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from bt_ddos_shield_client import ed25519_ecies
from bt_ddos_shield_client.types import PrivateKey, PublicKey


class CertificateAlgorithmEnum(enum.IntEnum):
    ED25519 = 1


@dataclass(frozen=True)
class Certificate:
    algorithm: CertificateAlgorithmEnum
    public_key: PublicKey
    private_key: PrivateKey


class EDDSACertificateManager:
    @classmethod
    def generate_certificate(cls) -> Certificate:
        private_key = ed25519_ecies.generate_private_key_hex()
        return Certificate(
            private_key=private_key,
            public_key=ed25519_ecies.public_key_from_private_key(private_key),
            algorithm=CertificateAlgorithmEnum.ED25519,
        )

    @classmethod
    def save_certificate(cls, certificate: Certificate, path: str) -> None:
        private_key_bytes = bytes.fromhex(certificate.private_key)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        pem_data = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with open(path, 'wb') as file_obj:
            file_obj.write(pem_data)

    @classmethod
    def load_certificate(cls, path: str) -> Certificate:
        with open(path, 'rb') as file_obj:
            private_key_raw = file_obj.read()

        private_key = cast(
            'ed25519.Ed25519PrivateKey',
            serialization.load_pem_private_key(private_key_raw, password=None),
        )
        private_key_hex = private_key.private_bytes_raw().hex()
        return Certificate(
            private_key=private_key_hex,
            public_key=ed25519_ecies.public_key_from_private_key(private_key_hex),
            algorithm=CertificateAlgorithmEnum.ED25519,
        )
