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

For live chain-reader verification against Finney subnet 12, add these values to `manual_tests/.env`:

- `SERVER_SHIELD_SUBTENSOR_ADDRESS=finney`
- `SERVER_SHIELD_NETUID=12`
- `SERVER_SHIELD_STATE_DIR=/tmp/server-shield-state`

Prepare the shared state directory:

```bash
mkdir -p /tmp/server-shield-state
cp ../server_shield/src/server_shield/shared/state_files/*.example.json /tmp/server-shield-state/
for file in /tmp/server-shield-state/*.example.json; do mv "$file" "${file%.example.json}.json"; done
printf '{"domain": "shield.example.com"}\n' > /tmp/server-shield-state/root_domain.json
printf '[]\n' > /tmp/server-shield-state/blacklist.json
```

Run the reader:

```bash
./run_chain_reader.sh
cat /tmp/server-shield-state/desired_domains.json
```

The resulting `desired_domains.json` should contain one entry per eligible validator with a domain shaped like `<first8hotkey>-<12 hex chars>.shield.example.com`.

Inspect the generated manifest payload:

```bash
cat /tmp/server-shield-state/manifest.json
```

It should contain `ddos_shield_manifest.encrypted_url_mapping` with one base64 ciphertext per eligible validator hotkey.

To exclude a validator manually, edit the blacklist and rerun:

```bash
printf '["<validator-hotkey>"]\n' > /tmp/server-shield-state/blacklist.json
./run_chain_reader.sh
cat /tmp/server-shield-state/desired_domains.json
```

That hotkey should be absent from `desired_domains.json` after the rerun.

After `./run_pulumi.sh`, confirm the uploaded object if you have AWS CLI access to the bucket:

```bash
aws s3 cp "s3://<bucket-name>/shield_manifest.json" -
```

The downloaded object should match `/tmp/server-shield-state/manifest.json`.

To verify the manual Pulumi helper exists in the built container, run:

```bash
docker exec <container-name> shield-pulumi stack output
```

The helper should run Pulumi from the project directory with the same backend/AWS environment as the scheduled runner. It also uses the same supervisor lock, so it will skip if the automated `pulumi-runner` loop is already active.
