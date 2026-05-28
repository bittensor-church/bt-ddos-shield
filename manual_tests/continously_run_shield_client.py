import time

import pathlib

import os

from bt_ddos_shield_client import ShieldMetagraph


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

while True:
    gra.sync()
    for neuron in gra.neurons:
        print(neuron.hotkey, neuron.axon_info.ip, neuron.axon_info.port)
    print(gra.block)
    time.sleep(12)
