from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "odoo-core-svc"
    database_url: str = "sqlite+pysqlite:///./odoo.db"
    redis_url: str = "redis://localhost:6379/0"
    credential_encryption_key: str = "replace-me-with-32-byte-key-material"
    auto_create_tables: bool = False
    core_public_base_url: str = "http://localhost:8000"
    shopify_client_id: str = ""
    shopify_client_secret: str = ""
    shopify_scopes: str = "read_products,write_products,read_orders,write_fulfillments,read_all_orders"


@lru_cache
def get_settings() -> Settings:
    return Settings()
