import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pulumi
import pulumi_aws as aws
from pulumi_aws.wafv2 import WebAcl, WebAclAssociation
from pulumi_aws.wafv2._inputs import (
    WebAclDefaultActionArgs,
    WebAclDefaultActionBlockArgs,
    WebAclDefaultActionBlockCustomResponseArgs,
    WebAclRuleActionAllowArgs,
    WebAclRuleActionArgs,
    WebAclRuleArgs,
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

from server_shield.shared.config import get_config
from server_shield.shared.state import DesiredDomainEntry
from server_shield.shared.state_store import (
    read_desired_domains,
    read_manifest,
    write_axon_public_ip,
    write_root_domain,
)


def _desired_domain_names(
    desired_domains: Mapping[str, DesiredDomainEntry | dict[str, str]],
) -> list[str]:
    return [
        entry.domain if isinstance(entry, DesiredDomainEntry) else entry["domain"]
        for entry in desired_domains.values()
    ]


def should_create_domain_allow_rule(
    desired_domains: Mapping[str, DesiredDomainEntry | dict[str, str]],
) -> bool:
    return bool(desired_domains)


def build_waf_rule_names(
    desired_domains: Mapping[str, DesiredDomainEntry | dict[str, str]],
) -> list[str]:
    names: list[str] = []
    if should_create_domain_allow_rule(desired_domains):
        names.extend(
            f"allow-predefined-domain-{index}"
            for index, _domain in enumerate(_desired_domain_names(desired_domains))
        )
    names.append("allow-manifest")
    return names


def build_waf_rules(
    desired_domains: Mapping[str, DesiredDomainEntry | dict[str, str]],
    miner_port: int,
) -> list[WebAclRuleArgs]:
    waf_rules: list[WebAclRuleArgs] = []
    if should_create_domain_allow_rule(desired_domains):
        for index, domain_name in enumerate(_desired_domain_names(desired_domains)):
            waf_rules.append(
                WebAclRuleArgs(
                    name=f"allow-predefined-domain-{index}",
                    priority=index,
                    action=WebAclRuleActionArgs(allow=WebAclRuleActionAllowArgs()),
                    visibility_config=WebAclRuleVisibilityConfigArgs(
                        sampled_requests_enabled=True,
                        cloudwatch_metrics_enabled=False,
                        metric_name=f"allow-predefined-domain-{index}",
                    ),
                    statement=WebAclRuleStatementArgs(
                        byte_match_statement=WebAclRuleStatementByteMatchStatementArgs(
                            search_string=domain_name.lower(),
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
                        )
                    ),
                )
            )
    waf_rules.append(
        WebAclRuleArgs(
            name="allow-manifest",
            priority=len(waf_rules),
            action=WebAclRuleActionArgs(allow=WebAclRuleActionAllowArgs()),
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
                )
            ),
        )
    )
    return waf_rules


def serialize_manifest_content(manifest: Mapping[str, object]) -> str:
    return json.dumps(manifest, indent=4, sort_keys=True) + "\n"


def manifest_source_hash(serialized_manifest: str) -> str:
    return hashlib.sha256(serialized_manifest.encode("utf-8")).hexdigest()


def run_program() -> None:
    config = get_config()
    desired_domains = read_desired_domains().domains
    manifest = read_manifest().model_dump()
    serialized_manifest = serialize_manifest_content(manifest)
    miner_instance_id = config.pulumi.aws.miner_instance_id
    miner_port = config.miner_port
    hosted_zone_id = config.pulumi.aws.hosted_zone_id

    pulumi.log.info(f"Loaded {len(desired_domains)} domain(s) from state store")

    hosted_zone = aws.route53.get_zone(zone_id=hosted_zone_id)
    zone_domain = hosted_zone.name.rstrip(".")
    pulumi.log.info(f"Hosted zone domain: {zone_domain}")
    write_root_domain(domain=zone_domain)

    miner_instance = aws.ec2.get_instance(instance_id=miner_instance_id)
    miner_subnet = aws.ec2.get_subnet(id=miner_instance.subnet_id)
    vpc_id = miner_subnet.vpc_id

    vpc_subnets = aws.ec2.get_subnets(
        filters=[aws.ec2.GetSubnetsFilterArgs(name="vpc-id", values=[vpc_id])]
    )
    seen_azs: dict[str, str] = {}
    for subnet_id in vpc_subnets.ids:
        subnet = aws.ec2.get_subnet(id=subnet_id)
        if subnet.availability_zone not in seen_azs:
            seen_azs[subnet.availability_zone] = subnet_id
    subnet_ids = list(seen_azs.values())

    bucket = aws.s3.Bucket("shield-public-files", force_destroy=True)
    bucket_ownership = aws.s3.BucketOwnershipControls(
        "shield-public-files-ownership",
        bucket=bucket.id,
        rule=aws.s3.BucketOwnershipControlsRuleArgs(object_ownership="ObjectWriter"),
    )
    bucket_public_access = aws.s3.BucketPublicAccessBlock(
        "shield-public-files-public-access",
        bucket=bucket.id,
        block_public_acls=False,
        block_public_policy=False,
        ignore_public_acls=False,
        restrict_public_buckets=False,
    )
    aws.s3.BucketPolicy(
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
    aws.s3.BucketObject(
        "shield-manifest-object",
        bucket=bucket.id,
        key="shield_manifest.json",
        content=serialized_manifest,
        content_type="application/json",
        source_hash=manifest_source_hash(serialized_manifest),
        opts=pulumi.ResourceOptions(depends_on=[bucket_public_access, bucket_ownership]),
    )

    elb_sg = aws.ec2.SecurityGroup(
        "shield-elb-sg",
        description="Allow ELB to reach miner EC2 instance",
        vpc_id=vpc_id,
        ingress=[
            aws.ec2.SecurityGroupIngressArgs(
                protocol="tcp",
                from_port=miner_port,
                to_port=miner_port,
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
    ec2_from_elb_sg = aws.ec2.SecurityGroup(
        "shield-ec2-from-elb-sg",
        description="Allow inbound from ELB to miner EC2 on miner port",
        vpc_id=vpc_id,
        ingress=[
            aws.ec2.SecurityGroupIngressArgs(
                protocol="tcp",
                from_port=miner_port,
                to_port=miner_port,
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

    miner_eni = aws.ec2.get_network_interfaces(
        filters=[
            aws.ec2.GetNetworkInterfacesFilterArgs(
                name="attachment.instance-id",
                values=[miner_instance_id],
            )
        ]
    )
    aws.ec2.NetworkInterfaceSecurityGroupAttachment(
        "shield-ec2-sg-attachment",
        network_interface_id=miner_eni.ids[0],
        security_group_id=ec2_from_elb_sg.id,
    )

    alb = aws.lb.LoadBalancer(
        "shield-alb",
        internal=True,
        load_balancer_type="application",
        security_groups=[elb_sg.id],
        subnets=subnet_ids,
    )
    miner_tg = aws.lb.TargetGroup(
        "shield-miner-tg",
        port=miner_port,
        protocol="HTTP",
        vpc_id=vpc_id,
        target_type="instance",
        health_check=aws.lb.TargetGroupHealthCheckArgs(
            path="/",
            protocol="HTTP",
            port=str(miner_port),
            healthy_threshold=2,
            unhealthy_threshold=5,
            timeout=5,
            interval=30,
        ),
    )
    aws.lb.TargetGroupAttachment(
        "shield-miner-tg-attachment",
        target_group_arn=miner_tg.arn,
        target_id=miner_instance_id,
        port=miner_port,
    )
    alb_listener = aws.lb.Listener(
        "shield-alb-listener",
        load_balancer_arn=alb.arn,
        port=miner_port,
        protocol="HTTP",
        default_actions=[
            aws.lb.ListenerDefaultActionArgs(
                type="forward",
                target_group_arn=miner_tg.arn,
            )
        ],
    )
    aws.lb.ListenerRule(
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
                    status_code="HTTP_302",
                ),
            )
        ],
        conditions=[
            aws.lb.ListenerRuleConditionArgs(
                path_pattern=aws.lb.ListenerRuleConditionPathPatternArgs(
                    values=["/shield_manifest.json"],
                )
            )
        ],
    )

    waf_rules = build_waf_rules(desired_domains, miner_port=miner_port)
    waf_acl = WebAcl(
        "shield-waf-acl",
        scope="REGIONAL",
        default_action=WebAclDefaultActionArgs(
            block=WebAclDefaultActionBlockArgs(
                custom_response=WebAclDefaultActionBlockCustomResponseArgs(response_code=403),
            )
        ),
        visibility_config=WebAclVisibilityConfigArgs(
            sampled_requests_enabled=True,
            cloudwatch_metrics_enabled=False,
            metric_name="shield-waf",
        ),
        rules=waf_rules,
    )
    WebAclAssociation(
        "shield-waf-association",
        resource_arn=alb.arn,
        web_acl_arn=waf_acl.arn,
    )

    nlb_eip = aws.ec2.Eip("shield-nlb-eip", domain="vpc")
    primary_subnet_id = subnet_ids[0]
    other_subnet_ids = subnet_ids[1:] if len(subnet_ids) > 1 else []
    subnet_mappings = [
        aws.lb.LoadBalancerSubnetMappingArgs(
            subnet_id=primary_subnet_id,
            allocation_id=nlb_eip.id,
        )
    ]
    for subnet_id in other_subnet_ids:
        subnet_mappings.append(aws.lb.LoadBalancerSubnetMappingArgs(subnet_id=subnet_id))
    nlb = aws.lb.LoadBalancer(
        "shield-nlb",
        load_balancer_type="network",
        subnet_mappings=subnet_mappings,
    )
    nlb_tg = aws.lb.TargetGroup(
        "shield-nlb-tg",
        port=miner_port,
        protocol="TCP",
        vpc_id=vpc_id,
        target_type="alb",
        health_check=aws.lb.TargetGroupHealthCheckArgs(
            protocol="HTTP",
            port=str(miner_port),
            path="/shield_manifest.json",
            healthy_threshold=2,
            unhealthy_threshold=2,
            timeout=5,
            interval=30,
        ),
        opts=pulumi.ResourceOptions(depends_on=[alb, alb_listener]),
    )
    aws.lb.TargetGroupAttachment(
        "shield-nlb-tg-attachment",
        target_group_arn=nlb_tg.arn,
        target_id=alb.arn,
        port=miner_port,
        opts=pulumi.ResourceOptions(depends_on=[alb_listener, alb]),
    )
    aws.lb.Listener(
        "shield-nlb-listener",
        load_balancer_arn=nlb.arn,
        port=miner_port,
        protocol="TCP",
        default_actions=[
            aws.lb.ListenerDefaultActionArgs(
                type="forward",
                target_group_arn=nlb_tg.arn,
            )
        ],
    )
    aws.route53.Record(
        "shield-dns-wildcard",
        zone_id=hosted_zone_id,
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

    nlb_eip.public_ip.apply(_write_axon_public_ip)

    pulumi.export("bucket_name", bucket.bucket)
    pulumi.export("bucket_regional_domain", bucket.bucket_regional_domain_name)
    pulumi.export("alb_dns_name", alb.dns_name)
    pulumi.export("nlb_dns_name", nlb.dns_name)
    pulumi.export("nlb_static_ip", nlb_eip.public_ip)
    pulumi.export("hosted_zone_domain", zone_domain)
    pulumi.export("domains", desired_domains)
    pulumi.export("waf_rule_names", build_waf_rule_names(desired_domains))


def _write_axon_public_ip(ip: str) -> str:
    write_axon_public_ip(ip=ip)
    return ip
