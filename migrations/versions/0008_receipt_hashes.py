"""Persist request/output hashes independently of encrypted content retention."""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("prompt_sha256", "payload_sha256", "output_sha256"):
        op.add_column("job_requests", sa.Column(name, sa.String(64), nullable=True))


def downgrade():
    for name in ("output_sha256", "payload_sha256", "prompt_sha256"):
        op.drop_column("job_requests", name)
