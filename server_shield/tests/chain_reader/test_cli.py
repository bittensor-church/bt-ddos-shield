from pathlib import Path

from server_shield.chain_reader.cli import _run_once


def test_chain_reader_bootstraps_state_and_exits_zero(tmp_path: Path, capsys) -> None:
    exit_code = _run_once(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "hello from chain_reader" in captured.out
    assert (tmp_path / "desired_domains.json").exists()
