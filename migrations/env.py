from alembic import context
from packages.common.db import Base, engine

config = context.config
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
