import logging

import sentry_sdk

from server_shield.shared.config import get_config


def init_sentry(component_name: str) -> None:
    config = get_config()
    if not config.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=config.sentry_dsn,
        environment=config.env,
        release="server-shield@0.1.0",
    )
    sentry_sdk.set_tag("component", component_name)


def capture_component_failure(component_name: str, exit_code: int, detail: str) -> None:
    config = get_config()
    logging.error("%s exited with code %s: %s", component_name, exit_code, detail)
    if not config.sentry_dsn:
        return

    sentry_sdk.capture_message(
        f"{component_name} exited with code {exit_code}: {detail}",
        level="error",
    )
