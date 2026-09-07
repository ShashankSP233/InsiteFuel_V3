from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "InsiteFuel V3"
    debug: bool = True
    database_url: str

    sounding_deadline_hour: int = 6
    sounding_deadline_minute: int = 0

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "ChangeMe@2026!"
    bootstrap_admin_name: str = "System Administrator"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
