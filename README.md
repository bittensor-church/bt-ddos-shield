miner part input params:

pulumi runner:
    sentry_dsn - optional
    hosted_zone_id
    ec2_id
    miner_port
    AWS creds for creating the infra
    stack configuration (s3 bucket, lcoal, etc., can be seprate from AWS creds for creating the infra)
dumps the domain to a file
dumps the nlb public ip
reads the desired subdomains for the elb file, can be missing or empty, that's fine


chain reader:
    subtensor_address
    netuid
reads the domain file
reads the blackilist file - can be missing or empty, must mountable from host
writes the file with desired subdomains for the elb
writes the manifest file (encrypted addresses)


chain writer:
    wallet
    subtensor_address
    netuid
    miner_port
writes the nlb public ip to axon info