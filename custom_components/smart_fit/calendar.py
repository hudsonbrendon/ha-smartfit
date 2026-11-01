"""Calendários do Smart Fit: treinos feitos, aulas coletivas da unidade e pagamentos.

Tudo vem do mesmo coordinator; nada é gravado na Smart Fit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEntityDescription, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .data import SmartFitConfigEntry
from .entity import DEVICE_ACCOUNT, DEVICE_TRAINING, DEVICE_UNIT, SmartFitEntity
from .sensor import _br, _classes, _money, _parse_date, _parse_done_at, _payments, _sessions


@dataclass(frozen=True, kw_only=True)
class SmartFitCalendarDescription(CalendarEntityDescription):
    """Calendário com uma função que gera os eventos a partir dos dados."""

    events_fn: Callable[[dict[str, Any]], list[CalendarEvent]]
    device: str = DEVICE_ACCOUNT


def _training_events(data: dict[str, Any]) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    for s in _sessions(data):
        start = _parse_done_at(s.get("done_at"))
        if not start:
            continue
        dur = s.get("duration")
        end = start + timedelta(seconds=dur if isinstance(dur, (int, float)) and dur > 0 else 3600)
        mins = round(dur / 60) if isinstance(dur, (int, float)) else None
        events.append(
            CalendarEvent(
                start=start,
                end=end,
                summary=f"Treino {s.get('group') or ''} - {s.get('description') or ''}".strip(" -"),
                description=f"{s.get('exercises_done')} exercícios, {s.get('exercises_repetitions')} repetições, {mins} min",
                uid=f"smartfit-training-{s.get('training_group_id')}-{start.timestamp():.0f}",
            )
        )
    return events


def _class_events(data: dict[str, Any]) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    for c in _classes(data):
        start: datetime = c["_start"]
        end = dt_util.parse_datetime(str(c.get("end_at") or "")) or start + timedelta(minutes=c.get("duration") or 30)
        events.append(
            CalendarEvent(
                start=start,
                end=end,
                summary=str(c.get("name") or "Aula"),
                description=f"{c.get('teacher') or ''} - {c.get('room') or ''}".strip(" -"),
                location=c.get("room"),
                uid=f"smartfit-class-{c.get('id')}",
            )
        )
    return events


def _payment_events(data: dict[str, Any]) -> list[CalendarEvent]:
    labels = {"payed": "Pago", "scheduled": "Agendado", "overdue": "Em atraso"}
    events: list[CalendarEvent] = []
    for status, label in labels.items():
        for p in _payments(data, status):
            due = _parse_date(p.get("dueDate"))
            if not due:
                continue
            val = _money(p.get("value"))
            events.append(
                CalendarEvent(
                    start=due,
                    end=due + timedelta(days=1),
                    summary=f"Mensalidade Smart Fit R$ {val:.2f} ({label})".replace(".", ","),
                    description=f"Plano {p.get('planName')} - período {_br(p.get('startAt'))} a {_br(p.get('endAt'))}",
                    uid=f"smartfit-payment-{p.get('id')}",
                )
            )
    return events


CALENDARS: tuple[SmartFitCalendarDescription, ...] = (
    SmartFitCalendarDescription(key="trainings", name="Treinos", events_fn=_training_events, device=DEVICE_TRAINING),
    SmartFitCalendarDescription(key="classes", name="Aulas coletivas", events_fn=_class_events, device=DEVICE_UNIT),
    SmartFitCalendarDescription(key="payments", name="Pagamentos", events_fn=_payment_events, device=DEVICE_ACCOUNT),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SmartFitConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Cria os calendários."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(SmartFitCalendar(coordinator, desc) for desc in CALENDARS)


def _as_dt(v: datetime | date) -> datetime:
    if isinstance(v, datetime):
        return dt_util.as_local(v)
    return datetime.combine(v, datetime.min.time(), tzinfo=dt_util.DEFAULT_TIME_ZONE)


class SmartFitCalendar(SmartFitEntity, CalendarEntity):
    """Calendário somente leitura."""

    entity_description: SmartFitCalendarDescription

    def __init__(self, coordinator, description: SmartFitCalendarDescription) -> None:
        """Inicializa."""
        super().__init__(coordinator, description.device)
        self.entity_description = description
        document = coordinator.config_entry.data.get("document", "")
        self._attr_unique_id = f"{document}_calendar_{description.key}"

    def _events(self) -> list[CalendarEvent]:
        try:
            return sorted(self.entity_description.events_fn(self.coordinator.data or {}), key=lambda e: _as_dt(e.start))
        except (KeyError, TypeError, ValueError):
            return []

    @property
    def event(self) -> CalendarEvent | None:
        """Evento em andamento ou o próximo."""
        now = dt_util.now()
        return next((e for e in self._events() if _as_dt(e.end) >= now), None)

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        """Eventos no intervalo pedido."""
        return [e for e in self._events() if _as_dt(e.end) > start_date and _as_dt(e.start) < end_date]
