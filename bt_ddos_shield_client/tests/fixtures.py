from __future__ import annotations

from pathlib import Path

from bt_ddos_shield_client.certificates import Certificate, EDDSACertificateManager


FIXTURES_DIR = Path(__file__).parent / 'fixtures' / 'certs'


def certificate_fixture_path(filename: str) -> Path:
    return FIXTURES_DIR / filename


def load_certificate_fixture(filename: str) -> Certificate:
    return EDDSACertificateManager.load_certificate(str(certificate_fixture_path(filename)))
