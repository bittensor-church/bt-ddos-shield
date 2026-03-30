import asyncio
import os
import pathlib

import bittensor
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


async def main():
    for neuron in bittensor.Subtensor(os.environ['SERVER_SHIELD_SUBTENSOR_ADDRESS']).metagraph(int(os.environ['SERVER_SHIELD_NETUID'])).neurons:
        print(
                    neuron.hotkey,
                    neuron.axon_info.ip,
                    # unshielded_addres_dict[neuron.hotkey],
                    neuron.axon_info.port,
                    {
                        vali_wallet.hotkey.ss58_address: "validator",
                        miner_wallet.hotkey.ss58_address: "miner"
                    }.get(neuron.hotkey, ''),
                )
    # async with Bittensor(os.environ['BITTENSOR_NETWORK']) as plain_bittensor:
    #     sn = plain_bittensor.subnet(os.environ['BITTENSOR_NETUID'])
    #     unshielded_addres_dict = {n.hotkey: n.axon_info.ip for n in await sn.list_neurons()}
    #     print(unshielded_addres_dict)
    # async with ShieldedBittensor(
    #         os.environ['BITTENSOR_NETWORK'],
    #         ddos_shield_netuid=2,
    #         wallet=vali_wallet,
    # ) as bittensor:
    #     sn = bittensor.subnet(2)
    #     for neuron in await sn.list_neurons():
    #         print(
    #             neuron.hotkey,
    #             neuron.axon_info.ip,
    #             unshielded_addres_dict[neuron.hotkey],
    #             neuron.axon_info.port,
    #             {
    #                 vali_wallet.hotkey.ss58_address: "validator",
    #                 miner_wallet.hotkey.ss58_address: "miner"
    #             }.get(neuron.hotkey, ''),
    #         )

asyncio.run(main())
