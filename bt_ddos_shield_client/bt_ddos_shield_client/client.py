from __future__ import annotations

import asyncio
import os
from typing import Any

from bt_ddos_shield_client.certificates import Certificate, EDDSACertificateManager
from bt_ddos_shield_client.encryption import ECIESEncryptionManager
from bt_ddos_shield_client.manifest import JsonManifestSerializer, fetch_manifest, get_address_for_validator
from bt_ddos_shield_client.types import Hotkey, ShieldAddress


class ShieldClient:
    def __init__(
        self,
        wallet,
        subtensor: Any,
        certificate_path: str | None = None,
        disable_uploading_certificate: bool = False,
        upload_retry_delay_seconds: float = 3,
        manifest_timeout: int = 10,
    ):
        self.wallet = wallet
        self.subtensor = subtensor
        self.certificate_path = certificate_path or os.getenv(
            'VALIDATOR_SHIELD_CERTIFICATE_PATH',
            './validator_cert.pem',
        )
        self.disable_uploading_certificate = disable_uploading_certificate
        self.upload_retry_delay_seconds = upload_retry_delay_seconds
        self.manifest_timeout = manifest_timeout
        self.certificate_manager = EDDSACertificateManager()
        self.encryption_manager = ECIESEncryptionManager()
        self.manifest_serializer = JsonManifestSerializer()
        self.certificate: Certificate

    async def __aenter__(self):
        await self._init_certificate()
        return self

    async def __aexit__(self, *args, **kwargs):
        return None

    def get_validator_hotkey(self) -> Hotkey:
        if hasattr(self.subtensor, 'get_hotkey'):
            return self.subtensor.get_hotkey()
        return self.wallet.hotkey.ss58_address

    async def _init_certificate(self) -> None:
        try:
            self.certificate = self.certificate_manager.load_certificate(self.certificate_path)
        except FileNotFoundError:
            self.certificate = self.certificate_manager.generate_certificate()
            self.certificate_manager.save_certificate(self.certificate, self.certificate_path)

        if self.disable_uploading_certificate:
            return

        public_key = await self.subtensor.get_own_public_key()
        if public_key == self.certificate.public_key:
            return

        try:
            await self.subtensor.upload_public_key(
                self.certificate.public_key,
                self.certificate.algorithm,
            )
        except Exception:
            await asyncio.sleep(self.upload_retry_delay_seconds)
            await self.subtensor.upload_public_key(
                self.certificate.public_key,
                self.certificate.algorithm,
            )

    async def resolve_shield_address(
        self,
        validator_hotkey: Hotkey,
        axon_ip: str,
        axon_port: int,
    ) -> ShieldAddress | None:
        manifest = await fetch_manifest(
            axon_ip,
            axon_port,
            timeout=self.manifest_timeout,
            serializer=self.manifest_serializer,
        )
        if manifest is None:
            return None

        return get_address_for_validator(
            manifest,
            validator_hotkey,
            self.certificate.private_key,
            self.encryption_manager,
        )
