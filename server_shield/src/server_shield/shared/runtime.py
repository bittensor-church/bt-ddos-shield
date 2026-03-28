import traceback
from collections.abc import Callable

from server_shield.shared.sentry import capture_component_failure, init_sentry


def run_component(component_name: str, fn: Callable[[], int]) -> int:
    init_sentry(component_name)
    try:
        exit_code = fn()
    except Exception as exc:  # noqa: BLE001
        capture_component_failure(component_name, 1, f"uncaught exception: {exc}")
        traceback.print_exc()
        return 1

    if exit_code != 0:
        capture_component_failure(component_name, exit_code, "non-zero exit")
    return exit_code
