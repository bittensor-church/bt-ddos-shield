import json
from pathlib import Path

from server_shield.shared import state_store
from server_shield.shared.state_store import ensure_state_files, read_desired_domains, read_nlb_ip, write_desired_domains


def _write_example_files(example_dir: Path) -> None:
    example_dir.mkdir(parents=True, exist_ok=True)
    (example_dir / "hosted_zone_domain.example.json").write_text('{"domain": null}\n')
    (example_dir / "nlb_ip.example.json").write_text('{"ip": null}\n')
    (example_dir / "desired_domains.example.json").write_text('{"domains": []}\n')
    (example_dir / "blacklist.example.json").write_text('{"domains": []}\n')
    (
        example_dir / "manifest.example.json"
    ).write_text('{"manifest_url": null, "encrypted_addresses": []}\n')


def test_ensure_state_files_creates_null_and_empty_defaults(tmp_path: Path, monkeypatch) -> None:
    example_dir = tmp_path / "examples"
    runtime_dir = tmp_path / "runtime"
    _write_example_files(example_dir)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", example_dir)
    ensure_state_files(runtime_dir)

    assert json.loads((runtime_dir / "hosted_zone_domain.json").read_text()) == {"domain": None}
    assert json.loads((runtime_dir / "nlb_ip.json").read_text()) == {"ip": None}
    assert json.loads((runtime_dir / "desired_domains.json").read_text()) == {"domains": []}
    assert json.loads((runtime_dir / "blacklist.json").read_text()) == {"domains": []}
    assert json.loads((runtime_dir / "manifest.json").read_text()) == {
        "manifest_url": None,
        "encrypted_addresses": [],
    }


def test_round_trip_domain_state_uses_typed_models(tmp_path: Path, monkeypatch) -> None:
    example_dir = tmp_path / "examples"
    runtime_dir = tmp_path / "runtime"
    _write_example_files(example_dir)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", example_dir)
    ensure_state_files(runtime_dir)

    write_desired_domains(runtime_dir, ["alpha.example.com", "beta.example.com"])
    desired_domains = read_desired_domains(runtime_dir)
    nlb_ip = read_nlb_ip(runtime_dir)

    assert desired_domains.domains == ["alpha.example.com", "beta.example.com"]
    assert nlb_ip.ip is None


def test_read_copies_example_file_when_runtime_state_missing(tmp_path: Path, monkeypatch) -> None:
    example_dir = tmp_path / "examples"
    runtime_dir = tmp_path / "runtime"
    _write_example_files(example_dir)
    (example_dir / "nlb_ip.example.json").write_text('{"ip": "7.7.7.7"}\n')
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", example_dir)

    nlb_ip = read_nlb_ip(runtime_dir)

    assert nlb_ip.ip == "7.7.7.7"
    assert (runtime_dir / "nlb_ip.json").read_text() == (example_dir / "nlb_ip.example.json").read_text()


def test_read_uses_default_state_dir_when_state_dir_not_provided(tmp_path: Path, monkeypatch) -> None:
    _write_example_files(tmp_path)
    monkeypatch.setattr(state_store, "DEFAULT_STATE_DIR", tmp_path)

    desired_domains = read_desired_domains()

    assert desired_domains.domains == []
    assert (tmp_path / "desired_domains.json").exists()
