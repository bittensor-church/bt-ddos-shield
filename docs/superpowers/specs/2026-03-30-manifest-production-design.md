# Manifest Production and Upload Design

## Goal

Make `chain_reader` produce the final desired `shield_manifest.json` payload from the reconciled validator/domain state, and make `pulumi_runner` upload that payload to S3 only when the content changes.

## Scope

This change covers:

- changing the persisted `manifest.json` state contract
- extending `chain_reader` to build encrypted manifest content
- extending `pulumi_runner` to upload `shield_manifest.json` from state
- making shared state-file JSON writes deterministic and pretty-printed
- README updates describing the new manifest state behavior

This change does not cover:

- any change to `chain_writer` responsibilities
- adding a separate manifest-builder component
- storing a manifest hash inside the JSON payload

## Requirements

- `chain_reader` remains the sole producer of chain-derived desired state.
- `manifest.json` becomes the desired future upload payload, not a published URL record.
- `chain_writer` never consumes `manifest.json`; it continues to consume only the public axon address state.
- `manifest.json` must contain the final upload shape:

```json
{
    "ddos_shield_manifest": {
        "encrypted_url_mapping": {
            "<validator-hotkey>": "<base64-encrypted-endpoint>"
        }
    }
}
```

- The encrypted plaintext for each validator is the assigned hostname plus miner port, formatted as `{domain}:{port}`.
- When there are zero eligible validators, `chain_reader` must write exactly:

```json
{
    "ddos_shield_manifest": {
        "encrypted_url_mapping": {}
    }
}
```

- All shared state JSON files must be written deterministically:
  - pretty-printed
  - `indent=4` or equivalent
  - sorted dictionary keys
  - trailing newline
- `pulumi_runner` must upload `manifest.json` to the public bucket as `shield_manifest.json`.
- Pulumi, not the file payload, must compute the content hash used to decide whether the S3 object needs to be updated.

## Current Problems

Today the repo has two mismatches:

- `manifest.json` is still shaped like an old placeholder output state with `manifest_url` and `encrypted_addresses`
- `pulumi_runner` provisions the bucket and manifest redirect path but does not upload a manifest object

That leaves the ALB/NLB manifest path wired up without an actual `shield_manifest.json` producer in the current architecture.

## Recommended Approach

Keep the component split strict:

- `chain_reader` owns desired state derived from chain data
- `pulumi_runner` owns AWS resources and S3 object lifecycle

Under this split, `chain_reader` writes both:

- `desired_domains.json`
- `manifest.json`

`pulumi_runner` reads both desired-state files:

- `desired_domains.json` for WAF host allow rules
- `manifest.json` for S3 upload content

This keeps chain/certificate/encryption logic out of the infrastructure component while still letting Pulumi manage idempotent uploads.

## State Contract Changes

### `manifest.json`

Replace the current shape:

```json
{
    "manifest_url": null,
    "encrypted_addresses": []
}
```

with:

```json
{
    "ddos_shield_manifest": {
        "encrypted_url_mapping": {}
    }
}
```

No `manifest_url` field remains.
No `md5_hash` field remains.

The state file now represents the exact desired uploaded JSON payload.

### Pretty JSON Invariant

The shared state writer should serialize every state file with stable formatting so humans can inspect diffs and Pulumi sees deterministic content:

- `json.dump(..., indent=4, sort_keys=True)`
- newline at end of file

This applies to all shared state files, not only `manifest.json`.

## Chain Reader Design

`chain_reader` already reconciles validator hotkeys, certs, blacklist exclusions, and root-domain changes into `desired_domains.json`.

After that reconciliation, it should build `manifest.json` from the resulting desired mapping.

### Inputs

- current reconciled desired domains
- validator hotkeys
- validator public certs from `desired_domains.json`

### Output mapping

For each desired-domain entry:

- key: validator hotkey
- plaintext value: assigned endpoint such as `5Hjbf5s2-abc123def456.example.com:9001`
- encrypted value: ECIES encryption using the validator public cert
- stored JSON value: base64-encoded encrypted bytes

### Encryption behavior

Use the ECIES logic from the old repo’s `encryption_manager.py` as the compatibility baseline:

- ed25519 public keys in hex format
- encrypt bytes using ECIES
- base64-encode the ciphertext for JSON serialization

The implementation should copy only the minimal compatible encryption logic needed locally. It should not import or depend on the old repo.

### Empty manifest

If the reconciled desired-domain mapping is empty, `chain_reader` still writes:

```json
{
    "ddos_shield_manifest": {
        "encrypted_url_mapping": {}
    }
}
```

This makes the empty-manifest case explicit and lets Pulumi upload a valid empty manifest object.

## Pulumi Runner Design

`pulumi_runner` already creates:

- the public S3 bucket
- the ALB listener redirect from `/shield_manifest.json`
- the manifest-allow WAF rule

It should now also create the actual S3 object:

- object key: `shield_manifest.json`
- content type: `application/json`
- content: serialized `manifest.json` state payload

### Change detection

Pulumi AWS `s3.BucketObject` supports content-based update triggers through `source_hash` or `etag`.

Use a Pulumi-side content hash derived from the serialized manifest JSON string. This makes updates happen only when manifest content changes and avoids storing sync metadata inside `manifest.json`.

The hash is implementation-internal only. It does not appear in the uploaded JSON and does not appear in shared state.

## Components Affected

- `server_shield/src/server_shield/shared/state.py`
- `server_shield/src/server_shield/shared/state_store.py`
- `server_shield/src/server_shield/shared/state_files/manifest.example.json`
- `server_shield/src/server_shield/chain_reader/cli.py`
- a new focused chain-reader helper module for manifest building/encryption
- `server_shield/src/server_shield/pulumi_runner/program.py`
- tests and docs that reference the old `manifest.json` shape

## Error Handling

### `chain_reader`

- If `root_domain` is `null`, it exits `0` and leaves both `desired_domains.json` and `manifest.json` unchanged.
- If manifest encryption fails for a validator that otherwise has a valid desired-domain entry, the run should fail. A partial manifest is worse than no manifest because it silently drops an eligible validator.
- If there are no eligible validators, the run succeeds and writes the empty manifest payload.

### `pulumi_runner`

- If `manifest.json` contains a valid empty manifest, upload that exact empty manifest object.
- If manifest state is malformed, Pulumi should fail rather than uploading invalid content.

## Testing and Verification

Per the current user instruction, do not add unit tests for this change now.

Manual verification should cover:

- `chain_reader` writes an empty manifest payload when there are no eligible validators
- `chain_reader` writes encrypted values keyed by validator hotkey when eligible validators exist
- the manifest JSON is pretty-printed and keys are sorted
- `pulumi_runner` uploads `shield_manifest.json` to S3 from state
- rerunning Pulumi without manifest content changes does not force a new object update
- changing a desired domain or validator cert changes the uploaded object content

## Risks

- The manifest state contract changes materially, so any stale code paths still expecting `manifest_url` or `encrypted_addresses` must be updated in one pass.
- Encryption compatibility matters: if the local ECIES configuration differs from the old client/server expectation, validators will not be able to decrypt their assigned endpoints.
- Deterministic JSON formatting reduces diff churn but means every state write path must use the shared stable serializer consistently.
