"""Runtime configuration. Secrets stay in the process environment."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPSPILOT_",
        env_file=".env",
        extra="ignore",
    )

    env: str = "local"
    auth_mode: str = "local_synthetic"
    data_dir: Path = Path("./data")
    seed: bool = True
    support_mailbox: str = "servicedesk@northstar.example"
    company_timezone: str = "Europe/London"
    allow_local_approval_simulation: bool = True
    teams_webhook_url: str = ""
    graph_base_url: str = "https://graph.microsoft.com/v1.0"
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_redirect_uri: str = "http://localhost:8090/auth/callback"
    public_app_url: str = "http://localhost:5173"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "opspilot.db"

    @property
    def entra_configured(self) -> bool:
        return bool(self.azure_tenant_id.strip() and self.azure_client_id.strip())

    @property
    def teams_configured(self) -> bool:
        return bool(self.teams_webhook_url.strip())
