import bittensor_wallet

from server_shield.shared.config import AppConfig, get_config
from server_shield.shared.runtime import run_component
from server_shield.shared.state_store import ensure_state_files, read_axon_public_ip
from server_shield.subtensor_contact import subtensor_contact


def _run_once() -> int:
    ensure_state_files()
    axon_public_ip = read_axon_public_ip()
    if axon_public_ip.ip is None:
        print("skipping chain_writer because axon_public_ip is null", flush=True)
        return 0

    config = get_config()
    return _publish_axon_if_needed(config, axon_public_ip.ip)


def _publish_axon_if_needed(config: AppConfig, axon_public_ip: str) -> int:
    wallet = bittensor_wallet.Wallet(
        config.chain_writer.wallet_name,
        config.chain_writer.wallet_hotkey,
    )
    hotkey_ss58 = wallet.hotkey.ss58_address
    contact = subtensor_contact(config.subtensor_address)
    if not contact.is_hotkey_registered(hotkey_ss58=hotkey_ss58, netuid=config.netuid):
        print(
            f"skipping chain_writer because hotkey {hotkey_ss58} is not registered on netuid {config.netuid}",
            flush=True,
        )
        return 0

    neuron = contact.get_neuron_axon(hotkey_ss58=hotkey_ss58, netuid=config.netuid)
    if neuron.is_null:
        print(
            f"skipping chain_writer because neuron lookup failed for hotkey {hotkey_ss58} on netuid {config.netuid}",
            flush=True,
        )
        return 0

    desired_port = config.miner_port
    current_ip = neuron.ip
    current_port = neuron.port
    if neuron.is_serving and current_ip == axon_public_ip and current_port == desired_port:
        print(
            f"chain_writer axon already up to date for {hotkey_ss58}: {current_ip}:{current_port}",
            flush=True,
        )
        return 0

    success = contact.publish_axon(
        wallet=wallet,
        netuid=config.netuid,
        ip=axon_public_ip,
        port=desired_port,
    )
    if not success:
        raise RuntimeError("failed to set axon info")

    print(
        f"published axon info for {hotkey_ss58}: {axon_public_ip}:{desired_port}",
        flush=True,
    )
    return 0


def main() -> int:
    get_config()
    return run_component("chain-writer", _run_once)


if __name__ == "__main__":
    raise SystemExit(main())
