
# BT DDoS Shield

[![PyPI](https://img.shields.io/pypi/v/bt-ddos-shield-client)](https://pypi.org/project/bt-ddos-shield-client/)
[![License](https://img.shields.io/github/license/bactensor/bt-ddos-shield)](https://github.com/bactensor/bt-ddos-shield/blob/main/LICENSE)

BT DDoS Shield is a solution designed for **Bittensor subnet owners who want to protect miners from Distributed Denial-of-Service (DDoS)** attacks and foster honest competition.

The basic principle behind the shield is to assign multiple addresses to miners - one for each validator - **instead of exposing the miner's public IP in the metagraph**. 
These addresses are communicated to validators using Knowledge Commitments and encrypted with ECIES 
([Elliptic Curve Integrated Encryption Scheme](https://github.com/ecies/py)) keys published by the validators. 
This creates **a secure, permissionless method of distributing miner connection details**.

To use the shield in a subnet, the validator code must be modified by replacing the standard `metagraph` from the `bittensor` 
library with the drop-in replacement `bt_ddos_shield_client.ShieldMetagraph`. 
**Each miner is then responsible for running the shield server** to secure their infrastructure. 
Unshielded miners will still be reachable by their default public addresses published to the metagraph.

BT DDoS Shield offers a scalable and **cost-effective solution for subnets handling large volumes of data**.

## Product Highlights

BT DDoS Shield delivers a secure, decentralized, and scalable solution that:

- **Eliminates vulnerabilities:** Keeps sensitive IP addresses and ports off-chain, reducing the attack surface.
- **Encrypts the handshake:** Uses ECIES ([Elliptic Curve Integrated Encryption Scheme](https://github.com/ecies/py)) 
  to securely exchange connection information between miners and validators.
- **Delivers cost-effective defense:** Provides a decentralized alternative to traditional DDoS protection methods, maintaining performance while minimizing attack vectors.

## Getting Started

If you're a **subnet owner**, enable `bt-ddos-shield-client` in your validator code 
(see [Using Shield on Client (Validator) Side](#using-shield-on-client-validator-side)) so that everything runs automatically. 
**Validators** can review the detailed workings in that section.

If you're a **miner**, activate `bt-ddos-shield-server` on your end by running it as described in the [Running Shield on Server (Miner) Side](#running-shield-on-server-miner-side) section.

We welcome your contributions—see [Contribution Guidelines](#contribution-guidelines) for more information. 

For requests, feedback, or questions, **join us on the [ComputeHorde Discord channel](https://discordapp.com/channels/799672011265015819/1201941624243109888)**.

Also, be sure to check out our subnet and other products at [ComputeHorde](https://computehorde.io).


## Running Shield on server (Miner) side

### Disclaimers

* As for now BT DDoS Shield can only be used for hiding AWS EC2 server and uses AWS ELB and WAF to handle communication.
* As autohiding is not yet implemented, after starting the Shield it is required to manually block the traffic from all sources except the
Shield's load balancer (ELB created by the Shield during first run). This can be done using any firewall (like UFW) locally on
server or by configuring security groups in AWS via AWS panel (EC2 instance security groups should allow traffic only from ELB).

### Prerequisites

* AWS account with given privileges:
  * `ec2:DescribeInstances`
  * `ec2:DescribeVpcs`
  * `ec2:DescribeAvailabilityZones`
  * `ec2:CreateSubnet`
  * `ec2:DeleteSubnet`
  * `ec2:DescribeSubnets`
  * `ec2:CreateSecurityGroup`
  * `ec2:DeleteSecurityGroup`
  * `ec2:AuthorizeSecurityGroupIngress`
  * `wafv2:CreateWebACL`
  * `wafv2:DeleteWebACL`
  * `wafv2:GetWebACL`
  * `wafv2:UpdateWebACL`
  * `wafv2:AssociateWebACL`
  * `wafv2:DisassociateWebACL`
  * `elasticloadbalancing:CreateLoadBalancer`
  * `elasticloadbalancing:DeleteLoadBalancer`
  * `elasticloadbalancing:DescribeLoadBalancers`
  * `elasticloadbalancing:CreateListener`
  * `elasticloadbalancing:CreateRule`
  * `elasticloadbalancing:CreateTargetGroup`
  * `elasticloadbalancing:DeleteTargetGroup`
  * `elasticloadbalancing:RegisterTargets`
  * `elasticloadbalancing:DeregisterTargets`
  * `route53:ListHostedZones`
  * `route53:ChangeResourceRecordSets`
  * `route53:ListResourceRecordSets`
  * `route53:GetHostedZone`
  * `s3:PutObject`
* A domain, either 
  * registered via AWS; or
  * via another registrar, a Route 53 hosted zone created for it, and name servers configured to match those of the Route 53 hosted zone     
* Hosted zone id from the previous step, can be obtained from `aws route53 list-hosted-zones --query "HostedZones[].{Name:Name,Id:Id}" --output table `
* Miner's server needs to respond to ELB health checks. This can be done by configuring server to respond with 200 status
to `GET /` request on server's traffic port. Also, server security group should allow traffic from ELB.
* Miner hotkey - the shield server process will need access to it.


### Miner part internal architecture

The server shield now lives under `server_shield` as one Python project with 3 internal components:

- `pulumi_runner`: provisions and updates the AWS infrastructure
- `chain_reader`: reads the validator set and validator certs from chain, then reconciles `desired_domains.json`
- `chain_writer`: publishes the miner axon info back to chain when `axon_public_ip.json` is available

These components communicate through typed JSON state files stored in the server shield state directory. On initial bootstrap the files always exist, but their values may be `null`, empty arrays, or empty objects so downstream components can skip work without treating missing upstream data as an error.

Current state files:

- `root_domain.json`: `{ "domain": null }`
- `axon_public_ip.json`: `{ "ip": null }`
- `desired_domains.json`: `{ "domains": {} }`
- `blacklist.json`: `[]`
- `manifest.json`:

```json
{
    "ddos_shield_manifest": {
        "encrypted_url_mapping": {}
    }
}
```

Behavior notes:

- If `root_domain.json` still contains `null`, the chain reader exits cleanly and leaves `desired_domains.json` unchanged.
- The chain reader fetches validators from chain, excludes any hotkeys listed in `blacklist.json`, excludes validators with missing or invalid certs, reconciles `desired_domains.json`, and writes `manifest.json`.
- Existing validator domains stay stable across runs unless the validator cert changes or the root domain changes.
- `manifest.json` contains the final JSON that Pulumi uploads to S3 as `shield_manifest.json`.
- All state files are written with stable pretty-printed JSON so diffs and Pulumi content hashes do not churn unnecessarily.
- If `desired_domains.json` contains no domains, the Pulumi runner still applies the base infrastructure and skips the host-based WAF allow rules.
- If `axon_public_ip.json` still contains `null`, the chain writer exits cleanly and does nothing.
- All three components run in one Docker image, attempt one run every minute, never overlap with themselves, and each run is capped at 20 minutes.
- Logs from all three components stay on stdout/stderr, so they are visible through `docker logs`.
- Uncaught exceptions and non-zero exits are reported to Sentry when `SENTRY_DSN` is configured.
- Configuration is parsed from environment variables via shared Pydantic settings; the application code does not load `.env` files directly.

Build the Docker image from the repository root with:

```bash
docker build -f server_shield/Dockerfile -t server-shield:local .
```

Pulumi backend configuration is mandatory. Set `SERVER_SHIELD_PULUMI__BACKEND_URL` in your environment.

If you want `blacklist.json` and the other shared state files to persist across container restarts, set `SERVER_SHIELD_STATE_DIR` to a mounted directory. This is recommended in production. Mount the whole state directory, not just `blacklist.json`, so the operator-managed blacklist and the generated JSON state stay together.

Local file backend example:

```dotenv
SERVER_SHIELD_PULUMI__BACKEND_URL=file:///var/lib/server-shield/pulumi-state
SERVER_SHIELD_PULUMI__STACK_NAME=server-shield
SERVER_SHIELD_PULUMI__SHIELD_BACKEND=AWS
SERVER_SHIELD_MINER_PORT=9001
SERVER_SHIELD_SUBTENSOR_ADDRESS=ws://...
SERVER_SHIELD_NETUID=...
SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME=...
SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY=...
SERVER_SHIELD_STATE_DIR=/var/lib/server-shield/state
SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID=...
SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY=...
SERVER_SHIELD_PULUMI__AWS__AWS_REGION=eu-north-1
SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID=...
SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID=...
```

Run the container with a persistent Pulumi state volume:

```bash
docker run \
  --env-file .env \
  --volume server-shield-pulumi-state:/var/lib/server-shield/pulumi-state \
  --volume server-shield-state:/var/lib/server-shield/state \
  server-shield:local
```

If the automated Pulumi runner needs operator intervention, you can run manual Pulumi commands inside the container with:

```bash
docker exec <container-name> shield-pulumi refresh --clear-pending-creates
docker exec <container-name> shield-pulumi import ...
```

`shield-pulumi` runs from the Pulumi project directory with the same Pulumi backend/AWS environment as the scheduled runner and goes through the same supervisor lock. If the automated Pulumi run is active, the manual command will skip rather than overlapping it.

S3 backend example:

```dotenv
SERVER_SHIELD_PULUMI__BACKEND_URL=s3://my-pulumi-state-bucket/server-shield
SERVER_SHIELD_PULUMI__STACK_NAME=server-shield
SERVER_SHIELD_PULUMI__SHIELD_BACKEND=AWS
SERVER_SHIELD_MINER_PORT=9001
SERVER_SHIELD_SUBTENSOR_ADDRESS=ws://...
SERVER_SHIELD_NETUID=...
SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME=...
SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY=...
SERVER_SHIELD_STATE_DIR=/var/lib/server-shield/state
SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID=...
SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY=...
SERVER_SHIELD_PULUMI__AWS__AWS_REGION=eu-north-1
SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID=...
SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID=...
```

Run the container against the S3 backend:

```bash
docker run \
  --env-file .env \
  --volume server-shield-state:/var/lib/server-shield/state \
  server-shield:local
```

The build command must be run from the repository root so `COPY server_shield ...` in the Dockerfile can see the project files. For the local file backend, `/var/lib/server-shield/pulumi-state` must be persisted with a Docker volume. For the S3 backend, the bucket must already exist. In both cases, `/var/lib/server-shield/state` should be persisted if you want the shared JSON state and `blacklist.json` edits to survive restarts. `SERVER_SHIELD_PULUMI__STACK_NAME` is optional and defaults to `server-shield`. `SERVER_SHIELD_PULUMI__SHIELD_BACKEND` is currently required and must be `AWS`. `SERVER_SHIELD_SUBTENSOR_ADDRESS`, `SERVER_SHIELD_NETUID`, `SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME`, and `SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY` are also required.

Operators control validator exclusions through `blacklist.json`, which is a JSON array of validator hotkeys in the shared state directory. Add a hotkey to remove that validator from `desired_domains.json` on the next `chain_reader` run. Remove a hotkey to let the chain reader add it back if it is still a validator with a valid cert.
