# Chain Reader Validator Domain Reconciliation Design

## Goal

Replace the placeholder `chain_reader` with a real reconciler that reads the validator set and validator certificates from chain, then updates `desired_domains.json` so it contains exactly the eligible validators that should receive shield domains.

## Scope

This change covers:

- the `chain_reader` component implementation
- any small shared helpers or typed state changes needed to support reconciliation
- README updates for operator-managed blacklist handling and state-directory mounting
- manual verification against `bittensor_network=finney` and `netuid=12`

This change does not cover:

- manifest generation logic
- chain writer behavior
- changes to Pulumi state layout beyond consuming the reconciled `desired_domains.json`
- unit test additions for this feature

## Requirements

- If `root_domain.json` contains `{ "domain": null }`, `chain_reader` must exit successfully and leave `desired_domains.json` unchanged.
- If `root_domain.json` contains a domain, `chain_reader` must fetch the active validators for the configured subnet and their published certificates from chain.
- Validators already present in `desired_domains.json` must keep their existing domain across subsequent runs if both of these are true:
  - the validator is still eligible
  - the validator certificate is unchanged
- A validator gets a new domain if either of these is true:
  - the validator certificate changed
  - the current `root_domain` changed compared with the suffix of the stored domain
- New eligible validators must be added.
- Validators that are no longer eligible must be removed.
- Hotkeys listed in `blacklist.json` must never appear in `desired_domains.json`.
- Validators with missing or malformed certificates must be logged and excluded, not treated as fatal errors.

## Data Model

`desired_domains.json` remains the desired-state contract for the Pulumi runner:

```json
{
  "domains": {
    "<hotkey>": {
      "domain": "<hostname under current root domain>",
      "public_cert": "<hex public key from chain>"
    }
  }
}
```

No separate history file is introduced. The current `desired_domains.json` content is sufficient to decide whether a validator should keep its existing domain or receive a new one.

`blacklist.json` remains a JSON array of hotkey strings maintained by human operators.

## Architecture

The `chain_reader` stays a one-shot batch component invoked by the existing supervisor. Each run performs the following sequence:

1. Ensure the shared state files exist.
2. Read `root_domain.json`.
3. If `root_domain.domain` is `null`, log a skip message and exit `0` without modifying `desired_domains.json`.
4. Read `blacklist.json`.
5. Read the current `desired_domains.json`.
6. Connect to the configured subtensor endpoint and fetch the current validator set for `netuid`.
7. For each validator hotkey, fetch and decode its published certificate.
8. Filter out blacklisted validators and validators without a valid decodable certificate.
9. Reconcile the filtered chain view against the current desired-state mapping.
10. Atomically write the new `desired_domains.json`.
11. Log reconciliation counts and exit `0`.

`manifest.json` remains untouched by this change.

## Chain Access

The implementation should use the `bittensor` dependency already present in this repo and the existing configuration fields:

- `SERVER_SHIELD_SUBTENSOR_ADDRESS`
- `SERVER_SHIELD_NETUID`

For manual verification, the operator can set these so the process talks to Finney and subnet 12.

Validator certificate lookup should reuse the certificate decoding shape demonstrated in the reference repo:

- query `NeuronCertificates` for `(netuid, hotkey)`
- extract `algorithm` and the first `public_key` entry
- normalize the public key to a hex string

The new implementation may copy only the minimal local helper needed for that decoding. It should not copy the old repo’s state-keeping design.

## Eligibility Rules

A validator is eligible only if all of the following are true:

- it is part of the current validator set on the configured subnet
- its hotkey is not listed in `blacklist.json`
- it has a published certificate that can be decoded into a hex public key

If a validator is present on chain but excluded because of blacklist or certificate problems, `chain_reader` logs the reason and omits it from the output mapping.

## Reconciliation Rules

Reconciliation is keyed by validator hotkey.

For each currently eligible validator:

- If the hotkey is absent from the current desired mapping, allocate a new domain and add an entry.
- If the hotkey is present and the stored `public_cert` matches the current chain certificate, preserve the entry only if the stored `domain` ends with the current `root_domain`.
- If the hotkey is present and the stored `public_cert` differs from the chain certificate, allocate a new domain and replace the entry.
- If the hotkey is present and the stored `domain` does not end with the current `root_domain`, allocate a new domain and replace the entry even if the certificate is unchanged.

For entries currently in `desired_domains.json` but not eligible in the current run:

- remove the entry from the output mapping

This satisfies both invariants:

- no churn across subsequent runs for unchanged eligible validators
- full rotation when the hosted root domain changes

## Domain Allocation

New or rotated domains use this label format:

`<first-8-hotkey-characters>-<12-lowercase-hex-characters>`

Example:

`abcdef12-1a2b3c4d5e6f.example.com`

Allocation rules:

- the prefix is always the first 8 characters of the validator hotkey
- the suffix is generated randomly at creation time
- uniqueness is checked against every preserved domain and every newly generated domain in the current reconciliation pass
- once allocated, a domain is never rewritten on later runs unless the validator certificate changes or the root domain changes

Twelve lowercase hex characters are enough to keep collisions negligible while staying readable during operations and debugging.

## Logging and Error Handling

Successful skip cases:

- `root_domain` is `null`: log that chain reader is skipping because the root domain is unavailable, exit `0`

Non-fatal exclusions:

- blacklisted hotkey: log and exclude
- missing certificate: log and exclude
- malformed certificate payload: log and exclude

Fatal errors:

- chain connection or subnet query failure
- unexpected errors during reconciliation or state write

Fatal errors continue to rely on the existing runtime wrapper to return a non-zero exit and report the failure through Sentry when configured.

Successful reconciliation should log at least:

- total validators observed
- eligible validators kept
- new domains created
- existing domains rotated because of certificate change
- existing domains rotated because of root domain change
- entries removed
- blacklisted validators skipped
- validators skipped because of missing or invalid certificates

## README and Operations

The README should explain that `blacklist.json` is the operator-controlled input file inside the shared state directory.

Operator workflow:

1. Edit `blacklist.json` to add or remove validator hotkeys.
2. Keep the file as a JSON array of strings.
3. Wait for the next `chain_reader` run, or restart the container to force an immediate run.
4. Confirm the hotkeys are absent from `desired_domains.json`.

Production deployment guidance should recommend mounting the entire state directory rather than an individual file. This keeps:

- operator-managed `blacklist.json`
- generated `desired_domains.json`
- other shared state files

in one persistent location with one mount.

## Verification

No new unit tests are added for this task.

Verification is manual:

- run `chain_reader` with no root domain and confirm it exits `0` without changing `desired_domains.json`
- run `chain_reader` with a valid root domain against Finney subnet 12 and confirm it populates `desired_domains.json`
- rerun with no chain changes and confirm domains are preserved exactly
- modify `blacklist.json` and confirm blacklisted hotkeys disappear from `desired_domains.json`
- confirm validators with no valid cert are logged and omitted
- simulate or observe a cert change and confirm a new domain is assigned
- change `root_domain.json` and confirm all retained validators receive new domains under the new root

## Risks

- Bittensor validator selection APIs may expose validator membership differently than expected, so the implementation should verify the chosen API against real subnet 12 data.
- Certificate payload shapes may vary across library versions, so decoding should be tolerant of both string and byte-like public key values.
- Root-domain rotation intentionally causes bulk domain churn, which is required behavior but operationally significant.
