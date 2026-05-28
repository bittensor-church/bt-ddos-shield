from __future__ import annotations

import sys

import pytest

from tests.library.contacts.local_subtensor import start_local_subtensor_env


@pytest.fixture(scope='session')
def local_subtensor_env():
    try:
        env = start_local_subtensor_env()
    except Exception as exc:  # pragma: no cover - environment gate
        pytest.skip(f'local subtensor integration environment unavailable: {exc}')
    try:
        yield env
    finally:
        env.cleanup()


@pytest.fixture(scope='session')
def subtensor(local_subtensor_env):
    return local_subtensor_env.subtensor


@pytest.fixture(scope='session')
def validator_wallet(local_subtensor_env):
    return local_subtensor_env.validator_wallet


@pytest.fixture(scope='session')
def miner_wallet(local_subtensor_env):
    return local_subtensor_env.miner_wallet


@pytest.fixture(scope='session')
def netuid(local_subtensor_env):
    return local_subtensor_env.netuid


@pytest.fixture
def turbobt_bittensor(local_subtensor_env, validator_wallet):
    if sys.platform and sys.version_info >= (3, 14):
        turbobt = pytest.importorskip('turbobt', reason='turbobt is not available on this Python version')
    else:
        # Deferred so collecting integration fixtures does not require turbobt on unsupported Python.
        import turbobt
    return turbobt.Bittensor(local_subtensor_env.ws_endpoint, wallet=validator_wallet)
