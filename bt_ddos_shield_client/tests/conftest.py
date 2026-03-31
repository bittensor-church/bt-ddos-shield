from __future__ import annotations

import pytest

from bt_ddos_shield_client.contacts import MockBittensorSubtensorContact
from bt_ddos_shield_client.shielded_turbobt.contacts import MockTurboBittensorSubtensorContact


@pytest.fixture
def patched_bittensor_contact(monkeypatch) -> MockBittensorSubtensorContact:
    contact = MockBittensorSubtensorContact()
    monkeypatch.setattr(
        'bt_ddos_shield_client.shield_metagraph.bittensor_subtensor_contact',
        lambda: contact,
    )
    return contact


@pytest.fixture
def patched_turbo_bittensor_contact(monkeypatch) -> MockTurboBittensorSubtensorContact:
    contact = MockTurboBittensorSubtensorContact()
    monkeypatch.setattr(
        'bt_ddos_shield_client.shielded_turbobt.shielded_bittensor.turbo_bittensor_subtensor_contact',
        lambda: contact,
    )
    return contact
