from __future__ import annotations

import asyncio
from concurrent.futures import Executor
import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class SubtensorCertificate:
    algorithm: int
    hex_data: str


def decode_subtensor_certificate_info(subtensor_certificate_info: dict[str, Any]) -> SubtensorCertificate | None:
    try:
        algorithm = subtensor_certificate_info['algorithm']
        data = subtensor_certificate_info['public_key']
    except (KeyError, TypeError, IndexError):
        return None

    if isinstance(data, str):
        return SubtensorCertificate(algorithm, data)

    if (
        isinstance(data, (list, tuple))
        and len(data) == 1
        and isinstance(data[0], (bytes, bytearray, list, tuple))
    ):
        data = data[0]

    return SubtensorCertificate(algorithm, bytes(data).hex())


def parse_shield_address(shield_address: str) -> tuple[str, int] | None:
    host, separator, port_text = shield_address.rpartition(':')
    if not host or not separator or not port_text:
        return None

    try:
        return host, int(port_text)
    except ValueError:
        return None


def _run_coroutine(async_fn) -> Any:
    return asyncio.run(async_fn)


def run_async_in_thread(async_fn, *, executor: Executor | None = None) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_fn)

    if executor is not None:
        future = executor.submit(_run_coroutine, async_fn)
        return future.result()

    result = None
    exception = None

    def thread_runner():
        nonlocal result, exception
        try:
            result = asyncio.run(async_fn)
        except Exception as exc:  # pragma: no cover - passthrough
            exception = exc

    thread = threading.Thread(target=thread_runner)
    thread.start()
    thread.join()

    if exception is not None:
        raise exception
    return result
