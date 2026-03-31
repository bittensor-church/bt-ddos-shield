from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from server_shield.subtensor_contact import AbstractSubtensorContact


@dataclass(frozen=True)
class ValidatorOnChain:
    hotkey: str
    public_cert: str | None
    cert_invalid_reason: str | None = None


def _decode_certificate_payload(payload: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if payload is None:
        return None, "missing certificate"

    try:
        public_key = payload["public_key"][0]
    except (KeyError, TypeError, IndexError):
        return None, "malformed certificate payload"

    if isinstance(public_key, str):
        return public_key, None

    try:
        return bytes(public_key).hex(), None
    except (TypeError, ValueError):
        return None, "malformed certificate payload"


def fetch_validators_with_certs(
    *,
    contact: AbstractSubtensorContact,
    netuid: int,
) -> list[ValidatorOnChain]:
    validators: list[ValidatorOnChain] = []
    for record in contact.list_validator_certificates(netuid=netuid):
        public_cert, invalid_reason = _decode_certificate_payload(record.certificate_payload)
        validators.append(
            ValidatorOnChain(
                hotkey=record.hotkey,
                public_cert=public_cert,
                cert_invalid_reason=invalid_reason,
            )
        )
    return validators
