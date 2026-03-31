from __future__ import annotations

from functools import partial
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import os

from bittensor import Subtensor
from bittensor.core.metagraph import Metagraph

from bt_ddos_shield_client.certificate_reconciliation import CertificateReconciler
from bt_ddos_shield_client.client import ShieldClient
from bt_ddos_shield_client.contacts import bittensor_subtensor_contact
from bt_ddos_shield_client.internal import parse_shield_address, run_async_in_thread


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
        self._contact = bittensor_subtensor_contact()
        self._shield_client = ShieldClient(
            certificate_path=resolve_certificate_path(self.options.certificate_path),
        )
        self._certificate_reconciler = CertificateReconciler(
            get_own_public_key=partial(
                self._contact.get_own_public_key,
                subtensor=self.subtensor,
                netuid=netuid,
                hotkey=wallet.hotkey.ss58_address,
            ),
            upload_public_key=partial(
                self._contact.upload_public_key,
                subtensor=self.subtensor,
                wallet=wallet,
                netuid=netuid,
            ),
            certificate=self._shield_client.certificate,
            disabled=self.options.disable_uploading_certificate,
        )
        self._async_executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix='shield-metagraph',
        )

        if sync:
            self.sync(block=block, lite=lite, subtensor=self.subtensor)
        elif block is not None:
            raise ValueError('Block argument is valid only when sync is True')

    def sync(self, block: int | None = None, lite: bool | None = None, subtensor=None):
        if subtensor is not None and subtensor is not self.subtensor:
            self.subtensor = subtensor
            self._certificate_reconciler.get_own_public_key = partial(
                self._contact.get_own_public_key,
                subtensor=self.subtensor,
                netuid=self.netuid,
                hotkey=self.wallet.hotkey.ss58_address,
            )
            self._certificate_reconciler.upload_public_key = partial(
                self._contact.upload_public_key,
                subtensor=self.subtensor,
                wallet=self.wallet,
                netuid=self.netuid,
            )
        self._contact.sync_metagraph(self, subtensor=self.subtensor, block=block, lite=lite)
        run_async_in_thread(
            self._certificate_reconciler.ensure_own_certificate_matches(),
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
