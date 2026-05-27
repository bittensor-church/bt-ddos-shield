from __future__ import annotations

import os

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from Crypto.PublicKey.ECC import EccKey
from Crypto.Signature.eddsa import import_private_key, import_public_key


CURVE = "ed25519"
PROTOCOL_VERSION = "ed25519-ecies-v1"
PRIVATE_KEY_BYTES = 32
PUBLIC_KEY_BYTES = 32
EPHEMERAL_PUBLIC_KEY_BYTES = 32
AES_GCM_NONCE_BYTES = 16
AES_GCM_TAG_BYTES = 16
AES_KEY_BYTES = 32
MIN_ENCRYPTED_BYTES = EPHEMERAL_PUBLIC_KEY_BYTES + AES_GCM_NONCE_BYTES + AES_GCM_TAG_BYTES


def _decode_hex(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("0x").removeprefix("0X"))


def _derive_key(master: bytes) -> bytes:
    return HKDF(master, AES_KEY_BYTES, b"", SHA256, num_keys=1)


def _public_key_from_private_key_bytes(private_key: bytes) -> bytes:
    return import_private_key(private_key).public_key().export_key(format="raw")


def _shared_point(private_key: bytes, public_key: bytes) -> bytes:
    shared_point = import_public_key(public_key).pointQ * import_private_key(private_key).d
    return EccKey(curve=CURVE, point=shared_point).export_key(format="raw")


def generate_private_key_hex() -> str:
    return os.urandom(PRIVATE_KEY_BYTES).hex()


def public_key_from_private_key(private_key_hex: str) -> str:
    return _public_key_from_private_key_bytes(_decode_hex(private_key_hex)).hex()


def encrypt(public_key_hex: str, data: bytes) -> bytes:
    receiver_public_key = _decode_hex(public_key_hex)
    ephemeral_private_key = os.urandom(PRIVATE_KEY_BYTES)
    ephemeral_public_key = _public_key_from_private_key_bytes(ephemeral_private_key)
    symmetric_key = _derive_key(ephemeral_public_key + _shared_point(ephemeral_private_key, receiver_public_key))

    nonce = os.urandom(AES_GCM_NONCE_BYTES)
    cipher = AES.new(symmetric_key, AES.MODE_GCM, nonce)
    encrypted, tag = cipher.encrypt_and_digest(data)
    return ephemeral_public_key + nonce + tag + encrypted


def decrypt(private_key_hex: str, data: bytes) -> bytes:
    if len(data) < MIN_ENCRYPTED_BYTES:
        raise ValueError("Encrypted payload is shorter than the manifest ECIES header")

    private_key = _decode_hex(private_key_hex)
    ephemeral_public_key = data[:EPHEMERAL_PUBLIC_KEY_BYTES]
    nonce_start = EPHEMERAL_PUBLIC_KEY_BYTES
    nonce_end = nonce_start + AES_GCM_NONCE_BYTES
    tag_end = nonce_end + AES_GCM_TAG_BYTES
    nonce = data[nonce_start:nonce_end]
    tag = data[nonce_end:tag_end]
    encrypted = data[tag_end:]

    symmetric_key = _derive_key(ephemeral_public_key + _shared_point(private_key, ephemeral_public_key))
    cipher = AES.new(symmetric_key, AES.MODE_GCM, nonce)
    return cipher.decrypt_and_verify(encrypted, tag)
