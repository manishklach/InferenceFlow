from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE worker_nodes ADD COLUMN telemetry text")


def downgrade():
    op.execute("ALTER TABLE worker_nodes DROP COLUMN telemetry")
