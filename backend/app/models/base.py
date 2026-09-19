"""Declarative base and column types shared by every model.

Tests run on SQLite and dev/deploy on PostgreSQL (PROJECT_PLAN 1A2), so the
types here are chosen to behave the same on both.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Dialect, MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

# Deterministic constraint names, so migrations name the same constraint the
# same way on every backend (https://alembic.sqlalchemy.org/en/latest/naming.html).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UtcDateTime(TypeDecorator[datetime]):
    """Stores naive UTC, returns aware UTC. SQLite keeps no timezone, so a plain
    DateTime(timezone=True) would come back naive there and aware on
    PostgreSQL. Pattern from
    https://docs.sqlalchemy.org/en/20/core/custom_types.html (TZDateTime)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise TypeError("a timezone-aware datetime is required")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)
