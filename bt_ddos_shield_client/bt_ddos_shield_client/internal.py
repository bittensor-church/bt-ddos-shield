from __future__ import annotations

import asyncio
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

    return SubtensorCertificate(algorithm, bytes(data).hex())


def run_async_in_thread(async_fn) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_fn)

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
