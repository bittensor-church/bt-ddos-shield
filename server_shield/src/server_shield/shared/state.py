from pydantic import BaseModel, Field


class HostedZoneDomainState(BaseModel):
    domain: str | None = None


class NlbIpState(BaseModel):
    ip: str | None = None


class DesiredDomainsState(BaseModel):
    domains: list[str] = Field(default_factory=list)


class BlacklistState(BaseModel):
    domains: list[str] = Field(default_factory=list)


class ManifestState(BaseModel):
    manifest_url: str | None = None
    encrypted_addresses: list[str] = Field(default_factory=list)
