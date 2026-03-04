from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.db import engine


def run_db_bootstrap() -> None:
    cfg = Config("alembic.ini")
    inspector = inspect(engine)

    has_alembic_version = inspector.has_table("alembic_version")
    has_legacy_schema = inspector.has_table("tenants")

    if not has_alembic_version and has_legacy_schema:
        command.stamp(cfg, "0001_initial")
        command.upgrade(cfg, "head")
        return

    command.upgrade(cfg, "head")


if __name__ == "__main__":
    run_db_bootstrap()
