from __future__ import annotations

import pytest

from tests.contacts.local_subtensor import start_local_subtensor_env


@pytest.fixture(scope="session")
def local_subtensor_env():
    try:
        env = start_local_subtensor_env()
    except Exception as exc:  # pragma: no cover - environment gate
        pytest.skip(f"local subtensor integration environment unavailable: {exc}")
    try:
        yield env
    finally:
        env.cleanup()


@pytest.fixture(scope="session")
def subtensor(local_subtensor_env):
    return local_subtensor_env.subtensor


@pytest.fixture(scope="session")
def ws_endpoint(local_subtensor_env):
    return local_subtensor_env.ws_endpoint


@pytest.fixture(scope="session")
def validator_wallet(local_subtensor_env):
    return local_subtensor_env.validator_wallet


@pytest.fixture(scope="session")
def miner_wallet(local_subtensor_env):
    return local_subtensor_env.miner_wallet


@pytest.fixture(scope="session")
def netuid(local_subtensor_env):
    return local_subtensor_env.netuid
