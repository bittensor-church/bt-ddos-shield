import os
import subprocess
from pathlib import Path

from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component


def _build_pulumi_env(config: object) -> dict[str, str]:
    env = dict(os.environ)
    env["PULUMI_CONFIG_PASSPHRASE"] = ""
    if config.pulumi.shield_backend == "AWS":
        env["AWS_ACCESS_KEY_ID"] = config.pulumi.aws.aws_access_key_id
        env["AWS_SECRET_ACCESS_KEY"] = config.pulumi.aws.aws_secret_access_key
        env["AWS_REGION"] = config.pulumi.aws.aws_region
        env["AWS_DEFAULT_REGION"] = config.pulumi.aws.aws_region
    return env


def _project_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "pulumi_project"


def invoke_pulumi_cli(args: list[str]) -> int:
    config = get_config()
    pulumi_env = _build_pulumi_env(config)
    project_dir = _project_dir()
    login_command = [
        "pulumi",
        "login",
        config.pulumi.backend_url,
    ]
    login_result = subprocess.run(login_command, check=False, env=pulumi_env)
    if login_result.returncode != 0:
        return login_result.returncode

    select_command = [
        "pulumi",
        "stack",
        "select",
        config.pulumi.stack_name,
        "--create",
        "--cwd",
        str(project_dir),
    ]
    select_result = subprocess.run(select_command, check=False, env=pulumi_env)
    if select_result.returncode != 0:
        return select_result.returncode

    command = ["pulumi", *args, "--cwd", str(project_dir)]
    return subprocess.run(command, check=False, env=pulumi_env).returncode


def _invoke_pulumi() -> int:
    config = get_config()
    return invoke_pulumi_cli(["up", "--yes", "--stack", config.pulumi.stack_name])


def main() -> int:
    get_config()
    return run_component("pulumi-runner", _invoke_pulumi)


if __name__ == "__main__":
    raise SystemExit(main())
