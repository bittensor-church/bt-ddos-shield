from pathlib import Path
import os
import subprocess
from types import SimpleNamespace

from server_shield.chain_reader.cli import _run_once, main
from server_shield.shared import state_store
from server_shield.shared.state_store import read_root_domain


def _write_example_files(example_dir: Path) -> None:
    example_dir.mkdir(parents=True, exist_ok=True)
    (example_dir / "root_domain.example.json").write_text('{"domain": null}\n')
    (example_dir / "axon_public_ip.example.json").write_text('{"ip": null}\n')
    (example_dir / "desired_domains.example.json").write_text('{"domains": []}\n')
    (example_dir / "blacklist.example.json").write_text('{"domains": []}\n')
    (example_dir / "manifest.example.json").write_text('{"manifest_url": null, "encrypted_addresses": []}\n')


def test_chain_reader_bootstraps_state_and_exits_zero(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    exit_code = _run_once()
    root_domain = read_root_domain(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert root_domain.domain is None
    assert "hello from chain_reader" in captured.out
    assert (tmp_path / "desired_domains.json").exists()


def test_chain_reader_module_execution_runs_main(tmp_path: Path) -> None:
    completed = subprocess.run(
        [".venv/bin/python", "-m", "server_shield.chain_reader.cli"],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "SERVER_SHIELD_STATE_DIR": str(tmp_path),
            "SERVER_SHIELD_PULUMI__BACKEND_URL": "file:///tmp/server-shield-test-state",
            "SERVER_SHIELD_PULUMI__SHIELD_BACKEND": "AWS",
            "SERVER_SHIELD_MINER_PORT": "9001",
            "SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID": "key",
            "SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY": "secret",
            "SERVER_SHIELD_PULUMI__AWS__AWS_REGION": "eu-north-1",
            "SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID": "Z123",
            "SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID": "i-123",
        },
    )

    assert completed.returncode == 0
    assert "hello from chain_reader" in completed.stdout


def test_chain_reader_main_does_not_require_state_dir(monkeypatch) -> None:
    monkeypatch.setattr(
        "server_shield.chain_reader.cli.get_config",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "server_shield.chain_reader.cli._run_once",
        lambda: 0,
    )
    monkeypatch.setattr(
        "server_shield.chain_reader.cli.run_component",
        lambda component_name, fn: fn(),
    )

    assert main() == 0
