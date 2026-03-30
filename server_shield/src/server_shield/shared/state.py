from pydantic import BaseModel, Field, RootModel


class RootDomainState(BaseModel):
    domain: str | None = None


class AxonPublicIpState(BaseModel):
    ip: str | None = None


class DesiredDomainEntry(BaseModel):
    domain: str
    public_cert: str


class DesiredDomainsState(BaseModel):
    domains: dict[str, DesiredDomainEntry] = Field(default_factory=dict)


class BlacklistState(RootModel[list[str]]):
    root: list[str] = Field(default_factory=list)


class ManifestState(BaseModel):
    manifest_url: str | None = None
    encrypted_addresses: list[str] = Field(default_factory=list)
