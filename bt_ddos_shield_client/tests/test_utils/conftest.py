from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
import bittensor


TEST_WALLET_ROOT = Path(tempfile.gettempdir()) / 'bt-ddos-shield-client-test-wallets'
TEST_WALLET_NAME = 'validator'
TEST_WALLET_HOTKEY = 'default'


def _make_real_validator_wallet() -> bittensor.wallet:
    wallet = bittensor.wallet(
        name=TEST_WALLET_NAME,
        hotkey=TEST_WALLET_HOTKEY,
        path=str(TEST_WALLET_ROOT),
    )
    Path(wallet.hotkey_file.path).parent.mkdir(parents=True, exist_ok=True)
    if not Path(wallet.hotkey_file.path).exists():
        wallet.create_hotkey_from_uri('//Alice', use_password=False, overwrite=True, suppress=True)
    return wallet


def pytest_configure(config):
    shutil.rmtree(TEST_WALLET_ROOT, ignore_errors=True)
    os.environ['VALIDATOR_WALLET_NAME'] = TEST_WALLET_NAME
    os.environ['VALIDATOR_WALLET_HOTKEY'] = TEST_WALLET_HOTKEY
    os.environ['VALIDATOR_WALLET_PATH'] = str(TEST_WALLET_ROOT)
    _make_real_validator_wallet()


@pytest.fixture(scope='session')
def validator_wallet() -> bittensor.wallet:
    return _make_real_validator_wallet()
