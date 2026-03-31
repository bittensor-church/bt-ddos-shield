from __future__ import annotations

import pytest

from server_shield.subtensor_contact import BittensorSubtensorContact


@pytest.mark.subtensor_integration
def test_subtensor_contact_lists_registered_validator_certificates(
    ws_endpoint,
    validator_wallet,
    miner_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    records = contact.list_validator_certificates(netuid=netuid)

    hotkeys = {record.hotkey for record in records}
    assert validator_wallet.hotkey.ss58_address in hotkeys
    assert miner_wallet.hotkey.ss58_address not in hotkeys


@pytest.mark.subtensor_integration
def test_subtensor_contact_reports_registration_for_registered_hotkey(
    ws_endpoint,
    validator_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    registered = contact.is_hotkey_registered(
        hotkey_ss58=validator_wallet.hotkey.ss58_address,
        netuid=netuid,
    )

    assert registered is True


@pytest.mark.subtensor_integration
def test_subtensor_contact_reads_registered_neuron_axon(
    ws_endpoint,
    validator_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    neuron = contact.get_neuron_axon(
        hotkey_ss58=validator_wallet.hotkey.ss58_address,
        netuid=netuid,
    )

    assert neuron.is_null is False


@pytest.mark.subtensor_integration
def test_subtensor_contact_publishes_and_reads_back_axon_info(
    ws_endpoint,
    validator_wallet,
    netuid,
):
    contact = BittensorSubtensorContact(ws_endpoint)

    published = contact.publish_axon(
        wallet=validator_wallet,
        netuid=netuid,
        ip="203.0.113.77",
        port=19001,
    )
    after = contact.get_neuron_axon(
        hotkey_ss58=validator_wallet.hotkey.ss58_address,
        netuid=netuid,
    )

    assert published is True
    assert after.is_null is False
    assert after.port == 19001
