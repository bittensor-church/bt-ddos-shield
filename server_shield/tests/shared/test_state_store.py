import json
from pathlib import Path

from server_shield.shared.state_store import (
    ensure_state_files,
    read_desired_domains,
    read_nlb_ip,
    write_desired_domains,
)


def test_ensure_state_files_creates_null_and_empty_defaults(tmp_path: Path) -> None:
    ensure_state_files(tmp_path)

    assert json.loads((tmp_path / "hosted_zone_domain.json").read_text()) == {"domain": None}
    assert json.loads((tmp_path / "nlb_ip.json").read_text()) == {"ip": None}
    assert json.loads((tmp_path / "desired_domains.json").read_text()) == {"domains": []}
    assert json.loads((tmp_path / "blacklist.json").read_text()) == {"domains": []}
    assert json.loads((tmp_path / "manifest.json").read_text()) == {
        "manifest_url": None,
        "encrypted_addresses": [],
    }


def test_round_trip_domain_state_uses_typed_models(tmp_path: Path) -> None:
    ensure_state_files(tmp_path)

    write_desired_domains(tmp_path, ["alpha.example.com", "beta.example.com"])
    desired_domains = read_desired_domains(tmp_path)
    nlb_ip = read_nlb_ip(tmp_path)

    assert desired_domains.domains == ["alpha.example.com", "beta.example.com"]
    assert nlb_ip.ip is None
