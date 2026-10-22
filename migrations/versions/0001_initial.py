from alembic import op
from migrations.schema_v1 import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(op.get_bind())
    op.execute(
        """CREATE FUNCTION immutable_ledger() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'wallet ledger is append only'; END $$"""
    )
    op.execute(
        "CREATE TRIGGER wallet_ledger_immutable BEFORE UPDATE OR DELETE ON wallet_ledger FOR EACH ROW EXECUTE FUNCTION immutable_ledger()"
    )


def downgrade():
    op.execute("DROP TRIGGER wallet_ledger_immutable ON wallet_ledger")
    op.execute("DROP FUNCTION immutable_ledger()")
    Base.metadata.drop_all(op.get_bind())
