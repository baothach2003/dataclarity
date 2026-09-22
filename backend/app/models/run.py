"""The `runs` table (SPECS section 9). Contract files stay on disk under
runs/<id>/ (CONTRACTS.md section 1); this row tracks the run itself."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UtcDateTime


class RunStatus(StrEnum):
    """SPECS section 3 state machine, plus failed and expired. `cleaning` is not
    a step the user sees: it is the claim a run holds while its plan executes, so
    a second execute for the same run is refused instead of racing (1G)."""

    UPLOADED = "uploaded"
    PROFILED = "profiled"
    PLANNED = "planned"
    CLEANING = "cleaning"
    CLEANED = "cleaned"
    ANALYZED = "analyzed"
    IMPORTED = "imported"
    FAILED = "failed"
    EXPIRED = "expired"


class Run(Base):
    __tablename__ = "runs"

    # The canonical UUID string, identical to the directory name and the API
    # value; a native UUID type would differ between SQLite and PostgreSQL.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[RunStatus] = mapped_column(
        # VARCHAR + CHECK on every backend; create_constraint defaults to False
        # in SQLAlchemy 2.0, so it is enabled explicitly.
        Enum(
            RunStatus,
            name="run_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda members: [m.value for m in members],
        )
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    # A SPECS section 10 code, set only when the run moves to `failed`.
    error_code: Mapped[str | None] = mapped_column(String(32))
