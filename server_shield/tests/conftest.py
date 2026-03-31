from __future__ import annotations

import pytest

from server_shield.subtensor_contact import MockSubtensorContact


@pytest.fixture
def patched_subtensor_contact(monkeypatch) -> MockSubtensorContact:
    contact = MockSubtensorContact()
    monkeypatch.setattr("server_shield.chain_reader.cli.subtensor_contact", lambda subtensor_address: contact)
    monkeypatch.setattr("server_shield.chain_writer.cli.subtensor_contact", lambda subtensor_address: contact)
    return contact
