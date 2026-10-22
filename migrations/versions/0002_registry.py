from alembic import op
from sqlalchemy import inspect
from packages.common.db import ModelVersion, ModelPrice

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    ModelVersion.__table__.create(bind, checkfirst=True)
    ModelPrice.__table__.create(bind, checkfirst=True)
    columns = {c["name"] for c in inspect(bind).get_columns("job_requests")}
    if "model_revision" not in columns:
        op.execute("ALTER TABLE job_requests ADD COLUMN model_revision varchar NOT NULL DEFAULT 'mock-v1'")
        op.execute("ALTER TABLE job_requests ADD COLUMN price_id varchar REFERENCES model_prices(id)")
    if "provider_instance_id" not in {c["name"] for c in inspect(bind).get_columns("worker_nodes")}:
        op.execute("ALTER TABLE worker_nodes ADD COLUMN provider_instance_id varchar")
    if "terminated_at" not in {c["name"] for c in inspect(bind).get_columns("provider_instances")}:
        op.execute("ALTER TABLE provider_instances ADD COLUMN terminated_at timestamptz")
    op.execute(
        "CREATE TRIGGER model_prices_immutable BEFORE UPDATE OR DELETE ON model_prices FOR EACH ROW EXECUTE FUNCTION immutable_ledger()"
    )


def downgrade():
    op.execute("DROP TRIGGER model_prices_immutable ON model_prices")
    op.execute("ALTER TABLE job_requests DROP COLUMN price_id")
    op.execute("ALTER TABLE job_requests DROP COLUMN model_revision")
    op.execute("ALTER TABLE worker_nodes DROP COLUMN provider_instance_id")
    op.execute("ALTER TABLE provider_instances DROP COLUMN terminated_at")
    ModelPrice.__table__.drop(op.get_bind())
    ModelVersion.__table__.drop(op.get_bind())
