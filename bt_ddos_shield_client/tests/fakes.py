from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from types import SimpleNamespace

from bt_ddos_shield_client.certificates import CertificateAlgorithmEnum
from bt_ddos_shield_client.encryption import ECIESEncryptionManager


@dataclass(frozen=True)
class CertificateUpload:
    public_key: str
    algorithm: CertificateAlgorithmEnum


@dataclass
class FakeSubtensorContact:
    hotkey: str = 'validator-hotkey'
    own_public_key: str | None = None
    upload_failures_remaining: int = 0
    uploads: list[CertificateUpload] = field(default_factory=list)

    def get_hotkey(self) -> str:
        return self.hotkey

    async def get_own_public_key(self) -> str | None:
        return self.own_public_key

    async def upload_public_key(self, public_key: str, algorithm: CertificateAlgorithmEnum) -> None:
        if self.upload_failures_remaining > 0:
            self.upload_failures_remaining -= 1
            raise RuntimeError('upload failed')

        self.uploads.append(CertificateUpload(public_key=public_key, algorithm=algorithm))
        self.own_public_key = public_key


def make_wallet(hotkey: str = 'validator-hotkey'):
    return SimpleNamespace(hotkey=SimpleNamespace(ss58_address=hotkey))


def build_manifest_body(public_key: str, address: str, validator_hotkey: str = 'validator-hotkey') -> bytes:
    encrypted = ECIESEncryptionManager().encrypt(public_key, address.encode())
    return json.dumps(
        {
            'ddos_shield_manifest': {
                'encrypted_url_mapping': {
                    validator_hotkey: base64.b64encode(encrypted).decode(),
                },
            }
        }
    ).encode()
