from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from packages.common.db import engine


def test_migration_roundtrip():
    assert engine.url.database.endswith("_test")
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    assert "jobs" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    assert {"users", "tenant_memberships", "jobs", "job_requests", "wallet_ledger", "model_prices"} <= set(
        inspect(engine).get_table_names()
    )
