from __future__ import annotations

from abc import ABC, abstractmethod

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
        *,
        bittensor,
        netuid: int,
        wallet,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
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
        *,
        bittensor,
        netuid: int,
        wallet,
        public_key: PublicKey,
        algorithm: CertificateAlgorithmEnum,
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


_turbo_bittensor_subtensor_contact_instance: AbstractTurboBittensorSubtensorContact | None = None


def turbo_bittensor_subtensor_contact() -> AbstractTurboBittensorSubtensorContact:
    global _turbo_bittensor_subtensor_contact_instance
    if _turbo_bittensor_subtensor_contact_instance is None:
        _turbo_bittensor_subtensor_contact_instance = TurboBittensorSubtensorContact()
    return _turbo_bittensor_subtensor_contact_instance
