from __future__ import annotations

import dataclasses

import turbobt
import turbobt.neuron

from bt_ddos_shield_client.certificate_reconciliation import CertificateReconciler
from bt_ddos_shield_client.client import ShieldClient
from bt_ddos_shield_client.internal import parse_shield_address
from bt_ddos_shield_client.shield_metagraph import ShieldMetagraphOptions, resolve_certificate_path
from bt_ddos_shield_client.shielded_turbobt.contacts import TurboBittensorSubtensorContact


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
        self.ddos_shield_netuid = ddos_shield_netuid
        self._contact = TurboBittensorSubtensorContact(
            bittensor=self,
            netuid=ddos_shield_netuid,
            wallet=wallet,
        )
        self._shield_client = ShieldClient(
            certificate_path=resolve_certificate_path(self.ddos_shield_options.certificate_path),
        )
        self._certificate_reconciler = CertificateReconciler(
            contact=self._contact,
            certificate=self._shield_client.certificate,
            disabled=self.ddos_shield_options.disable_uploading_certificate,
        )

    async def __aenter__(self):
        await super().__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs):
        await super().__aexit__(*args, **kwargs)

    def subnet(self, netuid: int) -> turbobt.subnet.SubnetReference:
        if netuid == self.ddos_shield_netuid:
            return ShieldedSubnetReference.from_bittensor(
                self,
                netuid,
                wallet=self.wallet,
                ddos_shield_options=self.ddos_shield_options,
                contact=self._contact,
                shield_client=self._shield_client,
                certificate_reconciler=self._certificate_reconciler,
            )
        return super().subnet(netuid)


@dataclasses.dataclass
class ShieldedSubnetReference(turbobt.subnet.SubnetReference):
    client: dataclasses.InitVar[turbobt.Bittensor]
    wallet: dataclasses.InitVar[object | None] = None
    ddos_shield_options: dataclasses.InitVar[ShieldMetagraphOptions | None] = None
    contact: dataclasses.InitVar[TurboBittensorSubtensorContact | None] = None
    shield_client: dataclasses.InitVar[ShieldClient | None] = None
    certificate_reconciler: dataclasses.InitVar[CertificateReconciler | None] = None

    def __post_init__(
        self,
        client,
        wallet=None,
        ddos_shield_options=None,
        contact=None,
        shield_client=None,
        certificate_reconciler=None,
    ):
        super().__post_init__(client)
        self.wallet = wallet or client.wallet
        self.ddos_shield_options = ddos_shield_options or ShieldMetagraphOptions()
        self._contact = contact or TurboBittensorSubtensorContact(
            bittensor=client,
            netuid=self.netuid,
            wallet=self.wallet,
        )
        self._shield_client = shield_client or ShieldClient(
            certificate_path=resolve_certificate_path(self.ddos_shield_options.certificate_path),
        )
        self._certificate_reconciler = certificate_reconciler or CertificateReconciler(
            contact=self._contact,
            certificate=self._shield_client.certificate,
            disabled=self.ddos_shield_options.disable_uploading_certificate,
        )

    @classmethod
    def from_bittensor(
        cls,
        bittensor: turbobt.Bittensor,
        netuid: int,
        *,
        wallet=None,
        ddos_shield_options: ShieldMetagraphOptions | None = None,
        contact: TurboBittensorSubtensorContact | None = None,
        shield_client: ShieldClient | None = None,
        certificate_reconciler: CertificateReconciler | None = None,
    ) -> 'ShieldedSubnetReference':
        return cls(
            netuid=netuid,
            client=bittensor,
            wallet=wallet,
            ddos_shield_options=ddos_shield_options,
            contact=contact,
            shield_client=shield_client,
            certificate_reconciler=certificate_reconciler,
        )

    async def list_neurons(self, *args, **kwargs) -> list[turbobt.neuron.Neuron]:
        await self._certificate_reconciler.ensure_own_certificate_matches()
        neurons = await self._contact.list_neurons(*args, **kwargs)
        validator_hotkey = self.wallet.hotkey.ss58_address
        for neuron in neurons:
            shield_address = await self._shield_client.resolve_shield_address(
                validator_hotkey,
                neuron.hotkey,
                str(neuron.axon_info.ip),
                neuron.axon_info.port,
            )
            if shield_address is None:
                continue
            parsed_address = parse_shield_address(shield_address)
            if parsed_address is None:
                continue
            neuron.axon_info.ip = parsed_address[0]
            neuron.axon_info.port = parsed_address[1]
        return neurons
