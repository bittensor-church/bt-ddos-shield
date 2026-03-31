from pathlib import Path

from bittensor_wallet import Wallet

from server_shield.chain_writer.cli import main
from server_shield.shared import state_store
from server_shield.shared.config import get_config
from server_shield.shared.state_store import write_axon_public_ip
from server_shield.subtensor_contact import MockSubtensorContact, NeuronAxonRecord


def _write_example_files(example_dir: Path) -> None:
    example_dir.mkdir(parents=True, exist_ok=True)
    (example_dir / "root_domain.example.json").write_text('{\n    "domain": null\n}\n')
    (example_dir / "axon_public_ip.example.json").write_text('{\n    "ip": null\n}\n')
    (example_dir / "desired_domains.example.json").write_text('{\n    "domains": {}\n}\n')
    (example_dir / "blacklist.example.json").write_text('[]\n')
    (example_dir / "manifest.example.json").write_text(
        '{\n'
        '    "ddos_shield_manifest": {\n'
        '        "encrypted_url_mapping": {}\n'
        '    }\n'
        '}\n'
    )


def _set_required_env(monkeypatch, tmp_path: Path) -> None:
    get_config.cache_clear()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SERVER_SHIELD_MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_SUBTENSOR_ADDRESS", "ws://subtensor")
    monkeypatch.setenv("SERVER_SHIELD_NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__BACKEND_URL", "file:///tmp/server-shield-test-state")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__SHIELD_BACKEND", "AWS")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY", "miner-hotkey")


def _create_real_wallet(home_dir: Path, wallet_name: str, hotkey_name: str) -> str:
    wallet = Wallet(path=str(home_dir / ".bittensor" / "wallets"), name=wallet_name, hotkey=hotkey_name)
    wallet.create_coldkey_from_uri("//Alice", use_password=False, overwrite=True)
    wallet.create_hotkey_from_uri("//Alice", use_password=False, overwrite=True)
    return wallet.hotkey.ss58_address


def test_chain_writer_main_skips_when_axon_public_ip_missing(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    _set_required_env(monkeypatch, tmp_path)

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "skipping chain_writer because axon_public_ip is null" in captured.out


def test_chain_writer_main_logs_up_to_date_with_real_wallet(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    _set_required_env(monkeypatch, tmp_path)
    hotkey_ss58 = _create_real_wallet(tmp_path, "miner", "miner-hotkey")
    patched_subtensor_contact.set_registration(hotkey_ss58=hotkey_ss58, netuid=12, registered=True)
    patched_subtensor_contact.set_neuron_axon(
        hotkey_ss58=hotkey_ss58,
        netuid=12,
        neuron_axon=NeuronAxonRecord(
            is_null=False,
            is_serving=True,
            ip="1.2.3.4",
            port=9001,
        ),
    )
    write_axon_public_ip(tmp_path, "1.2.3.4")

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert hotkey_ss58 in captured.out
    assert "chain_writer axon already up to date" in captured.out
    assert [call.method for call in patched_subtensor_contact.calls] == [
        "is_hotkey_registered",
        "get_neuron_axon",
    ]


def test_chain_writer_main_publishes_when_chain_state_is_stale(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    _set_required_env(monkeypatch, tmp_path)
    hotkey_ss58 = _create_real_wallet(tmp_path, "miner", "miner-hotkey")
    patched_subtensor_contact.set_registration(hotkey_ss58=hotkey_ss58, netuid=12, registered=True)
    patched_subtensor_contact.set_neuron_axon(
        hotkey_ss58=hotkey_ss58,
        netuid=12,
        neuron_axon=NeuronAxonRecord(
            is_null=False,
            is_serving=True,
            ip="9.9.9.9",
            port=9001,
        ),
    )
    patched_subtensor_contact.set_publish_behavior(result=True)
    write_axon_public_ip(tmp_path, "1.2.3.4")

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "published axon info for " in captured.out
    assert [call.method for call in patched_subtensor_contact.calls] == [
        "is_hotkey_registered",
        "get_neuron_axon",
        "publish_axon",
    ]
    assert patched_subtensor_contact.calls[-1].ip == "1.2.3.4"
    assert patched_subtensor_contact.calls[-1].port == 9001


def test_chain_writer_main_returns_one_when_publish_fails(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    _set_required_env(monkeypatch, tmp_path)
    hotkey_ss58 = _create_real_wallet(tmp_path, "miner", "miner-hotkey")
    patched_subtensor_contact.set_registration(hotkey_ss58=hotkey_ss58, netuid=12, registered=True)
    patched_subtensor_contact.set_neuron_axon(
        hotkey_ss58=hotkey_ss58,
        netuid=12,
        neuron_axon=NeuronAxonRecord(
            is_null=False,
            is_serving=True,
            ip="9.9.9.9",
            port=9001,
        ),
    )
    patched_subtensor_contact.set_publish_behavior(result=False)
    write_axon_public_ip(tmp_path, "1.2.3.4")

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "RuntimeError: failed to set axon info" in captured.err
