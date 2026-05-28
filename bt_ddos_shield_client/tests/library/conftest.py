from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from bt_ddos_shield_client.contacts import MockBittensorSubtensorContact

if TYPE_CHECKING:
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
    if sys.platform and sys.version_info >= (3, 14):
        pytest.importorskip('turbobt', reason='turbobt is not available on this Python version')
    # Deferred so Python versions without the turbobt extra can still collect non-turbobt tests.
    from bt_ddos_shield_client.shielded_turbobt.contacts import MockTurboBittensorSubtensorContact

    contact = MockTurboBittensorSubtensorContact()
    monkeypatch.setattr(
        'bt_ddos_shield_client.shielded_turbobt.neuron_mutator.turbo_bittensor_subtensor_contact',
        lambda: contact,
    )
    return contact
