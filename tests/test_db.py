import sqlite3

import pytest

from itsm import db

@pytest.fixture()
def path(tmp_path):
    target = tmp_path / "test.db"
    db.init_db(target)
    return target

def test_creates_each_practice_and_generates_unique_codes(path):
    ids = [db.create_record(path, kind, {"title": "Exemplo"}) for kind in db.KINDS]
    codes = [db.get_record(path, item_id)["code"] for item_id in ids]
    assert len(set(codes)) == 4
    assert [code[:3] for code in codes] == ["INC", "REQ", "CHG", "PRB"]
    assert db.dashboard(path)["open_records"] == 4

def test_incident_transition_and_audit(path):
    item = db.create_record(path, "incident", {"title": "Roteador parado"}, "tecnico")
    with pytest.raises(ValueError):
        db.set_status(path, item, "closed")
    db.set_status(path, item, "triage", "tecnico")
    db.set_status(path, item, "in_progress", "tecnico")
    db.set_status(path, item, "resolved", "tecnico")
    db.set_status(path, item, "closed", "tecnico")
    assert db.get_record(path, item)["status"] == "closed"
    assert len(db.list_audit(path)) == 5
    assert db.dashboard(path)["open_records"] == 0

def test_request_approval_is_explicit(path):
    item = db.create_record(path, "request", {"title": "Novo acesso"})
    db.set_status(path, item, "approval_pending")
    with pytest.raises(ValueError):
        db.set_status(path, item, "approved")
    with pytest.raises(ValueError):
        db.decide_approval(path, item, True, "")
    db.decide_approval(path, item, True, "gestor")
    assert db.get_record(path, item)["status"] == "approved"
    assert db.get_record(path, item)["approved_by"] == "gestor"
    with pytest.raises(ValueError):
        db.decide_approval(path, item, True, "gestor")

def test_change_requires_approval_window_and_plans(path):
    item = db.create_record(path, "change", {"title": "Atualizar servidores"})
    db.set_status(path, item, "assessment")
    db.set_status(path, item, "awaiting_approval")
    with pytest.raises(ValueError):
        db.set_status(path, item, "scheduled")
    db.decide_approval(path, item, True, "CAB")
    with pytest.raises(ValueError):
        db.set_status(path, item, "scheduled")
    db.update_record(path, item, {
        "planned_start": "2026-11-10", "planned_end": "2026-11-11",
        "implementation_plan": "Aplicar patch e validar serviços",
        "rollback_plan": "Restaurar snapshot e verificar integridade",
    })
    db.set_status(path, item, "scheduled")
    db.set_status(path, item, "implementing")
    db.set_status(path, item, "review")
    db.set_status(path, item, "closed")
    assert db.get_record(path, item)["status"] == "closed"

def test_change_implementation_needs_plans(path):
    item = db.create_record(path, "change", {
        "title": "Firewall", "planned_start": "2026-11-08", "planned_end": "2026-11-08"
    })
    for status in ("assessment", "awaiting_approval"):
        db.set_status(path, item, status)
    db.decide_approval(path, item, True, "gestor")
    db.set_status(path, item, "scheduled")
    with pytest.raises(ValueError, match="reversão"):
        db.set_status(path, item, "implementing")

def test_asset_link_and_problem_restrictions(path):
    asset = db.create_asset(path, {
        "tag": "SERV-01", "name": "Servidor", "status": "active"
    })
    problem = db.create_record(path, "problem", {"title": "Falha recorrente"})
    incident = db.create_record(path, "incident", {
        "title": "Reinicialização", "asset_id": asset, "problem_id": problem,
    })
    assert db.get_record(path, incident)["asset_id"] == asset
    assert db.list_records(path, "incident")[0]["problem_code"].startswith("PRB")
    with pytest.raises(ValueError):
        db.update_record(path, incident, {"problem_id": incident})
    with pytest.raises(sqlite3.IntegrityError):
        db.create_asset(path, {"tag": "SERV-01", "name": "Duplicado"})

def test_incorrect_dates_and_protected_status(path):
    item = db.create_record(path, "incident", {"title": "Teste"})
    with pytest.raises(ValueError):
        db.update_record(path, item, {"status": "closed"})
    with pytest.raises(ValueError):
        db.update_record(path, item, {"target_at": "31/12/2026"})
    with pytest.raises(ValueError):
        db.create_record(path, "change", {
            "title": "Janela", "planned_start": "2026-12-03", "planned_end": "2026-12-01"
        })

def test_search_update_asset_and_history(path):
    asset = db.create_asset(path, {"tag": "NTB-01", "name": "Notebook"})
    db.update_asset(path, asset, {"owner": "Suporte", "status": "maintenance"}, "operador")
    assert db.list_assets(path, "NTB")[0]["owner"] == "Suporte"
    assert db.dashboard(path)["active_assets"] == 0
    assert db.list_audit(path)[0]["actor"] == "operador"
