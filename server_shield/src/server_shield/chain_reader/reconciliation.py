from __future__ import annotations

from dataclasses import dataclass
import secrets

from server_shield.chain_reader.chain import ValidatorOnChain
from server_shield.shared.state import DesiredDomainEntry


@dataclass(frozen=True)
class ReconciliationResult:
    desired_domains: dict[str, DesiredDomainEntry]
    observed: int
    kept: int
    created: int
    rotated_for_cert: int
    rotated_for_root_domain: int
    removed: int
    blacklisted: int
    invalid_cert: int


def _matches_root_domain(domain: str, root_domain: str) -> bool:
    return domain.endswith(f".{root_domain}")


def _generate_domain(hotkey: str, root_domain: str, used_domains: set[str]) -> str:
    prefix = hotkey[:8]
    while True:
        candidate = f"{prefix}-{secrets.token_hex(6)}.{root_domain}"
        if candidate not in used_domains:
            used_domains.add(candidate)
            return candidate


def reconcile_desired_domains(
    *,
    root_domain: str,
    current_domains: dict[str, DesiredDomainEntry],
    validators: list[ValidatorOnChain],
    blacklist: set[str],
) -> ReconciliationResult:
    desired_domains: dict[str, DesiredDomainEntry] = {}
    used_domains: set[str] = set()
    kept = 0
    created = 0
    rotated_for_cert = 0
    rotated_for_root_domain = 0
    blacklisted_count = 0
    invalid_cert = 0

    for validator in sorted(validators, key=lambda entry: entry.hotkey):
        if validator.hotkey in blacklist:
            blacklisted_count += 1
            continue
        if validator.public_cert is None:
            invalid_cert += 1
            continue

        current_entry = current_domains.get(validator.hotkey)
        if (
            current_entry is not None
            and current_entry.public_cert == validator.public_cert
            and _matches_root_domain(current_entry.domain, root_domain)
        ):
            desired_domains[validator.hotkey] = current_entry
            used_domains.add(current_entry.domain)
            kept += 1
            continue

        next_entry = DesiredDomainEntry(
            domain=_generate_domain(validator.hotkey, root_domain, used_domains),
            public_cert=validator.public_cert,
        )
        desired_domains[validator.hotkey] = next_entry

        if current_entry is None:
            created += 1
        elif current_entry.public_cert != validator.public_cert:
            rotated_for_cert += 1
        else:
            rotated_for_root_domain += 1

    removed = len(set(current_domains) - set(desired_domains))
    return ReconciliationResult(
        desired_domains=desired_domains,
        observed=len(validators),
        kept=kept,
        created=created,
        rotated_for_cert=rotated_for_cert,
        rotated_for_root_domain=rotated_for_root_domain,
        removed=removed,
        blacklisted=blacklisted_count,
        invalid_cert=invalid_cert,
    )
