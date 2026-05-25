from __future__ import annotations

import dataclasses

import turbobt
import turbobt.neuron

from bt_ddos_shield_client.certificate_reconciliation import CertificateReconciler
from bt_ddos_shield_client.client import ShieldClient
from bt_ddos_shield_client.shielded_turbobt.contacts import turbo_bittensor_subtensor_contact
from bt_ddos_shield_client.shielded_turbobt.neuron_mutator import ShieldedNeuronMutator


class ShieldedBittensor(turbobt.Bittensor):
    def __init__(
        self,
        *args,
        wallet,
        ddos_shield_netuid: int,
        **kwargs,
    ):
        super().__init__(*args, wallet=wallet, **kwargs)
        self.ddos_shield_netuid = ddos_shield_netuid
        self._contact = turbo_bittensor_subtensor_contact()
        self._shield_client = ShieldClient(wallet=wallet)
        self._certificate_reconciler = CertificateReconciler(
            certificate=self._shield_client.certificate,
        )
        self._neuron_mutator = ShieldedNeuronMutator(
            wallet=self.wallet,
            netuid=self.ddos_shield_netuid,
            contact=self._contact,
            shield_client=self._shield_client,
            certificate_reconciler=self._certificate_reconciler,
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
                contact=self._contact,
                shield_client=self._shield_client,
                certificate_reconciler=self._certificate_reconciler,
                neuron_mutator=self._neuron_mutator,
            )
        return super().subnet(netuid)


@dataclasses.dataclass
class ShieldedSubnetReference(turbobt.subnet.SubnetReference):
    client: dataclasses.InitVar[turbobt.Bittensor]
    wallet: dataclasses.InitVar[object | None] = None
    contact: dataclasses.InitVar[object | None] = None
    shield_client: dataclasses.InitVar[ShieldClient | None] = None
    certificate_reconciler: dataclasses.InitVar[CertificateReconciler | None] = None
    neuron_mutator: dataclasses.InitVar[ShieldedNeuronMutator | None] = None

    def __post_init__(
        self,
        client,
        wallet=None,
        contact=None,
        shield_client=None,
        certificate_reconciler=None,
        neuron_mutator=None,
    ):
        super().__post_init__(client)
        self.client = client
        self.wallet = wallet or client.wallet
        self._contact = contact or turbo_bittensor_subtensor_contact()
        self._shield_client = shield_client or ShieldClient(wallet=self.wallet)
        self._certificate_reconciler = certificate_reconciler or CertificateReconciler(
            certificate=self._shield_client.certificate,
        )
        self._neuron_mutator = neuron_mutator or ShieldedNeuronMutator(
            wallet=self.wallet,
            netuid=self.netuid,
            contact=self._contact,
            shield_client=self._shield_client,
            certificate_reconciler=self._certificate_reconciler,
        )

    @classmethod
    def from_bittensor(
        cls,
        bittensor: turbobt.Bittensor,
        netuid: int,
        *,
        wallet=None,
        contact=None,
        shield_client: ShieldClient | None = None,
        certificate_reconciler: CertificateReconciler | None = None,
        neuron_mutator: ShieldedNeuronMutator | None = None,
    ) -> 'ShieldedSubnetReference':
        return cls(
            netuid=netuid,
            client=bittensor,
            wallet=wallet,
            contact=contact,
            shield_client=shield_client,
            certificate_reconciler=certificate_reconciler,
            neuron_mutator=neuron_mutator,
        )

    def clone(self, client: turbobt.Bittensor) -> 'ShieldedSubnetReference':
        return type(self)(
            netuid=self.netuid,
            client=client,
            wallet=self.wallet,
            contact=self._contact,
            shield_client=self._shield_client,
            certificate_reconciler=self._certificate_reconciler,
            neuron_mutator=self._neuron_mutator,
        )

    async def list_neurons(self, *args, **kwargs) -> list[turbobt.neuron.Neuron]:
        neurons = await self._contact.list_neurons(
            bittensor=self.client,
            netuid=self.netuid,
            *args,
            **kwargs,
        )
        return await self._neuron_mutator.mutate_neurons(self.client, neurons)
