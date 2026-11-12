"""Last observed status per machine, kept by the machine status monitor
(core/machine_status_monitor.py, Remote Access support plan phase 4, gap 10).

One row per machine: the status the monitor last recorded and since when. It
is the baseline that turns a 15-minute readiness read into transitions -- an
alert when a machine leaves `complete` (or falls to offline/not_prepared/
unknown), a "voltou" when it comes back -- and it survives restarts, so a
restart never re-alerts. Goes with its machine (ON DELETE CASCADE).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, false
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# The colors `classify_status` gives an enabled machine (api/routes/server.py).
MACHINE_OBSERVED_STATUSES = ("complete", "partial", "not_prepared", "offline", "unknown")


class MachineStatusObservation(Base, TimestampMixin):
    __tablename__ = "machine_status_observations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('complete', 'partial', 'not_prepared', 'offline', 'unknown')",
            name="ck_machine_status_observations_status",
        ),
        CheckConstraint(
            "pending_status IS NULL OR pending_status IN "
            "('complete', 'partial', 'not_prepared', 'offline', 'unknown')",
            name="ck_machine_status_observations_pending_status",
        ),
        UniqueConstraint("server_id", name="uq_machine_status_observations_server_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.servers.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # When the monitor first saw this status (the transition instant).
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Debounce: a degrade seen once waits here; it is recorded (and alerted)
    # only when the next pass still sees the machine degraded.
    pending_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pending_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The current status was recorded by a mass degrade (one summary instead of
    # one alert per machine), so its recovery doesn't alert one by one either.
    mass_batch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
