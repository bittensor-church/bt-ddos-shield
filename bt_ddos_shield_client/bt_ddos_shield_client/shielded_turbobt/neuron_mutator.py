from __future__ import annotations

from collections.abc import Mapping

import turbobt
import turbobt.neuron

from bt_ddos_shield_client.certificate_reconciliation import CertificateReconciler
from bt_ddos_shield_client.client import ShieldClient
from bt_ddos_shield_client.internal import parse_shield_address
from bt_ddos_shield_client.shield_metagraph import ShieldMetagraphOptions, resolve_certificate_path
from bt_ddos_shield_client.shielded_turbobt.contacts import turbo_bittensor_subtensor_contact


class ShieldedNeuronMutator:
    def __init__(
        self,
        *,
        wallet,
        netuid: int,
        ddos_shield_options: ShieldMetagraphOptions | None = None,
        contact=None,
        shield_client: ShieldClient | None = None,
        certificate_reconciler: CertificateReconciler | None = None,
    ):
        self.wallet = wallet
        self.netuid = netuid
        self.ddos_shield_options = ddos_shield_options or ShieldMetagraphOptions()
        self._contact = contact or turbo_bittensor_subtensor_contact()
        self._shield_client = shield_client or ShieldClient(
            certificate_path=resolve_certificate_path(self.ddos_shield_options.certificate_path),
        )
        self._certificate_reconciler = certificate_reconciler or CertificateReconciler(
            certificate=self._shield_client.certificate,
            disabled=self.ddos_shield_options.disable_uploading_certificate,
        )

    async def mutate_neurons(
        self,
        bittensor: turbobt.Bittensor,
        neurons: list[turbobt.neuron.Neuron],
    ) -> list[turbobt.neuron.Neuron]:
        await self._certificate_reconciler.ensure_own_certificate_matches(
            contact=self._contact,
            client=bittensor,
            netuid=self.netuid,
            hotkey=self.wallet.hotkey.ss58_address,
            wallet=self.wallet,
        )
        neurons_by_hotkey = self._neurons_by_hotkey(neurons)
        shield_addresses = await self._shield_client.resolve_shield_addresses_by_hotkey(
            self.wallet.hotkey.ss58_address,
            {
                neuron.hotkey: (str(neuron.axon_info.ip), neuron.axon_info.port)
                for neuron in neurons
            },
        )
        self._apply_shield_addresses(neurons_by_hotkey, shield_addresses)
        return neurons

    def _neurons_by_hotkey(
        self,
        neurons: list[turbobt.neuron.Neuron],
    ) -> dict[str, turbobt.neuron.Neuron]:
        neurons_by_hotkey: dict[str, turbobt.neuron.Neuron] = {}
        for neuron in neurons:
            if neuron.hotkey in neurons_by_hotkey:
                raise ValueError(f'duplicate neuron hotkey: {neuron.hotkey}')
            neurons_by_hotkey[neuron.hotkey] = neuron
        return neurons_by_hotkey

    def _apply_shield_addresses(
        self,
        neurons_by_hotkey: Mapping[str, turbobt.neuron.Neuron],
        shield_addresses: Mapping[str, str | None],
    ) -> None:
        for hotkey, shield_address in shield_addresses.items():
            if shield_address is None:
                continue
            parsed_address = parse_shield_address(shield_address)
            if parsed_address is None:
                continue
            neuron = neurons_by_hotkey.get(hotkey)
            if neuron is None:
                continue
            neuron.axon_info.ip = parsed_address[0]
            neuron.axon_info.port = parsed_address[1]
