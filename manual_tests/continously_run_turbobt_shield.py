import asyncio

import bittensor_wallet
import pathlib

import os

from bt_ddos_shield_client.shielded_turbobt import ShieldedNeuronMutator
from turbobt import Bittensor


from bittensor_wallet import bittensor_wallet
from dotenv import load_dotenv

import logging

logging.basicConfig(
    level=logging.DEBUG,
    force=True,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

logging.getLogger("websockets").setLevel(logging.INFO)
logging.getLogger("btdecode").setLevel(logging.INFO)

load_dotenv(pathlib.Path(__file__).parent / '.env')

vali_wallet = bittensor_wallet.Wallet(
    os.environ['BITTENSOR_VALIDATOR_WALLET_NAME'],
    os.environ['BITTENSOR_VALIDATOR_WALLET_HOTKEY'],
)

logger = logging.getLogger(__name__)
async def main():
    logger.debug("turbobt start")
    async with Bittensor(
        os.environ['SERVER_SHIELD_SUBTENSOR_ADDRESS'],
        wallet=bittensor_wallet.Wallet(os.environ['BITTENSOR_VALIDATOR_WALLET_NAME'], os.environ['BITTENSOR_VALIDATOR_WALLET_HOTKEY']),
    ) as bittensor:
        netuid = int(os.environ['SERVER_SHIELD_NETUID'])
        mutator = ShieldedNeuronMutator(wallet=bittensor.wallet, netuid=netuid)
        sn = bittensor.subnet(netuid)
        while True:
            for neuron in await mutator.mutate_neurons(bittensor, await sn.list_neurons()):
                print(neuron.hotkey, neuron.axon_info.ip, neuron.axon_info.port)
            logger.debug("done")
            await asyncio.sleep(12)


asyncio.run(main())
