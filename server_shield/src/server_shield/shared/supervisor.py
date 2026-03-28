import contextlib
import fcntl
import os
import subprocess
import sys
import threading
from pathlib import Path

from server_shield.shared.sentry import capture_component_failure, init_sentry


def run_supervised(component_name: str, command: list[str], lock_dir: Path, timeout_spec: str) -> int:
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{component_name}.lock"

    with lock_path.open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"[{component_name}] skipped because previous run is still active", flush=True)
            return 0

        init_sentry(component_name)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stdout_thread = threading.Thread(
            target=_forward_stream,
            args=(process.stdout, sys.stdout, component_name),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_forward_stream,
            args=(process.stderr, sys.stderr, component_name),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        try:
            return_code = process.wait(timeout=_parse_duration(timeout_spec))
        except subprocess.TimeoutExpired:
            process.kill()
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
            detail = f"timed out after {timeout_spec}"
            print(f"[{component_name}] {detail}", file=sys.stderr, flush=True)
            capture_component_failure(component_name, 124, detail)
            return 124

        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        if return_code != 0:
            capture_component_failure(component_name, return_code, "non-zero exit")
        return return_code


def _forward_stream(stream: object, sink: object, component_name: str) -> None:
    if stream is None:
        return
    with contextlib.closing(stream):
        for line in stream:
            sink.write(f"[{component_name}] {line}")
            sink.flush()


def _parse_duration(raw: str) -> float:
    if raw.endswith("s"):
        return float(raw[:-1])
    if raw.endswith("m"):
        return float(raw[:-1]) * 60
    return float(raw)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        raise SystemExit("usage: supervisor.py <component> <command> [args...]")

    component_name = args[0]
    command = args[1:]
    lock_dir = Path(os.environ.get("LOCK_DIR", "/tmp/server-shield-locks"))
    timeout_spec = os.environ.get("RUN_TIMEOUT", "20m")
    return run_supervised(component_name, command, lock_dir, timeout_spec)


if __name__ == "__main__":
    raise SystemExit(main())
