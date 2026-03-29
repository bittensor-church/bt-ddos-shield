from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component
from server_shield.shared.state_store import ensure_state_files, read_axon_public_ip


def _run_once() -> int:
    ensure_state_files()
    axon_public_ip = read_axon_public_ip()
    if axon_public_ip.ip is None:
        print("skipping chain_writer because axon_public_ip is null", flush=True)
        return 0

    print(f"hello from chain_writer for {axon_public_ip.ip}", flush=True)
    return 0


def main() -> int:
    get_config()
    return run_component("chain-writer", _run_once)


if __name__ == "__main__":
    raise SystemExit(main())
