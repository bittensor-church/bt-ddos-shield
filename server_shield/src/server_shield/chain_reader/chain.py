from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import bittensor

from server_shield.shared.config import AppConfig


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


def fetch_validators_with_certs(config: AppConfig) -> list[ValidatorOnChain]:
    subtensor = bittensor.subtensor(config.subtensor_address)
    metagraph = bittensor.metagraph(
        netuid=config.netuid,
        subtensor=subtensor,
    )

    validators: list[ValidatorOnChain] = []
    for hotkey, permit in zip(metagraph.hotkeys, metagraph.validator_permit, strict=False):
        if not bool(permit):
            continue

        certificate = subtensor.query_subtensor(
            name="NeuronCertificates",
            params=[config.netuid, hotkey],
        )
        public_cert, invalid_reason = _decode_certificate_payload(certificate)
        validators.append(
            ValidatorOnChain(
                hotkey=hotkey,
                public_cert=public_cert,
                cert_invalid_reason=invalid_reason,
            )
        )

    return validators
