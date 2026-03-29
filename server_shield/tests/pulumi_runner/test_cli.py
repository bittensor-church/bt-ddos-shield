from pathlib import Path
from types import SimpleNamespace

from server_shield.pulumi_runner.cli import _invoke_pulumi, main


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


def test_pulumi_runner_main_does_not_require_state_dir(monkeypatch) -> None:
    monkeypatch.setattr(
        "server_shield.pulumi_runner.cli.get_config",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "server_shield.pulumi_runner.cli._invoke_pulumi",
        lambda: 0,
    )
    monkeypatch.setattr(
        "server_shield.pulumi_runner.cli.run_component",
        lambda component_name, fn: fn(),
    )

    assert main() == 0
