"""Pulumi program for Server Shield infrastructure."""

import json
import os
import pathlib

import pulumi
import pulumi_aws as aws
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration from environment variables
# ---------------------------------------------------------------------------
AWS_REGION = os.environ["AWS_REGION_NAME"]
MINER_INSTANCE_ID = os.environ["AWS_MINER_INSTANCE_ID"]
MINER_INSTANCE_PORT = int(os.environ["MINER_INSTANCE_PORT"])
HOSTED_ZONE_ID = os.environ["AWS_ROUTE53_HOSTED_ZONE_ID"]

DOMAINS_FILE = os.environ.get("DOMAINS_FILE", "domains.txt")
NLB_IP_FILE = os.environ.get("NLB_IP_FILE", "nlb_ip.txt")
DOMAIN_OUTPUT_FILE = os.environ.get("DOMAIN_OUTPUT_FILE", "hosted_zone_domain.txt")

# ---------------------------------------------------------------------------
# 1. Read domains file (may be missing or empty)
# ---------------------------------------------------------------------------
domains: list[str] = []
domains_path = pathlib.Path(DOMAINS_FILE)
if domains_path.exists():
    domains = [
        line.strip()
        for line in domains_path.read_text().splitlines()
        if line.strip()
    ]
pulumi.log.info(f"Loaded {len(domains)} domain(s) from {DOMAINS_FILE}")

# ---------------------------------------------------------------------------
# 2. Dump the hosted zone domain
# ---------------------------------------------------------------------------
hosted_zone = aws.route53.get_zone(zone_id=HOSTED_ZONE_ID)
zone_domain = hosted_zone.name.rstrip(".")
pulumi.log.info(f"Hosted zone domain: {zone_domain}")
pathlib.Path(DOMAIN_OUTPUT_FILE).write_text(zone_domain + "\n")

# ---------------------------------------------------------------------------
# Look up the miner EC2 instance to get its VPC / subnet info
# ---------------------------------------------------------------------------
miner_instance = aws.ec2.get_instance(instance_id=MINER_INSTANCE_ID)
miner_subnet_id = miner_instance.subnet_id

# Get VPC ID from the subnet
miner_subnet = aws.ec2.get_subnet(id=miner_subnet_id)
vpc_id = miner_subnet.vpc_id

# We need all subnets in the VPC for the load balancers (need ≥2 AZs)
# But only one subnet per AZ is allowed
vpc_subnets = aws.ec2.get_subnets(
    filters=[aws.ec2.GetSubnetsFilterArgs(name="vpc-id", values=[vpc_id])]
)
_seen_azs: dict[str, str] = {}
for sid in vpc_subnets.ids:
    s = aws.ec2.get_subnet(id=sid)
    if s.availability_zone not in _seen_azs:
        _seen_azs[s.availability_zone] = sid
subnet_ids = list(_seen_azs.values())

# ---------------------------------------------------------------------------
# 3. Create an S3 bucket for public files
# ---------------------------------------------------------------------------
bucket = aws.s3.Bucket(
    "shield-public-files",
    force_destroy=True,
)

bucket_ownership = aws.s3.BucketOwnershipControls(
    "shield-public-files-ownership",
    bucket=bucket.id,
    rule=aws.s3.BucketOwnershipControlsRuleArgs(
        object_ownership="ObjectWriter",
    ),
)

bucket_public_access = aws.s3.BucketPublicAccessBlock(
    "shield-public-files-public-access",
    bucket=bucket.id,
    block_public_acls=False,
    block_public_policy=False,
    ignore_public_acls=False,
    restrict_public_buckets=False,
)

bucket_policy = aws.s3.BucketPolicy(
    "shield-public-files-policy",
    bucket=bucket.id,
    policy=bucket.arn.apply(
        lambda arn: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "PublicReadGetObject",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "s3:GetObject",
                        "Resource": f"{arn}/*",
                    }
                ],
            }
        )
    ),
    opts=pulumi.ResourceOptions(depends_on=[bucket_public_access, bucket_ownership]),
)

# ---------------------------------------------------------------------------
# 8. Security group: allow ELB to reach the EC2 miner instance
# ---------------------------------------------------------------------------
elb_sg = aws.ec2.SecurityGroup(
    "shield-elb-sg",
    description="Allow ELB to reach miner EC2 instance",
    vpc_id=vpc_id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=MINER_INSTANCE_PORT,
            to_port=MINER_INSTANCE_PORT,
            cidr_blocks=["0.0.0.0/0"],
            description="Allow inbound on miner port",
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"],
            description="Allow all outbound",
        ),
    ],
)

# New security group on the EC2 instance: allow inbound from the ELB SG
ec2_from_elb_sg = aws.ec2.SecurityGroup(
    "shield-ec2-from-elb-sg",
    description="Allow inbound from ELB to miner EC2 on miner port",
    vpc_id=vpc_id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=MINER_INSTANCE_PORT,
            to_port=MINER_INSTANCE_PORT,
            security_groups=[elb_sg.id],
            description="Allow inbound from ELB SG on miner port",
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"],
            description="Allow all outbound",
        ),
    ],
)

# Attach the new SG to the miner instance's primary ENI so ELB can reach it
miner_eni = aws.ec2.get_network_interfaces(
    filters=[
        aws.ec2.GetNetworkInterfacesFilterArgs(
            name="attachment.instance-id", values=[MINER_INSTANCE_ID]
        )
    ]
)

# Get existing SGs on the ENI and append the new one
primary_eni_id = miner_eni.ids[0]
primary_eni = aws.ec2.get_network_interface(id=primary_eni_id)
existing_sg_ids = list(primary_eni.security_groups)

network_interface_sg_attachment = aws.ec2.NetworkInterfaceSecurityGroupAttachment(
    "shield-ec2-sg-attachment",
    network_interface_id=primary_eni_id,
    security_group_id=ec2_from_elb_sg.id,
)

# ---------------------------------------------------------------------------
# 4. Create an ALB (Application Load Balancer, i.e. ELB v2)
# ---------------------------------------------------------------------------
alb = aws.lb.LoadBalancer(
    "shield-alb",
    internal=True,
    load_balancer_type="application",
    security_groups=[elb_sg.id],
    subnets=subnet_ids,
)

# Target group pointing at the miner EC2 instance
miner_tg = aws.lb.TargetGroup(
    "shield-miner-tg",
    port=MINER_INSTANCE_PORT,
    protocol="HTTP",
    vpc_id=vpc_id,
    target_type="instance",
    health_check=aws.lb.TargetGroupHealthCheckArgs(
        path="/",
        protocol="HTTP",
        port=str(MINER_INSTANCE_PORT),
        healthy_threshold=2,
        unhealthy_threshold=5,
        timeout=5,
        interval=30,
    ),
)

miner_tg_attachment = aws.lb.TargetGroupAttachment(
    "shield-miner-tg-attachment",
    target_group_arn=miner_tg.arn,
    target_id=MINER_INSTANCE_ID,
    port=MINER_INSTANCE_PORT,
)

# --- ALB Listener -----------------------------------------------------------
# Default action: forward everything to miner (WAF handles domain filtering)
alb_listener = aws.lb.Listener(
    "shield-alb-listener",
    load_balancer_arn=alb.arn,
    port=MINER_INSTANCE_PORT,
    protocol="HTTP",
    default_actions=[aws.lb.ListenerDefaultActionArgs(
        type="forward",
        target_group_arn=miner_tg.arn,
    )],
)

# Rule: /shield_manifest.json → redirect to S3 bucket
manifest_redirect_rule = aws.lb.ListenerRule(
    "shield-manifest-redirect",
    listener_arn=alb_listener.arn,
    priority=1,
    actions=[
        aws.lb.ListenerRuleActionArgs(
            type="redirect",
            redirect=aws.lb.ListenerRuleActionRedirectArgs(
                host=bucket.bucket_regional_domain_name,
                path="/shield_manifest.json",
                protocol="HTTPS",
                port="443",
                status_code="HTTP_303",
            ),
        )
    ],
    conditions=[
        aws.lb.ListenerRuleConditionArgs(
            path_pattern=aws.lb.ListenerRuleConditionPathPatternArgs(
                values=["/shield_manifest.json"],
            ),
        )
    ],
)

# ---------------------------------------------------------------------------
# WAFv2: allow only predefined subdomains, block everything else
# ---------------------------------------------------------------------------
from pulumi_aws.wafv2 import WebAcl, WebAclAssociation
from pulumi_aws.wafv2._inputs import (
    WebAclDefaultActionArgs,
    WebAclDefaultActionBlockArgs,
    WebAclDefaultActionBlockCustomResponseArgs,
    WebAclRuleArgs,
    WebAclRuleActionArgs,
    WebAclRuleActionAllowArgs,
    WebAclRuleStatementArgs,
    WebAclRuleStatementByteMatchStatementArgs,
    WebAclRuleStatementByteMatchStatementFieldToMatchArgs,
    WebAclRuleStatementByteMatchStatementFieldToMatchSingleHeaderArgs,
    WebAclRuleStatementByteMatchStatementFieldToMatchUriPathArgs,
    WebAclRuleStatementByteMatchStatementTextTransformationArgs,
    WebAclRuleStatementOrStatementArgs,
    WebAclRuleVisibilityConfigArgs,
    WebAclVisibilityConfigArgs,
)

waf_rules = []
if domains:
    waf_rules.append(
        WebAclRuleArgs(
            name="allow-predefined-domains",
            priority=0,
            action=WebAclRuleActionArgs(
                allow=WebAclRuleActionAllowArgs(),
            ),
            visibility_config=WebAclRuleVisibilityConfigArgs(
                sampled_requests_enabled=True,
                cloudwatch_metrics_enabled=False,
                metric_name="allow-predefined-domains",
            ),
            statement=WebAclRuleStatementArgs(
                or_statement=WebAclRuleStatementOrStatementArgs(
                    statements=[
                        WebAclRuleStatementArgs(
                            byte_match_statement=WebAclRuleStatementByteMatchStatementArgs(
                                search_string=d,
                                positional_constraint="EXACTLY",
                                field_to_match=WebAclRuleStatementByteMatchStatementFieldToMatchArgs(
                                    single_header=WebAclRuleStatementByteMatchStatementFieldToMatchSingleHeaderArgs(
                                        name="host",
                                    ),
                                ),
                                text_transformations=[
                                    WebAclRuleStatementByteMatchStatementTextTransformationArgs(
                                        priority=0,
                                        type="LOWERCASE",
                                    ),
                                ],
                            ),
                        )
                        for d in domains
                    ],
                ),
            ),
        )
    )

# Also allow /shield_manifest.json path regardless of host
waf_rules.append(
    WebAclRuleArgs(
        name="allow-manifest",
        priority=1,
        action=WebAclRuleActionArgs(
            allow=WebAclRuleActionAllowArgs(),
        ),
        visibility_config=WebAclRuleVisibilityConfigArgs(
            sampled_requests_enabled=True,
            cloudwatch_metrics_enabled=False,
            metric_name="allow-manifest",
        ),
        statement=WebAclRuleStatementArgs(
            byte_match_statement=WebAclRuleStatementByteMatchStatementArgs(
                search_string="/shield_manifest.json",
                positional_constraint="EXACTLY",
                field_to_match=WebAclRuleStatementByteMatchStatementFieldToMatchArgs(
                    uri_path=WebAclRuleStatementByteMatchStatementFieldToMatchUriPathArgs(),
                ),
                text_transformations=[
                    WebAclRuleStatementByteMatchStatementTextTransformationArgs(
                        priority=0,
                        type="NONE",
                    ),
                ],
            ),
        ),
    )
)

waf_acl = WebAcl(
    "shield-waf-acl",
    scope="REGIONAL",
    default_action=WebAclDefaultActionArgs(
        block=WebAclDefaultActionBlockArgs(
            custom_response=WebAclDefaultActionBlockCustomResponseArgs(
                response_code=403,
            ),
        ),
    ),
    visibility_config=WebAclVisibilityConfigArgs(
        sampled_requests_enabled=True,
        cloudwatch_metrics_enabled=False,
        metric_name="shield-waf",
    ),
    rules=waf_rules,
)

waf_association = WebAclAssociation(
    "shield-waf-association",
    resource_arn=alb.arn,
    web_acl_arn=waf_acl.arn,
)

# ---------------------------------------------------------------------------
# 6. Create an NLB with a static public IPv4 (Elastic IP)
# ---------------------------------------------------------------------------
nlb_eip = aws.ec2.Eip("shield-nlb-eip", domain="vpc")

# NLB needs exactly one subnet mapping per AZ; pick the first subnet
# (we need at least one public subnet for the EIP).
# Use the first subnet for the EIP mapping; add remaining subnets without EIP.
primary_subnet_id = subnet_ids[0]
other_subnet_ids = subnet_ids[1:] if len(subnet_ids) > 1 else []

subnet_mappings = [
    aws.lb.LoadBalancerSubnetMappingArgs(
        subnet_id=primary_subnet_id,
        allocation_id=nlb_eip.id,
    )
]
for sid in other_subnet_ids:
    subnet_mappings.append(
        aws.lb.LoadBalancerSubnetMappingArgs(subnet_id=sid)
    )

nlb = aws.lb.LoadBalancer(
    "shield-nlb",
    load_balancer_type="network",
    subnet_mappings=subnet_mappings,
)

# NLB target group → ALB
nlb_tg = aws.lb.TargetGroup(
    "shield-nlb-tg",
    port=MINER_INSTANCE_PORT,
    protocol="TCP",
    vpc_id=vpc_id,
    target_type="alb",
    health_check=aws.lb.TargetGroupHealthCheckArgs(
        protocol="HTTP",
        port=str(MINER_INSTANCE_PORT),
        path="/shield_manifest.json",
        healthy_threshold=2,
        unhealthy_threshold=2,
        timeout=5,
        interval=30,
    ),
    opts=pulumi.ResourceOptions(depends_on=[alb, alb_listener]),
)

nlb_tg_attachment = aws.lb.TargetGroupAttachment(
    "shield-nlb-tg-attachment",
    target_group_arn=nlb_tg.arn,
    target_id=alb.arn,
    port=MINER_INSTANCE_PORT,
    opts=pulumi.ResourceOptions(depends_on=[alb_listener, alb]),
)

nlb_listener = aws.lb.Listener(
    "shield-nlb-listener",
    load_balancer_arn=nlb.arn,
    port=MINER_INSTANCE_PORT,
    protocol="TCP",
    default_actions=[aws.lb.ListenerDefaultActionArgs(
        type="forward",
        target_group_arn=nlb_tg.arn,
    )],
)

# ---------------------------------------------------------------------------
# 5. Create wildcard subdomain record in Route 53 (single wildcard only)
# ---------------------------------------------------------------------------
aws.route53.Record(
    "shield-dns-wildcard",
    zone_id=HOSTED_ZONE_ID,
    name=f"*.{zone_domain}",
    type="A",
    aliases=[
        aws.route53.RecordAliasArgs(
            name=nlb.dns_name,
            zone_id=nlb.zone_id,
            evaluate_target_health=True,
        )
    ],
)

# ---------------------------------------------------------------------------
# 7. Dump the NLB static IP to a file
# ---------------------------------------------------------------------------
nlb_eip.public_ip.apply(
    lambda ip: pathlib.Path(NLB_IP_FILE).write_text(ip + "\n")
)

# ---------------------------------------------------------------------------
# Pulumi exports
# ---------------------------------------------------------------------------
pulumi.export("bucket_name", bucket.bucket)
pulumi.export("bucket_regional_domain", bucket.bucket_regional_domain_name)
pulumi.export("alb_dns_name", alb.dns_name)
pulumi.export("nlb_dns_name", nlb.dns_name)
pulumi.export("nlb_static_ip", nlb_eip.public_ip)
pulumi.export("hosted_zone_domain", zone_domain)
pulumi.export("domains", domains)
