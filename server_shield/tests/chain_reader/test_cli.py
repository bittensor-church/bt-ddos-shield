import base64
import json
from pathlib import Path
import re

from Crypto.PublicKey import ECC

from server_shield.chain_reader.cli import main
from server_shield.shared import state_store
from server_shield.shared.config import get_config
from server_shield.shared.state_store import (
    read_manifest,
    write_desired_domains,
    write_root_domain,
)
from server_shield.subtensor_contact import (
    AbstractSubtensorContact,
    MockSubtensorContact,
    ValidatorCertificateRecord,
    subtensor_contact,
)


def test_subtensor_contact_types_are_importable() -> None:
    assert callable(subtensor_contact)
    assert issubclass(MockSubtensorContact, AbstractSubtensorContact)


def _write_example_files(example_dir: Path) -> None:
    example_dir.mkdir(parents=True, exist_ok=True)
    (example_dir / "root_domain.example.json").write_text('{\n    "domain": null\n}\n')
    (example_dir / "axon_public_ip.example.json").write_text('{\n    "ip": null\n}\n')
    (example_dir / "desired_domains.example.json").write_text('{\n    "domains": {}\n}\n')
    (example_dir / "blacklist.example.json").write_text('[]\n')
    (example_dir / "manifest.example.json").write_text(
        '{\n'
        '    "ddos_shield_manifest": {\n'
        '        "encrypted_url_mapping": {}\n'
        '    }\n'
        '}\n'
    )


def _set_required_env(monkeypatch) -> None:
    get_config.cache_clear()
    monkeypatch.setenv("SERVER_SHIELD_MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_SUBTENSOR_ADDRESS", "ws://subtensor")
    monkeypatch.setenv("SERVER_SHIELD_NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__BACKEND_URL", "file:///tmp/server-shield-test-state")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__SHIELD_BACKEND", "AWS")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY", "miner-hotkey")


def _valid_public_key_hex() -> str:
    return ECC.generate(curve="ed25519").public_key().export_key(format="raw").hex()


class MatchesRegex:
    def __init__(self, pattern: str) -> None:
        self._pattern = re.compile(pattern)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, str) and self._pattern.fullmatch(other) is not None

    def __repr__(self) -> str:
        return f"MatchesRegex({self._pattern.pattern!r})"


def _generated_domain(hotkey: str, root_domain: str) -> MatchesRegex:
    return MatchesRegex(rf"{re.escape(hotkey[:8])}-[0-9a-f]{{12}}\.{re.escape(root_domain)}")


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def test_chain_reader_main_skips_when_root_domain_missing(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    _set_required_env(monkeypatch)
    write_desired_domains(
        tmp_path,
        {
            "validator-hotkey-1": {
                "domain": "validator-hotkey-1.example.com",
                "public_cert": _valid_public_key_hex(),
            }
        },
    )

    exit_code = main()

    desired_domains = _read_json(tmp_path / "desired_domains.json")
    manifest = read_manifest(tmp_path)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "skipping chain_reader because root_domain is null" in captured.out
    assert desired_domains == {
        "domains": {
            "validator-hotkey-1": {
                "domain": "validator-hotkey-1.example.com",
                "public_cert": MatchesRegex(r"[0-9a-f]{64}"),
            }
        }
    }
    assert manifest.ddos_shield_manifest.encrypted_url_mapping == {}


def test_chain_reader_main_reconciles_domains_from_contact(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    _set_required_env(monkeypatch)
    write_root_domain(tmp_path, "shield.example.com")
    existing_cert = _valid_public_key_hex()
    new_cert = _valid_public_key_hex()
    cert_rotated_cert = _valid_public_key_hex()
    root_rotated_cert = _valid_public_key_hex()
    blacklisted_cert = _valid_public_key_hex()
    write_desired_domains(
        tmp_path,
        {
            "existing-validator": {
                "domain": "existing-validator.shield.example.com",
                "public_cert": existing_cert,
            },
            "cert-rotated-validator": {
                "domain": "cert-rotated-validator.shield.example.com",
                "public_cert": "old-cert",
            },
            "root-rotated-validator": {
                "domain": "root-rotated-validator.old.example.com",
                "public_cert": root_rotated_cert,
            },
            "removed-validator": {
                "domain": "removed-validator.shield.example.com",
                "public_cert": "removed-cert",
            },
        },
    )
    state_store.write_blacklist(tmp_path, ["blacklisted-validator"])
    patched_subtensor_contact.set_validator_certificates(
        [
            ValidatorCertificateRecord(
                hotkey="existing-validator",
                certificate_payload={"public_key": [existing_cert]},
            ),
            ValidatorCertificateRecord(
                hotkey="new-validator",
                certificate_payload={"public_key": [new_cert]},
            ),
            ValidatorCertificateRecord(
                hotkey="cert-rotated-validator",
                certificate_payload={"public_key": [cert_rotated_cert]},
            ),
            ValidatorCertificateRecord(
                hotkey="root-rotated-validator",
                certificate_payload={"public_key": [root_rotated_cert]},
            ),
            ValidatorCertificateRecord(
                hotkey="blacklisted-validator",
                certificate_payload={"public_key": [blacklisted_cert]},
            ),
            ValidatorCertificateRecord(
                hotkey="missing-cert-validator",
                certificate_payload=None,
            ),
        ]
    )

    exit_code = main()

    desired_domains_json = _read_json(tmp_path / "desired_domains.json")
    manifest = read_manifest(tmp_path)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert desired_domains_json == {
        "domains": {
            "cert-rotated-validator": {
                "domain": _generated_domain("cert-rotated-validator", "shield.example.com"),
                "public_cert": cert_rotated_cert,
            },
            "existing-validator": {
                "domain": "existing-validator.shield.example.com",
                "public_cert": existing_cert,
            },
            "new-validator": {
                "domain": _generated_domain("new-validator", "shield.example.com"),
                "public_cert": new_cert,
            },
            "root-rotated-validator": {
                "domain": _generated_domain("root-rotated-validator", "shield.example.com"),
                "public_cert": root_rotated_cert,
            },
        }
    }
    assert set(manifest.ddos_shield_manifest.encrypted_url_mapping) == {
        "cert-rotated-validator",
        "existing-validator",
        "new-validator",
        "root-rotated-validator",
    }
    assert all(
        base64.b64decode(value)
        for value in manifest.ddos_shield_manifest.encrypted_url_mapping.values()
    )
    assert [call.method for call in patched_subtensor_contact.calls] == ["list_validator_certificates"]
    assert "excluding blacklisted validator blacklisted-validator" in captured.out
    assert "excluding validator missing-cert-validator: missing certificate" in captured.out
    assert (
        "chain_reader reconciled observed=6 kept=1 created=1 "
        "rotated_for_cert=1 rotated_for_root_domain=1 removed=1 "
        "blacklisted=1 invalid_cert=1 manifest_entries=4"
    ) in captured.out


def test_chain_reader_main_returns_one_when_contact_raises(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    _set_required_env(monkeypatch)
    write_root_domain(tmp_path, "shield.example.com")
    patched_subtensor_contact.set_validator_certificates([], exception=RuntimeError("boom"))

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "RuntimeError: boom" in captured.err


def test_chain_reader_main_keeps_valid_results_when_one_certificate_payload_is_malformed(
    tmp_path: Path,
    capsys,
    monkeypatch,
    patched_subtensor_contact: MockSubtensorContact,
) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    _set_required_env(monkeypatch)
    write_root_domain(tmp_path, "shield.example.com")
    good_cert = _valid_public_key_hex()
    patched_subtensor_contact.set_validator_certificates(
        [
            ValidatorCertificateRecord(
                hotkey="good-validator",
                certificate_payload={"public_key": [good_cert]},
            ),
            ValidatorCertificateRecord(
                hotkey="malformed-validator",
                certificate_payload={"public_key": []},
            ),
        ]
    )

    exit_code = main()

    manifest = read_manifest(tmp_path)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert _read_json(tmp_path / "desired_domains.json") == {
        "domains": {
            "good-validator": {
                "domain": _generated_domain("good-validator", "shield.example.com"),
                "public_cert": good_cert,
            }
        }
    }
    assert set(manifest.ddos_shield_manifest.encrypted_url_mapping) == {"good-validator"}
    assert "excluding validator malformed-validator: malformed certificate payload" in captured.out
    assert "invalid_cert=1" in captured.out
    assert "observed=2" in captured.out
