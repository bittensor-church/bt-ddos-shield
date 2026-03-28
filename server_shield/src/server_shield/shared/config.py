from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class PulumiSettings(BaseModel):
    aws_region: str
    hosted_zone_id: str
    miner_instance_id: str
    miner_port: int


class ChainReaderSettings(BaseModel):
    subtensor_address: str = ""
    netuid: int = 0


class ChainWriterSettings(BaseModel):
    wallet_name: str = ""
    subtensor_address: str = ""
    netuid: int = 0
    miner_port: int = 0


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SERVER_SHIELD_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    env: str = "dev"
    log_level: str = "INFO"
    sentry_dsn: str | None = None
    state_dir: Path = Path("state")
    pulumi: PulumiSettings
    chain_reader: ChainReaderSettings = ChainReaderSettings()
    chain_writer: ChainWriterSettings = ChainWriterSettings()


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig()
