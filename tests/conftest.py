import tests.environment  # noqa: F401 -- isolate DB before application imports
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient
from packages.common.db import Session, engine
from packages.common.service import account, new_key, lock_wallet, post
from apps.api.main import app


@pytest.fixture(scope="session", autouse=True)
def migrate_test_database():
    from alembic import command
    from alembic.config import Config

    assert engine.url.database.endswith("_test")
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def clean(migrate_test_database):
    # Dedicated test database only. Never run this against production data.
    with engine.begin() as c:
        names = (
            c.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename != 'alembic_version'")
            )
            .scalars()
            .all()
        )
        if names:
            c.execute(text("TRUNCATE " + ",".join('"' + n + '"' for n in names) + " CASCADE"))


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def tenant():
    with Session.begin() as s:
        t = account(s, "test:a")
        key = new_key(s, t.id, "test")["key"]
        w = lock_wallet(s, t.id)
        post(s, w, "test:seed", "topup", 10000000, 0)
        return t.id, key


@pytest.fixture
def headers(tenant):
    return {"Authorization": "Bearer " + tenant[1], "Idempotency-Key": "test-key"}
