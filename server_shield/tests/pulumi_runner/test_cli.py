from pathlib import Path
from types import SimpleNamespace

from server_shield.pulumi_runner.cli import _invoke_pulumi


def test_invoke_pulumi_uses_fixed_stack(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("server_shield.pulumi_runner.cli.subprocess.run", fake_run)

    exit_code = _invoke_pulumi()

    assert exit_code == 0
    assert calls == [[
        "pulumi",
        "up",
        "--yes",
        "--stack",
        "server-shield",
        "--cwd",
        str(Path(__file__).resolve().parents[2] / "pulumi_project"),
    ]]
