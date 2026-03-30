import json
from pathlib import Path

from server_shield.shared import state_store
from server_shield.shared.state_store import (
    ensure_state_files,
    read_axon_public_ip,
    read_desired_domains,
    write_desired_domains,
)


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


def test_ensure_state_files_creates_null_and_empty_defaults(tmp_path: Path, monkeypatch) -> None:
    example_dir = tmp_path / "examples"
    runtime_dir = tmp_path / "runtime"
    _write_example_files(example_dir)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", example_dir)
    ensure_state_files(runtime_dir)

    assert json.loads((runtime_dir / "root_domain.json").read_text()) == {"domain": None}
    assert json.loads((runtime_dir / "axon_public_ip.json").read_text()) == {"ip": None}
    assert json.loads((runtime_dir / "desired_domains.json").read_text()) == {"domains": {}}
    assert json.loads((runtime_dir / "blacklist.json").read_text()) == []
    assert json.loads((runtime_dir / "manifest.json").read_text()) == {
        "ddos_shield_manifest": {
            "encrypted_url_mapping": {},
        },
    }
    assert (runtime_dir / "root_domain.json").read_text() == '{\n    "domain": null\n}\n'


def test_round_trip_domain_state_uses_typed_models(tmp_path: Path, monkeypatch) -> None:
    example_dir = tmp_path / "examples"
    runtime_dir = tmp_path / "runtime"
    _write_example_files(example_dir)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", example_dir)
    ensure_state_files(runtime_dir)

    write_desired_domains(
        runtime_dir,
        {
            "validator-hotkey-1": {
                "domain": "alpha.example.com",
                "public_cert": "cert-a",
            },
            "validator-hotkey-2": {
                "domain": "beta.example.com",
                "public_cert": "cert-b",
            },
        },
    )
    desired_domains = read_desired_domains(runtime_dir)
    axon_public_ip = read_axon_public_ip(runtime_dir)

    assert desired_domains.domains["validator-hotkey-1"].domain == "alpha.example.com"
    assert desired_domains.domains["validator-hotkey-1"].public_cert == "cert-a"
    assert desired_domains.domains["validator-hotkey-2"].domain == "beta.example.com"
    assert desired_domains.domains["validator-hotkey-2"].public_cert == "cert-b"
    assert axon_public_ip.ip is None
    assert (runtime_dir / "desired_domains.json").read_text().startswith('{\n    "domains": {')


def test_read_copies_example_file_when_runtime_state_missing(tmp_path: Path, monkeypatch) -> None:
    example_dir = tmp_path / "examples"
    runtime_dir = tmp_path / "runtime"
    _write_example_files(example_dir)
    (example_dir / "axon_public_ip.example.json").write_text('{"ip": "7.7.7.7"}\n')
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", example_dir)

    axon_public_ip = read_axon_public_ip(runtime_dir)

    assert axon_public_ip.ip == "7.7.7.7"
    assert (runtime_dir / "axon_public_ip.json").read_text() == (
        example_dir / "axon_public_ip.example.json"
    ).read_text()


def test_read_uses_default_state_dir_when_state_dir_not_provided(tmp_path: Path, monkeypatch) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)

    desired_domains = read_desired_domains()

    assert desired_domains.domains == {}
    assert (tmp_path / "desired_domains.json").exists()


def test_blacklist_round_trip_uses_validator_hotkey_list(tmp_path: Path, monkeypatch) -> None:
    example_dir = tmp_path / "examples"
    runtime_dir = tmp_path / "runtime"
    _write_example_files(example_dir)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", example_dir)
    ensure_state_files(runtime_dir)

    state_store.write_blacklist(runtime_dir, ["validator-hotkey-1", "validator-hotkey-2"])
    blacklist = state_store.read_blacklist(runtime_dir)

    assert json.loads((runtime_dir / "blacklist.json").read_text()) == [
        "validator-hotkey-1",
        "validator-hotkey-2",
    ]
    assert blacklist.root == ["validator-hotkey-1", "validator-hotkey-2"]
