from __future__ import annotations

import pathlib

import pytest
import bittensor

from bt_ddos_shield_client.contacts import MockBittensorSubtensorContact
from bt_ddos_shield_client.shielded_turbobt.contacts import MockTurboBittensorSubtensorContact


def _make_real_validator_wallet(tmp_path):
    wallet = bittensor.wallet(name='validator', hotkey='default', path=str(tmp_path / 'wallets'))
    wallet.create_hotkey_from_uri('//Alice', use_password=False, overwrite=True, suppress=True)
    pathlib.Path(wallet.hotkey_file.path).parent.mkdir(parents=True, exist_ok=True)
    return wallet


@pytest.fixture(autouse=True, scope="function")
def validator_wallet(monkeypatch, tmp_path):
    wallet = _make_real_validator_wallet(tmp_path)
    monkeypatch.setenv(
        'VALIDATOR_WALLET_PATH',
        str(tmp_path / 'wallets' / 'validator'),
    )
    return wallet

