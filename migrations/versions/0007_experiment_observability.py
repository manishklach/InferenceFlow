"""Additive first-dispatch timing and single-use live worker probes."""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    for table, names in (("jobs", ("received_at", "accepted_at")),
                         ("job_requests", ("initial_eligible_at", "eligibility_observed_at", "lease_decision_at"))):
        for name in names:
            op.add_column(table, sa.Column(name, sa.DateTime(timezone=True)))
    for name in ("worker_start_delay_seconds", "worker_engine_seconds"):
        op.add_column("execution_attempts", sa.Column(name, sa.Float()))
    op.create_table("worker_probes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("worker_id", sa.String(), sa.ForeignKey("worker_nodes.id"), nullable=False, index=True),
        sa.Column("generation", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_table("worker_probes")
    for name in ("worker_start_delay_seconds", "worker_engine_seconds"):
        op.drop_column("execution_attempts", name)
    for table, names in (("job_requests", ("initial_eligible_at", "eligibility_observed_at", "lease_decision_at")),
                         ("jobs", ("received_at", "accepted_at"))):
        for name in names:
            op.drop_column(table, name)
