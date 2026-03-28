import subprocess
from pathlib import Path

from server_shield.shared.config import get_config
from server_shield.shared.runtime import run_component


def _invoke_pulumi() -> int:
    project_dir = Path(__file__).resolve().parents[3] / "pulumi_project"
    command = ["pulumi", "up", "--yes", "--cwd", str(project_dir)]
    return subprocess.run(command, check=False).returncode


def main() -> int:
    get_config()
    return run_component("pulumi-runner", _invoke_pulumi)
