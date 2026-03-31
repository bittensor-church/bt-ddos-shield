from __future__ import annotations

import turbobt
import turbobt.neuron
import turbobt.subnet

from bt_ddos_shield_client.certificates import CertificateAlgorithmEnum
from bt_ddos_shield_client.internal import decode_subtensor_certificate_info
from bt_ddos_shield_client.types import PublicKey


class TurboBittensorSubtensorContact:
    def __init__(self, bittensor, netuid: int, wallet):
        self.bittensor = bittensor
        self.netuid = netuid
        self.wallet = wallet
        self.subnet = turbobt.subnet.SubnetReference(netuid, client=bittensor)

    async def list_neurons(self, block_hash: str | None = None) -> list[turbobt.neuron.Neuron]:
        return await self.subnet.list_neurons(block_hash)

    async def get_own_public_key(self) -> PublicKey | None:
        neuron = self.subnet.neuron(hotkey=self.wallet.hotkey.ss58_address)
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

    async def upload_public_key(self, public_key: PublicKey, algorithm: CertificateAlgorithmEnum) -> None:
        neuron = await self.subnet.get_neuron(self.wallet.hotkey.ss58_address)
        ip = '1.1.1.1'
        port = 1
        if neuron and neuron.axon_info and str(neuron.axon_info.ip) != '0.0.0.0':
            ip = str(neuron.axon_info.ip or ip)
            port = neuron.axon_info.port or port
        certificate_data = bytes([algorithm]) + bytes.fromhex(public_key)
        await self.subnet.neurons.serve(ip, port, certificate=certificate_data, wallet=self.wallet)
