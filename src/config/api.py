"""API server configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class APIConfig(BaseSettings):
    """API server settings."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    host: str = Field(default="0.0.0.0", alias="api_host")
    port: int = Field(default=8000, ge=1, le=65535, alias="api_port")
    debug: bool = Field(default=False, alias="api_debug")
    reload: bool = Field(default=False, alias="api_reload")

    # Server tuning
    timeout_keep_alive: int = Field(
        default=75,
        ge=5,
        le=600,
        alias="api_timeout_keep_alive",
        description="Seconds to keep idle HTTP connections open (uvicorn --timeout-keep-alive). "
        "Must be higher than the client's keep-alive timeout to avoid socket hang-up race conditions.",
    )

    # SSL/HTTPS Configuration
    enable_https: bool = Field(default=False)
    https_port: int = Field(default=443, ge=1, le=65535)
    ssl_cert_file: str | None = Field(default=None)
    ssl_key_file: str | None = Field(default=None)
    ssl_redirect: bool = Field(default=False)
    ssl_ca_certs: str | None = Field(default=None)

    # CORS Configuration
    enable_cors: bool = Field(default=False)
    cors_origins: list[str] = Field(default_factory=list)

    # Documentation
    enable_docs: bool = Field(default=True)
