from __future__ import annotations

import importlib


def test_core_submodules_import_without_loading_public_wrappers() -> None:
    encryption = importlib.import_module("bt_ddos_shield_client.encryption")
    certificates = importlib.import_module("bt_ddos_shield_client.certificates")

    assert encryption.ECIESEncryptionManager
    assert certificates.EDDSACertificateManager
