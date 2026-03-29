from pathlib import Path
from types import SimpleNamespace

from server_shield.pulumi_runner.cli import _invoke_pulumi, main


def test_invoke_pulumi_logs_in_selects_stack_and_runs_up_with_provider_env(monkeypatch) -> None:
    calls: list[tuple[list[str], bool, dict[str, str] | None]] = []

    def fake_run(command: list[str], check: bool, env: dict[str, str] | None = None) -> SimpleNamespace:
        calls.append((command, check, env))
        return SimpleNamespace(returncode=0)

    config = SimpleNamespace(
        pulumi=SimpleNamespace(
            backend_url="s3://example-state-bucket/server-shield",
            stack_name="custom-stack",
            shield_backend="AWS",
                        aws=SimpleNamespace(
                aws_access_key_id="key",
                aws_secret_access_key="secret",
                aws_region="eu-north-1",
                hosted_zone_id="Z123",
                miner_instance_id="i-123",
            ),
        )
    )
    monkeypatch.setattr("server_shield.pulumi_runner.cli.get_config", lambda: config)
    monkeypatch.setattr("server_shield.pulumi_runner.cli.subprocess.run", fake_run)

    exit_code = _invoke_pulumi()

    assert exit_code == 0
    assert [call[0] for call in calls] == [
        ["pulumi", "login", "s3://example-state-bucket/server-shield"],
        [
            "pulumi",
            "stack",
            "select",
            "custom-stack",
            "--create",
            "--cwd",
            str(Path(__file__).resolve().parents[2] / "pulumi_project"),
        ],
        [
            "pulumi",
            "up",
            "--yes",
            "--stack",
            "custom-stack",
            "--cwd",
            str(Path(__file__).resolve().parents[2] / "pulumi_project"),
        ],
    ]
    for _, _, env in calls:
        assert env is not None
        assert env["AWS_ACCESS_KEY_ID"] == "key"
        assert env["AWS_SECRET_ACCESS_KEY"] == "secret"
        assert env["AWS_REGION"] == "eu-north-1"
        assert env["AWS_DEFAULT_REGION"] == "eu-north-1"


def test_invoke_pulumi_uses_default_stack_name_from_provider_config(monkeypatch) -> None:
    calls: list[tuple[list[str], bool, dict[str, str] | None]] = []

    def fake_run(command: list[str], check: bool, env: dict[str, str] | None = None) -> SimpleNamespace:
        calls.append((command, check, env))
        return SimpleNamespace(returncode=0)

    config = SimpleNamespace(
        pulumi=SimpleNamespace(
            backend_url="file:///var/lib/server-shield/pulumi-state",
            stack_name="server-shield",
            shield_backend="AWS",
            miner_port=9001,
            aws=SimpleNamespace(
                aws_access_key_id="key",
                aws_secret_access_key="secret",
                aws_region="eu-north-1",
                hosted_zone_id="Z123",
                miner_instance_id="i-123",
            ),
        )
    )
    monkeypatch.setattr("server_shield.pulumi_runner.cli.get_config", lambda: config)
    monkeypatch.setattr("server_shield.pulumi_runner.cli.subprocess.run", fake_run)

    exit_code = _invoke_pulumi()

    assert exit_code == 0
    assert calls[1][0][3] == "server-shield"
    assert calls[2][0][4] == "server-shield"


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
