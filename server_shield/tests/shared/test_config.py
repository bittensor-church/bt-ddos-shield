from pathlib import Path

import pytest
from pydantic import ValidationError

from server_shield.shared.config import get_config


def test_get_config_reads_provider_scoped_pulumi_settings(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SERVER_SHIELD_ENV", "test")
    monkeypatch.setenv("SERVER_SHIELD_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("SERVER_SHIELD_MINER_PORT", "9001")
    monkeypatch.setenv(
        "SERVER_SHIELD_PULUMI__BACKEND_URL",
        "file:///var/lib/server-shield/pulumi-state",
    )
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__STACK_NAME", "server-shield")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__SHIELD_BACKEND", "AWS")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_SUBTENSOR_ADDRESS", "ws://reader")
    monkeypatch.setenv("SERVER_SHIELD_NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY", "miner-hotkey")

    get_config.cache_clear()
    config = get_config()

    assert config.miner_port == 9001
    assert config.pulumi.backend_url == "file:///var/lib/server-shield/pulumi-state"
    assert config.pulumi.stack_name == "server-shield"
    assert config.pulumi.shield_backend == "AWS"
    assert config.pulumi.aws.aws_access_key_id == "key"
    assert config.pulumi.aws.aws_secret_access_key == "secret"
    assert config.pulumi.aws.aws_region == "eu-north-1"
    assert config.pulumi.aws.hosted_zone_id == "Z123"
    assert config.pulumi.aws.miner_instance_id == "i-123"
    assert config.subtensor_address == "ws://reader"
    assert config.netuid == 12
    assert config.chain_writer.wallet_name == "miner"
    assert config.chain_writer.wallet_hotkey == "miner-hotkey"


def test_get_config_requires_provider_scoped_pulumi_backend(monkeypatch) -> None:
    monkeypatch.setenv("SERVER_SHIELD_MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_SUBTENSOR_ADDRESS", "ws://reader")
    monkeypatch.setenv("SERVER_SHIELD_NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY", "miner-hotkey")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__BACKEND_URL", "file:///var/lib/server-shield/pulumi-state")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID", "i-123")
    monkeypatch.delenv("SERVER_SHIELD_PULUMI__SHIELD_BACKEND", raising=False)

    get_config.cache_clear()

    with pytest.raises(ValidationError):
        get_config()


def test_get_config_requires_top_level_chain_settings(monkeypatch) -> None:
    monkeypatch.setenv("SERVER_SHIELD_MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__BACKEND_URL", "file:///var/lib/server-shield/pulumi-state")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__SHIELD_BACKEND", "AWS")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS__MINER_INSTANCE_ID", "i-123")
    monkeypatch.delenv("SERVER_SHIELD_SUBTENSOR_ADDRESS", raising=False)
    monkeypatch.delenv("SERVER_SHIELD_NETUID", raising=False)
    monkeypatch.delenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", raising=False)
    monkeypatch.delenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_HOTKEY", raising=False)

    get_config.cache_clear()

    with pytest.raises(ValidationError):
        get_config()
