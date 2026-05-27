#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
env_file="${script_dir}/.env"

set -a
source "${env_file}"
set +a

uv run btcli wallet transfer --wallet.name alice --destination $(cat ~/.bittensor/wallets/validator/coldkeypub.txt | jq '.ss58Address' -r) --amount 50000 --network $SERVER_SHIELD_SUBTENSOR_ADDRESS -y
uv run btcli wallet transfer --wallet.name alice --destination $(cat ~/.bittensor/wallets/miner/coldkeypub.txt | jq '.ss58Address' -r) --amount 50000 --network $SERVER_SHIELD_SUBTENSOR_ADDRESS -y
uv run btcli subnet create --wallet.name alice --hotkey default --network $SERVER_SHIELD_SUBTENSOR_ADDRESS -y
uv run btcli subnet register --netuid 2 --wallet-name validator --hotkey default --network $SERVER_SHIELD_SUBTENSOR_ADDRESS -y
uv run btcli subnet register --netuid 2 --wallet-name miner --hotkey default --network $SERVER_SHIELD_SUBTENSOR_ADDRESS -y
uv run btcli subnet start --netuid 2 --wallet-name alice --hotkey default --network $SERVER_SHIELD_SUBTENSOR_ADDRESS -y

for i in {1..11}; do
  uv run btcli stake add --netuid 2 --wallet-name validator --hotkey default --network $SERVER_SHIELD_SUBTENSOR_ADDRESS --amount 5000 --tolerance 1 --partial -y
done
uv run btcli subnet show --netuid 2 --network $SERVER_SHIELD_SUBTENSOR_ADDRESS