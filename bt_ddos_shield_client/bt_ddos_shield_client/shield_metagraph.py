from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
import os
from typing import Any

from bittensor import Subtensor
from bittensor.core.extrinsics.serving import serve_extrinsic
from bittensor.core.metagraph import Metagraph

from bt_ddos_shield_client.certificates import CertificateAlgorithmEnum
from bt_ddos_shield_client.client import ShieldClient
from bt_ddos_shield_client.internal import decode_subtensor_certificate_info, run_async_in_thread
from bt_ddos_shield_client.types import PublicKey


@dataclass
class ShieldMetagraphOptions:
    certificate_path: str | None = None
    disable_uploading_certificate: bool = False


def resolve_certificate_path(configured_path: str | None) -> str:
    if configured_path is not None:
        return configured_path

    env_path = os.getenv('VALIDATOR_SHIELD_CERTIFICATE_PATH')
    if env_path is not None:
        return env_path

    return './validator_cert.pem'


class BittensorSubtensorContact:
    def __init__(self, subtensor: Subtensor, netuid: int, wallet):
        self.subtensor = subtensor
        self.netuid = netuid
        self.wallet = wallet

    def get_hotkey(self) -> str:
        return self.wallet.hotkey.ss58_address

    async def get_own_public_key(self) -> PublicKey | None:
        return await asyncio.to_thread(self._get_own_public_key)

    async def upload_public_key(self, public_key: PublicKey, algorithm: CertificateAlgorithmEnum) -> None:
        await asyncio.to_thread(self._upload_public_key, public_key, algorithm)

    def _get_own_public_key(self) -> PublicKey | None:
        certificate: Any | None = self.subtensor.query_subtensor(
            name='NeuronCertificates',
            params=[self.netuid, self.get_hotkey()],
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


def get_contact_instance(*, wallet, netuid: int, subtensor: Subtensor):
    return BittensorSubtensorContact(
        subtensor=subtensor,
        netuid=netuid,
        wallet=wallet,
    )


class ShieldMetagraph(Metagraph):
    def __init__(
        self,
        wallet,
        netuid: int,
        network: str | None = None,
        lite: bool = True,
        sync: bool = True,
        block: int | None = None,
        subtensor=None,
        options: ShieldMetagraphOptions | None = None,
    ):
        if subtensor is None:
            subtensor = Subtensor(network=network)
        super().__init__(
            netuid=netuid,
            network=network or 'finney',
            lite=lite,
            sync=False,
            subtensor=subtensor,
        )
        self.wallet = wallet
        self.options = options or ShieldMetagraphOptions()
        self._shield_client = ShieldClient(
            wallet=wallet,
            subtensor=get_contact_instance(
                wallet=wallet,
                netuid=netuid,
                subtensor=self.subtensor,
            ),
            certificate_path=resolve_certificate_path(self.options.certificate_path),
            disable_uploading_certificate=self.options.disable_uploading_certificate,
        )
        run_async_in_thread(self._shield_client.__aenter__())

        if sync:
            self.sync(block=block, lite=lite, subtensor=self.subtensor)
        elif block is not None:
            raise ValueError('Block argument is valid only when sync is True')

    def sync(self, block: int | None = None, lite: bool | None = None, subtensor=None):
        super().sync(block=block, lite=lite, subtensor=subtensor)
        own_hotkey = self._shield_client.get_validator_hotkey()
        for axon in self.axons:
            shield_address = run_async_in_thread(
                self._shield_client.resolve_shield_address(
                    own_hotkey,
                    str(axon.ip),
                    axon.port,
                )
            )
            if shield_address is None:
                continue
            axon.ip = shield_address
