from pathlib import Path
import os
import subprocess

from server_shield.chain_writer.cli import _run_once
from server_shield.shared.state_store import ensure_state_files, write_nlb_ip


def test_chain_writer_skips_when_nlb_ip_missing(tmp_path: Path, capsys) -> None:
    ensure_state_files(tmp_path)

    exit_code = _run_once(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "skipping chain_writer because nlb_ip is null" in captured.out


def test_chain_writer_logs_placeholder_when_nlb_ip_present(tmp_path: Path, capsys) -> None:
    ensure_state_files(tmp_path)
    write_nlb_ip(tmp_path, "1.2.3.4")

    exit_code = _run_once(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "hello from chain_writer for 1.2.3.4" in captured.out


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
            "SERVER_SHIELD_PULUMI__AWS_REGION": "eu-north-1",
            "SERVER_SHIELD_PULUMI__HOSTED_ZONE_ID": "Z123",
            "SERVER_SHIELD_PULUMI__MINER_INSTANCE_ID": "i-123",
            "SERVER_SHIELD_PULUMI__MINER_PORT": "9001",
        },
    )

    assert completed.returncode == 0
    assert "skipping chain_writer because nlb_ip is null" in completed.stdout
