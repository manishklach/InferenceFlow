"""Additive scheduling predictions, attempt observations and internal GPU costs."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("admission", sa.Text()))
    op.add_column("job_requests", sa.Column("first_dispatched_at", sa.DateTime(timezone=True)))
    op.add_column("worker_nodes", sa.Column("telemetry_at", sa.DateTime(timezone=True)))
    op.add_column("worker_nodes", sa.Column("adaptive_limit", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("worker_nodes", sa.Column("adaptive_changed_at", sa.DateTime(timezone=True)))
    op.add_column("worker_nodes", sa.Column("model_loading_seconds", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("execution_attempts",
        sa.Column("request_id", sa.String(), sa.ForeignKey("job_requests.id"), primary_key=True),
        sa.Column("epoch", sa.Integer(), primary_key=True),
        sa.Column("worker_id", sa.String(), nullable=False, index=True),
        sa.Column("instance_id", sa.String()),
        sa.Column("identity", sa.String(), nullable=False, index=True),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String()),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False))
    op.create_table("gpu_observations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("worker_id", sa.String(), nullable=False, index=True),
        sa.Column("instance_id", sa.String(), index=True),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("active_seconds", sa.Integer(), nullable=False),
        sa.Column("idle_seconds", sa.Integer(), nullable=False))
    op.create_table("gpu_cost_profiles",
        sa.Column("instance_id", sa.String(), sa.ForeignKey("provider_instances.id"), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("gpu_type", sa.String(), nullable=False),
        sa.Column("billing_increment_seconds", sa.Integer(), nullable=False),
        sa.Column("startup_seconds", sa.Integer(), nullable=False),
        sa.Column("invoiced_micro_usd", sa.BigInteger()),
        sa.Column("invoice_reference", sa.String()),
        sa.Column("invoiced_through", sa.DateTime(timezone=True)),
        sa.CheckConstraint("billing_increment_seconds > 0 AND startup_seconds >= 0 AND (invoiced_micro_usd IS NULL OR invoiced_micro_usd >= 0)"))


def downgrade():
    for table in ("gpu_cost_profiles", "gpu_observations", "execution_attempts"):
        op.drop_table(table)
    for name in ("telemetry_at", "adaptive_limit", "adaptive_changed_at", "model_loading_seconds"):
        op.drop_column("worker_nodes", name)
    op.drop_column("job_requests", "first_dispatched_at")
    op.drop_column("jobs", "admission")
