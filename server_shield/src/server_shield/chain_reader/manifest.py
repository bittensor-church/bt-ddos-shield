from __future__ import annotations

import base64
import os

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from Crypto.PublicKey.ECC import EccKey
from Crypto.Signature.eddsa import import_private_key, import_public_key

from server_shield.shared.state import DesiredDomainEntry, ManifestPayloadState, ManifestState


def _get_public_key(secret: bytes) -> bytes:
    return import_private_key(secret).public_key().export_key(format="raw")


def _get_shared_point(secret: bytes, public_key: bytes) -> bytes:
    shared_point = import_public_key(public_key).pointQ * import_private_key(secret).d
    return EccKey(curve="ed25519", point=shared_point).export_key(format="raw")


def _derive_key(master: bytes) -> bytes:
    return HKDF(master, 32, b"", SHA256, num_keys=1)


def _encrypt_with_ed25519_ecies(public_key_hex: str, data: bytes) -> bytes:
    receiver_public_key = bytes.fromhex(public_key_hex.removeprefix("0x"))
    ephemeral_secret = os.urandom(32)
    ephemeral_public_key = _get_public_key(ephemeral_secret)
    shared_point = _get_shared_point(ephemeral_secret, receiver_public_key)
    symmetric_key = _derive_key(ephemeral_public_key + shared_point)

    nonce = os.urandom(16)
    cipher = AES.new(symmetric_key, AES.MODE_GCM, nonce)
    encrypted, tag = cipher.encrypt_and_digest(data)
    return ephemeral_public_key + nonce + tag + encrypted


def build_manifest_state(desired_domains: dict[str, DesiredDomainEntry]) -> ManifestState:
    encrypted_url_mapping: dict[str, str] = {}
    for hotkey, entry in sorted(desired_domains.items()):
        encrypted_bytes = _encrypt_with_ed25519_ecies(
            entry.public_cert,
            entry.domain.encode("utf-8"),
        )
        encrypted_url_mapping[hotkey] = base64.b64encode(encrypted_bytes).decode("ascii")

    return ManifestState(
        ddos_shield_manifest=ManifestPayloadState(
            encrypted_url_mapping=encrypted_url_mapping,
        )
    )
