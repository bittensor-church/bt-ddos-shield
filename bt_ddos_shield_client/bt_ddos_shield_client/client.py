from __future__ import annotations

import asyncio
from collections.abc import Mapping
import os

from bt_ddos_shield_client.certificates import Certificate, EDDSACertificateManager
from bt_ddos_shield_client.encryption import ECIESEncryptionManager
from bt_ddos_shield_client.manifest import JsonManifestSerializer, fetch_manifest, get_address_for_validator
from bt_ddos_shield_client.types import Hotkey, ShieldAddress


class ShieldClient:
    def __init__(
        self,
        certificate_path: str | None = None,
        manifest_timeout: int = 10,
    ):
        self.certificate_path = certificate_path or os.getenv(
            'VALIDATOR_SHIELD_CERTIFICATE_PATH',
            './validator_cert.pem',
        )
        self.manifest_timeout = manifest_timeout
        self.certificate_manager = EDDSACertificateManager()
        self.encryption_manager = ECIESEncryptionManager()
        self.manifest_serializer = JsonManifestSerializer()
        self.certificate = self._load_or_create_certificate()

    def _load_or_create_certificate(self) -> Certificate:
        try:
            return self.certificate_manager.load_certificate(self.certificate_path)
        except FileNotFoundError:
            certificate = self.certificate_manager.generate_certificate()
            self.certificate_manager.save_certificate(certificate, self.certificate_path)
            return certificate

    async def resolve_shield_address(
        self,
        validator_hotkey: Hotkey,
        miner_hotkey: Hotkey,
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
            miner_hotkey,
            self.certificate.private_key,
            self.encryption_manager,
        )

    async def resolve_shield_addresses(
        self,
        validator_hotkey: Hotkey,
        miners: list[tuple[Hotkey, str, int]],
    ) -> list[ShieldAddress | None]:
        return await asyncio.gather(
            *[
                self.resolve_shield_address(
                    validator_hotkey,
                    miner_hotkey,
                    axon_ip,
                    axon_port,
                )
                for miner_hotkey, axon_ip, axon_port in miners
            ]
        )

    async def resolve_shield_addresses_by_hotkey(
        self,
        validator_hotkey: Hotkey,
        miners: Mapping[Hotkey, tuple[str, int]],
    ) -> dict[Hotkey, ShieldAddress | None]:
        resolved_addresses = await asyncio.gather(
            *[
                self.resolve_shield_address(
                    validator_hotkey,
                    miner_hotkey,
                    axon_ip,
                    axon_port,
                )
                for miner_hotkey, (axon_ip, axon_port) in miners.items()
            ]
        )
        return {
            miner_hotkey: shield_address
            for (miner_hotkey, _), shield_address in zip(miners.items(), resolved_addresses, strict=True)
        }
