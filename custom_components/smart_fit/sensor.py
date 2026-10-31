"""Sensores do Smart Fit.

Shapes confirmados em login real (v4.9.26):

- `profile` = `GET v1/users/user` →
  `{"profile": {"name","plan","current_plan","registration_id",
    "location_acronym","black_benefits",...}, "access": {...}}`.
- `training_sessions` = `GET v3/training_sessions` →
  `{"training_sessions": [{"done_at":"YYYY-MM-DD HH:MM:SS UTC","group",
    "duration","description","exercises_done", ...}]}`.
- `training_stats` = `GET v3/training_session_stats` →
  `{"last_training_session":{...}, "weekly_training_streak":{"current_weekly_count",...},
    "training_progress":{"completed_session","total_session","progress_in_percent",...}}`.
- `monthly_activity` = `GET v1/monthly_activity_results` →
  `{"cards":[{"tracking":"training_sessions"|"training_duration",
    "metadata":{"title":"Você fez 1 treino..."/"...155 minutos"}}]}`.
- `occupancy` = `GET v1/locations/{acronym}/occupancy_rates` →
  `{"location":{...}, "occupancy_rates":[{"hour":"4".."23","total":int}]}`.
- `debts` = `GET v2/debts` (com `empty_state` = sem pendências).
- `guests` = `GET v1/guests` → `{"guests":[...]}`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .data import SmartFitConfigEntry
from .entity import SmartFitEntity


@dataclass(frozen=True, kw_only=True)
class SmartFitSensorDescription(SensorEntityDescription):
    """Descrição com extratores de valor e atributos."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


# -- helpers de acesso -------------------------------------------------


def _profile(data: dict[str, Any]) -> dict[str, Any]:
    prof = data.get("profile")
    if isinstance(prof, dict):
        inner = prof.get("profile")
        return inner if isinstance(inner, dict) else prof
    return {}


def _sessions(data: dict[str, Any]) -> list[dict[str, Any]]:
    ts = data.get("training_sessions")
    if isinstance(ts, dict):
        items = ts.get("training_sessions")
        if isinstance(items, list):
            return [s for s in items if isinstance(s, dict)]
    return []


def _stats(data: dict[str, Any]) -> dict[str, Any]:
    s = data.get("training_stats")
    return s if isinstance(s, dict) else {}


def _parse_done_at(value: Any) -> datetime | None:
    """Aceita "2026-10-13 19:13:25 UTC" e "2026-10-13T19:13:25Z"."""
    if not isinstance(value, str):
        return None
    txt = value.replace(" UTC", "").replace("T", " ").replace("Z", "").strip()
    try:
        return datetime.strptime(txt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _first_int(text: Any) -> int | None:
    if not isinstance(text, str):
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def _monthly_metric(data: dict[str, Any], tracking: str) -> int | None:
    ma = data.get("monthly_activity")
    if not isinstance(ma, dict):
        return None
    for card in ma.get("cards") or []:
        if isinstance(card, dict) and card.get("tracking") == tracking:
            meta = card.get("metadata") or {}
            return _first_int(meta.get("title"))
    return None


# -- extratores de valor ----------------------------------------------


def _plan_value(data: dict[str, Any]) -> Any:
    prof = _profile(data)
    return prof.get("plan") or prof.get("current_plan")


def _registration(data: dict[str, Any]) -> Any:
    return _profile(data).get("registration_id")


def _unit_value(data: dict[str, Any]) -> Any:
    occ = data.get("occupancy")
    if isinstance(occ, dict):
        loc = occ.get("location") or {}
        if loc.get("name"):
            return loc["name"]
    return _profile(data).get("location_acronym")


def _month_count(data: dict[str, Any]) -> int:
    monthly = _monthly_metric(data, "training_sessions")
    if monthly is not None:
        return monthly
    now = dt_util.utcnow()
    return sum(
        1
        for s in _sessions(data)
        if (d := _parse_done_at(s.get("done_at")))
        and d.year == now.year
        and d.month == now.month
    )


def _month_minutes(data: dict[str, Any]) -> int | None:
    return _monthly_metric(data, "training_duration")


def _total_trainings(data: dict[str, Any]) -> int:
    return len(_sessions(data))


def _weekly_streak(data: dict[str, Any]) -> Any:
    wk = _stats(data).get("weekly_training_streak") or {}
    return wk.get("current_weekly_count")


def _progress(data: dict[str, Any]) -> Any:
    return (_stats(data).get("training_progress") or {}).get("progress_in_percent")


def _progress_attrs(data: dict[str, Any]) -> dict[str, Any]:
    tp = _stats(data).get("training_progress") or {}
    return {
        "sessoes_concluidas": tp.get("completed_session"),
        "sessoes_totais": tp.get("total_session"),
        "renovar_treino": tp.get("renew_training"),
    }


def _last_training(data: dict[str, Any]) -> Any:
    stats_last = _stats(data).get("last_training_session") or {}
    dt = _parse_done_at(stats_last.get("done_at"))
    if dt:
        return dt
    best: datetime | None = None
    for s in _sessions(data):
        d = _parse_done_at(s.get("done_at"))
        if d and (best is None or d > best):
            best = d
    return best


def _last_training_attrs(data: dict[str, Any]) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    best_dt: datetime | None = None
    for s in _sessions(data):
        d = _parse_done_at(s.get("done_at"))
        if d and (best_dt is None or d > best_dt):
            best_dt, best = d, s
    if not best:
        return {}
    dur = best.get("duration")
    return {
        "grupo": best.get("group"),
        "descricao": best.get("description"),
        "duracao_min": round(dur / 60) if isinstance(dur, (int, float)) else None,
        "exercicios": best.get("exercises_done"),
        "repeticoes": best.get("exercises_repetitions"),
    }


def _occupancy_now(data: dict[str, Any]) -> Any:
    occ = data.get("occupancy")
    if not isinstance(occ, dict):
        return None
    rates = occ.get("occupancy_rates")
    if not isinstance(rates, list):
        return None
    hour = dt_util.now().hour
    for r in rates:
        if isinstance(r, dict) and str(r.get("hour")) == str(hour):
            return r.get("total")
    return None


def _occupancy_attrs(data: dict[str, Any]) -> dict[str, Any]:
    occ = data.get("occupancy")
    if not isinstance(occ, dict):
        return {}
    loc = occ.get("location") if isinstance(occ.get("location"), dict) else {}
    rates = occ.get("occupancy_rates") or []
    by_hour = {
        str(r.get("hour")): r.get("total") for r in rates if isinstance(r, dict)
    }
    totals = [v for v in by_hour.values() if isinstance(v, (int, float))]
    peak_hour = None
    if by_hour:
        peak_hour = max(by_hour, key=lambda h: by_hour[h] or 0)
    return {
        "unidade": loc.get("name"),
        "endereco": loc.get("address"),
        "acronym": loc.get("acronym"),
        "pico_hoje": max(totals) if totals else None,
        "hora_pico": peak_hour,
        "lotacao_por_hora": by_hour,
    }


def _debts_value(data: dict[str, Any]) -> str | None:
    debts = data.get("debts")
    if not isinstance(debts, dict):
        return None
    if debts.get("empty_state"):
        return "Em dia"
    items = debts.get("debts") or debts.get("invoices") or []
    return f"{len(items)} pendência(s)" if items else "Em dia"


def _guests_count(data: dict[str, Any]) -> int | None:
    g = data.get("guests")
    if isinstance(g, dict) and isinstance(g.get("guests"), list):
        return len(g["guests"])
    return None


SENSORS: tuple[SmartFitSensorDescription, ...] = (
    SmartFitSensorDescription(
        key="plan",
        name="Plano",
        icon="mdi:card-account-details",
        value_fn=_plan_value,
    ),
    SmartFitSensorDescription(
        key="registration",
        name="Matrícula",
        icon="mdi:identifier",
        value_fn=_registration,
    ),
    SmartFitSensorDescription(
        key="unit",
        name="Unidade",
        icon="mdi:map-marker",
        value_fn=_unit_value,
    ),
    SmartFitSensorDescription(
        key="trainings_month",
        name="Treinos no mês",
        icon="mdi:calendar-check",
        native_unit_of_measurement="treinos",
        value_fn=_month_count,
    ),
    SmartFitSensorDescription(
        key="minutes_month",
        name="Minutos no mês",
        icon="mdi:timer",
        native_unit_of_measurement="min",
        value_fn=_month_minutes,
    ),
    SmartFitSensorDescription(
        key="total_trainings",
        name="Total de treinos",
        icon="mdi:counter",
        native_unit_of_measurement="treinos",
        value_fn=_total_trainings,
    ),
    SmartFitSensorDescription(
        key="weekly_streak",
        name="Sequência semanal",
        icon="mdi:fire",
        native_unit_of_measurement="semanas",
        value_fn=_weekly_streak,
    ),
    SmartFitSensorDescription(
        key="training_progress",
        name="Progresso do treino",
        icon="mdi:progress-check",
        native_unit_of_measurement="%",
        value_fn=_progress,
        attrs_fn=_progress_attrs,
    ),
    SmartFitSensorDescription(
        key="last_training",
        name="Último treino",
        icon="mdi:dumbbell",
        device_class="timestamp",
        value_fn=_last_training,
        attrs_fn=_last_training_attrs,
    ),
    SmartFitSensorDescription(
        key="occupancy",
        name="Lotação da unidade",
        icon="mdi:account-group",
        native_unit_of_measurement="pessoas",
        value_fn=_occupancy_now,
        attrs_fn=_occupancy_attrs,
    ),
    SmartFitSensorDescription(
        key="debts",
        name="Pendências financeiras",
        icon="mdi:cash-check",
        value_fn=_debts_value,
    ),
    SmartFitSensorDescription(
        key="guests",
        name="Convidados",
        icon="mdi:account-multiple-plus",
        native_unit_of_measurement="convidados",
        value_fn=_guests_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartFitConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Cria os sensores."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(SmartFitSensor(coordinator, desc) for desc in SENSORS)


class SmartFitSensor(SmartFitEntity, SensorEntity):
    """Sensor genérico do Smart Fit."""

    entity_description: SmartFitSensorDescription

    def __init__(self, coordinator, description: SmartFitSensorDescription) -> None:
        """Inicializa o sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        document = coordinator.config_entry.data.get("document", "")
        self._attr_unique_id = f"{document}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Valor atual."""
        data = self.coordinator.data or {}
        try:
            return self.entity_description.value_fn(data)
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Atributos extras."""
        if self.entity_description.attrs_fn is None:
            return None
        data = self.coordinator.data or {}
        try:
            return self.entity_description.attrs_fn(data) or None
        except (KeyError, TypeError, ValueError):
            return None
