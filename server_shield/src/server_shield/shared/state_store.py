import json
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

from server_shield.shared.state import BlacklistState, DesiredDomainsState, HostedZoneDomainState, ManifestState, NlbIpState


DEFAULT_STATE_DIR = Path(__file__).resolve().parent / "state_files"
STATE_FILE_NAMES = (
    "hosted_zone_domain.json",
    "nlb_ip.json",
    "desired_domains.json",
    "blacklist.json",
    "manifest.json",
)


def ensure_state_files(state_dir: Path | None = None) -> None:
    resolved_state_dir = _resolve_state_dir(state_dir)
    resolved_state_dir.mkdir(parents=True, exist_ok=True)
    for file_name in STATE_FILE_NAMES:
        path = resolved_state_dir / file_name
        if not path.exists():
            _copy_example_state_file(file_name, resolved_state_dir)


def read_desired_domains(state_dir: Path | None = None) -> DesiredDomainsState:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    return DesiredDomainsState.model_validate_json((resolved_state_dir / "desired_domains.json").read_text())


def write_desired_domains(state_dir: Path | None = None, domains: list[str] | None = None) -> None:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    _atomic_write(
        resolved_state_dir / "desired_domains.json",
        DesiredDomainsState(domains=domains or []).model_dump(),
    )


def read_nlb_ip(state_dir: Path | None = None) -> NlbIpState:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    return NlbIpState.model_validate_json((resolved_state_dir / "nlb_ip.json").read_text())


def write_nlb_ip(state_dir: Path | None = None, ip: str | None = None) -> None:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    _atomic_write(resolved_state_dir / "nlb_ip.json", NlbIpState(ip=ip).model_dump())


def write_hosted_zone_domain(state_dir: Path | None = None, domain: str | None = None) -> None:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    _atomic_write(
        resolved_state_dir / "hosted_zone_domain.json",
        HostedZoneDomainState(domain=domain).model_dump(),
    )


def read_hosted_zone_domain(state_dir: Path | None = None) -> HostedZoneDomainState:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    return HostedZoneDomainState.model_validate_json(
        (resolved_state_dir / "hosted_zone_domain.json").read_text()
    )


def read_blacklist(state_dir: Path | None = None) -> BlacklistState:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    return BlacklistState.model_validate_json((resolved_state_dir / "blacklist.json").read_text())


def write_blacklist(state_dir: Path | None = None, domains: list[str] | None = None) -> None:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    _atomic_write(
        resolved_state_dir / "blacklist.json",
        BlacklistState(domains=domains or []).model_dump(),
    )


def write_manifest(
    state_dir: Path | None = None,
    manifest_url: str | None = None,
    encrypted_addresses: list[str] | None = None,
) -> None:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    _atomic_write(
        resolved_state_dir / "manifest.json",
        ManifestState(
            manifest_url=manifest_url,
            encrypted_addresses=encrypted_addresses or [],
        ).model_dump(),
    )


def read_manifest(state_dir: Path | None = None) -> ManifestState:
    resolved_state_dir = _resolve_state_dir(state_dir)
    ensure_state_files(resolved_state_dir)
    return ManifestState.model_validate_json((resolved_state_dir / "manifest.json").read_text())


def _resolve_state_dir(state_dir: Path | None) -> Path:
    if state_dir is None:
        return DEFAULT_STATE_DIR
    return state_dir


def _copy_example_state_file(file_name: str, state_dir: Path) -> None:
    example_path = DEFAULT_STATE_DIR / file_name.replace(".json", ".example.json")
    if not example_path.exists():
        raise FileNotFoundError(f"Missing state example file: {example_path}")
    shutil.copyfile(example_path, state_dir / file_name)


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    with NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)
