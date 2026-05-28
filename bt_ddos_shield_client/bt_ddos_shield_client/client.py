from __future__ import annotations

import asyncio
from collections.abc import Mapping
import os
from pathlib import Path

import aiohttp

from bt_ddos_shield_client.certificates import Certificate, EDDSACertificateManager
from bt_ddos_shield_client.encryption import ECIESEncryptionManager
from bt_ddos_shield_client.manifest import JsonManifestSerializer, fetch_manifest, get_address_for_validator
from bt_ddos_shield_client.types import Hotkey, ShieldAddress


def resolve_certificate_path(wallet: object | None = None) -> str:
    env_path = os.getenv('VALIDATOR_SHIELD_CERTIFICATE_PATH')
    if env_path is not None:
        return env_path

    if wallet is None:
        raise ValueError('wallet is required when VALIDATOR_SHIELD_CERTIFICATE_PATH is not set')

    hotkey_path = Path(str(wallet.hotkey_file.path))
    return str(hotkey_path.with_name(f'{hotkey_path.name}.cert.pem'))


class ShieldClient:
    def __init__(
        self,
        wallet: object | None = None,
        manifest_timeout: int = 10,
    ):
        self.certificate_path = resolve_certificate_path(wallet)
        self.manifest_timeout = manifest_timeout
        self.certificate_manager = EDDSACertificateManager()
        self.encryption_manager = ECIESEncryptionManager()
        self.manifest_serializer = JsonManifestSerializer()
        self.certificate = self._load_or_create_certificate()
        self._manifest_session: aiohttp.ClientSession | None = None
        self._manifest_session_loop: asyncio.AbstractEventLoop | None = None

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
        session = self._get_manifest_session()
        manifest = await fetch_manifest(
            axon_ip,
            axon_port,
            timeout=self.manifest_timeout,
            serializer=self.manifest_serializer,
            session=session,
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

    def _get_manifest_session(self) -> aiohttp.ClientSession:
        loop = asyncio.get_running_loop()
        if (
            self._manifest_session is None
            or self._manifest_session.closed
            or self._manifest_session_loop is not loop
            or self._manifest_session_loop.is_closed()
        ):
            self._manifest_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.manifest_timeout),
            )
            self._manifest_session_loop = loop
        return self._manifest_session

    async def aclose(self) -> None:
        session = self._manifest_session
        self._manifest_session = None
        self._manifest_session_loop = None
        if session is not None and not session.closed:
            await session.close()
