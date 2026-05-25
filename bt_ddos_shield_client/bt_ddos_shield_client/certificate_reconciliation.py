from __future__ import annotations

import inspect
import time
from dataclasses import dataclass

from bt_ddos_shield_client.certificates import Certificate
from bt_ddos_shield_client.types import PublicKey


def _contact_client_kwargs(method, client: object) -> dict[str, object]:
    parameters = inspect.signature(method).parameters
    if 'subtensor' in parameters:
        return {'subtensor': client}
    if 'bittensor' in parameters:
        return {'bittensor': client}
    raise TypeError('contact method must accept either "subtensor" or "bittensor"')


@dataclass
class CertificateReconciler:
    certificate: Certificate
    match_ttl_seconds: float = 300.0
    _matched_public_key: str | None = None
    _matched_until: float = 0.0

    def _is_match_cached(self) -> bool:
        return (
            self._matched_public_key == self.certificate.public_key
            and time.monotonic() < self._matched_until
        )

    def _cache_match(self) -> None:
        self._matched_public_key = self.certificate.public_key
        self._matched_until = time.monotonic() + self.match_ttl_seconds

    async def ensure_own_certificate_matches(
        self,
        *,
        contact,
        client,
        netuid: int,
        hotkey: str,
        wallet,
    ) -> None:
        if self._is_match_cached():
            return

        public_key = await contact.get_own_public_key(
            netuid=netuid,
            hotkey=hotkey,
            **_contact_client_kwargs(contact.get_own_public_key, client),
        )
        if public_key == self.certificate.public_key:
            self._cache_match()
            return

        await contact.upload_public_key(
            self.certificate.public_key,
            self.certificate.algorithm,
            wallet=wallet,
            netuid=netuid,
            **_contact_client_kwargs(contact.upload_public_key, client),
        )
        self._cache_match()
