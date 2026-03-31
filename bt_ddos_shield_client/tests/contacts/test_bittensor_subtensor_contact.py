from __future__ import annotations

import pytest
from bittensor.core.metagraph import Metagraph

from bt_ddos_shield_client.certificates import EDDSACertificateManager
from bt_ddos_shield_client.contacts import BittensorSubtensorContact


@pytest.mark.subtensor_integration
def test_bittensor_contact_sync_metagraph_populates_registered_neurons(
    subtensor,
    validator_wallet,
    miner_wallet,
    netuid,
):
    contact = BittensorSubtensorContact()
    metagraph = Metagraph(netuid=netuid, network='local', lite=True, sync=False, subtensor=subtensor)

    contact.sync_metagraph(metagraph, subtensor=subtensor)

    hotkeys = {neuron.hotkey for neuron in metagraph.neurons}
    assert validator_wallet.hotkey.ss58_address in hotkeys
    assert miner_wallet.hotkey.ss58_address in hotkeys
    assert len(metagraph.axons) >= 2


@pytest.mark.subtensor_integration
@pytest.mark.asyncio
async def test_bittensor_contact_reads_missing_certificate_for_registered_miner(
    subtensor,
    miner_wallet,
    netuid,
):
    contact = BittensorSubtensorContact()

    public_key = await contact.get_own_public_key(
        subtensor=subtensor,
        netuid=netuid,
        hotkey=miner_wallet.hotkey.ss58_address,
    )

    assert public_key is None


@pytest.mark.subtensor_integration
@pytest.mark.asyncio
async def test_bittensor_contact_reads_uploaded_certificate_for_validator(
    subtensor,
    validator_wallet,
    netuid,
):
    contact = BittensorSubtensorContact()
    certificate = EDDSACertificateManager.generate_certificate()
    hotkey = validator_wallet.hotkey.ss58_address

    await contact.upload_public_key(
        certificate.public_key,
        certificate.algorithm,
        subtensor=subtensor,
        wallet=validator_wallet,
        netuid=netuid,
    )

    after = await contact.get_own_public_key(
        subtensor=subtensor,
        netuid=netuid,
        hotkey=hotkey,
    )

    assert after == certificate.public_key
