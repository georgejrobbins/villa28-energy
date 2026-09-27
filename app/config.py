from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_project_id: str = ""  # Legacy alias for Device Access project ID
    google_device_access_project_id: str = ""
    google_pubsub_subscription: str = ""
    google_service_account_json: str = ""
    encryption_key: str = ""
    dashboard_username: str = "owner"
    dashboard_password: str = ""
    polling_interval_seconds: int = Field(default=300, ge=30)
    environment: str = "production"
    log_level: str = "INFO"
    railway_public_domain: str = ""
    public_base_url: str = ""
    background_tasks_enabled: bool = True

    @property
    def device_access_project_id(self):
        return self.google_device_access_project_id or self.google_project_id

    @property
    def base_url(self):
        return (self.public_base_url or (f"https://{self.railway_public_domain}" if self.railway_public_domain else "http://localhost:8000")).rstrip("/")

    @property
    def google_callback_url(self):
        return self.base_url + "/auth/google/callback"

    @property
    def sungrow_callback_url(self):
        return self.base_url + "/auth/sungrow/callback"

    @property
    def google_configured(self):
        values = (self.google_client_id, self.google_client_secret, self.device_access_project_id)
        return all(v and not v.startswith("your-") for v in values)

@lru_cache()
def get_settings():
    return Settings()
