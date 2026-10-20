"""Time rules of the personal domain: recurrence, due reminders and the day summary text.

Pure functions over the ORM rows (no DB access) so routes and tests share them. Times are naive
America/Sao_Paulo wall time -- the domain is one person's agenda in one city, and storing UTC would
only move a timezone conversion into every caller (Maia, the UI, the cron).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
DATE_ONLY_TASK_HOUR = 8          # a task with only a date reminds at 8h of that day
LATE_WINDOW = timedelta(hours=6)  # a reminder missed while the server was down still goes out for 6 h
DEFAULT_REMINDERS = {"event": [60], "task": [0]}
WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def now_local() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None, second=0, microsecond=0)


def task_moment(task) -> datetime | None:
    if task.due_at is None:
        return None
    return task.due_at if task.due_has_time else task.due_at.replace(hour=DATE_ONLY_TASK_HOUR, minute=0)


def next_occurrence(moment: datetime, recurrence: str) -> datetime:
    if recurrence == "daily":
        return moment + timedelta(days=1)
    if recurrence == "weekly":
        return moment + timedelta(weeks=1)
    if recurrence == "monthly":
        year, month = (moment.year + 1, 1) if moment.month == 12 else (moment.year, moment.month + 1)
        return moment.replace(year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1]))
    if recurrence == "yearly":
        return moment.replace(year=moment.year + 1, day=min(moment.day, calendar.monthrange(moment.year + 1, moment.month)[1]))
    return moment


def describe(kind: str, title: str, moment: datetime, has_time: bool, location: str | None = None,
             recurrence: str = "") -> str:
    when = f"{WEEKDAYS[moment.weekday()]} {moment:%d/%m}" + (f" às {moment:%H:%M}" if has_time else "")
    text = f"{when}: {title}"
    if location:
        text += f" — {location}"
    if recurrence:
        text += f" (repete: {dict(daily='diária', weekly='semanal', monthly='mensal', yearly='anual')[recurrence]})"
    return text


def _lead(minutes: int) -> str:
    if minutes == 0:
        return "agora"
    if minutes < 60:
        return f"em {minutes} min"
    if minutes % 1440 == 0:
        days = minutes // 1440
        return "amanhã" if days == 1 else f"em {days} dias"
    hours, rest = divmod(minutes, 60)
    return f"em {hours}h{rest:02d}" if rest else f"em {hours}h"


def collect_due(items: list, at: datetime) -> list[str]:
    """Reminder lines for (kind, row) pairs whose reminder time has come; marks them on the row.
    Recurring rows that already passed roll to their next occurrence (re-arming reminders)."""
    lines = []
    for kind, row in items:
        moment = row.starts_at if kind == "event" else task_moment(row)
        if moment is None:
            continue
        sent = list(row.reminders_sent or [])
        for minutes in row.reminders or []:
            key = f"{moment:%Y-%m-%dT%H:%M}|{minutes}"
            fire = moment - timedelta(minutes=int(minutes))
            if key in sent or not (fire <= at <= fire + LATE_WINDOW):
                continue
            sent.append(key)
            has_time = (not row.all_day) if kind == "event" else row.due_has_time
            icon = "📅" if kind == "event" else "✅"
            line = f"{icon} Lembrete ({_lead(int(minutes))}): " + describe(
                kind, row.title, moment, has_time, getattr(row, "location", None), row.recurrence)
            if row.notes:
                line += f"\n   {row.notes[:300]}"
            lines.append(line)
        row.reminders_sent = sent[-50:]
        if row.recurrence and moment + timedelta(hours=1) < at:
            nxt = next_occurrence(moment, row.recurrence)
            if kind == "event":
                duration = (row.ends_at - row.starts_at) if row.ends_at else None
                row.starts_at = nxt
                row.ends_at = nxt + duration if duration else None
            else:
                row.due_at = nxt if row.due_has_time else nxt.replace(hour=0, minute=0)
            row.reminders_sent = []
    return lines


def day_summary(day: date, events: list, tasks: list) -> str:
    today, overdue, upcoming = [], [], []
    for e in events:
        if e.starts_at.date() == day:
            today.append((e.starts_at, "📅 " + describe("event", e.title, e.starts_at, not e.all_day, e.location)))
        elif day < e.starts_at.date() <= day + timedelta(days=3):
            upcoming.append((e.starts_at, "📅 " + describe("event", e.title, e.starts_at, not e.all_day, e.location)))
    for t in tasks:
        m = task_moment(t)
        if m is None:
            continue
        line = "✅ " + describe("task", t.title, m, t.due_has_time) + (f" [{t.list_name}]" if t.list_name else "")
        if m.date() == day:
            today.append((m, line))
        elif m.date() < day:
            overdue.append((m, line))
        elif m.date() <= day + timedelta(days=3):
            upcoming.append((m, line))
    out = [f"Agenda de {WEEKDAYS[day.weekday()]}, {day:%d/%m/%Y}."]
    for title, group in (("Hoje", today), ("Tarefas atrasadas", overdue), ("Próximos 3 dias", upcoming)):
        out.append(f"{title}:")
        out += [f"- {text}" for _, text in sorted(group, key=lambda x: x[0])] or ["- nada"]
    return "\n".join(out)
