# BT DDoS Shield

[![PyPI](https://img.shields.io/pypi/v/bt-ddos-shield-client)](https://pypi.org/project/bt-ddos-shield-client/)
[![License](https://img.shields.io/github/license/bactensor/bt-ddos-shield)](https://github.com/bactensor/bt-ddos-shield/blob/main/LICENSE)

BT DDoS Shield helps Bittensor subnet operators keep miner connection details off-chain. Validators use the client package as a drop-in metagraph wrapper, while miners run the server shield to publish validator-specific protected addresses.

The shield has two main parts:

- `bt_ddos_shield_client`: validator-side Python package with `ShieldMetagraph`, optional `turbobt` support, and public testing helpers.
- `server_shield`: miner-side Docker service that provisions AWS infrastructure, builds encrypted manifests for validators, and publishes the miner's shield endpoint to chain.

## How It Works

1. A validator runs the client package and publishes its shield certificate to chain.
2. A miner runs the server shield against its AWS EC2 miner instance and Route 53 hosted zone.
3. The server shield reads validator certificates from chain, creates a unique DNS name for each eligible validator, and writes `shield_manifest.json`.
4. AWS routes validator traffic through a Network Load Balancer, an internal Application Load Balancer, and WAF host allow rules.
5. The validator client fetches each miner's manifest from `http://{axon_ip}:{axon_port}/shield_manifest.json`, decrypts the entry for its own hotkey, and replaces that miner's axon endpoint when the manifest entry is valid.

Miners without a working shield manifest are treated as unshielded by validators and remain reachable through their metagraph axon addresses.

## Repository Layout

- [bt_ddos_shield_client/README.md](bt_ddos_shield_client/README.md): install, API, usage, and tests for the validator client package.
- `server_shield/`: miner-side service, Docker image, Pulumi program, and tests.
- `manual_tests/`: local scripts for manual subtensor and end-to-end checks.
- [docs/engineering-standards.md](docs/engineering-standards.md): repository engineering and testing standards.

## Validator Client

Install the validator-side package with:

```bash
pip install bt-ddos-shield-client
```

The base client supports Python 3.11 through 3.14.

Use `ShieldMetagraph` where validator code would normally use `bittensor.core.metagraph.Metagraph`:

```python
from bt_ddos_shield_client import ShieldMetagraph

metagraph = ShieldMetagraph(wallet, netuid, subtensor=subtensor)
```

Install the optional `turbobt` integration when validator code uses `turbobt` neurons:

```bash
pip install "bt-ddos-shield-client[turbobt]"
```

The optional `turbobt` extra is currently limited to Python 3.11 through 3.13 because upstream `turbobt` still depends on `eciespy`/`coincurve`.

See the [client README](bt_ddos_shield_client/README.md) for complete validator-side behavior, certificate handling, public APIs, and test helpers.

## Miner Server

The miner-side server shield is distributed as a Docker image built from `server_shield/Dockerfile`. It provisions an AWS-backed shield for a miner running on EC2, using Route 53, S3, WAF, an internal ALB, and an internet-facing NLB.

### Requirements

- AWS credentials that can manage the required EC2, ELBv2, WAFv2, Route 53, and S3 resources.
- An EC2 instance running the miner service.
- A Route 53 hosted zone for the shield domain.
- A miner hotkey registered on the target subnet.
- Miner service health checks that return HTTP 200 for `GET /` on the miner traffic port.
- Network rules that allow the shield-created load balancer security group to reach the miner port.
- A Pulumi backend URL for server shield state.

### Build

Run the Docker build from the repository root:

```bash
docker build -f server_shield/Dockerfile -t server-shield:local .
```

The image contains three supervised components:

- `server-shield-pulumi`: applies the Pulumi program and writes the root domain and NLB public IP into local state.
- `server-shield-chain-reader`: reads validator certificates from chain, reconciles desired validator domains, and writes the encrypted manifest.
- `server-shield-chain-writer`: publishes the shield NLB public IP and miner port to chain when the miner hotkey is registered.

The container runs each component once per minute. Component runs do not overlap with themselves, each run has a 20 minute timeout by default, and logs are written to stdout/stderr.

### Configuration

The service reads configuration from environment variables with the `SERVER_SHIELD_` prefix. It does not load `.env` files itself; pass environment variables through Docker, your process supervisor, or your deployment system.

Required variables:

```dotenv
SERVER_SHIELD_MINER_PORT=9001
SERVER_SHIELD_SUBTENSOR_ADDRESS=ws://...
SERVER_SHIELD_NETUID=...
SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME=...
SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY=...
SERVER_SHIELD_PULUMI__BACKEND_URL=file:///var/lib/server-shield/pulumi-state
SERVER_SHIELD_PULUMI__STACK_NAME=server-shield
SERVER_SHIELD_PULUMI__SHIELD_BACKEND=AWS
SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID=...
SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY=...
SERVER_SHIELD_PULUMI__AWS__AWS_REGION=eu-north-1
SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID=i-...
SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID=Z...
```

Optional variables:

```dotenv
SERVER_SHIELD_ENV=production
SERVER_SHIELD_LOG_LEVEL=INFO
SERVER_SHIELD_SENTRY_DSN=...
SERVER_SHIELD_STATE_DIR=/var/lib/server-shield/state
RUN_TIMEOUT=20m
LOCK_DIR=/tmp/server-shield-locks
```

`SERVER_SHIELD_PULUMI__STACK_NAME` defaults to `server-shield`. `SERVER_SHIELD_PULUMI__SHIELD_BACKEND` must be `AWS`.

### State Files

Server shield state defaults to `/var/lib/server-shield/state`. Mount this directory in production so validator domains, manifests, the discovered root domain, the discovered NLB public IP, and operator blacklist edits survive container restarts.

The state directory contains:

- `root_domain.json`: hosted zone domain discovered by the Pulumi program.
- `axon_public_ip.json`: NLB public IP discovered by the Pulumi program.
- `desired_domains.json`: validator hotkey to DNS name and certificate mapping.
- `blacklist.json`: validator hotkeys excluded by the operator.
- `manifest.json`: `shield_manifest.json` content uploaded to S3.

Missing state files are created from bundled examples. State writes are atomic and pretty-printed with stable key ordering.

### Run

With a local Pulumi backend:

```bash
docker run \
  --env-file .env \
  --volume server-shield-pulumi-state:/var/lib/server-shield/pulumi-state \
  --volume /opt/bittensor-ddos-shield/state:/var/lib/server-shield/state \
  server-shield:local
```

With an S3 Pulumi backend:

```dotenv
SERVER_SHIELD_PULUMI__BACKEND_URL=s3://my-pulumi-state-bucket/server-shield
```

```bash
docker run \
  --env-file .env \
  --volume /opt/bittensor-ddos-shield/state:/var/lib/server-shield/state \
  server-shield:local
```

For local file backends, persist `/var/lib/server-shield/pulumi-state`. For S3 backends, create the bucket ahead of container startup.

### Operations

Edit `blacklist.json` in the state directory to exclude validators. The file is a JSON array of validator hotkeys. The chain reader removes blacklisted validators from `desired_domains.json` and the manifest on its next run.

Manual Pulumi commands can be run inside the container with:

```bash
docker exec <container-name> shield-pulumi refresh --clear-pending-creates
docker exec <container-name> shield-pulumi import ...
```

`shield-pulumi` uses the same Pulumi backend, AWS environment, project directory, and supervisor lock as the scheduled Pulumi runner. If the scheduled runner is active, the manual command exits without overlapping it.

Uncaught exceptions, non-zero component exits, and timeouts are reported to Sentry when `SERVER_SHIELD_SENTRY_DSN` is set.

## Development

Run client tests from the client package:

```bash
cd bt_ddos_shield_client
uv run --group test pytest tests -v
```

Run server tests from the server package:

```bash
cd server_shield
uv run --group dev pytest tests -v
```

Both packages mark Docker-backed subtensor integration tests with `subtensor_integration`; default pytest configuration excludes that marker.

## Community

For requests, feedback, or questions, join the [ComputeHorde Discord channel](https://discordapp.com/channels/799672011265015819/1201941624243109888). You can also learn more about ComputeHorde at [computehorde.io](https://computehorde.io).
