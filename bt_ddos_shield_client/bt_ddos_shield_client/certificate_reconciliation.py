from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from bt_ddos_shield_client.certificates import Certificate
from bt_ddos_shield_client.types import PublicKey


@dataclass
class CertificateReconciler:
    get_own_public_key: Callable[[], Awaitable[PublicKey | None]]
    upload_public_key: Callable[[PublicKey, int], Awaitable[None]]
    certificate: Certificate
    disabled: bool = False
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

    async def ensure_own_certificate_matches(self) -> None:
        if self.disabled or self._is_match_cached():
            return

        public_key = await self.get_own_public_key()
        if public_key == self.certificate.public_key:
            self._cache_match()
            return

        await self.upload_public_key(
            self.certificate.public_key,
            self.certificate.algorithm,
        )
        self._cache_match()
