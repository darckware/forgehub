"""Personal domain -- Marcelo's own tasks, agenda, notes (2026-10-07) and demands (2026-10-14).

Marcelo: "não seria bom criar no ForgeHub lista de tarefas, anotações, agenda para a Maia ter
acesso". These rows belong to Marcelo, not to any product/version/project: the traceability chain of
the software factory does not apply here. Access is the admin user (UI) and the agents listed in
``settings.PERSONAL_AGENT_SLUGS`` (default ``maia``, his personal assistant) -- see
``api/routes/personal.py``. Maia reads and writes them through her ``pessoal`` MCP server, and her
cron turns due reminders into Telegram messages (``POST /api/v1/personal/reminders:due``).

Reminders are minutes before the moment (``[1440, 60]`` = a day and an hour before);
``reminders_sent`` holds ``"<moment iso>|<minutes>"`` keys so each one fires once per occurrence,
and moving the moment re-arms them. Recurring items roll forward to their next occurrence.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

PERSONAL_RECURRENCES = ("", "daily", "weekly", "monthly", "yearly")
PERSONAL_TASK_STATUSES = ("pending", "done", "cancelled")
PERSONAL_TASK_PRIORITIES = ("low", "normal", "high")
PERSONAL_EVENT_STATUSES = ("scheduled", "done", "cancelled")
PERSONAL_DEMAND_STATUSES = ("open", "done")
#: Built-in contact categories (the Maia's original set); more can be added as rows.
PERSONAL_CONTACT_DEFAULT_CATEGORIES = (
    "familia", "parentes", "amigos", "trabalho_semed", "cliente_darckware", "outros", "a_classificar",
)
#: Who wrote a history line: the contact, Marcelo himself, the Maia, or a manual note.
PERSONAL_MESSAGE_DIRECTIONS = ("in", "out", "note")
#: The context pass's state per message (contexto + suggestions), see core/personal_context.py.
PERSONAL_CONTEXT_STATUSES = ("pending", "done", "skipped", "failed")
PERSONAL_SUGGESTION_KINDS = ("demand", "task", "note")
PERSONAL_SUGGESTION_STATUSES = ("pending", "accepted", "dismissed")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class PersonalTask(Base, TimestampMixin):
    __tablename__ = "personal_tasks"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(PERSONAL_TASK_STATUSES)})", name="ck_personal_tasks_status"),
        CheckConstraint(f"priority IN ({_in(PERSONAL_TASK_PRIORITIES)})", name="ck_personal_tasks_priority"),
        CheckConstraint(f"recurrence IN ({_in(PERSONAL_RECURRENCES)})", name="ck_personal_tasks_recurrence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Free list name ("Pessoal", "SEMED", "Darckware", "Casa"...) -- grouping, not a FK.
    list_name: Mapped[str] = mapped_column(String(80), nullable=False, default="Pessoal", server_default="Pessoal")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal", server_default="normal")
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending", server_default="pending")
    #: Local São Paulo wall time (naive). due_has_time=False -> a date-only task (reminds at 8h).
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True, index=True)
    due_has_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    recurrence: Mapped[str] = mapped_column(String(10), nullable=False, default="", server_default="")
    reminders: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    reminders_sent: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Who created it: "marcelo" (UI) or the agent's profile slug (e.g. "maia").
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="marcelo", server_default="marcelo")


class PersonalEvent(Base, TimestampMixin):
    __tablename__ = "personal_events"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(PERSONAL_EVENT_STATUSES)})", name="ck_personal_events_status"),
        CheckConstraint(f"recurrence IN ({_in(PERSONAL_RECURRENCES)})", name="ck_personal_events_recurrence"),
        CheckConstraint("ends_at IS NULL OR ends_at >= starts_at", name="ck_personal_events_window"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    #: Local São Paulo wall time (naive).
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="scheduled", server_default="scheduled")
    recurrence: Mapped[str] = mapped_column(String(10), nullable=False, default="", server_default="")
    reminders: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    reminders_sent: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="marcelo", server_default="marcelo")


class PersonalNote(Base, TimestampMixin):
    __tablename__ = "personal_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="marcelo", server_default="marcelo")


class PersonalDemandType(Base, TimestampMixin):
    """A demand type Marcelo registers and removes on the Pessoal screen's Demandas tab
    (2026-10-14: "agrupar por tipo. Os tipo posso cadastrar e remover dentro da própria tela,
    ela se torna um tag"). Shown as the demand's tag and as its group header."""

    __tablename__ = "personal_demand_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="marcelo", server_default="marcelo")


class PersonalDemand(Base, TimestampMixin):
    """Something Marcelo has to get done, grouped by type. Removing a type never removes its
    demands: the FK is SET NULL, so they fall back to the "Sem tipo" group."""

    __tablename__ = "personal_demands"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(PERSONAL_DEMAND_STATUSES)})", name="ck_personal_demands_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.personal_demand_types.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open", server_default="open")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="marcelo", server_default="marcelo")


class PersonalContactCategory(Base, TimestampMixin):
    """A contact category key ("familia", "trabalho_semed", ...). Seeded with
    PERSONAL_CONTACT_DEFAULT_CATEGORIES; Marcelo or the Maia add more (2026-10-14: contacts moved
    from the knowledge-base Markdown files into the database)."""

    __tablename__ = "personal_contact_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)


class PersonalContact(Base, TimestampMixin):
    """A person who talks to Marcelo on his personal WhatsApp (2026-10-14, Marcelo: "adiciona uma aba
    dos contatos do whatsapp e seus históricos dos contexto"). Until this date the source was
    ``knowledge_base/marcelo/pessoal/CONTATOS.md`` + ``contatos/<telefone>.md``; those files were
    imported once and are no longer written.

    ``phone`` is digits only with the country code (``5521999999999``) -- the identity the WhatsApp
    plugin matches on. ``outros_dados`` keeps the free fields the old "Outros dados" section held;
    ``blocked`` is the WhatsApp blacklist (the old ``tipo: blacklist`` line), now a real column.
    """

    __tablename__ = "personal_contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="a_classificar", server_default="a_classificar")
    relation: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    #: "dd/mm" or "dd/mm/aaaa", as Marcelo says it.
    birthday: Mapped[str] = mapped_column(String(10), nullable=False, default="", server_default="")
    observations: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    who_is: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    how_to_treat: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    other_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="marcelo", server_default="marcelo")


class PersonalContactMessage(Base, TimestampMixin):
    """One history line of a contact: what was said, by whom, and its context.

    ``context`` is a one-or-two-sentence reading of the message in light of the recent conversation,
    written by the context pass (ForgeRouter, Maia's key) after the message is recorded; the same pass
    may propose PersonalCaptureSuggestion rows. Messages are never edited or deleted by the Maia.
    """

    __tablename__ = "personal_contact_messages"
    __table_args__ = (
        CheckConstraint(f"direction IN ({_in(PERSONAL_MESSAGE_DIRECTIONS)})", name="ck_personal_contact_messages_direction"),
        CheckConstraint(f"context_status IN ({_in(PERSONAL_CONTEXT_STATUSES)})", name="ck_personal_contact_messages_context_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.personal_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, default="in", server_default="in")
    #: Display name of who wrote it ("Ana", "Marcelo", "Maia").
    author: Mapped[str] = mapped_column(String(100), nullable=False, default="", server_default="")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    #: "whatsapp" (the plugin), "telegram"/"manual" (Marcelo through the Maia or the screen), "import".
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="whatsapp", server_default="whatsapp")
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending", server_default="pending")


class PersonalCaptureSuggestion(Base, TimestampMixin):
    """A demand, task or note the context pass found in a message -- only a proposal: Marcelo accepts
    it (which creates the real PersonalDemand/PersonalTask/PersonalNote) or dismisses it (2026-10-14:
    "Sugere, você confirma" -- what a contact writes is never trusted to land in his lists by itself)."""

    __tablename__ = "personal_capture_suggestions"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(PERSONAL_SUGGESTION_KINDS)})", name="ck_personal_capture_suggestions_kind"),
        CheckConstraint(f"status IN ({_in(PERSONAL_SUGGESTION_STATUSES)})", name="ck_personal_capture_suggestions_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.personal_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.personal_contact_messages.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending", server_default="pending")
    #: The PersonalDemand/PersonalTask/PersonalNote created on accept.
    created_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PersonalAssistantSettings(Base, TimestampMixin):
    """The Maia's WhatsApp service rules, one row (2026-10-14: "uma aba de contexto da Maia, uma regra
    de atendimento do whatsapp"). Until this date they lived in the Maia profile's
    ``whatsapp/INSTRUCOES_PESSOAIS.md`` and ``atendimento.json``; the plugin reads them from here and
    keeps a local copy for when ForgeHub is unreachable."""

    __tablename__ = "personal_assistant_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    #: Minutes the Maia waits before answering, giving Marcelo the chance to answer first.
    wait_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    #: Whether the context pass runs (context + suggestions after each message).
    capture_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


PERSONAL_LOCATION_SOURCES = ("telegram", "whatsapp", "browser")


class PersonalLocation(Base, TimestampMixin):
    """Marcelo's current GPS location, for the daily summary's weather (2026-10-24).

    One row, replaced on every share -- there is no history of where he was (Marcelo: "o
    conceito era registrar a localização GPS atual, não precisa o histórico"). It arrives as a
    pin he sends the Maia on Telegram or WhatsApp, or from the browser's GPS on Pessoal →
    Localização. Never the VPS's location. ``slot`` is a constant with a unique index, so a
    second row can't exist. ``city``/``state`` are a best-effort reverse geocode; coordinates
    alone are enough for the weather.
    """

    __tablename__ = "personal_location"
    __table_args__ = (
        UniqueConstraint("slot", name="uq_personal_location_slot"),
        CheckConstraint("slot = 'current'", name="ck_personal_location_slot"),
        CheckConstraint(f"source IN {PERSONAL_LOCATION_SOURCES}", name="ck_personal_location_source"),
        CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
                        name="ck_personal_location_coordinates"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slot: Mapped[str] = mapped_column(String(16), nullable=False, default="current", server_default="current")
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    #: Reported by the browser's geolocation; pins carry none.
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: "telegram"/"whatsapp" (a pin sent to the Maia) or "browser" (Marcelo on the screen).
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    shared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PersonalDailySummary(Base, TimestampMixin):
    """The morning summary the Maia sent Marcelo, one per day (2026-10-24).

    The text is the one she actually delivered, saved by her through the MCP
    (``personal_daily_summary_save``); a second save the same day replaces it. The location
    is a snapshot of the current location at save time -- the one the weather used --
    because the current location itself keeps no history.
    """

    __tablename__ = "personal_daily_summaries"
    __table_args__ = (UniqueConstraint("day", name="uq_personal_daily_summaries_day"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: São Paulo date of the summary.
    day: Mapped[date] = mapped_column(Date, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    location_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: The actor that saved it ("maia" or "marcelo").
    created_by: Mapped[str] = mapped_column(String(50), nullable=False)
