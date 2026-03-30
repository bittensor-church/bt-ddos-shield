import asyncio

import bittensor_wallet

from bt_ddos_shield_client import ShieldMetagraph

# gra = ShieldMetagraph(
#     bittensor_wallet.Wallet("validator", "default"),
#     2,
#     "ws://localhost:9945",
# )
#
# for neuron in gra.neurons:
#     print(neuron.hotkey, neuron.axon_info.ip, neuron.axon_info.port)


from bt_ddos_shield_client.shielded_turbobt import ShieldedBittensor

async def main():
    async with ShieldedBittensor(
        "ws://localhost:9945",
        wallet=bittensor_wallet.Wallet("validator", "default"),
        ddos_shield_netuid=2,
    ) as bittensor:
        sn = bittensor.subnet(2)
        for neuron in await sn.list_neurons():
            print(neuron.hotkey, neuron.axon_info.ip, neuron.axon_info.port)


asyncio.run(main())
