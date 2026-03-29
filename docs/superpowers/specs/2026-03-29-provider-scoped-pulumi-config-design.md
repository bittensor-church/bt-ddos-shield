# Provider-Scoped Pulumi Config Design

## Goal

Restructure Pulumi configuration so provider-specific infrastructure settings live under a provider-scoped namespace, while shared Pulumi settings remain top-level. Also ensure the Pulumi CLI subprocess receives the provider credentials and region variables explicitly.

## Scope

This change only affects the server shield Pulumi configuration structure, Pulumi CLI environment propagation, and related tests/docs.

In scope:
- add a top-level Pulumi `shield_backend` selector
- move AWS-specific Pulumi settings under `pulumi.aws`
- keep `pulumi.backend_url`, `pulumi.stack_name`, and `pulumi.miner_port` at the top level
- explicitly pass AWS credentials and region env vars to Pulumi subprocess commands
- update tests and documentation

Out of scope:
- implementing any non-AWS provider
- changing non-Pulumi component behavior beyond config compatibility
- changing Pulumi infrastructure logic other than config access paths

## Current Problem

The Pulumi config currently mixes generic and AWS-specific fields in one flat settings object. That makes future provider expansion awkward and leaves subprocess environment propagation implicit. The user also observed that AWS region was not consistently propagated where the Pulumi CLI needed it.

## Design

### Configuration Shape

Top-level Pulumi config will be:
- `backend_url: str`
- `stack_name: str = "server-shield"`
- `shield_backend: Literal["AWS"]`
- `miner_port: int`
- `aws: AwsShieldSettings`

AWS-specific nested config will be:
- `aws_access_key_id: str`
- `aws_secret_access_key: str`
- `aws_region: str`
- `miner_instance_id: str`
- `hosted_zone_id: str`

Environment variables become:
- `SERVER_SHIELD_PULUMI__BACKEND_URL`
- `SERVER_SHIELD_PULUMI__STACK_NAME`
- `SERVER_SHIELD_PULUMI__SHIELD_BACKEND=AWS`
- `SERVER_SHIELD_PULUMI__MINER_PORT`
- `SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID`
- `SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY`
- `SERVER_SHIELD_PULUMI__AWS__AWS_REGION`
- `SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID`
- `SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID`

`miner_port` stays top-level because it is not backend-specific and may be used by other components.

### Pulumi Runner Subprocess Environment

The Pulumi runner will build an explicit subprocess environment for Pulumi CLI commands.

For `shield_backend=AWS`, the subprocess environment will include:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `AWS_DEFAULT_REGION`

These values come from `config.pulumi.aws.*`.

This explicit env construction applies to all Pulumi commands the runner invokes:
1. `pulumi login <backend_url>`
2. `pulumi stack select <stack_name> --create`
3. `pulumi up --stack <stack_name>`

### Pulumi Program Access

The Pulumi program will read:
- `config.pulumi.miner_port` for the shared miner port
- `config.pulumi.aws.aws_region`
- `config.pulumi.aws.miner_instance_id`
- `config.pulumi.aws.hosted_zone_id`

This keeps provider-specific data in the nested AWS block while preserving the shared top-level miner port.

### Documentation

README and env examples will document the new structure using only the `AWS` backend name.

The docs will not mention hypothetical future backend names.

### Testing

Tests will cover:
- shared config reads the nested AWS structure
- `shield_backend` is required and must currently be `AWS`
- `miner_port` remains top-level under `pulumi`
- Pulumi runner passes AWS credentials and both region vars into subprocess env
- Pulumi program uses the nested AWS config path successfully

## Error Handling

If the backend selector or required nested AWS config is missing, config parsing should fail early.

If subprocess env construction is incorrect, Pulumi command tests should fail by asserting the exact env mapping passed to `subprocess.run`.

## Acceptance Criteria

- AWS-specific Pulumi settings are no longer top-level under `pulumi`
- `miner_port` remains top-level under `pulumi`
- Pulumi CLI commands receive explicit AWS credential and region env vars
- `AWS_REGION` and `AWS_DEFAULT_REGION` are both set from config
- README shows the provider-scoped env var structure using `AWS`
