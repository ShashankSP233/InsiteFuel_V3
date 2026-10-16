from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "InsiteFuel V3"
    debug: bool = True

    database_url: str = "postgresql+psycopg://postgres:root@localhost:5432/insitefuel_v3"

    # --- IoT shift-data ingestion -------------------------------------
    # Shared secret the vendor sends in the X-API-Key header.  When empty,
    # the ingestion endpoint is disabled (503).
    iot_api_key: str = ""
    # Username of the system account that owns IoT-created records.
    iot_service_username: str = "iot-integration"
    # IoT shifts are closed automatically this long after their data arrived.
    iot_shift_auto_close_hours: int = 11
    # Post the vendor's per-engine "refill" / "drain" into the fuel ledger.
    iot_post_refills_to_ledger: bool = True
    # How often the background sweeper looks for IoT shifts due to close.
    iot_auto_close_check_seconds: int = 300

    sounding_deadline_hour: int = 6
    sounding_deadline_minute: int = 0

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "ChangeMe@2026!"
    bootstrap_admin_name: str = "System Administrator"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="INSITEFUEL_",
    )


settings = Settings()