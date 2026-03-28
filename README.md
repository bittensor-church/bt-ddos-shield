
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
- `chain_reader`: placeholder job that will eventually read chain state and prepare local desired-domain and manifest data
- `chain_writer`: placeholder job that will eventually publish miner connection data back to chain

These components communicate through typed JSON state files stored in the server shield state directory. On initial bootstrap the files always exist, but their values may be `null` or empty arrays so downstream components can skip work without treating missing upstream data as an error.

Current state files:

- `hosted_zone_domain.json`: `{ "domain": null }`
- `nlb_ip.json`: `{ "ip": null }`
- `desired_domains.json`: `{ "domains": [] }`
- `blacklist.json`: `{ "domains": [] }`
- `manifest.json`: `{ "manifest_url": null, "encrypted_addresses": [] }`

Behavior notes:

- If `desired_domains.json` contains no domains, the Pulumi runner still applies the base infrastructure and skips the host-based WAF allow rules.
- If `nlb_ip.json` still contains `null`, the chain writer exits cleanly and does nothing.
- All three components run in one Docker image, attempt one run every minute, never overlap with themselves, and each run is capped at 20 minutes.
- Logs from all three components stay on stdout/stderr, so they are visible through `docker logs`.
- Uncaught exceptions and non-zero exits are reported to Sentry when `SENTRY_DSN` is configured.
- Configuration is parsed from environment variables via shared Pydantic settings; the application code does not load `.env` files directly.
