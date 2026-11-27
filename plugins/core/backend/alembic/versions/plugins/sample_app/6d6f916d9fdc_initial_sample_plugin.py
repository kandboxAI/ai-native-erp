"""initial sample plugin"""

revision = '6d6f916d9fdc'
down_revision = None
branch_labels = ('sample_app',)
depends_on = 'core_0001'

from alembic import op
import sqlalchemy as sa
import sqlmodel


sa.NullType = sa.types.NullType


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
