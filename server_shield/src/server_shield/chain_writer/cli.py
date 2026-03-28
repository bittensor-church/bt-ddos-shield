from pathlib import Path

from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component
from server_shield.shared.state_store import ensure_state_files, read_nlb_ip


def _run_once(state_dir: Path) -> int:
    ensure_state_files(state_dir)
    nlb_ip = read_nlb_ip(state_dir)
    if nlb_ip.ip is None:
        print("skipping chain_writer because nlb_ip is null", flush=True)
        return 0

    print(f"hello from chain_writer for {nlb_ip.ip}", flush=True)
    return 0


def main() -> int:
    config = get_config()
    return run_component("chain-writer", lambda: _run_once(config.state_dir))


if __name__ == "__main__":
    raise SystemExit(main())
