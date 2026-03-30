import asyncio

import bittensor_wallet
import pathlib

import os

from bt_ddos_shield_client import ShieldMetagraph


from bittensor_wallet import bittensor_wallet
from dotenv import load_dotenv


# from bt_ddos_shield.turbobt import ShieldedBittensor
# from turbobt import Bittensor

load_dotenv(pathlib.Path(__file__).parent / '.env')

vali_wallet = bittensor_wallet.Wallet(
    os.environ['BITTENSOR_VALIDATOR_WALLET_NAME'],
    os.environ['BITTENSOR_VALIDATOR_WALLET_HOTKEY'],
)

miner_wallet = bittensor_wallet.Wallet(
    os.environ['SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME'],
    os.environ['SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY'],
)

# gra = ShieldMetagraph(
#     bittensor_wallet.Wallet(
#         os.environ['BITTENSOR_VALIDATOR_WALLET_NAME'],
#         os.environ['BITTENSOR_VALIDATOR_WALLET_HOTKEY']
#     ),
#     int(os.environ['SERVER_SHIELD_NETUID']),
#     os.environ['SERVER_SHIELD_SUBTENSOR_ADDRESS'],
# )
#
# for neuron in gra.neurons:
#     print(neuron.hotkey, neuron.axon_info.ip, neuron.axon_info.port)


from bt_ddos_shield_client.shielded_turbobt import ShieldedBittensor

async def main():
    async with ShieldedBittensor(
        os.environ['SERVER_SHIELD_SUBTENSOR_ADDRESS'],
        wallet=bittensor_wallet.Wallet(os.environ['BITTENSOR_VALIDATOR_WALLET_NAME'], os.environ['BITTENSOR_VALIDATOR_WALLET_HOTKEY']),
        ddos_shield_netuid=int(os.environ['SERVER_SHIELD_NETUID']),
    ) as bittensor:
        sn = bittensor.subnet(int(os.environ['SERVER_SHIELD_NETUID']))
        for neuron in await sn.list_neurons():
            print(neuron.hotkey, neuron.axon_info.ip, neuron.axon_info.port)


asyncio.run(main())
