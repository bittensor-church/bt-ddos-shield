from __future__ import annotations

import asyncio
from typing import Protocol

from bittensor import Subtensor
from bittensor.core.extrinsics.serving import serve_extrinsic
from bittensor.core.metagraph import Metagraph

from bt_ddos_shield_client.certificates import CertificateAlgorithmEnum
from bt_ddos_shield_client.internal import decode_subtensor_certificate_info
from bt_ddos_shield_client.types import PublicKey


class CertificateContact(Protocol):
    async def get_own_public_key(self) -> PublicKey | None: ...

    async def upload_public_key(
        self,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
    ) -> None: ...


class MetagraphContact(CertificateContact, Protocol):
    def sync_metagraph(
        self,
        metagraph: Metagraph,
        *,
        block: int | None = None,
        lite: bool | None = None,
    ) -> None: ...


class BittensorSubtensorContact:
    def __init__(self, subtensor: Subtensor, netuid: int, wallet):
        self.subtensor = subtensor
        self.netuid = netuid
        self.wallet = wallet

    def sync_metagraph(
        self,
        metagraph: Metagraph,
        *,
        block: int | None = None,
        lite: bool | None = None,
    ) -> None:
        Metagraph.sync(
            metagraph,
            block=block,
            lite=lite,
            subtensor=self.subtensor,
        )

    async def get_own_public_key(self) -> PublicKey | None:
        return await asyncio.to_thread(self._get_own_public_key)

    async def upload_public_key(
        self,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
    ) -> None:
        await asyncio.to_thread(self._upload_public_key, public_key, algorithm)

    def _get_own_public_key(self) -> PublicKey | None:
        certificate = self.subtensor.query_subtensor(
            name='NeuronCertificates',
            params=[self.netuid, self.wallet.hotkey.ss58_address],
        )
        if certificate is None:
            return None

        decoded_certificate = decode_subtensor_certificate_info(certificate)
        if decoded_certificate is None:
            return None
        return decoded_certificate.hex_data

    def _upload_public_key(self, public_key: PublicKey, algorithm: CertificateAlgorithmEnum) -> None:
        axon_info = self._get_current_axon_info()
        new_ip = '1.1.1.1' if axon_info is None else str(axon_info.ip)
        new_port = 1 if axon_info is None else axon_info.port
        new_protocol = 0 if axon_info is None else axon_info.protocol
        new_placeholder1 = 0 if axon_info is None else (axon_info.placeholder1 + 1) % 256
        certificate_data = bytes([algorithm]) + bytes.fromhex(public_key)

        serve_extrinsic(
            self.subtensor,
            self.wallet,
            new_ip,
            new_port,
            new_protocol,
            self.netuid,
            certificate=certificate_data,  # type: ignore[arg-type]
            placeholder1=new_placeholder1,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )

    def _get_current_axon_info(self):
        neuron = self.subtensor.get_neuron_for_pubkey_and_subnet(
            self.wallet.hotkey.ss58_address,
            netuid=self.netuid,
        )
        if neuron is None or neuron.axon_info is None or not neuron.axon_info.is_serving:
            return None
        return neuron.axon_info
