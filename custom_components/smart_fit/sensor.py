"""Sensores do Smart Fit.

Shapes confirmados em login real (v4.9.26):

- `profile` = `GET v1/users/user` →
  `{"profile": {"name","plan","current_plan","registration_id",
    "location_acronym", ...}, "access": {...}}`.
- `training_sessions` = `GET v3/training_sessions` →
  `{"training_sessions": [{"done_at":"YYYY-MM-DD HH:MM:SS UTC","group",
    "duration","description","exercises_done", ...}]}`.
- `occupancy` = `GET v1/locations/{acronym}/occupancy_rates` →
  `{"location": {"acronym","name","address"},
    "occupancy_rates": [{"hour":"4".."23","total":int}]}`.
"""

from __future__ import annotations

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


def _parse_done_at(value: Any) -> datetime | None:
    """Converte "2026-10-13 19:13:25 UTC" em datetime aware."""
    if not isinstance(value, str):
        return None
    txt = value.replace(" UTC", "").strip()
    try:
        return datetime.strptime(txt, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _plan_value(data: dict[str, Any]) -> Any:
    prof = _profile(data)
    return prof.get("plan") or prof.get("current_plan")


def _month_count(data: dict[str, Any]) -> int:
    now = dt_util.utcnow()
    count = 0
    for s in _sessions(data):
        done = _parse_done_at(s.get("done_at"))
        if done and done.year == now.year and done.month == now.month:
            count += 1
    return count


def _last_training(data: dict[str, Any]) -> Any:
    best: datetime | None = None
    for s in _sessions(data):
        done = _parse_done_at(s.get("done_at"))
        if done and (best is None or done > best):
            best = done
    return best


def _last_training_attrs(data: dict[str, Any]) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    best_dt: datetime | None = None
    for s in _sessions(data):
        done = _parse_done_at(s.get("done_at"))
        if done and (best_dt is None or done > best_dt):
            best_dt, best = done, s
    if not best:
        return {}
    return {
        "grupo": best.get("group"),
        "descricao": best.get("description"),
        "duracao_min": round(best.get("duration", 0) / 60) if best.get("duration") else None,
        "exercicios": best.get("exercises_done"),
        "repeticoes": best.get("exercises_repetitions"),
    }


def _occupancy_now(data: dict[str, Any]) -> Any:
    occ = data.get("occupancy")
    if not isinstance(occ, dict):
        return None
    rates = occ.get("occupancy_rates")
    if not isinstance(rates, list) or not rates:
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
    return {
        "unidade": loc.get("name"),
        "endereco": loc.get("address"),
        "acronym": loc.get("acronym"),
        "lotacao_por_hora": {
            str(r.get("hour")): r.get("total")
            for r in rates
            if isinstance(r, dict)
        },
    }


SENSORS: tuple[SmartFitSensorDescription, ...] = (
    SmartFitSensorDescription(
        key="plan",
        name="Plano",
        icon="mdi:card-account-details",
        value_fn=_plan_value,
    ),
    SmartFitSensorDescription(
        key="trainings_month",
        name="Treinos no mês",
        icon="mdi:calendar-check",
        native_unit_of_measurement="treinos",
        value_fn=_month_count,
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
