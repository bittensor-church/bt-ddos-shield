import asyncio

import bittensor_wallet
import pathlib

import os

from bt_ddos_shield_client import ShieldMetagraph
# from bt_ddos_shield_client.shielded_turbobt import ShieldedNeuronMutator
# from turbobt import Bittensor


from bittensor_wallet import bittensor_wallet
from dotenv import load_dotenv

import logging

logging.basicConfig(
    level=logging.DEBUG,
    force=True,
)

logging.getLogger("websockets").setLevel(logging.INFO)
logging.getLogger("btdecode").setLevel(logging.INFO)

load_dotenv(pathlib.Path(__file__).parent / '.env')

vali_wallet = bittensor_wallet.Wallet(
    os.environ['BITTENSOR_VALIDATOR_WALLET_NAME'],
    os.environ['BITTENSOR_VALIDATOR_WALLET_HOTKEY'],
)

miner_wallet = bittensor_wallet.Wallet(
    os.environ['SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME'],
    os.environ['SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY'],
)

gra = ShieldMetagraph(
    bittensor_wallet.Wallet(
        os.environ['BITTENSOR_VALIDATOR_WALLET_NAME'],
        os.environ['BITTENSOR_VALIDATOR_WALLET_HOTKEY']
    ),
    int(os.environ['SERVER_SHIELD_NETUID']),
    os.environ['SERVER_SHIELD_SUBTENSOR_ADDRESS'],
)

for neuron in gra.neurons:
    print(neuron.hotkey, neuron.axon_info.ip, neuron.axon_info.port)


async def main():
    async with Bittensor(
        os.environ['SERVER_SHIELD_SUBTENSOR_ADDRESS'],
        wallet=bittensor_wallet.Wallet(os.environ['BITTENSOR_VALIDATOR_WALLET_NAME'], os.environ['BITTENSOR_VALIDATOR_WALLET_HOTKEY']),
    ) as bittensor:
        netuid = int(os.environ['SERVER_SHIELD_NETUID'])
        mutator = ShieldedNeuronMutator(wallet=bittensor.wallet, netuid=netuid)
        sn = bittensor.subnet(netuid)
        for neuron in await mutator.mutate_neurons(bittensor, await sn.list_neurons()):
            print(neuron.hotkey, neuron.axon_info.ip, neuron.axon_info.port)


asyncio.run(main())
