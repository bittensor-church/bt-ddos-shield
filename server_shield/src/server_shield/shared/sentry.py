import logging
import os

import sentry_sdk

from server_shield.shared.config import get_config


def init_sentry(component_name: str) -> None:
    sentry_dsn, environment = _load_sentry_settings()
    if not sentry_dsn:
        return

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=environment,
        release="server-shield@0.1.0",
    )
    sentry_sdk.set_tag("component", component_name)
    sentry_sdk.set_tag("environment", environment)


def capture_component_failure(component_name: str, exit_code: int, detail: str) -> None:
    sentry_dsn, _environment = _load_sentry_settings()
    logging.error("%s exited with code %s: %s", component_name, exit_code, detail)
    if not sentry_dsn:
        return

    with sentry_sdk.push_scope() as scope:
        scope.set_tag("component", component_name)
        scope.set_extra("exit_code", exit_code)
        scope.set_extra("detail", detail)
        sentry_sdk.capture_message(f"{component_name} failure", level="error")


def _load_sentry_settings() -> tuple[str | None, str]:
    try:
        config = get_config()
        return config.sentry_dsn, config.env
    except Exception:  # noqa: BLE001
        return os.environ.get("SERVER_SHIELD_SENTRY_DSN"), os.environ.get("SERVER_SHIELD_ENV", "dev")
