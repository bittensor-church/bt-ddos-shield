import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from server_shield.shared.state import (
    BlacklistState,
    DesiredDomainsState,
    HostedZoneDomainState,
    ManifestState,
    NlbIpState,
)


DEFAULT_STATE_FILES = {
    "hosted_zone_domain.json": HostedZoneDomainState(),
    "nlb_ip.json": NlbIpState(),
    "desired_domains.json": DesiredDomainsState(),
    "blacklist.json": BlacklistState(),
    "manifest.json": ManifestState(),
}


def ensure_state_files(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    for file_name, model in DEFAULT_STATE_FILES.items():
        path = state_dir / file_name
        if not path.exists():
            _atomic_write(path, model.model_dump())


def read_desired_domains(state_dir: Path) -> DesiredDomainsState:
    ensure_state_files(state_dir)
    return DesiredDomainsState.model_validate_json((state_dir / "desired_domains.json").read_text())


def write_desired_domains(state_dir: Path, domains: list[str]) -> None:
    ensure_state_files(state_dir)
    _atomic_write(state_dir / "desired_domains.json", DesiredDomainsState(domains=domains).model_dump())


def read_nlb_ip(state_dir: Path) -> NlbIpState:
    ensure_state_files(state_dir)
    return NlbIpState.model_validate_json((state_dir / "nlb_ip.json").read_text())


def write_nlb_ip(state_dir: Path, ip: str | None) -> None:
    ensure_state_files(state_dir)
    _atomic_write(state_dir / "nlb_ip.json", NlbIpState(ip=ip).model_dump())


def write_hosted_zone_domain(state_dir: Path, domain: str | None) -> None:
    ensure_state_files(state_dir)
    _atomic_write(
        state_dir / "hosted_zone_domain.json",
        HostedZoneDomainState(domain=domain).model_dump(),
    )


def read_hosted_zone_domain(state_dir: Path) -> HostedZoneDomainState:
    ensure_state_files(state_dir)
    return HostedZoneDomainState.model_validate_json(
        (state_dir / "hosted_zone_domain.json").read_text()
    )


def read_blacklist(state_dir: Path) -> BlacklistState:
    ensure_state_files(state_dir)
    return BlacklistState.model_validate_json((state_dir / "blacklist.json").read_text())


def write_blacklist(state_dir: Path, domains: list[str]) -> None:
    ensure_state_files(state_dir)
    _atomic_write(state_dir / "blacklist.json", BlacklistState(domains=domains).model_dump())


def write_manifest(state_dir: Path, manifest_url: str | None, encrypted_addresses: list[str]) -> None:
    ensure_state_files(state_dir)
    _atomic_write(
        state_dir / "manifest.json",
        ManifestState(
            manifest_url=manifest_url,
            encrypted_addresses=encrypted_addresses,
        ).model_dump(),
    )


def read_manifest(state_dir: Path) -> ManifestState:
    ensure_state_files(state_dir)
    return ManifestState.model_validate_json((state_dir / "manifest.json").read_text())


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    with NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)
