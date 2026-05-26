from __future__ import annotations

import pytest


@pytest.mark.subtensor_integration
def test_local_subtensor_bootstrap_exposes_registered_test_state(
    subtensor,
    validator_wallet,
    miner_wallet,
    netuid,
):
    validator_hotkey = validator_wallet.hotkey.ss58_address
    miner_hotkey = miner_wallet.hotkey.ss58_address

    assert subtensor.subnet_exists(netuid)
    assert subtensor.is_hotkey_registered_on_subnet(validator_hotkey, netuid=netuid)
    assert subtensor.is_hotkey_registered_on_subnet(miner_hotkey, netuid=netuid)
