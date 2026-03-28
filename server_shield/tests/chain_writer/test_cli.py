from pathlib import Path

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
