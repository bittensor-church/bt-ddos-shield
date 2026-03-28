import os
import subprocess
from pathlib import Path


def test_run_component_prefixes_logs_and_returns_zero(tmp_path: Path) -> None:
    script = Path("docker/run_component.sh")
    component = "chain-reader"
    command = ["bash", str(script), component, "python", "-c", "print('hello')"]

    completed = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "LOCK_DIR": str(tmp_path), "RUN_TIMEOUT": "20m"},
    )

    assert completed.returncode == 0
    assert "[chain-reader] hello" in completed.stdout


def test_run_component_skips_when_lock_exists(tmp_path: Path) -> None:
    script = Path("docker/run_component.sh")
    lock_path = tmp_path / "chain-writer.lock"
    holder = subprocess.Popen(
        [
            "python",
            "-c",
            (
                "import fcntl, pathlib, time; "
                f"path = pathlib.Path(r'{lock_path}'); "
                "path.parent.mkdir(parents=True, exist_ok=True); "
                "handle = path.open('w'); "
                "fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB); "
                "time.sleep(2)"
            ),
        ],
        cwd=Path(__file__).resolve().parents[2],
    )
    command = ["bash", str(script), "chain-writer", "python", "-c", "print('ignored')"]

    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "LOCK_DIR": str(tmp_path), "RUN_TIMEOUT": "20m"},
        )
    finally:
        holder.terminate()
        holder.wait(timeout=5)

    assert completed.returncode == 0
    assert "[chain-writer] skipped because previous run is still active" in completed.stdout


def test_run_component_times_out(tmp_path: Path) -> None:
    script = Path("docker/run_component.sh")
    command = [
        "bash",
        str(script),
        "pulumi-runner",
        "python",
        "-c",
        "import time; time.sleep(2)",
    ]

    completed = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "LOCK_DIR": str(tmp_path), "RUN_TIMEOUT": "1s"},
    )

    assert completed.returncode != 0
    assert "timed out after 1s" in (completed.stdout + completed.stderr)
