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
from .entity import DEVICE_ACCOUNT, DEVICE_TRAINING, DEVICE_UNIT, SmartFitEntity


@dataclass(frozen=True, kw_only=True)
class SmartFitSensorDescription(SensorEntityDescription):
    """Descrição com extratores de valor e atributos."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    picture_fn: Callable[[dict[str, Any]], str | None] | None = None
    device: str = DEVICE_ACCOUNT


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


def _br(value: Any) -> str | None:
    """Formata data/hora em dd/mm/aaaa (hora local quando houver)."""
    if value is None or value == "":
        return None
    dt: datetime | None = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        dt = _parse_done_at(value) or dt_util.parse_datetime(value)
        if dt is None:
            try:
                return date.fromisoformat(value[:10]).strftime("%d/%m/%Y")
            except ValueError:
                return value
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(dt_util.DEFAULT_TIME_ZONE)
    if dt.hour or dt.minute:
        return dt.strftime("%d/%m/%Y %H:%M")
    return dt.strftime("%d/%m/%Y")


def _brd(value: Any) -> str | None:
    """Só a data, dd/mm/aaaa."""
    out = _br(value)
    return out[:10] if out else out


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


def _sessions_attrs(data: dict[str, Any]) -> dict[str, Any]:
    items = sorted(
        (s for s in _sessions(data) if _parse_done_at(s.get("done_at"))),
        key=lambda s: _parse_done_at(s.get("done_at")),
        reverse=True,
    )
    return {
        "historico": [
            {
                "data": _br(s.get("done_at")),
                "grupo": s.get("group"),
                "descricao": s.get("description"),
                "duracao_min": round(s["duration"] / 60) if isinstance(s.get("duration"), (int, float)) else None,
                "exercicios": s.get("exercises_done"),
                "repeticoes": s.get("exercises_repetitions"),
            }
            for s in items[:30]
        ]
    }


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
        "inicio": _br(wt.get("start_date")),
        "validade": _br(expiry),
        "dias_para_vencer": (expiry - dt_util.now().date()).days if expiry else None,
        "gerado_automaticamente": wt.get("automatically_generated"),
        "grupos": {
            str(g.get("letter")): {
                "nome": g.get("label"),
                "exercicios": len(g.get("exercises") or []),
                "ultima_vez": _br(_group_done_at(g)),
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
        "ultima_vez": _br(d),
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
        "cliente_desde": _brd(purchase.get("confirmed_at")),
        "limite_convidados": purchase.get("limit_guests"),
        "convidados_atuais": u.get("count_current_guests"),
        "pendencia": u.get("has_pending_payments"),
        "corporativo": purchase.get("is_corporate"),
        "transferivel": purchase.get("is_transferable"),
        "skeelo_ativo": purchase.get("skeelo_active"),
        "anuidade": purchase.get("anual_fee_amount_to_site"),
        "mes_anuidade": purchase.get("anual_fee_date_to_site"),
        "beneficio_vip": u.get("has_vip_benefit"),
        "boleto_url": u.get("bank_slip_url"),
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
        "validade": _br(w.get("expires_at")),
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
        "vencimento": _br(due),
        "valor": _money(p.get("value")),
        "periodo": f"{_br(p.get('startAt'))} a {_br(p.get('endAt'))}",
        "dias_para_vencer": (due - dt_util.now().date()).days if due else None,
        "agendados": [
            {"vencimento": _br(q.get("dueDate")), "valor": _money(q.get("value"))} for q in sched
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
        "pago_em": _br(p.get("payed_at")),
        "valor": _money(p.get("value")),
        "vencimento": _br(p.get("dueDate")),
        "periodo": f"{_br(p.get('startAt'))} a {_br(p.get('endAt'))}",
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
                "vencimento": _br(p.get("dueDate")),
                "pago_em": _br(p.get("payed_at")),
                "valor": _money(p.get("value")),
            }
            for p in paid[:36]
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
                "vencimento": _br(p.get("dueDate")),
                "valor": _money(p.get("value")),
                "boleto_url": p.get("client_bank_slip_url"),
                "codigo_barras": p.get("barcode"),
            }
            for p in items
        ],
    }


# -- conta / perfil / unidade ---------------------------------------------


def _profile_name(data: dict[str, Any]) -> Any:
    return _profile(data).get("name") or (_cs_user(data).get("personal") or {}).get("name")


def _profile_picture(data: dict[str, Any]) -> str | None:
    url = _profile(data).get("photo_url")
    return str(url) if url else None


def _profile_attrs(data: dict[str, Any]) -> dict[str, Any]:
    prof = _profile(data)
    personal = _cs_user(data).get("personal") or {}
    phone = personal.get("phone") or {}
    addr = _cs_user(data).get("address") or {}
    access = (data.get("profile") or {}).get("access") or {}
    return {
        "email": prof.get("email") or personal.get("email"),
        "telefone": f"({phone.get('area')}) {phone.get('number')}" if phone.get("number") else None,
        "nascimento": _br((personal.get("personal_group") or {}).get("birthdate")),
        "cadastro_em": _brd(personal.get("sign_up_at")),
        "endereco": ", ".join(
            str(x)
            for x in (
                addr.get("street"),
                (addr.get("address_group_1") or {}).get("number"),
                (addr.get("address_group_1") or {}).get("complement"),
                addr.get("region"),
            )
            if x
        )
        or None,
        "cep": (addr.get("address_group_0") or {}).get("zip"),
        "anamnese_respondida": prof.get("anamnesis_answered"),
        "parq_pendente": prof.get("parq_pending"),
        "beneficios_black": prof.get("black_benefits"),
        "acessos": sorted(k for k, v in access.items() if v is True),
    }


def _social(data: dict[str, Any]) -> dict[str, Any]:
    so = data.get("social")
    return so if isinstance(so, dict) else {}


def _followers(data: dict[str, Any]) -> Any:
    return (_social(data).get("profile") or {}).get("followers")


def _social_attrs(data: dict[str, Any]) -> dict[str, Any]:
    p = _social(data).get("profile") or {}
    return {
        "seguindo": p.get("following"),
        "amigos": p.get("friends"),
        "cliente_ha": p.get("smartfit_at"),
        "perfil_privado": p.get("private"),
        "link": p.get("link"),
    }


def _partners_count(data: dict[str, Any]) -> int | None:
    pc = data.get("partners")
    items = pc.get("partner_connections") if isinstance(pc, dict) else None
    return len(items) if isinstance(items, list) else None


def _partners_attrs(data: dict[str, Any]) -> dict[str, Any]:
    pc = data.get("partners")
    items = pc.get("partner_connections") if isinstance(pc, dict) else None
    return {
        "parceiros": [
            {"nome": (i.get("partner") or {}).get("name"), "conectado_em": _br(i.get("connected_at"))}
            for i in items or []
            if isinstance(i, dict)
        ]
    }


def _unit_attrs(data: dict[str, Any]) -> dict[str, Any]:
    loc = _cs_user(data).get("location") or {}
    occ = data.get("occupancy") if isinstance(data.get("occupancy"), dict) else {}
    oloc = occ.get("location") or {}
    return {
        "acronym": loc.get("acronym") or _profile(data).get("location_acronym"),
        "endereco": loc.get("address") or oloc.get("address"),
        "bairro": loc.get("region"),
        "cidade": f"{loc.get('city_name')}/{loc.get('state_uf')}" if loc.get("city_name") else None,
        "cep": loc.get("zipcode"),
        "inaugurada_em": _brd(loc.get("real_opening_date")),
        "categoria": loc.get("tier_membership"),
        "franquia": loc.get("franchise"),
        "aceita_pix": loc.get("allow_pix_issue"),
        "aceita_boleto": loc.get("allow_bank_slip_issue"),
        "limite_convidados": loc.get("limit_guests"),
    }


def _guests_attrs(data: dict[str, Any]) -> dict[str, Any]:
    g = data.get("guests") if isinstance(data.get("guests"), dict) else {}
    return {
        "usados": g.get("used_guests"),
        "maximo": g.get("max_guests"),
        "renova_em": _br(g.get("renewal_date")),
        "convidados": [
            {"nome": x.get("name"), "bloqueado": x.get("blocked")}
            for x in g.get("guests") or []
            if isinstance(x, dict)
        ],
    }


# -- treino: frequência / anamnese -----------------------------------------


def _social_training(data: dict[str, Any]) -> dict[str, Any]:
    t = _social(data).get("training")
    return t if isinstance(t, dict) else {}


def _week_frequency(data: dict[str, Any]) -> Any:
    return _social_training(data).get("frequency_in_week")


def _week_frequency_attrs(data: dict[str, Any]) -> dict[str, Any]:
    t = _social_training(data)
    wk = _stats(data).get("weekly_training_streak") or {}
    feed = data.get("feed") if isinstance(data.get("feed"), dict) else {}
    brief = next(
        (w.get("metadata") or {} for w in feed.get("widgets") or [] if isinstance(w, dict) and w.get("id") == "engagement_brief"),
        {},
    )
    return {
        "esperada": t.get("expected_frequency"),
        "semanas_consecutivas": t.get("consecutive_frequency"),
        "treinos_na_semana": t.get("sessions_in_week"),
        "proxima_atualizacao": _br(wk.get("update_in")),
        "total_sessoes": t.get("total_sessions"),
        "aulas_coletivas_feitas": brief.get("total_group_classes"),
        "hits_feitos": brief.get("total_hit_done"),
    }


def _anamnese_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    a = data.get("anamnese")
    items = a.get("last_anamnesis") if isinstance(a, dict) else None
    return [i for i in items or [] if isinstance(i, dict)]


def _anamnese_value(data: dict[str, Any]) -> Any:
    """Objetivo se houver; senão a ênfase do treino; senão a 1ª resposta."""
    items = _anamnese_items(data)
    for needle in ("objetivo", "ênfase", "enfase"):
        for i in items:
            if needle in str(i.get("review_label", "")).lower():
                return i.get("value")
    return items[0].get("value") if items else None


def _anamnese_attrs(data: dict[str, Any]) -> dict[str, Any]:
    return {str(i.get("review_label")): i.get("value") for i in _anamnese_items(data)}


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
        attrs_fn=_unit_attrs,
        device=DEVICE_UNIT,
    ),
    SmartFitSensorDescription(
        key="trainings_month",
        device=DEVICE_TRAINING,
        name="Treinos no mês",
        icon="mdi:calendar-check",
        native_unit_of_measurement="treinos",
        value_fn=_month_count,
    ),
    SmartFitSensorDescription(
        key="minutes_month",
        device=DEVICE_TRAINING,
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
        attrs_fn=_sessions_attrs,
        device=DEVICE_TRAINING,
    ),
    SmartFitSensorDescription(
        key="weekly_streak",
        device=DEVICE_TRAINING,
        name="Sequência semanal",
        icon="mdi:fire",
        native_unit_of_measurement="semanas",
        value_fn=_weekly_streak,
    ),
    SmartFitSensorDescription(
        key="training_progress",
        device=DEVICE_TRAINING,
        name="Progresso do treino",
        icon="mdi:progress-check",
        native_unit_of_measurement="%",
        value_fn=_progress,
        attrs_fn=_progress_attrs,
    ),
    SmartFitSensorDescription(
        key="last_training",
        device=DEVICE_TRAINING,
        name="Último treino",
        icon="mdi:dumbbell",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_training,
        attrs_fn=_last_training_attrs,
    ),
    SmartFitSensorDescription(
        key="occupancy",
        device=DEVICE_UNIT,
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
        attrs_fn=_guests_attrs,
    ),
    SmartFitSensorDescription(
        key="profile",
        name="Perfil",
        icon="mdi:account",
        value_fn=_profile_name,
        attrs_fn=_profile_attrs,
        picture_fn=_profile_picture,
    ),
    SmartFitSensorDescription(
        key="followers",
        name="Seguidores",
        icon="mdi:account-heart",
        native_unit_of_measurement="seguidores",
        value_fn=_followers,
        attrs_fn=_social_attrs,
    ),
    SmartFitSensorDescription(
        key="partners",
        name="Apps conectados",
        icon="mdi:link-variant",
        native_unit_of_measurement="apps",
        value_fn=_partners_count,
        attrs_fn=_partners_attrs,
    ),
    SmartFitSensorDescription(
        key="week_frequency",
        name="Treinos na semana",
        icon="mdi:calendar-week",
        native_unit_of_measurement="treinos",
        value_fn=_week_frequency,
        attrs_fn=_week_frequency_attrs,
        device=DEVICE_TRAINING,
    ),
    SmartFitSensorDescription(
        key="anamnese",
        name="Anamnese",
        icon="mdi:target",
        value_fn=_anamnese_value,
        attrs_fn=_anamnese_attrs,
        device=DEVICE_TRAINING,
    ),
    # -- ficha de treino / aulas
    SmartFitSensorDescription(
        key="current_training",
        device=DEVICE_TRAINING,
        name="Ficha de treino",
        icon="mdi:clipboard-list",
        value_fn=_training_value,
        attrs_fn=_training_attrs,
    ),
    SmartFitSensorDescription(
        key="next_group",
        device=DEVICE_TRAINING,
        name="Próximo treino",
        icon="mdi:arm-flex",
        value_fn=_next_group_value,
        attrs_fn=_next_group_attrs,
    ),
    SmartFitSensorDescription(
        key="training_expiry",
        device=DEVICE_TRAINING,
        name="Validade do treino",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.DATE,
        value_fn=_training_expiry,
    ),
    SmartFitSensorDescription(
        key="weekly_record",
        device=DEVICE_TRAINING,
        name="Recorde semanal",
        icon="mdi:trophy",
        native_unit_of_measurement="semanas",
        value_fn=_weekly_record,
    ),
    SmartFitSensorDescription(
        key="next_class",
        device=DEVICE_UNIT,
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
        super().__init__(coordinator, description.device)
        self.entity_description = description
        document = coordinator.config_entry.data.get("document", "")
        self._attr_unique_id = f"{document}_{description.key}"

    @property
    def entity_picture(self) -> str | None:
        """Foto (perfil)."""
        if self.entity_description.picture_fn is None:
            return None
        try:
            return self.entity_description.picture_fn(self.coordinator.data or {})
        except (KeyError, TypeError, ValueError):
            return None

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
