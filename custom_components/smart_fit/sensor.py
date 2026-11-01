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
- `training` = `GET v2/trainings` → `{"weight_training":{"frequency","start_date",
    "finish_date"(epoch),"teacher_name","groups":[{"letter","label","exercises":[...],
    "data":{"done_at":epoch}}],"weekly_streak":{"current_record",...}}}`.
- `classes` = `GET v1/classes` → `{"location":{...},"schedule":[{"date",
    "classes":[{"name","start_at","end_at","teacher","room","duration"}]}]}`.
- `client_space` = Espaço do Cliente (web, via magic link) →
    `{"user":{"purchase":{"membership_price",...},"wallet":{...},"plan":{"status"}},
      "user_plan":{"payment_method","membership_due_date"},
      "payed":[...], "scheduled":[...], "overdue":[...]}` (itens:
    `{"dueDate","value","payed_at","startAt","endAt","siteRpsPath","barcode",...}`).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
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


# -- ficha de treino / aulas (api-mobile) --------------------------------


def _training(data: dict[str, Any]) -> dict[str, Any]:
    t = data.get("training")
    wt = t.get("weight_training") if isinstance(t, dict) else None
    return wt if isinstance(wt, dict) else {}


def _groups(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [g for g in (_training(data).get("groups") or []) if isinstance(g, dict)]


def _epoch_date(value: Any) -> date | None:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(dt_util.DEFAULT_TIME_ZONE).date()
    return None


def _group_done_at(g: dict[str, Any]) -> date | None:
    d = g.get("data") if isinstance(g.get("data"), dict) else {}
    return _epoch_date(d.get("done_at"))


def _training_value(data: dict[str, Any]) -> str | None:
    groups = _groups(data)
    if not groups:
        return None
    letters = "".join(str(g.get("letter") or "?") for g in groups)
    freq = _training(data).get("frequency")
    return f"{letters} ({freq}x/semana)" if freq else letters


def _training_attrs(data: dict[str, Any]) -> dict[str, Any]:
    wt = _training(data)
    expiry = _epoch_date(wt.get("finish_date"))
    return {
        "professor": wt.get("teacher_name"),
        "frequencia_semanal": wt.get("frequency"),
        "inicio": wt.get("start_date"),
        "validade": expiry.isoformat() if expiry else None,
        "dias_para_vencer": (expiry - dt_util.now().date()).days if expiry else None,
        "gerado_automaticamente": wt.get("automatically_generated"),
        "grupos": {
            str(g.get("letter")): {
                "nome": g.get("label"),
                "exercicios": len(g.get("exercises") or []),
                "ultima_vez": (d.isoformat() if (d := _group_done_at(g)) else None),
            }
            for g in _groups(data)
        },
    }


def _training_expiry(data: dict[str, Any]) -> date | None:
    return _epoch_date(_training(data).get("finish_date"))


def _next_group(data: dict[str, Any]) -> dict[str, Any] | None:
    """Rotação simples: o grupo feito há mais tempo (ou nunca feito) é o próximo."""
    groups = _groups(data)
    if not groups:
        return None
    return min(groups, key=lambda g: (_group_done_at(g) or date.min, str(g.get("letter"))))


def _next_group_value(data: dict[str, Any]) -> str | None:
    g = _next_group(data)
    if not g:
        return None
    return f"{g.get('letter')} - {g.get('label')}"


def _fmt_range(v: Any) -> Any:
    if isinstance(v, list) and len(v) == 2 and v[0] != v[1]:
        return f"{v[0]}-{v[1]}"
    if isinstance(v, list) and v:
        return v[0]
    return v


def _next_group_attrs(data: dict[str, Any]) -> dict[str, Any]:
    g = _next_group(data)
    if not g:
        return {}
    d = _group_done_at(g)
    return {
        "letra": g.get("letter"),
        "grupo_muscular": g.get("label"),
        "ultima_vez": d.isoformat() if d else None,
        "exercicios": [
            {
                "titulo": e.get("title"),
                "series": e.get("series"),
                "repeticoes": _fmt_range(e.get("repetitions")),
                "intervalo_s": _fmt_range(e.get("interval")),
                "maquina": e.get("smartfit_code"),
                "metodo": e.get("intensification_method"),
            }
            for e in g.get("exercises") or []
            if isinstance(e, dict)
        ],
    }


def _weekly_record(data: dict[str, Any]) -> Any:
    return (_training(data).get("weekly_streak") or {}).get("current_record")


def _classes(data: dict[str, Any]) -> list[dict[str, Any]]:
    c = data.get("classes")
    out: list[dict[str, Any]] = []
    for day in (c.get("schedule") or []) if isinstance(c, dict) else []:
        for cl in (day.get("classes") or []) if isinstance(day, dict) else []:
            if isinstance(cl, dict) and (start := dt_util.parse_datetime(str(cl.get("start_at") or ""))):
                out.append({**cl, "_start": start})
    return sorted(out, key=lambda x: x["_start"])


def _next_class(data: dict[str, Any]) -> datetime | None:
    now = dt_util.now()
    nxt = next((c for c in _classes(data) if c["_start"] >= now), None)
    return nxt["_start"] if nxt else None


def _next_class_attrs(data: dict[str, Any]) -> dict[str, Any]:
    now = dt_util.now()
    upcoming = [c for c in _classes(data) if c["_start"] >= now]
    if not upcoming:
        return {}
    nxt = upcoming[0]
    today = [c for c in upcoming if c["_start"].date() == now.date()]
    return {
        "aula": nxt.get("name"),
        "professor": nxt.get("teacher"),
        "sala": nxt.get("room"),
        "duracao_min": nxt.get("duration"),
        "aulas_hoje": [f"{c['_start'].strftime('%H:%M')} {c.get('name')}" for c in today],
    }


# -- financeiro (Espaço do Cliente) ---------------------------------------


def _cs(data: dict[str, Any]) -> dict[str, Any]:
    cs = data.get("client_space")
    return cs if isinstance(cs, dict) else {}


def _cs_user(data: dict[str, Any]) -> dict[str, Any]:
    u = _cs(data).get("user")
    return u if isinstance(u, dict) else {}


def _payments(data: dict[str, Any], status: str) -> list[dict[str, Any]]:
    return [p for p in (_cs(data).get(status) or []) if isinstance(p, dict)]


def _money(v: Any) -> float | None:
    try:
        return round(float(v), 2) if v is not None else None
    except (TypeError, ValueError):
        return None


def _parse_date(v: Any) -> date | None:
    if not isinstance(v, str) or not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def _membership_price(data: dict[str, Any]) -> float | None:
    return _money((_cs_user(data).get("purchase") or {}).get("membership_price"))


def _membership_attrs(data: dict[str, Any]) -> dict[str, Any]:
    u = _cs_user(data)
    purchase = u.get("purchase") or {}
    plan = _cs(data).get("user_plan") or {}
    return {
        "plano": (purchase.get("plan") or {}).get("name"),
        "status": (u.get("plan") or {}).get("status"),
        "dia_vencimento": plan.get("membership_due_date"),
        "forma_pagamento": plan.get("payment_method"),
        "cliente_desde": (purchase.get("confirmed_at") or "")[:10] or None,
        "limite_convidados": purchase.get("limit_guests"),
        "convidados_atuais": u.get("count_current_guests"),
        "pendencia": u.get("has_pending_payments"),
    }


def _card_value(data: dict[str, Any]) -> str | None:
    w = _cs_user(data).get("wallet") or {}
    masked = w.get("masked_card_number")
    if not masked:
        return None
    return f"{w.get('payment_company_name') or ''} •••• {str(masked)[-4:]}".strip()


def _card_attrs(data: dict[str, Any]) -> dict[str, Any]:
    w = _cs_user(data).get("wallet") or {}
    return {
        "bandeira": w.get("payment_company_name"),
        "tipo": w.get("payment_company_method"),
        "numero_mascarado": w.get("masked_card_number"),
        "validade": w.get("expires_at"),
        "ativo": w.get("payment_company_active"),
    }


def _next_payment(data: dict[str, Any]) -> date | None:
    sched = sorted(_payments(data, "scheduled"), key=lambda p: str(p.get("dueDate")))
    return _parse_date(sched[0].get("dueDate")) if sched else None


def _next_payment_attrs(data: dict[str, Any]) -> dict[str, Any]:
    sched = sorted(_payments(data, "scheduled"), key=lambda p: str(p.get("dueDate")))
    if not sched:
        return {}
    p = sched[0]
    due = _parse_date(p.get("dueDate"))
    return {
        "valor": _money(p.get("value")),
        "periodo": f"{p.get('startAt')} a {p.get('endAt')}",
        "dias_para_vencer": (due - dt_util.now().date()).days if due else None,
        "agendados": [
            {"vencimento": q.get("dueDate"), "valor": _money(q.get("value"))} for q in sched
        ],
    }


def _last_payment(data: dict[str, Any]) -> date | None:
    paid = sorted(_payments(data, "payed"), key=lambda p: str(p.get("payed_at") or p.get("dueDate")), reverse=True)
    return _parse_date(paid[0].get("payed_at") or paid[0].get("dueDate")) if paid else None


def _invoice(p: dict[str, Any]) -> dict[str, Any]:
    desc = p.get("invoiceDescription") or {}
    params = {x.get("label"): x.get("value") for x in desc.get("params") or [] if isinstance(x, dict)}
    return {
        "nota_fiscal_numero": params.get("Numnota"),
        "nota_fiscal_url": desc.get("url") or None,
        "recibo_url": p.get("siteRpsPath"),
    }


def _last_payment_attrs(data: dict[str, Any]) -> dict[str, Any]:
    paid = sorted(_payments(data, "payed"), key=lambda p: str(p.get("payed_at") or p.get("dueDate")), reverse=True)
    if not paid:
        return {}
    p = paid[0]
    return {
        "valor": _money(p.get("value")),
        "vencimento": p.get("dueDate"),
        "periodo": f"{p.get('startAt')} a {p.get('endAt')}",
        "plano": p.get("planName"),
        **_invoice(p),
    }


def _total_paid(data: dict[str, Any]) -> float | None:
    vals = [v for p in _payments(data, "payed") if (v := _money(p.get("value"))) is not None]
    return round(sum(vals), 2) if vals else None


def _total_paid_attrs(data: dict[str, Any]) -> dict[str, Any]:
    paid = sorted(_payments(data, "payed"), key=lambda p: str(p.get("dueDate")), reverse=True)
    return {
        "pagamentos": len(paid),
        "historico": [
            {
                "vencimento": p.get("dueDate"),
                "pago_em": (p.get("payed_at") or "")[:10] or None,
                "valor": _money(p.get("value")),
            }
            for p in paid[:24]
        ],
    }


def _overdue_count(data: dict[str, Any]) -> int:
    return len(_payments(data, "overdue"))


def _overdue_attrs(data: dict[str, Any]) -> dict[str, Any]:
    items = _payments(data, "overdue")
    return {
        "total": round(sum(v for p in items if (v := _money(p.get("value"))) is not None), 2),
        "atrasados": [
            {
                "vencimento": p.get("dueDate"),
                "valor": _money(p.get("value")),
                "boleto_url": p.get("client_bank_slip_url"),
                "codigo_barras": p.get("barcode"),
            }
            for p in items
        ],
    }


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
        device_class=SensorDeviceClass.TIMESTAMP,
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
    # -- ficha de treino / aulas
    SmartFitSensorDescription(
        key="current_training",
        name="Ficha de treino",
        icon="mdi:clipboard-list",
        value_fn=_training_value,
        attrs_fn=_training_attrs,
    ),
    SmartFitSensorDescription(
        key="next_group",
        name="Próximo treino",
        icon="mdi:arm-flex",
        value_fn=_next_group_value,
        attrs_fn=_next_group_attrs,
    ),
    SmartFitSensorDescription(
        key="training_expiry",
        name="Validade do treino",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.DATE,
        value_fn=_training_expiry,
    ),
    SmartFitSensorDescription(
        key="weekly_record",
        name="Recorde semanal",
        icon="mdi:trophy",
        native_unit_of_measurement="semanas",
        value_fn=_weekly_record,
    ),
    SmartFitSensorDescription(
        key="next_class",
        name="Próxima aula coletiva",
        icon="mdi:yoga",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_class,
        attrs_fn=_next_class_attrs,
    ),
    # -- financeiro (Espaço do Cliente)
    SmartFitSensorDescription(
        key="membership_price",
        name="Mensalidade",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="BRL",
        value_fn=_membership_price,
        attrs_fn=_membership_attrs,
    ),
    SmartFitSensorDescription(
        key="payment_card",
        name="Cartão cadastrado",
        icon="mdi:credit-card",
        value_fn=_card_value,
        attrs_fn=_card_attrs,
    ),
    SmartFitSensorDescription(
        key="next_payment",
        name="Próximo pagamento",
        icon="mdi:calendar-arrow-right",
        device_class=SensorDeviceClass.DATE,
        value_fn=_next_payment,
        attrs_fn=_next_payment_attrs,
    ),
    SmartFitSensorDescription(
        key="last_payment",
        name="Último pagamento",
        icon="mdi:receipt-text-check",
        device_class=SensorDeviceClass.DATE,
        value_fn=_last_payment,
        attrs_fn=_last_payment_attrs,
    ),
    SmartFitSensorDescription(
        key="total_paid",
        name="Total pago",
        icon="mdi:sigma",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="BRL",
        state_class=SensorStateClass.TOTAL,
        value_fn=_total_paid,
        attrs_fn=_total_paid_attrs,
    ),
    SmartFitSensorDescription(
        key="overdue_payments",
        name="Pagamentos em atraso",
        icon="mdi:alert-circle",
        native_unit_of_measurement="faturas",
        value_fn=_overdue_count,
        attrs_fn=_overdue_attrs,
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
