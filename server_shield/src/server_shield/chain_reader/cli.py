from pathlib import Path

from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component
from server_shield.shared.state_store import (
    ensure_state_files,
    read_blacklist,
    read_hosted_zone_domain,
    write_desired_domains,
    write_manifest,
)


def _run_once(state_dir: Path) -> int:
    ensure_state_files(state_dir)
    hosted_zone = read_hosted_zone_domain(state_dir)
    blacklist = read_blacklist(state_dir)
    write_desired_domains(state_dir, [])
    write_manifest(state_dir, None, [])
    print(
        f"hello from chain_reader hosted_zone={hosted_zone.domain!r} blacklist_size={len(blacklist.domains)}",
        flush=True,
    )
    return 0


def main() -> int:
    config = get_config()
    return run_component("chain-reader", lambda: _run_once(config.state_dir))


if __name__ == "__main__":
    raise SystemExit(main())
