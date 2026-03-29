from functools import lru_cache
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class AwsShieldSettings(BaseModel):
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    hosted_zone_id: str
    miner_instance_id: str


class PulumiSettings(BaseModel):
    backend_url: str
    stack_name: str = "server-shield"
    shield_backend: Literal["AWS"]
    aws: AwsShieldSettings


class ChainReaderSettings(BaseModel):
    subtensor_address: str = ""
    netuid: int = 0


class ChainWriterSettings(BaseModel):
    wallet_name: str = ""
    subtensor_address: str = ""
    netuid: int = 0


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SERVER_SHIELD_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    env: str = "dev"
    log_level: str = "INFO"
    sentry_dsn: str | None = None
    miner_port: int
    pulumi: PulumiSettings
    chain_reader: ChainReaderSettings = ChainReaderSettings()
    chain_writer: ChainWriterSettings = ChainWriterSettings()


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig()
