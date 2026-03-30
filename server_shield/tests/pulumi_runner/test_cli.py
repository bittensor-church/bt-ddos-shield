from pathlib import Path
from types import SimpleNamespace

from server_shield.pulumi_runner.cli import _build_pulumi_env, _invoke_pulumi, _project_dir, main


def _config(backend_url: str = "s3://example-state-bucket/server-shield", stack_name: str = "custom-stack") -> SimpleNamespace:
    return SimpleNamespace(
        pulumi=SimpleNamespace(
            backend_url=backend_url,
            stack_name=stack_name,
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


def test_build_pulumi_env_sets_runtime_env() -> None:
    env = _build_pulumi_env(_config())

    assert env["PULUMI_CONFIG_PASSPHRASE"] == ""
    assert env["AWS_ACCESS_KEY_ID"] == "key"
    assert env["AWS_SECRET_ACCESS_KEY"] == "secret"
    assert env["AWS_REGION"] == "eu-north-1"
    assert env["AWS_DEFAULT_REGION"] == "eu-north-1"


def test_project_dir_points_at_pulumi_project() -> None:
    assert _project_dir() == Path(__file__).resolve().parents[2] / "pulumi_project"


def test_invoke_pulumi_logs_in_selects_stack_and_runs_up_with_provider_env(monkeypatch) -> None:
    calls: list[tuple[list[str], bool, dict[str, str] | None]] = []

    def fake_run(command: list[str], check: bool, env: dict[str, str] | None = None) -> SimpleNamespace:
        calls.append((command, check, env))
        return SimpleNamespace(returncode=0)

    config = _config()
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
            str(_project_dir()),
        ],
        [
            "pulumi",
            "up",
            "--yes",
            "--stack",
            "custom-stack",
            "--cwd",
            str(_project_dir()),
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

    config = _config(
        backend_url="file:///var/lib/server-shield/pulumi-state",
        stack_name="server-shield",
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
