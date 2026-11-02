"""Teste funcional CMDB transversal, migração, impacto e invariantes."""
import sqlite3

import pytest

from itsm import cmdb, db, sla


@pytest.fixture
def path(tmp_path):
    target = tmp_path / "cmdb.db"
    db.init_db(target)
    return target


def ci(code, **overrides):
    row = {
        "code": code, "name": f"CI {code}", "ci_type": "application",
        "status": "active", "environment": "production",
        "criticality": "high", "owner": "Infraestrutura",
        "location": "DF", "service_name": "Serviço corporativo",
        "description": "",
    }
    row.update(overrides)
    return row


def test_cmdb_separate_from_itam_and_asset_reference(path):
    asset = db.create_asset(path, {"tag": "SW01", "name": "Switch de core"})
    first = cmdb.create_ci(path, ci("CI-SW01", asset_id=asset, ci_type="network"))
    assert cmdb.get_ci(path, first)["asset_id"] == asset
    assert cmdb.asset_cis(path, asset)[0]["code"] == "CI-SW01"
    assert db.get_asset(path, asset)["tag"] == "SW01"
    with pytest.raises(sqlite3.IntegrityError):
        cmdb.create_ci(path, ci("OUTRO", asset_id=asset))
    with pytest.raises(sqlite3.IntegrityError):
        cmdb.create_ci(path, ci("CI-SW01"))
    cmdb.update_ci(path, first, {"criticality": "critical", "name": "Switch principal"})
    assert cmdb.get_ci(path, first)["criticality"] == "critical"
    assert cmdb.stats(path) == {"cis": 1, "active": 1, "relations": 0, "linked_records": 0}


def test_ci_rejects_invalid_states_and_duplicate_code(path):
    with pytest.raises(ValueError, match="obrigatórios"):
        cmdb.create_ci(path, ci(""))
    with pytest.raises(ValueError, match="inválido"):
        cmdb.create_ci(path, ci("A", criticality="super-high"))
    with pytest.raises(ValueError, match="inválido"):
        cmdb.create_ci(path, ci("B", ci_type="hacker"))
    with pytest.raises(ValueError):
        cmdb.create_ci(path, ci("C", status="closed"))


def test_dependencies_and_impact_propagation(path):
    database = cmdb.create_ci(path, ci("DB", ci_type="database", criticality="critical"))
    app = cmdb.create_ci(path, ci("APP", ci_type="application"))
    service = cmdb.create_ci(path, ci("SVC", ci_type="business_service"))
    net = cmdb.create_ci(path, ci("NET", ci_type="network"))

    dep = cmdb.add_relation(path, app, database, "depends_on")
    cmdb.add_relation(path, service, app, "depends_on")
    cmdb.add_relation(path, database, net, "connects_to")
    result = cmdb.impact(path, database)
    assert [ci["code"] for ci in result["cis"]] == ["DB", "APP", "SVC"]
    assert [ci["depth"] for ci in result["cis"]] == [0, 1, 2]
    assert [ci["code"] for ci in cmdb.impact(path, net)["cis"]] == ["NET"]

    # A -> DB -> ... -> A seria circular e é recusado.
    with pytest.raises(ValueError, match="circular"):
        cmdb.add_relation(path, database, service, "depends_on")
    with pytest.raises(ValueError, match="próprio"):
        cmdb.add_relation(path, app, app, "supports")
    with pytest.raises(sqlite3.IntegrityError):
        cmdb.add_relation(path, app, database, "depends_on")
    with pytest.raises(ValueError, match="bidirecional"):
        cmdb.add_relation(path, net, database, "connects_to")

    cmdb.remove_relation(path, dep)
    assert [ci["code"] for ci in cmdb.impact(path, database)["cis"]] == ["DB"]


def test_supports_semantic_is_directional(path):
    platform = cmdb.create_ci(path, ci("PLATFORM"))
    service = cmdb.create_ci(path, ci("SERVICE"))
    cmdb.add_relation(path, platform, service, "supports")
    assert [ci["code"] for ci in cmdb.impact(path, platform)["cis"]] == [
        "PLATFORM", "SERVICE"
    ]
    assert [ci["code"] for ci in cmdb.impact(path, service)["cis"]] == ["SERVICE"]


def test_links_across_all_four_practices_and_history(path):
    host = cmdb.create_ci(path, ci("HOST"))
    app = cmdb.create_ci(path, ci("APP"))
    cmdb.add_relation(path, app, host, "hosted_on")
    record_ids = {}
    for kind in db.KINDS:
        role = "target" if kind == "change" else "affected"
        rid = db.create_record(path, kind, {
            "title": f"{kind} de exemplo",
            "ci_ids": [(app, role), (host, "related")],
        }, "operador")
        record_ids[kind] = rid
        assert len(cmdb.list_record_cis(path, rid)) == 2
        assert db.list_records(path, kind)[0]["ci_count"] == 2

    impacted = cmdb.impact(path, host)
    assert [ci["code"] for ci in impacted["cis"]] == ["HOST", "APP"]
    assert {r["kind"] for r in impacted["records"]} == set(db.KINDS)
    assert cmdb.stats(path)["linked_records"] == 4
    assert any(a["entity_type"] == "record_ci" for a in db.list_audit(path))

    rid = record_ids["change"]
    db.update_record(path, rid, {"ci_ids": [(host, "target")]}, "operador")
    assert [(ci["code"], ci["link_type"]) for ci in cmdb.list_record_cis(path, rid)] == [
        ("HOST", "target")
    ]
    assert cmdb.list_ci_records(path, app)
    db.update_record(path, rid, {"ci_ids": []}, "operador")
    assert cmdb.list_record_cis(path, rid) == []


def test_invalid_ci_link_rolls_back_record_creation(path):
    with pytest.raises(ValueError, match="CI não encontrado"):
        db.create_record(path, "incident", {
            "title": "Não deve existir", "ci_ids": [(9999, "affected")]
        })
    assert db.list_records(path, "incident") == []


def test_cmdb_migration_v2_to_v3_preserves_operational_records(tmp_path):
    path = tmp_path / "legacy.db"
    with db.connect(path) as con:
        con.executescript(db.SCHEMA)
        sla.init_schema(con)
    rid = db.create_record(path, "incident", {"title": "Registro v2"})
    db.init_db(path)
    db.init_db(path)
    with db.connect(path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 3
    assert db.get_record(path, rid)["title"] == "Registro v2"
    assert cmdb.list_record_cis(path, rid) == []
    assert db.list_audit(path)


def test_relational_restrictions_prevent_orphans(path):
    ci_id = cmdb.create_ci(path, ci("CI-EXEMPLO"))
    record_id = db.create_record(path, "problem", {
        "title": "Problema", "ci_ids": [ci_id],
    })
    with db.connect(path) as con:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("DELETE FROM configuration_items WHERE id=?", (ci_id,))
    assert cmdb.list_record_cis(path, record_id)


def test_map_marks_configuration_management_partial():
    from itsm.itil_catalog import counts, summary
    assert counts() == {"total": 34, "mvp": 7, "planned": 27}
    details = summary("service_configuration")
    assert details["status"] == "mvp"
    assert details["tab_index"] == 7
    assert "CMDB" in details["delivered"]
    assert summary("service_catalog")["status"] == "planned"
