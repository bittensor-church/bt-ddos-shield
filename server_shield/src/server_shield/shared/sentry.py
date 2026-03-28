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
    sentry_sdk.set_tag("environment", config.env)


def capture_component_failure(component_name: str, exit_code: int, detail: str) -> None:
    config = get_config()
    logging.error("%s exited with code %s: %s", component_name, exit_code, detail)
    if not config.sentry_dsn:
        return

    with sentry_sdk.push_scope() as scope:
        scope.set_tag("component", component_name)
        scope.set_extra("exit_code", exit_code)
        scope.set_extra("detail", detail)
        sentry_sdk.capture_message(f"{component_name} failure", level="error")
