from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from bittensor import Subtensor
from bittensor.core.metagraph import Metagraph

from bt_ddos_shield_client.certificate_reconciliation import CertificateReconciler
from bt_ddos_shield_client.client import ShieldClient, resolve_certificate_path
from bt_ddos_shield_client.contacts import bittensor_subtensor_contact
from bt_ddos_shield_client.internal import parse_shield_address, run_async_in_thread


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
        self._contact: SubtensorContact | None = None
        self._shield_client = ShieldClient(wallet=wallet)
        self._certificate_reconciler = CertificateReconciler(
            certificate=self._shield_client.certificate,
        )
        self._async_executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix='shield-metagraph',
        )

        if sync:
            self.sync(block=block, lite=lite, subtensor=self.subtensor)
        elif block is not None:
            raise ValueError('Block argument is valid only when sync is True')

    def _get_contact(self) -> AbstractBittensorSubtensorContact:
        if self._contact is None:
            self._contact = bittensor_subtensor_contact()
        return self._contact

    def sync(self, block: int | None = None, lite: bool | None = None, subtensor=None):
        if subtensor is not None and subtensor is not self.subtensor:
            self.subtensor = subtensor
        self._get_contact().sync_metagraph(self, subtensor=self.subtensor, block=block, lite=lite)
        run_async_in_thread(
            self._certificate_reconciler.ensure_own_certificate_matches(
                contact=self._get_contact(),
                client=self.subtensor,
                netuid=self.netuid,
                hotkey=self.wallet.hotkey.ss58_address,
                wallet=self.wallet,
            ),
            executor=self._async_executor,
        )
        own_hotkey = self.wallet.hotkey.ss58_address
        shield_addresses = run_async_in_thread(
            self._shield_client.resolve_shield_addresses(
                own_hotkey,
                [(axon.hotkey, str(axon.ip), axon.port) for axon in self.axons],
            ),
            executor=self._async_executor,
        )
        for axon, shield_address in zip(self.axons, shield_addresses, strict=False):
            if shield_address is None:
                continue
            parsed_address = parse_shield_address(shield_address)
            if parsed_address is None:
                continue
            axon.ip = parsed_address[0]
            axon.port = parsed_address[1]
