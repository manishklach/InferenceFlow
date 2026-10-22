from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
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


def test_upgrade_preserves_legacy_reversal_debt():
    import pytest
    from packages.common.db import Session, Wallet
    from packages.common.service import reconcile

    config = Config("alembic.ini")
    command.downgrade(config, "0004")
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tenants (id, subject, frozen) VALUES ('legacy', 'legacy', true)"))
            connection.execute(text("INSERT INTO wallets (tenant_id, available, reserved) VALUES ('legacy', 0, 0)"))
            connection.execute(
                text("""INSERT INTO payment_events (id, tenant_id, intent, amount, reversed_amount)
                                   VALUES ('payment', 'legacy', 'intent', 100, 100)""")
            )
            connection.execute(
                text("""INSERT INTO audit_events (id, kind, reference, created_at)
                                   VALUES ('reversal', 'reversal_debt', 'payment:25', now())""")
            )
    finally:
        command.upgrade(config, "head")
    with Session.begin() as session:
        assert session.get(Wallet, "legacy").debt == 25
        assert reconcile(session) == []
    with pytest.raises(RuntimeError, match="financial liability history"):
        command.downgrade(config, "0004")
