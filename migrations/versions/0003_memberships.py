from alembic import op
from packages.common.db import User, Membership

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    User.__table__.create(op.get_bind())
    Membership.__table__.create(op.get_bind())


def downgrade():
    Membership.__table__.drop(op.get_bind())
    User.__table__.drop(op.get_bind())
