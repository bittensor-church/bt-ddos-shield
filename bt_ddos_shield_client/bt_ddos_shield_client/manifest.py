from __future__ import annotations

import base64
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

import aiohttp

from bt_ddos_shield_client.encryption import ECIESEncryptionManager
from bt_ddos_shield_client.types import Hotkey, PrivateKey, ShieldAddress


class ManifestDeserializationException(Exception):
    pass


@dataclass
class Manifest:
    encrypted_url_mapping: dict[Hotkey, bytes]


class JsonManifestSerializer:
    MANIFEST_ROOT_JSON_KEY = 'ddos_shield_manifest'

    def __init__(self, encoding: str = 'utf-8'):
        self.encoding = encoding

    def serialize(self, manifest: Manifest) -> bytes:
        data = {self.MANIFEST_ROOT_JSON_KEY: asdict(manifest)}
        return json.dumps(data, default=self._custom_encoder).encode(self.encoding)

    def deserialize(self, serialized_data: bytes) -> Manifest:
        try:
            data = json.loads(serialized_data.decode(self.encoding), object_hook=self._custom_decoder)
            return Manifest(**data[self.MANIFEST_ROOT_JSON_KEY])
        except Exception as exc:
            raise ManifestDeserializationException(f'Failed to deserialize manifest data: {exc}') from exc

    @staticmethod
    def _custom_encoder(obj: Any) -> Any:
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode()
        raise TypeError(f'Unsupported object type {type(obj)!r}')

    @staticmethod
    def _custom_decoder(json_mapping: dict[str, Any]) -> Any:
        if 'encrypted_url_mapping' in json_mapping:
            json_mapping['encrypted_url_mapping'] = {
                hotkey: base64.b64decode(encoded_address.encode())
                for hotkey, encoded_address in json_mapping['encrypted_url_mapping'].items()
            }
        return json_mapping


def build_manifest_url(axon_ip: str, axon_port: int) -> str:
    return f'http://{axon_ip}:{axon_port}/shield_manifest.json'


looger = logging.getLogger(__name__)


async def fetch_manifest(
    axon_ip: str,
    axon_port: int,
    *,
    timeout: int = 10,
    serializer: JsonManifestSerializer | None = None,
) -> Manifest | None:
    serializer = serializer or JsonManifestSerializer()
    url = build_manifest_url(axon_ip, axon_port)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            looger.debug(f"trying {axon_ip}")
            async with session.get(url, allow_redirects=True) as response:
                looger.debug(f"{axon_ip} response {response.status}")
                response.raise_for_status()
                raw_manifest = await response.read()
    except Exception:
        looger.debug(f"failed to fetch manifest from {axon_ip}")
        return None
    try:
        return serializer.deserialize(raw_manifest)
    except ManifestDeserializationException:
        print(f"failed to deserialize manifest from {axon_ip}")
        return None

logger = logging.getLogger(__name__)
def get_address_for_validator(
    manifest: Manifest,
    validator_hotkey: Hotkey,
    validator_private_key: PrivateKey,
    encryption: ECIESEncryptionManager | None = None,
) -> ShieldAddress | None:
    print(manifest)
    print(validator_hotkey)
    encrypted_url = manifest.encrypted_url_mapping.get(validator_hotkey)
    if encrypted_url is None:
        return None

    try:
        return (encryption or ECIESEncryptionManager()).decrypt(validator_private_key, encrypted_url).decode()
    except Exception as ex:
        logger.debug(f"failed to decrypt address for validator {validator_hotkey}: {ex}")
        return None
