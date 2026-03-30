set -ex

uv run btcli wallet transfer --wallet.name alice --destination $(cat ~/.bittensor/wallets/validator/coldkeypub.txt | jq '.ss58Address' -r) --amount 50000 --network ws://127.0.0.1:9945 -y
uv run btcli wallet transfer --wallet.name alice --destination $(cat ~/.bittensor/wallets/miner/coldkeypub.txt | jq '.ss58Address' -r) --amount 50000 --network ws://127.0.0.1:9945 -y
uv run btcli subnet create --wallet.name alice --hotkey default --network ws://127.0.0.1:9945 -y
uv run btcli subnet register --netuid 2 --wallet-name validator --hotkey default --network ws://127.0.0.1:9945 -y
uv run btcli subnet register --netuid 2 --wallet-name miner --hotkey default --network ws://127.0.0.1:9945 -y
uv run btcli subnet start --netuid 2 --wallet-name alice --hotkey default --network ws://127.0.0.1:9945 -y

for i in {1..11}; do
  uv run btcli stake add --netuid 2 --wallet-name validator --hotkey default --network ws://127.0.0.1:9945 --amount 5000 --tolerance 1 --partial -y
done
uv run btcli subnet show --netuid 2 --network ws://127.0.0.1:9945