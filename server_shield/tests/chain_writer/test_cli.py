from pathlib import Path
import os
import subprocess
from types import SimpleNamespace

from server_shield.chain_writer.cli import _run_once, main
from server_shield.shared import state_store
from server_shield.shared.state_store import ensure_state_files, write_axon_public_ip


def _write_example_files(example_dir: Path) -> None:
    example_dir.mkdir(parents=True, exist_ok=True)
    (example_dir / "root_domain.example.json").write_text('{"domain": null}\n')
    (example_dir / "axon_public_ip.example.json").write_text('{"ip": null}\n')
    (example_dir / "desired_domains.example.json").write_text('{"domains": {}}\n')
    (example_dir / "blacklist.example.json").write_text('[]\n')
    (example_dir / "manifest.example.json").write_text('{"manifest_url": null, "encrypted_addresses": []}\n')


def test_chain_writer_skips_when_axon_public_ip_missing(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    ensure_state_files(tmp_path)

    exit_code = _run_once()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "skipping chain_writer because axon_public_ip is null" in captured.out


def test_chain_writer_delegates_to_publish_when_axon_public_ip_present(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    ensure_state_files(tmp_path)
    write_axon_public_ip(tmp_path, "1.2.3.4")
    fake_config = SimpleNamespace(name="config")
    monkeypatch.setattr("server_shield.chain_writer.cli.get_config", lambda: fake_config)

    def fake_publish(config, axon_public_ip: str) -> int:
        assert config is fake_config
        assert axon_public_ip == "1.2.3.4"
        print(f"delegated chain_writer publish for {axon_public_ip}")
        return 0

    monkeypatch.setattr(
        "server_shield.chain_writer.cli._publish_axon_if_needed",
        fake_publish,
    )

    exit_code = _run_once()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "delegated chain_writer publish for 1.2.3.4" in captured.out


def test_chain_writer_module_execution_runs_main(tmp_path: Path) -> None:
    completed = subprocess.run(
        [".venv/bin/python", "-m", "server_shield.chain_writer.cli"],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "SERVER_SHIELD_STATE_DIR": str(tmp_path),
            "SERVER_SHIELD_SUBTENSOR_ADDRESS": "ws://subtensor",
            "SERVER_SHIELD_NETUID": "12",
            "SERVER_SHIELD_PULUMI__BACKEND_URL": "file:///tmp/server-shield-test-state",
            "SERVER_SHIELD_PULUMI__SHIELD_BACKEND": "AWS",
            "SERVER_SHIELD_MINER_PORT": "9001",
            "SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID": "key",
            "SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY": "secret",
            "SERVER_SHIELD_PULUMI__AWS__AWS_REGION": "eu-north-1",
            "SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID": "Z123",
            "SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID": "i-123",
            "SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME": "miner",
            "SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY": "miner-hotkey",
        },
    )

    assert completed.returncode == 0
    assert (
        "skipping chain_writer because axon_public_ip is null" in completed.stdout
        or "hello from chain_writer for " in completed.stdout
    )


def test_chain_writer_main_does_not_require_state_dir(monkeypatch) -> None:
    monkeypatch.setattr(
        "server_shield.chain_writer.cli.get_config",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "server_shield.chain_writer.cli._run_once",
        lambda: 0,
    )
    monkeypatch.setattr(
        "server_shield.chain_writer.cli.run_component",
        lambda component_name, fn: fn(),
    )

    assert main() == 0
