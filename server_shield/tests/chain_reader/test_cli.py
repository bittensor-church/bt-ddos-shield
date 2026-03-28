from pathlib import Path
import os
import subprocess

from server_shield.chain_reader.cli import _run_once


def test_chain_reader_bootstraps_state_and_exits_zero(tmp_path: Path, capsys) -> None:
    exit_code = _run_once(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
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
            "SERVER_SHIELD_PULUMI__AWS_REGION": "eu-north-1",
            "SERVER_SHIELD_PULUMI__HOSTED_ZONE_ID": "Z123",
            "SERVER_SHIELD_PULUMI__MINER_INSTANCE_ID": "i-123",
            "SERVER_SHIELD_PULUMI__MINER_PORT": "9001",
        },
    )

    assert completed.returncode == 0
    assert "hello from chain_reader" in completed.stdout
