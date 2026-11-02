"""Verificações de SLA compartilhado por todas as práticas ITSM."""
from datetime import datetime, timezone

import pytest

from itsm import db, sla


@pytest.fixture
def path(tmp_path):
    file = tmp_path / "sla.db"
    db.init_db(file)
    return file


def policy(**overrides):
    values = {
        "code": "SLA-BASE", "name": "SLA de referência de testes",
        "kind": "*", "priority": "*",
        "response_minutes": 30, "resolution_minutes": 90,
        "calendar": "24x7", "start_hour": "09:00", "end_hour": "18:00",
        "weekdays": "0,1,2,3,4", "holidays": "",
        "pause_states": ["waiting", "approval_pending", "awaiting_approval", "scheduled"],
        "active": True,
    }
    values.update(overrides)
    return values


def set_clock(monkeypatch, when):
    monkeypatch.setattr(db, "utc_now", lambda: when)


def test_auto_assigns_single_sla_policy_for_every_practice(path):
    pid = sla.create_policy(path, policy())
    for kind in db.KINDS:
        record_id = db.create_record(path, kind, {"title": "Teste"})
        record = db.get_record(path, record_id)
        assert record["sla_policy_id"] == pid
        assert "SLA-BASE" in record["sla_policy_snapshot"]
    assert sla.overview(path)["assigned"] == 4


def test_no_default_means_no_implicit_sla(path):
    id_ = db.create_record(path, "incident", {"title": "Sem acordo"})
    assert db.get_record(path, id_)["sla_policy_id"] is None
    assert sla.evaluate(path, id_) is None


def test_fallback_and_override_are_deterministic(path):
    all_id = sla.create_policy(path, policy())
    specific = sla.create_policy(path, policy(
        code="P1-INC", name="Crítico", kind="incident", priority="P1"
    ))
    incident_id = db.create_record(
        path, "incident", {"title": "Indisponibilidade", "priority": "P1"}
    )
    request_id = db.create_record(path, "request", {"title": "Solicitação", "priority": "P1"})
    assert db.get_record(path, incident_id)["sla_policy_id"] == specific
    assert db.get_record(path, request_id)["sla_policy_id"] == all_id


def test_approval_waiting_pause_and_resume(monkeypatch, path):
    sla.create_policy(path, policy())
    set_clock(monkeypatch, "2026-11-02T12:00:00+00:00")
    rid = db.create_record(path, "incident", {"title": "Roteador"})
    set_clock(monkeypatch, "2026-11-02T12:20:00+00:00")
    db.set_status(path, rid, "in_progress")
    set_clock(monkeypatch, "2026-11-02T12:40:00+00:00")
    db.set_status(path, rid, "waiting")
    set_clock(monkeypatch, "2026-11-02T13:40:00+00:00")
    db.set_status(path, rid, "in_progress")
    set_clock(monkeypatch, "2026-11-02T14:20:00+00:00")
    db.set_status(path, rid, "resolved")
    result = sla.evaluate(path, rid, "2026-11-02T18:00:00+00:00")
    assert result["response"]["elapsed_minutes"] == 20.0
    assert result["response"]["state"] == "met"
    assert result["resolution"]["elapsed_minutes"] == 80.0
    assert result["resolution"]["state"] == "met"


def test_breach_uses_elapsed_not_days(monkeypatch, path):
    sla.create_policy(path, policy(
        response_minutes=15, resolution_minutes=60
    ))
    set_clock(monkeypatch, "2026-11-02T12:00:00+00:00")
    rid = db.create_record(path, "problem", {"title": "Falha recorrente"})
    result = sla.evaluate(path, rid, "2026-11-02T13:30:00+00:00")
    assert result["response"]["breached"]
    assert result["resolution"]["breached"]
    assert sla.overview(path, "2026-11-02T13:30:00+00:00")["breached"] == 1


def test_business_calendar_weekends_and_holidays():
    p = sla.validate_policy(policy(
        calendar="business", holidays="2026-11-03",
        response_minutes=60, resolution_minutes=180
    ))
    monday = datetime.fromisoformat("2026-11-02T20:00:00+00:00")  # seg 17h BRT
    end = sla.add_minutes(monday, 120, p)  # seg 1h + quarta 1h
    assert end == datetime.fromisoformat("2026-11-04T13:00:00+00:00")
    assert sla.minutes_between(monday, end, p) == pytest.approx(120.0)
    friday = datetime.fromisoformat("2026-11-06T20:30:00+00:00")  # sex 17h30 BRT
    next_day = sla.add_minutes(friday, 60, p)
    assert next_day == datetime.fromisoformat("2026-11-09T12:30:00+00:00")


def test_policy_snapshot_survives_policy_change(monkeypatch, path):
    sla.create_policy(path, policy(response_minutes=30, resolution_minutes=90))
    set_clock(monkeypatch, "2026-11-02T12:00:00+00:00")
    rid = db.create_record(path, "incident", {"title": "Teste"})
    stored = sla.get_policy(path, db.get_record(path, rid)["sla_policy_id"])
    modified = policy(response_minutes=5, resolution_minutes=40)
    sla.update_policy(path, stored["id"], modified)
    assert sla.evaluate(path, rid, "2026-11-02T12:20:00+00:00")["response"]["target_minutes"] == 30


def test_manual_reassign_and_priority_conflict(monkeypatch, path):
    specific_id = sla.create_policy(path, policy(
        kind="incident", priority="P1", code="P1", name="P1"
    ))
    normal_id = sla.create_policy(path, policy(
        kind="incident", priority="P2", code="P2", name="P2"
    ))
    rid = db.create_record(path, "incident", {"title": "Teste", "priority": "P1"})
    with pytest.raises(ValueError, match="Prioridade mudou"):
        db.update_record(path, rid, {"priority": "P2"})
    db.update_record(path, rid, {"priority": "P2", "sla_policy_id": normal_id})
    assert db.get_record(path, rid)["sla_policy_id"] == normal_id
    with pytest.raises(ValueError, match="incompatível"):
        db.update_record(path, rid, {"sla_policy_id": specific_id})
    db.update_record(path, rid, {"sla_policy_id": 0})
    assert db.get_record(path, rid)["sla_policy_id"] is None


def test_schema_migration_is_idempotent(path):
    rid = db.create_record(path, "incident", {"title": "Legado"})
    db.init_db(path)
    assert db.get_record(path, rid)["title"] == "Legado"
    with db.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
