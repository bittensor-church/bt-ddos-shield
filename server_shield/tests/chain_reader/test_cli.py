import base64
from pathlib import Path

from Crypto.PublicKey import ECC

from server_shield.chain_reader.cli import main
from server_shield.shared import state_store
from server_shield.shared.config import get_config
from server_shield.shared.state_store import (
    read_desired_domains,
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

    desired_domains = read_desired_domains(tmp_path)
    manifest = read_manifest(tmp_path)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "skipping chain_reader because root_domain is null" in captured.out
    assert desired_domains.domains["validator-hotkey-1"].domain == "validator-hotkey-1.example.com"
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
    state_store.write_blacklist(tmp_path, ["blacklisted-validator"])

    existing_cert = _valid_public_key_hex()
    new_cert = _valid_public_key_hex()
    blacklisted_cert = _valid_public_key_hex()
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

    desired_domains = read_desired_domains(tmp_path)
    manifest = read_manifest(tmp_path)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert desired_domains.domains["existing-validator"].public_cert == existing_cert
    assert desired_domains.domains["new-validator"].public_cert == new_cert
    assert "blacklisted-validator" not in desired_domains.domains
    assert "missing-cert-validator" not in desired_domains.domains
    assert set(manifest.ddos_shield_manifest.encrypted_url_mapping) == {
        "existing-validator",
        "new-validator",
    }
    assert all(
        base64.b64decode(value)
        for value in manifest.ddos_shield_manifest.encrypted_url_mapping.values()
    )
    assert [call.method for call in patched_subtensor_contact.calls] == ["list_validator_certificates"]
    assert "excluding blacklisted validator blacklisted-validator" in captured.out
    assert "excluding validator missing-cert-validator: missing certificate" in captured.out
    assert "chain_reader reconciled observed=4 kept=0 created=2" in captured.out


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

    desired_domains = read_desired_domains(tmp_path)
    manifest = read_manifest(tmp_path)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert desired_domains.domains["good-validator"].public_cert == good_cert
    assert "malformed-validator" not in desired_domains.domains
    assert set(manifest.ddos_shield_manifest.encrypted_url_mapping) == {"good-validator"}
    assert "excluding validator malformed-validator: malformed certificate payload" in captured.out
    assert "invalid_cert=1" in captured.out
    assert "observed=2" in captured.out
