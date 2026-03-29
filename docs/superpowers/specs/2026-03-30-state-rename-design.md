# State Rename Design

## Goal

Rename two persisted state artifacts and their state-store API names to remove AWS- and infrastructure-specific terminology without changing runtime behavior.

## Scope

This change applies to persisted state filenames, the Python models and helper functions that read and write those files, and all in-repo callers/tests/docs that consume those names.

The rename is:

- `hosted_zone_domain.json` -> `root_domain.json`
- `nlb_ip.json` -> `axon_public_ip.json`
- `HostedZoneDomainState` -> `RootDomainState`
- `NlbIpState` -> `AxonPublicIpState`
- `read_hosted_zone_domain()` / `write_hosted_zone_domain()` -> `read_root_domain()` / `write_root_domain()`
- `read_nlb_ip()` / `write_nlb_ip()` -> `read_axon_public_ip()` / `write_axon_public_ip()`

## Non-Goals

- No migration layer for legacy filenames.
- No change to Pulumi export names such as `hosted_zone_domain`.
- No change to serialized payload shapes beyond the filenames themselves. The JSON contents remain `{ "domain": ... }` for root domain state and `{ "ip": ... }` for axon public IP state.
- No behavioral changes in chain reader, chain writer, Pulumi orchestration, or runtime configuration.

## Design

The state layer remains the source of truth for these artifacts. The implementation changes only the names of the files and the Python symbols that represent them. Call sites continue to read and write the same logical values, with the same success and skip behavior as today.

`root_domain.json` continues to hold the domain value produced by the Pulumi runner and consumed by the chain reader. `axon_public_ip.json` continues to hold the public IP value produced by the Pulumi runner and consumed by the chain writer.

Pulumi may continue to use AWS-specific naming in infrastructure-local identifiers and exports. The rename stops at the state contract boundary.

## Components Affected

- `server_shield/shared/state.py`
- `server_shield/shared/state_store.py`
- `server_shield/shared/state_files/*.example.json`
- `server_shield/chain_reader/cli.py`
- `server_shield/chain_writer/cli.py`
- `server_shield/pulumi_runner/program.py`
- Tests that assert filenames, helper names, or log strings tied to the old names
- README references to the state directory contents

## Error Handling

Error handling remains unchanged:

- state initialization still creates or copies example files
- readers still validate the same JSON shapes
- chain writer still exits cleanly when the public IP value is `null`
- no backward compatibility is added for old filenames

## Testing

Implementation follows TDD with targeted failing tests first:

- state store tests for example-file initialization and read/write helpers
- chain writer tests for skip/non-skip paths using `axon_public_ip`
- chain reader tests for reading `root_domain`
- Pulumi runner tests covering state writes through the renamed helpers

## Risks

The main risk is incomplete rename coverage, especially hard-coded filenames in tests, docs, or helper call sites. Targeted search plus focused test execution is sufficient to control that risk.
