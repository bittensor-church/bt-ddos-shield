from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component
from server_shield.shared.state_store import (
    ensure_state_files,
    read_blacklist,
    read_root_domain,
    write_desired_domains,
    write_manifest,
)


def _run_once() -> int:
    ensure_state_files()
    root_domain = read_root_domain()
    blacklist = read_blacklist()
    write_desired_domains(domains=[])
    write_manifest(manifest_url=None, encrypted_addresses=[])
    print(
        f"hello from chain_reader hosted_zone={root_domain.domain!r} blacklist_size={len(blacklist.domains)}",
        flush=True,
    )
    return 0


def main() -> int:
    get_config()
    return run_component("chain-reader", _run_once)


if __name__ == "__main__":
    raise SystemExit(main())
