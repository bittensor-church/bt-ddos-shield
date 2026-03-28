from pathlib import Path

from server_shield.shared.config import get_config


def test_get_config_reads_nested_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SERVER_SHIELD_ENV", "test")
    monkeypatch.setenv("SERVER_SHIELD_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("SERVER_SHIELD_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__AWS_REGION", "eu-north-1")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__HOSTED_ZONE_ID", "Z123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__MINER_INSTANCE_ID", "i-123")
    monkeypatch.setenv("SERVER_SHIELD_PULUMI__MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_READER__SUBTENSOR_ADDRESS", "ws://reader")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_READER__NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__SUBTENSOR_ADDRESS", "ws://writer")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__NETUID", "12")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__MINER_PORT", "9001")
    monkeypatch.setenv("SERVER_SHIELD_CHAIN_WRITER__WALLET_NAME", "miner")

    get_config.cache_clear()
    config = get_config()

    assert config.env == "test"
    assert config.state_dir == tmp_path / "state"
    assert config.pulumi.aws_region == "eu-north-1"
    assert config.chain_reader.netuid == 12
    assert config.chain_writer.wallet_name == "miner"
