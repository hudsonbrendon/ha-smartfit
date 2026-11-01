"""Checagem mínima da lógica pura dos sensores (sem HA): rode `python -I tests/test_sensor_logic.py`.

Stuba `homeassistant.*` e importa sensor.py direto; dados sintéticos.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import sys
import types
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Fortaleza")


def _mod(name: str, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


@dataclasses.dataclass(frozen=True, kw_only=True)
class _Desc:
    key: str
    name: str | None = None
    icon: str | None = None
    device_class: str | None = None
    native_unit_of_measurement: str | None = None
    state_class: str | None = None


class _Enum:
    DATE = "date"
    TIMESTAMP = "timestamp"
    MONETARY = "monetary"
    TOTAL = "total"


class _dt:
    DEFAULT_TIME_ZONE = TZ

    @staticmethod
    def now():
        return datetime(2026, 11, 1, 10, 0, tzinfo=TZ)

    @staticmethod
    def utcnow():
        return datetime(2026, 11, 1, 13, 0, tzinfo=timezone.utc)

    @staticmethod
    def parse_datetime(s):
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None


def _load_sensor():
    _mod("homeassistant")
    _mod("homeassistant.components")
    _mod(
        "homeassistant.components.sensor",
        SensorEntity=object,
        SensorEntityDescription=_Desc,
        SensorDeviceClass=_Enum,
        SensorStateClass=_Enum,
    )
    _mod("homeassistant.core", HomeAssistant=object)
    _mod("homeassistant.helpers")
    _mod("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    _mod("homeassistant.util")
    sys.modules["homeassistant.util"].dt = _mod("homeassistant.util.dt", **_dt.__dict__)
    root = os.path.join(os.path.dirname(__file__), "..", "custom_components", "smart_fit")
    pkg = types.ModuleType("smart_fit")
    pkg.__path__ = [root]
    sys.modules["smart_fit"] = pkg
    _mod("smart_fit.data", SmartFitConfigEntry=object)
    _mod("smart_fit.entity", SmartFitEntity=type("SmartFitEntity", (), {}), DEVICE_ACCOUNT="account", DEVICE_TRAINING="training", DEVICE_UNIT="unit")
    spec = importlib.util.spec_from_file_location("smart_fit.sensor", os.path.join(root, "sensor.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["smart_fit.sensor"] = mod  # dataclasses (< 3.14) procura o módulo aqui
    spec.loader.exec_module(mod)
    return mod


def _epoch(y, m, d):
    return int(datetime(y, m, d, 12, tzinfo=TZ).timestamp())


DATA = {
    "training": {
        "weight_training": {
            "frequency": 3,
            "start_date": "2026-10-01",
            "finish_date": _epoch(2026, 11, 15),
            "weekly_streak": {"current_record": 7},
            "groups": [
                {"letter": "A", "label": "Pernas", "exercises": [{"title": "Leg", "series": 3, "repetitions": [8, 10], "interval": [45, 45], "smartfit_code": "09"}], "data": {"done_at": _epoch(2026, 10, 30)}},
                {"letter": "B", "label": "Peito", "exercises": [], "data": {"done_at": _epoch(2026, 10, 20)}},
                {"letter": "C", "label": "Costas", "exercises": [], "data": {}},
            ],
        }
    },
    "classes": {"schedule": [{"date": "2026-11-01", "classes": [
        {"name": "Cedo", "start_at": "2026-11-01T07:00:00.000-03:00"},
        {"name": "Tarde", "start_at": "2026-11-01T18:00:00.000-03:00", "teacher": "Ana", "room": "Sala 1", "duration": 30},
        {"name": "Noite", "start_at": "2026-11-01T20:00:00.000-03:00"},
    ]}]},
    "training_sessions": {"training_sessions": [
        {"training_group_id": 1, "done_at": "2026-10-13 19:13:25 UTC", "group": "B", "duration": 3600, "description": "Peito", "exercises_done": 9, "exercises_repetitions": 400},
    ]},
    "social": {"profile": {"followers": 4, "following": 1, "smartfit_at": "Cliente há 2 anos"}, "training": {"frequency_in_week": 2, "expected_frequency": 4}},
    "anamnese": {"last_anamnesis": [{"review_label": "Horário de treino", "value": "antes das 8:00"}, {"review_label": "Objetivo", "value": "Hipertrofia"}]},
    "partners": {"partner_connections": [{"connected_at": "2026-10-27 21:26:18 UTC", "partner": {"name": "GymRats"}}]},
    "guests": {"guests": [{"name": "Fulano", "blocked": False}], "used_guests": 0, "max_guests": 5, "renewal_date": "2026-12-01"},
    "personals": {"profiles": [{"name": "Ariane Souza", "expertise": ["Hipertrofia", "Emagrecimento"]}]},
    "unit": {
        "detail": {"data": {"id": "1043", "attributes": {"operational-status": "open", "latitude": "-5.92", "longitude": "-35.26", "picture-url": "http://foto"}}},
        "schedules": {"0": {"start_at": "05:00", "end_at": "23:00", "weekday": 1}, "6": {"start_at": "08:00", "end_at": "14:00", "weekday": 0}, "success": True},
    },
    "client_space": {
        "user": {"purchase": {"membership_price": "145.91", "plan": {"name": "Black"}, "confirmed_at": "2024-09-30T16:00:08.000-03:00", "expired_at": None}, "plan": {"status": "active"}, "wallet": {"masked_card_number": "534696XX-XXXX-3517", "payment_company_name": "Mastercard"}},
        "user_plan": {"payment_method": "Cartão de Crédito", "membership_due_date": "20"},
        "payed": [
            {"dueDate": "2026-09-20", "value": "141.19", "payed_at": "2026-09-20T00:00:00.000-03:00"},
            {"dueDate": "2026-10-20", "value": "141.19", "payed_at": "2026-10-20T00:00:00.000-03:00", "siteRpsPath": "http://r", "invoiceDescription": {"url": "http://nf", "params": [{"label": "Numnota", "value": "123"}]}},
        ],
        "scheduled": [{"dueDate": "2026-12-20", "value": "145.91"}, {"dueDate": "2026-11-20", "value": "145.91", "startAt": "2026-10-28", "endAt": "2026-11-27"}],
        "overdue": [{"dueDate": "2026-08-20", "value": "10.50", "barcode": "123"}],
    },
}


def main() -> None:
    s = _load_sensor()
    by = {d.key: d for d in s.SENSORS}
    v = lambda k: by[k].value_fn(DATA)  # noqa: E731
    a = lambda k: by[k].attrs_fn(DATA)  # noqa: E731

    assert {d.device for d in s.SENSORS} == {"account", "training", "unit"}
    assert v("current_training") == "ABC (3x/semana)"
    assert a("current_training")["validade"] == "15/11/2026", "datas em dd/mm/aaaa"
    assert a("total_trainings")["historico"][0]["data"] == "13/10/2026 16:13"
    assert v("week_frequency") == 2 and a("week_frequency")["esperada"] == 4
    assert v("anamnese") == "Hipertrofia"
    assert v("followers") == 4 and v("partners") == 1
    assert a("guests")["renova_em"] == "01/12/2026"
    assert a("current_training")["dias_para_vencer"] == 14
    assert v("next_group") == "C - Costas", "grupo nunca feito vem primeiro"
    assert str(v("training_expiry")) == "2026-11-15"
    assert v("weekly_record") == 7
    assert v("next_class").hour == 18 and a("next_class")["aulas_hoje"] == ["18:00 Tarde", "20:00 Noite"]

    assert v("membership_price") == 145.91
    assert a("membership_price")["dia_vencimento"] == "20"
    assert v("payment_card") == "Mastercard •••• 3517"
    assert str(v("next_payment")) == "2026-11-20", "escolhe o agendado mais próximo, não o 1º da lista"
    assert a("next_payment")["vencimento"] == "20/11/2026"
    assert a("total_paid")["historico"][0]["pago_em"] == "20/10/2026"
    assert a("next_payment")["dias_para_vencer"] == 19
    assert str(v("last_payment")) == "2026-10-20"
    assert a("last_payment")["nota_fiscal_numero"] == "123"
    assert v("total_paid") == 282.38
    assert v("overdue_payments") == 1 and a("overdue_payments")["total"] == 10.5

    # unidade / personais / plano
    assert v("unit_status") == "Aberta"
    assert v("unit_hours") == "08:00 às 14:00", "01/11/2026 é domingo (weekday 0)"
    assert a("unit_hours")["Segunda"] == "05:00 às 23:00" and a("unit_hours")["Sábado"] == "Fechada"
    assert a("unit")["latitude"] == -5.92 and by["unit"].picture_fn(DATA) == "http://foto"
    assert v("personal_trainers") == 1 and a("personal_trainers")["personais"][0]["especialidades"] == "Hipertrofia, Emagrecimento"
    assert v("plan_status") == "Ativo" and a("plan_status")["contratado_em"] == "30/09/2024"
    assert "latitude" not in by["unit"].attrs_fn({}), "sem coordenadas não polui o mapa"

    # estado de datas vira texto dd/mm/aaaa (o frontend formataria pelo idioma)
    def state(key):
        ent = object.__new__(s.SmartFitSensor)
        ent.entity_description = by[key]
        ent.coordinator = types.SimpleNamespace(data=DATA)
        return ent.native_value

    assert state("training_expiry") == "15/11/2026"
    assert state("next_payment") == "20/11/2026" and state("last_payment") == "20/10/2026"
    assert state("next_class") == "01/11/2026 18:00"
    assert state("last_training") == "13/10/2026 16:13"
    assert state("membership_price") == 145.91
    assert not any(d.device_class in ("date", "timestamp") for d in s.SENSORS)

    # dados ausentes não quebram
    for d in s.SENSORS:
        d.value_fn({})
        if d.attrs_fn:
            d.attrs_fn({})
    # calendários
    class CalendarEvent:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    _mod("homeassistant.components.calendar", CalendarEntity=type("CalendarEntity", (), {}), CalendarEntityDescription=_Desc, CalendarEvent=CalendarEvent)
    sys.modules["smart_fit.sensor"] = s
    root = os.path.join(os.path.dirname(__file__), "..", "custom_components", "smart_fit")
    spec = importlib.util.spec_from_file_location("smart_fit.calendar", os.path.join(root, "calendar.py"))
    cal = importlib.util.module_from_spec(spec)
    sys.modules["smart_fit.calendar"] = cal
    spec.loader.exec_module(cal)
    ev = {c.key: c.events_fn(DATA) for c in cal.CALENDARS}
    assert len(ev["trainings"]) == 1 and ev["trainings"][0].summary == "Treino B - Peito"
    assert len(ev["classes"]) == 3 and ev["classes"][1].summary == "Tarde"
    assert len(ev["payments"]) == 5 and "145,91" in ev["payments"][2].summary
    assert "28/10/2026 a 27/11/2026" in next(e.description for e in ev["payments"] if "28/10" in e.description)
    print(f"OK: {len(s.SENSORS)} sensores, {len(cal.CALENDARS)} calendários")


if __name__ == "__main__":
    main()
