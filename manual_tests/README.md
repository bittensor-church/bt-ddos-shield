here you can find manual tests that will help you run the full stack, or parts of it, locally.

if you want to run these gainst a local chain (where you have a lot fake money and can do whatever you like), follow 
these steps:

(based on https://docs.learnbittensor.org/local-build/deploy#running-a-local-subtensor-instance)

all the things below should be done once, they're not idempotent

```bash
uv run btcli wallet create --uri alice
uv run btcli wallet create --wallet.name miner --hotkey default --no-use-password
uv run btcli wallet create --wallet.name validator --hotkey default --no-use-password
./register_miner_and_vali.sh
```


## Server shield:

### pulumi:

fill in `.env` values and run. the current config also requires:

- `SERVER_SHIELD_SUBTENSOR_ADDRESS`
- `SERVER_SHIELD_NETUID`
- `SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME`
- `SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY`

```bash
./run_pulumu.sh
```

if you want to destroy the infra to save costs:

```bash
./pulumi_destroy.sh
```

### chain_reader
