# Chain Reader Manifest Domain Port Design

## Scope

Change the `chain_reader` manifest generation contract so each encrypted manifest value contains the assigned domain and the miner port, formatted as `{domain}:{port}`.

This change is limited to:

- `server_shield` manifest generation
- `server_shield` tests that verify manifest contents
- documentation that currently describes hostname-only plaintext

This change does not include:

- any JSON schema change to `manifest.json`
- any per-validator port selection
- any `bt_ddos_shield_client` behavioral change

## Design

The persisted manifest shape remains:

```json
{
    "ddos_shield_manifest": {
        "encrypted_url_mapping": {
            "<validator-hotkey>": "<base64-encrypted-value>"
        }
    }
}
```

Only the encrypted plaintext changes. Instead of encrypting the assigned hostname alone, `chain_reader` encrypts:

```text
{domain}:{SERVER_SHIELD_MINER_PORT}
```

For example:

```text
existing-validator.shield.example.com:9001
```

`miner_port` is sourced from the global app config via `get_config()`. This keeps the current implementation narrow while matching the current deployment model where a single global miner port applies to all manifest entries.

## Code Changes

- Update `server_shield/src/server_shield/chain_reader/manifest.py` so manifest plaintext is built from `DesiredDomainEntry.domain` plus `get_config().miner_port`.
- Keep `build_manifest_state()` as the public helper and leave the manifest JSON structure unchanged.
- Strengthen `server_shield/tests/chain_reader/test_cli.py` so tests decrypt produced manifest entries and assert the plaintext matches `{domain}:{port}`.
- Update docs that currently state the plaintext is hostname-only.

## Error Handling

No new error handling path is required. If config loading or encryption fails, the existing `chain_reader` failure behavior remains correct because a partial or malformed manifest is not acceptable.

## Verification

- Red-green on the targeted `chain_reader` test coverage
- Run the full `server_shield/tests/chain_reader/test_cli.py`
- Update documentation text so the repository no longer contradicts runtime behavior
