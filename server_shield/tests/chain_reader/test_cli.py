from pathlib import Path
import os
import subprocess
from types import SimpleNamespace

from server_shield.chain_reader.chain import ValidatorOnChain
from server_shield.chain_reader.cli import _run_once, main
from server_shield.shared import state_store
from server_shield.shared.state_store import read_desired_domains, read_root_domain, write_desired_domains, write_root_domain


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


def test_chain_reader_skips_when_root_domain_missing(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    write_desired_domains(
        tmp_path,
        {
            "validator-hotkey-1": {
                "domain": "validator-hotkey-1.example.com",
                "public_cert": "cert-a",
            }
        },
    )
    exit_code = _run_once()
    root_domain = read_root_domain(tmp_path)
    desired_domains = read_desired_domains(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert root_domain.domain is None
    assert "skipping chain_reader because root_domain is null" in captured.out
    assert desired_domains.domains["validator-hotkey-1"].domain == "validator-hotkey-1.example.com"


def test_chain_reader_reconciles_domains_from_chain_view(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)
    write_root_domain(tmp_path, "shield.example.com")
    write_desired_domains(
        tmp_path,
        {
            "existing-validator": {
                "domain": "existing-validator.shield.example.com",
                "public_cert": "cert-a",
            },
            "removed-validator": {
                "domain": "removed-validator.shield.example.com",
                "public_cert": "cert-old",
            },
        },
    )
    state_store.write_blacklist(tmp_path, ["blacklisted-validator"])
    monkeypatch.setattr(
        "server_shield.chain_reader.cli.get_config",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "server_shield.chain_reader.cli.fetch_validators_with_certs",
        lambda _config: [
            ValidatorOnChain("existing-validator", "cert-a"),
            ValidatorOnChain("new-validator", "cert-b"),
            ValidatorOnChain("blacklisted-validator", "cert-c"),
            ValidatorOnChain("missing-cert-validator", None, "missing certificate"),
        ],
    )

    exit_code = _run_once()
    desired_domains = read_desired_domains(tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert desired_domains.domains["existing-validator"].domain == "existing-validator.shield.example.com"
    assert desired_domains.domains["existing-validator"].public_cert == "cert-a"
    assert desired_domains.domains["new-validator"].public_cert == "cert-b"
    assert desired_domains.domains["new-validator"].domain.startswith("new-vali-")
    assert desired_domains.domains["new-validator"].domain.endswith(".shield.example.com")
    assert "removed-validator" not in desired_domains.domains
    assert "blacklisted-validator" not in desired_domains.domains
    assert "missing-cert-validator" not in desired_domains.domains
    assert "excluding blacklisted validator blacklisted-validator" in captured.out
    assert "excluding validator missing-cert-validator: missing certificate" in captured.out
    assert "chain_reader reconciled observed=4 kept=1 created=1" in captured.out


def test_chain_reader_module_execution_runs_main(tmp_path: Path) -> None:
    completed = subprocess.run(
        [".venv/bin/python", "-m", "server_shield.chain_reader.cli"],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "SERVER_SHIELD_STATE_DIR": str(tmp_path),
            "SERVER_SHIELD_SUBTENSOR_ADDRESS": "ws://subtensor",
            "SERVER_SHIELD_NETUID": "12",
            "SERVER_SHIELD_PULUMI__BACKEND_URL": "file:///tmp/server-shield-test-state",
            "SERVER_SHIELD_PULUMI__SHIELD_BACKEND": "AWS",
            "SERVER_SHIELD_MINER_PORT": "9001",
            "SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID": "key",
            "SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY": "secret",
            "SERVER_SHIELD_PULUMI__AWS__AWS_REGION": "eu-north-1",
            "SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID": "Z123",
            "SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID": "i-123",
            "SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME": "miner",
            "SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY": "miner-hotkey",
        },
    )

    assert completed.returncode == 0
    assert "skipping chain_reader because root_domain is null" in completed.stdout


def test_chain_reader_main_does_not_require_state_dir(monkeypatch) -> None:
    monkeypatch.setattr(
        "server_shield.chain_reader.cli.get_config",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "server_shield.chain_reader.cli._run_once",
        lambda: 0,
    )
    monkeypatch.setattr(
        "server_shield.chain_reader.cli.run_component",
        lambda component_name, fn: fn(),
    )

    assert main() == 0
