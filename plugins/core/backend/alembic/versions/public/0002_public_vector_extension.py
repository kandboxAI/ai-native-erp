"""Install the shared pgvector type used by tenant resource indexes."""

from alembic import op

revision = "0002_public_vector_extension"
down_revision = "0001_public_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("create extension if not exists vector with schema public")


def downgrade() -> None:
    # The extension may be used by every tenant; dropping it here would remove
    # objects outside this migration's scope.
    pass
