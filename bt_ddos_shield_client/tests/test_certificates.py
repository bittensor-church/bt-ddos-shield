from __future__ import annotations

from bt_ddos_shield_client.certificates import CertificateAlgorithmEnum, EDDSACertificateManager
from tests.library.fixtures import certificate_fixture_path, load_certificate_fixture


def test_existing_validator_a_fixture_derives_same_public_key() -> None:
    certificate = load_certificate_fixture("validator_a.pem")

    assert certificate.algorithm == CertificateAlgorithmEnum.ED25519
    assert certificate.private_key == "7cf7e2b11ba0f81baca37cc82212b30c193e201204d66f854a4d1ce9cbfa3f47"
    assert certificate.public_key == "3c61650569101a52bf8af49213af793b3bc8b4e6be21c75b09c016116bed46db"


def test_existing_validator_b_fixture_derives_same_public_key() -> None:
    certificate = load_certificate_fixture("validator_b.pem")

    assert certificate.algorithm == CertificateAlgorithmEnum.ED25519
    assert certificate.private_key == "bc598f2d8d0be93a71c64c9f36b91d4c4dd343521bd25ad4de16d8d1a1fc6ebf"
    assert certificate.public_key == "38a691a4cb6d28b6985ed3d75fff2555867ab0a980d94f03a660b7bbe4fe1e2a"


def test_generate_save_and_load_certificate_preserves_keys(tmp_path) -> None:
    certificate = EDDSACertificateManager.generate_certificate()
    path = tmp_path / "validator.cert.pem"

    EDDSACertificateManager.save_certificate(certificate, str(path))
    loaded = EDDSACertificateManager.load_certificate(str(path))

    assert loaded == certificate


def test_load_certificate_accepts_existing_pem_fixture() -> None:
    certificate = EDDSACertificateManager.load_certificate(str(certificate_fixture_path("validator_a.pem")))

    assert certificate.public_key == "3c61650569101a52bf8af49213af793b3bc8b4e6be21c75b09c016116bed46db"
