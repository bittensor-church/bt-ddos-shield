from __future__ import annotations

import sys

import pytest

from bt_ddos_shield_client.certificates import EDDSACertificateManager

if sys.platform and sys.version_info >= (3, 14):
    pytest.importorskip('turbobt', reason='turbobt is not available on this Python version')

from bt_ddos_shield_client.shielded_turbobt.contacts import TurboBittensorSubtensorContact


@pytest.mark.subtensor_integration
@pytest.mark.asyncio
async def test_turbobt_contact_lists_registered_neurons(
    turbobt_bittensor,
    validator_wallet,
    miner_wallet,
    netuid,
):
    contact = TurboBittensorSubtensorContact()

    neurons = await contact.list_neurons(
        bittensor=turbobt_bittensor,
        netuid=netuid,
    )

    hotkeys = {neuron.hotkey for neuron in neurons}
    assert validator_wallet.hotkey.ss58_address in hotkeys
    assert miner_wallet.hotkey.ss58_address in hotkeys


@pytest.mark.subtensor_integration
@pytest.mark.asyncio
async def test_turbobt_contact_reads_missing_certificate_for_registered_miner(
    turbobt_bittensor,
    miner_wallet,
    netuid,
):
    contact = TurboBittensorSubtensorContact()

    public_key = await contact.get_own_public_key(
        bittensor=turbobt_bittensor,
        netuid=netuid,
        hotkey=miner_wallet.hotkey.ss58_address,
    )

    assert public_key is None


@pytest.mark.subtensor_integration
@pytest.mark.asyncio
async def test_turbobt_contact_reads_uploaded_certificate_for_registered_hotkey(
    turbobt_bittensor,
    miner_wallet,
    netuid,
):
    contact = TurboBittensorSubtensorContact()
    certificate = EDDSACertificateManager.generate_certificate()
    hotkey = miner_wallet.hotkey.ss58_address

    await contact.upload_public_key(
        certificate.public_key,
        certificate.algorithm,
        bittensor=turbobt_bittensor,
        netuid=netuid,
        wallet=miner_wallet,
    )

    after = await contact.get_own_public_key(
        bittensor=turbobt_bittensor,
        netuid=netuid,
        hotkey=hotkey,
    )

    assert after == certificate.public_key
