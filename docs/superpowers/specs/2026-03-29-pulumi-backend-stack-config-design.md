# Pulumi Backend and Stack Configuration Design

## Goal

Make Pulumi backend selection explicit and mandatory, move stack naming into shared application config, and make first-run stack bootstrap automatic.

## Scope

This change only affects the server shield Pulumi runner configuration and documentation.

In scope:
- require Pulumi backend URL through shared Pydantic config
- add Pulumi stack name to shared Pydantic config with default `server-shield`
- make the runner log in to the configured backend and run `pulumi stack select --create`
- update tests for config and Pulumi CLI invocation
- update README with exact Docker build and run commands and backend configuration examples

Out of scope:
- changing non-Pulumi components
- changing state-file behavior
- changing Docker scheduling/supervision behavior
- changing Pulumi program resource logic

## Current Problem

The runtime currently mixes two configuration models:
- shared app config for AWS and component settings
- direct `PULUMI_BACKEND_URL` environment access inside the Pulumi runner

It also hardcodes the stack name in code and assumes the stack already exists. On a fresh backend this causes `pulumi up` to fail with `no stack named 'server-shield' found`.

## Design

### Configuration

Extend `PulumiSettings` with:
- `backend_url: str` (required)
- `stack_name: str = "server-shield"`

Environment variables become:
- `SERVER_SHIELD_PULUMI__BACKEND_URL`
- `SERVER_SHIELD_PULUMI__STACK_NAME` (optional)

This keeps all production configuration under the existing shared Pydantic settings object.

### Pulumi Runner Flow

The Pulumi runner will execute these commands in order:

1. `pulumi login <backend_url>`
2. `pulumi stack select <stack_name> --create --cwd <pulumi_project>`
3. `pulumi up --yes --stack <stack_name> --cwd <pulumi_project>`

Behavioral rules:
- if login fails, return that exit code immediately
- if stack select fails, return that exit code immediately
- if `up` fails, return that exit code
- the runner never tries to infer a backend URL from direct environment access

Using `stack select --create` on every run is intentional. It is idempotent for an existing stack and removes the need for a separate first-run bootstrap path.

### Documentation

README will document that `SERVER_SHIELD_PULUMI__BACKEND_URL` is mandatory.

Documented backend examples:

Local file backend:
- `SERVER_SHIELD_PULUMI__BACKEND_URL=file:///var/lib/server-shield/pulumi-state`
- requires a persistent Docker volume mounted at `/var/lib/server-shield/pulumi-state`

S3 backend:
- `SERVER_SHIELD_PULUMI__BACKEND_URL=s3://my-pulumi-state-bucket/server-shield`
- requires valid AWS credentials in the container
- requires the bucket to already exist

README will also retain exact Docker build and run commands.

### Testing

Tests will cover:
- shared config reads required backend URL
- shared config defaults stack name to `server-shield`
- Pulumi runner logs into configured backend URL
- Pulumi runner runs `stack select --create`
- Pulumi runner runs `up` against configured stack name
- missing backend URL raises config validation failure

## Error Handling

This design intentionally fails early when the backend URL is missing or invalid. That is preferable to silently defaulting to Pulumi Cloud or a local file backend, because backend selection affects durability, credentials, and operational behavior.

## Operational Notes

Local file backend is acceptable for single-container/local use only when the backend path is persisted with a Docker volume.

S3 backend is preferable when state durability outside the container is required.

The stack name default remains `server-shield`, but operators can override it when needed without code changes.

## Acceptance Criteria

- starting the container without `SERVER_SHIELD_PULUMI__BACKEND_URL` fails during config parsing
- starting against an empty backend creates/selects the configured stack automatically
- default stack name is `server-shield`
- overriding the stack name changes both stack selection and `pulumi up`
- README explains exact build/run commands and backend configuration for file and S3 backends
