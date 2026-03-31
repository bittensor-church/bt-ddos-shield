from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from typing import Protocol

from bittensor import Subtensor
from bittensor.core.chain_data import NeuronInfo
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


class AbstractBittensorSubtensorContact(ABC):
    @abstractmethod
    def sync_metagraph(
        self,
        metagraph: Metagraph,
        *,
        subtensor: Subtensor,
        block: int | None = None,
        lite: bool | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_own_public_key(
        self,
        *,
        subtensor: Subtensor,
        netuid: int,
        hotkey: str,
    ) -> PublicKey | None:
        raise NotImplementedError

    @abstractmethod
    async def upload_public_key(
        self,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
        *,
        subtensor: Subtensor,
        wallet,
        netuid: int,
    ) -> None:
        raise NotImplementedError


class BittensorSubtensorContact(AbstractBittensorSubtensorContact):

    def sync_metagraph(
        self,
        metagraph: Metagraph,
        *,
        subtensor: Subtensor,
        block: int | None = None,
        lite: bool | None = None,
    ) -> None:
        Metagraph.sync(
            metagraph,
            block=block,
            lite=lite,
            subtensor=subtensor,
        )

    async def get_own_public_key(
        self,
        *,
        subtensor: Subtensor,
        netuid: int,
        hotkey: str,
    ) -> PublicKey | None:
        return await asyncio.to_thread(self._get_own_public_key, subtensor, netuid, hotkey)

    async def upload_public_key(
        self,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
        *,
        subtensor: Subtensor,
        wallet,
        netuid: int,
    ) -> None:
        await asyncio.to_thread(
            self._upload_public_key,
            subtensor,
            wallet,
            netuid,
            public_key,
            algorithm,
        )

    def _get_own_public_key(self, subtensor: Subtensor, netuid: int, hotkey: str) -> PublicKey | None:
        certificate = subtensor.query_subtensor(
            name='NeuronCertificates',
            params=[netuid, hotkey],
        )
        if certificate is None:
            return None

        decoded_certificate = decode_subtensor_certificate_info(certificate)
        if decoded_certificate is None:
            return None
        return decoded_certificate.hex_data

    def _upload_public_key(
        self,
        subtensor: Subtensor,
        wallet,
        netuid: int,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
    ) -> None:
        axon_info = self._get_current_axon_info(subtensor, wallet, netuid)
        new_ip = '1.1.1.1' if axon_info is None else str(axon_info.ip)
        new_port = 1 if axon_info is None else axon_info.port
        new_protocol = 0 if axon_info is None else axon_info.protocol
        new_placeholder1 = 0 if axon_info is None else (axon_info.placeholder1 + 1) % 256
        certificate_data = bytes([algorithm]) + bytes.fromhex(public_key)

        serve_extrinsic(
            subtensor,
            wallet,
            new_ip,
            new_port,
            new_protocol,
            netuid,
            certificate=certificate_data,  # type: ignore[arg-type]
            placeholder1=new_placeholder1,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )

    def _get_current_axon_info(self, subtensor: Subtensor, wallet, netuid: int):
        neuron = subtensor.get_neuron_for_pubkey_and_subnet(
            wallet.hotkey.ss58_address,
            netuid=netuid,
        )
        if neuron is None or neuron.axon_info is None or not neuron.axon_info.is_serving:
            return None
        return neuron.axon_info


@dataclass(frozen=True)
class BittensorContactCall:
    method: str
    netuid: int | None = None
    hotkey: str | None = None
    public_key: PublicKey | None = None
    block: int | None = None
    lite: bool | None = None


@dataclass
class MockBittensorSubtensorContact(AbstractBittensorSubtensorContact):
    own_public_key: PublicKey | None = None
    own_public_key_exception: Exception | None = None
    upload_exception: Exception | None = None
    sync_neurons: list[NeuronInfo] = field(default_factory=list)
    calls: list[BittensorContactCall] = field(default_factory=list)

    def set_metagraph_sync(self, neurons: list[NeuronInfo]) -> None:
        self.sync_neurons = list(neurons)

    def set_own_certificate(
        self,
        public_key: PublicKey | None,
        *,
        exception: Exception | None = None,
    ) -> None:
        self.own_public_key = public_key
        self.own_public_key_exception = exception

    def set_upload_behavior(self, exception: Exception | None = None) -> None:
        self.upload_exception = exception

    def reset_calls(self) -> None:
        self.calls.clear()

    def sync_metagraph(
        self,
        metagraph: Metagraph,
        *,
        subtensor: Subtensor,
        block: int | None = None,
        lite: bool | None = None,
    ) -> None:
        self.calls.append(
            BittensorContactCall(
                method='sync_metagraph',
                netuid=metagraph.netuid,
                block=block,
                lite=lite,
            )
        )
        metagraph.neurons = list(self.sync_neurons)
        metagraph.axons = [neuron.axon_info for neuron in self.sync_neurons]
        if lite is not None:
            metagraph.lite = lite

    async def get_own_public_key(
        self,
        *,
        subtensor: Subtensor,
        netuid: int,
        hotkey: str,
    ) -> PublicKey | None:
        self.calls.append(
            BittensorContactCall(
                method='get_own_public_key',
                netuid=netuid,
                hotkey=hotkey,
            )
        )
        if self.own_public_key_exception is not None:
            raise self.own_public_key_exception
        return self.own_public_key

    async def upload_public_key(
        self,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
        *,
        subtensor: Subtensor,
        wallet,
        netuid: int,
    ) -> None:
        self.calls.append(
            BittensorContactCall(
                method='upload_public_key',
                netuid=netuid,
                public_key=public_key,
            )
        )
        if self.upload_exception is not None:
            raise self.upload_exception
        self.own_public_key = public_key
        self.own_public_key_exception = None


_bittensor_subtensor_contact_instance: AbstractBittensorSubtensorContact | None = None


def bittensor_subtensor_contact() -> AbstractBittensorSubtensorContact:
    global _bittensor_subtensor_contact_instance
    if _bittensor_subtensor_contact_instance is None:
        _bittensor_subtensor_contact_instance = BittensorSubtensorContact()
    return _bittensor_subtensor_contact_instance
