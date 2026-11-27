from decimal import Decimal
from sqlalchemy import Numeric, text
from sqlmodel import Field

def _money(comment: str, *, default: str = "0"):
    return Field(
        default=Decimal(default),
        sa_type=Numeric(18, 2),
        nullable=False,
        sa_column_kwargs={"server_default": text(default), "comment": comment},
    )


def _rate(comment: str):
    return Field(
        default=Decimal("0"),
        sa_type=Numeric(8, 4),
        nullable=False,
        sa_column_kwargs={"server_default": text("0"), "comment": comment},
    )
