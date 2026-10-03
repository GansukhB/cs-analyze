"""Shared column types and the timestamp mixin.

The types reproduce what Django creates on MySQL for cstat's fields, so the two
schemas line up column for column: Positive*Field is UNSIGNED, FloatField is
DOUBLE, DateTimeField is DATETIME(6), and primary keys are BIGINT (BigAutoField).
Each has a plain variant so the test suite can run the same models on SQLite.
"""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Double, Integer, LargeBinary, SmallInteger
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

# SQLite only autoincrements a column declared exactly INTEGER PRIMARY KEY.
BigId = BigInteger().with_variant(Integer(), "sqlite")
PositiveSmallInt = SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql")
PositiveInt = Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql")
Float = Double()
DateTime6 = DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
# MySQL's plain BLOB stops at 64 KB; a map's Tick Data is ~10 MB and its walked
# routes a few hundred KB.
LongBlob = LargeBinary().with_variant(mysql.LONGBLOB(), "mysql")
MediumBlob = LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql")


def utcnow() -> datetime:
    """Naive UTC, as Django stores datetimes on MySQL with USE_TZ."""
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime6, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime6, default=utcnow, onupdate=utcnow)
