from __future__ import annotations

import dataclasses

import turbobt
import turbobt.neuron
import turbobt.subnet

from bt_ddos_shield_client.certificates import CertificateAlgorithmEnum
from bt_ddos_shield_client.client import ShieldClient
from bt_ddos_shield_client.internal import decode_subtensor_certificate_info
from bt_ddos_shield_client.shield_metagraph import ShieldMetagraphOptions, resolve_certificate_path
from bt_ddos_shield_client.types import PublicKey


class TurboBittensorSubtensorContact:
    def __init__(self, bittensor, netuid: int, wallet):
        self.bittensor = bittensor
        self.wallet = wallet
        self.subnet = turbobt.Bittensor.subnet(bittensor, netuid)

    def get_hotkey(self) -> str:
        return self.wallet.hotkey.ss58_address

    async def get_own_public_key(self) -> PublicKey | None:
        neuron = self.subnet.neuron(hotkey=self.get_hotkey())
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
        neuron = await self.subnet.get_neuron(self.get_hotkey())
        ip = '1.1.1.1'
        port = 1
        if neuron and neuron.axon_info and str(neuron.axon_info.ip) != '0.0.0.0':
            ip = str(neuron.axon_info.ip or ip)
            port = neuron.axon_info.port or port
        certificate_data = bytes([algorithm]) + bytes.fromhex(public_key)
        await self.subnet.neurons.serve(ip, port, certificate=certificate_data, wallet=self.wallet)


def get_contact_instance(*, wallet, netuid: int, bittensor):
    return TurboBittensorSubtensorContact(
        bittensor=bittensor,
        netuid=netuid,
        wallet=wallet,
    )


class ShieldedBittensor(turbobt.Bittensor):
    def __init__(
        self,
        *args,
        wallet,
        ddos_shield_netuid: int,
        ddos_shield_options: ShieldMetagraphOptions | None = None,
        **kwargs,
    ):
        super().__init__(*args, wallet=wallet, **kwargs)
        self.ddos_shield_options = ddos_shield_options or ShieldMetagraphOptions()
        self._shield_client = ShieldClient(
            wallet=wallet,
            subtensor=get_contact_instance(
                wallet=wallet,
                netuid=ddos_shield_netuid,
                bittensor=self,
            ),
            certificate_path=resolve_certificate_path(self.ddos_shield_options.certificate_path),
            disable_uploading_certificate=self.ddos_shield_options.disable_uploading_certificate,
        )
        self.ddos_shield_netuid = ddos_shield_netuid

    async def __aenter__(self):
        await super().__aenter__()
        await self._shield_client.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._shield_client.__aexit__(*args, **kwargs)
        await super().__aexit__(*args, **kwargs)

    def subnet(self, netuid: int) -> turbobt.subnet.SubnetReference:
        if netuid == self.ddos_shield_netuid:
            return ShieldedSubnetReference(netuid, client=self)
        return super().subnet(netuid)


class ShieldedSubnetReference(turbobt.subnet.SubnetReference):
    client: ShieldedBittensor = dataclasses.field(compare=False, repr=False)

    async def list_neurons(self, *args, **kwargs) -> list[turbobt.neuron.Neuron]:
        neurons = await super().list_neurons(*args, **kwargs)
        validator_hotkey = self.client._shield_client.get_validator_hotkey()
        for neuron in neurons:
            shield_address = await self.client._shield_client.resolve_shield_address(
                validator_hotkey,
                str(neuron.axon_info.ip),
                neuron.axon_info.port,
            )
            if shield_address is None:
                continue
            neuron.axon_info.ip = shield_address
        return neurons
