from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import turbobt
import turbobt.neuron
import turbobt.subnet

from bt_ddos_shield_client.certificates import CertificateAlgorithmEnum
from bt_ddos_shield_client.internal import decode_subtensor_certificate_info
from bt_ddos_shield_client.types import PublicKey


class AbstractTurboBittensorSubtensorContact(ABC):
    @abstractmethod
    async def list_neurons(
        self,
        *,
        bittensor,
        netuid: int,
        block_hash: str | None = None,
    ) -> list[turbobt.neuron.Neuron]:
        raise NotImplementedError

    @abstractmethod
    async def get_own_public_key(
        self,
        *,
        bittensor,
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
        bittensor,
        netuid: int,
        wallet,
    ) -> None:
        raise NotImplementedError


class TurboBittensorSubtensorContact(AbstractTurboBittensorSubtensorContact):

    async def list_neurons(
        self,
        *,
        bittensor,
        netuid: int,
        block_hash: str | None = None,
    ) -> list[turbobt.neuron.Neuron]:
        subnet = turbobt.subnet.SubnetReference(netuid, client=bittensor)
        return await subnet.list_neurons(block_hash)

    async def get_own_public_key(
        self,
        *,
        bittensor,
        netuid: int,
        hotkey: str,
    ) -> PublicKey | None:
        subnet = turbobt.subnet.SubnetReference(netuid, client=bittensor)
        neuron = subnet.neuron(hotkey=hotkey)
        certificate = await neuron.get_certificate()
        if not certificate:
            return None
        if isinstance(certificate.get('public_key'), list):
            public_key = certificate['public_key'][0]
            if isinstance(public_key, str):
                certificate = {**certificate, 'public_key': [public_key]}
            else:
                certificate = {**certificate, 'public_key': [bytes.fromhex(public_key)]}
        decoded_certificate = decode_subtensor_certificate_info(certificate)
        if decoded_certificate is None:
            return None
        return decoded_certificate.hex_data

    async def upload_public_key(
        self,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
        *,
        bittensor,
        netuid: int,
        wallet,
    ) -> None:
        subnet = turbobt.subnet.SubnetReference(netuid, client=bittensor)
        neuron = await subnet.get_neuron(wallet.hotkey.ss58_address)
        ip = '1.1.1.1'
        port = 1
        if neuron and neuron.axon_info and str(neuron.axon_info.ip) != '0.0.0.0':
            ip = str(neuron.axon_info.ip or ip)
            port = neuron.axon_info.port or port
        certificate_data = bytes([algorithm]) + bytes.fromhex(public_key)
        await subnet.neurons.serve(ip, port, certificate=certificate_data, wallet=wallet)


@dataclass(frozen=True)
class TurboBittensorContactCall:
    method: str
    netuid: int | None = None
    hotkey: str | None = None
    public_key: PublicKey | None = None
    block_hash: str | None = None


@dataclass
class MockTurboBittensorSubtensorContact(AbstractTurboBittensorSubtensorContact):
    own_public_key: PublicKey | None = None
    own_public_key_exception: Exception | None = None
    upload_exception: Exception | None = None
    listed_neurons: list[turbobt.neuron.Neuron] = field(default_factory=list)
    calls: list[TurboBittensorContactCall] = field(default_factory=list)

    def set_neuron_listing(self, neurons: list[turbobt.neuron.Neuron]) -> None:
        self.listed_neurons = list(neurons)

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

    async def list_neurons(
        self,
        *,
        bittensor,
        netuid: int,
        block_hash: str | None = None,
    ) -> list[turbobt.neuron.Neuron]:
        self.calls.append(
            TurboBittensorContactCall(
                method='list_neurons',
                netuid=netuid,
                block_hash=block_hash,
            )
        )
        return list(self.listed_neurons)

    async def get_own_public_key(
        self,
        *,
        bittensor,
        netuid: int,
        hotkey: str,
    ) -> PublicKey | None:
        self.calls.append(
            TurboBittensorContactCall(
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
        bittensor,
        netuid: int,
        wallet,
    ) -> None:
        self.calls.append(
            TurboBittensorContactCall(
                method='upload_public_key',
                netuid=netuid,
                public_key=public_key,
            )
        )
        if self.upload_exception is not None:
            raise self.upload_exception
        self.own_public_key = public_key
        self.own_public_key_exception = None


_turbo_bittensor_subtensor_contact_instance: AbstractTurboBittensorSubtensorContact | None = None


def turbo_bittensor_subtensor_contact() -> AbstractTurboBittensorSubtensorContact:
    global _turbo_bittensor_subtensor_contact_instance
    if _turbo_bittensor_subtensor_contact_instance is None:
        _turbo_bittensor_subtensor_contact_instance = TurboBittensorSubtensorContact()
    return _turbo_bittensor_subtensor_contact_instance
