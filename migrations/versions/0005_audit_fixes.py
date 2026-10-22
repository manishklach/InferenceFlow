"""Worker identity fencing, reversal liabilities and shared admission limits."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("wallets", sa.Column("debt", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("wallet_debt_nonnegative", "wallets", "debt >= 0")
    op.add_column(
        "wallets",
        sa.Column("schedule_checked", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("wallet_ledger", sa.Column("debt_delta", sa.BigInteger(), nullable=False, server_default="0"))
    for name in ("generation", "revision", "repo", "tokenizer_revision", "execution_mode"):
        op.add_column("worker_nodes", sa.Column(name, sa.String(), nullable=False, server_default="unverified"))
    # Old workers cannot dispatch after upgrade; restarting enrolls a fresh generation and identity.
    op.add_column("job_requests", sa.Column("worker_generation", sa.String(), nullable=True))
    op.add_column("webhook_deliveries", sa.Column("claim", sa.String()))
    op.add_column("webhook_deliveries", sa.Column("claim_until", sa.DateTime(timezone=True)))
    op.create_table(
        "rate_buckets",
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("window", sa.BigInteger(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
    )
    # Preserve pre-upgrade shortfalls as financial liabilities, not just audit annotations.
    op.execute("""INSERT INTO wallet_ledger
        (id, tenant_id, source, kind, available_delta, reserved_delta, debt_delta, created_at)
        SELECT md5(a.id || '-debt-migration'), p.tenant_id, 'debt-migration:' || a.id,
               'reversal_debt', 0, 0, split_part(a.reference, ':', 2)::bigint, now()
        FROM audit_events a JOIN payment_events p ON p.id = split_part(a.reference, ':', 1)
        WHERE a.kind = 'reversal_debt'""")
    op.execute("""UPDATE wallets w SET debt = COALESCE((SELECT sum(l.debt_delta)
               FROM wallet_ledger l WHERE l.tenant_id = w.tenant_id), 0)""")


def downgrade():
    # Historical debt ledger entries must remain append-only, including their debt amounts.
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM wallet_ledger WHERE debt_delta <> 0)")):
        raise RuntimeError("Cannot discard financial liability history; restore a reviewed backup instead")
    op.drop_column("webhook_deliveries", "claim_until")
    op.drop_column("webhook_deliveries", "claim")
    op.drop_table("rate_buckets")
    op.drop_column("job_requests", "worker_generation")
    for name in ("generation", "revision", "repo", "tokenizer_revision", "execution_mode"):
        op.drop_column("worker_nodes", name)
    op.drop_column("wallet_ledger", "debt_delta")
    op.drop_column("wallets", "schedule_checked")
    op.drop_constraint("wallet_debt_nonnegative", "wallets")
    op.drop_column("wallets", "debt")
