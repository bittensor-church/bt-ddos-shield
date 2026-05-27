from __future__ import annotations

import json

from bt_ddos_shield_client.manifest import JsonManifestSerializer, get_address_for_validator


VALIDATOR_HOTKEY = "validator-hotkey"
MINER_HOTKEY = "miner-hotkey"
RECEIVER_PRIVATE_KEY_HEX = "00" * 32
PLAINTEXT = "validator-a.shield.example.com:9001"
SERVER_CONTRACT_PAYLOAD_B64 = (
    "iojj3XQJ8ZX9UtstPLpdcspnCb8dlBIb83SIAbQPb1wCAgICAgICAgICAgICAgIC7GnxP0NCwWvPk"
    "VafJ/8lOWa+ll93w315INR2Jz34UyQ/UgyGxcty7En0GY5xs5kNaU30"
)


def test_client_manifest_path_decrypts_server_manifest_encryption_contract_vector() -> None:
    raw_manifest = json.dumps(
        {
            "ddos_shield_manifest": {
                "encrypted_url_mapping": {
                    VALIDATOR_HOTKEY: SERVER_CONTRACT_PAYLOAD_B64,
                }
            }
        }
    ).encode("utf-8")

    manifest = JsonManifestSerializer().deserialize(raw_manifest)

    assert (
        get_address_for_validator(
            manifest,
            VALIDATOR_HOTKEY,
            MINER_HOTKEY,
            RECEIVER_PRIVATE_KEY_HEX,
        )
        == PLAINTEXT
    )
