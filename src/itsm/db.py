"""Persistência SQLite e regras de negócio do MVP ITSM.

Nenhuma chamada da UI altera status diretamente no banco: os fluxos são validados aqui.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

KINDS = {
    "incident": ("INC", "Incidentes"),
    "request": ("REQ", "Requisições"),
    "change": ("CHG", "Mudanças"),
    "problem": ("PRB", "Problemas"),
}
TRANSITIONS = {
    "incident": {
        "new": ("triage", "in_progress", "cancelled"),
        "triage": ("in_progress", "cancelled"),
        "in_progress": ("waiting", "resolved"),
        "waiting": ("in_progress", "cancelled"),
        "resolved": ("closed", "reopened"),
        "reopened": ("in_progress",),
        "closed": (), "cancelled": (),
    },
    "request": {
        "new": ("approval_pending", "in_progress", "cancelled"),
        "approval_pending": ("approved", "rejected"),
        "approved": ("in_progress", "cancelled"),
        "rejected": ("cancelled",),
        "in_progress": ("waiting", "fulfilled"),
        "waiting": ("in_progress", "cancelled"),
        "fulfilled": ("closed", "reopened"),
        "reopened": ("in_progress",),
        "closed": (), "cancelled": (),
    },
    "change": {
        "draft": ("assessment", "cancelled"),
        "assessment": ("awaiting_approval", "cancelled"),
        "awaiting_approval": ("scheduled", "rejected"),
        "rejected": ("assessment", "cancelled"),
        "scheduled": ("implementing", "cancelled"),
        "implementing": ("review", "rolled_back"),
        "rolled_back": ("review",),
        "review": ("closed", "implementing"),
        "closed": (), "cancelled": (),
    },
    "problem": {
        "new": ("investigating", "cancelled"),
        "investigating": ("known_error", "resolved"),
        "known_error": ("investigating", "resolved"),
        "resolved": ("closed", "reopened"),
        "reopened": ("investigating",),
        "closed": (), "cancelled": (),
    },
}
INITIAL_STATUS = {"incident": "new", "request": "new", "change": "draft", "problem": "new"}
PRIORITIES = ("P1", "P2", "P3", "P4")
ASSET_STATUSES = ("active", "stock", "maintenance", "retired")
RECORD_EDIT_FIELDS = (
    "title", "description", "requester", "assignee", "category", "priority",
    "asset_id", "problem_id", "sla_policy_id", "target_at", "risk", "implementation_plan",
    "rollback_plan", "planned_start", "planned_end", "resolution",
)
ASSET_FIELDS = ("tag", "name", "asset_type", "serial", "owner", "location", "status", "notes")

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT '',
    serial TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    kind TEXT NOT NULL CHECK(kind IN ('incident','request','change','problem')),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    requester TEXT NOT NULL DEFAULT '',
    assignee TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'P3',
    asset_id INTEGER REFERENCES assets(id) ON DELETE RESTRICT,
    problem_id INTEGER REFERENCES records(id) ON DELETE RESTRICT,
    target_at TEXT NOT NULL DEFAULT '',
    risk TEXT NOT NULL DEFAULT '',
    implementation_plan TEXT NOT NULL DEFAULT '',
    rollback_plan TEXT NOT NULL DEFAULT '',
    planned_start TEXT NOT NULL DEFAULT '',
    planned_end TEXT NOT NULL DEFAULT '',
    resolution TEXT NOT NULL DEFAULT '',
    approval_status TEXT NOT NULL DEFAULT 'not_requested',
    approved_by TEXT NOT NULL DEFAULT '',
    approved_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_records_kind_status ON records(kind, status);
CREATE INDEX IF NOT EXISTS ix_records_asset ON records(asset_id);
CREATE INDEX IF NOT EXISTS ix_records_problem ON records(problem_id);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_entity ON audit(entity_type, entity_id);
"""

def default_database_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    return base / "PT2VHF" / "ITSM" / "itsm.db"

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

@contextmanager
def connect(path: str | Path):
    con = sqlite3.connect(str(path), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=10000")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_db(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript(SCHEMA)
        from itsm import sla, cmdb
        sla.init_schema(db)
        cmdb.init_schema(db)
    return path

def row_dict(row):
    return dict(row) if row is not None else None

def record_audit(db, entity_type, entity_id, action, actor, before, after):
    db.execute(
        "INSERT INTO audit(entity_type,entity_id,action,actor,before_json,after_json,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (entity_type, entity_id, action, actor.strip() or "local",
         json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), utc_now()),
    )

def validate_date(value, field):
    if value:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field}: use a data AAAA-MM-DD.") from exc

def clean_record(payload, is_new=False):
    if not isinstance(payload, dict):
        raise ValueError("Dados inválidos.")
    if set(payload) - set(RECORD_EDIT_FIELDS):
        raise ValueError("Tentativa de alterar campo protegido.")
    values = {}
    for key, value in payload.items():
        if key in ("asset_id", "problem_id", "sla_policy_id"):
            values[key] = int(value) if value else None
        else:
            values[key] = str(value or "").strip()
    if is_new and not values.get("title"):
        raise ValueError("Título é obrigatório.")
    if "title" in values and not values["title"]:
        raise ValueError("Título é obrigatório.")
    if "priority" in values and values["priority"] not in PRIORITIES:
        raise ValueError("Prioridade inválida.")
    for field in ("target_at", "planned_start", "planned_end"):
        if field in values:
            validate_date(values[field], field)
    if values.get("planned_end") and values.get("planned_start"):
        if values["planned_end"] < values["planned_start"]:
            raise ValueError("Fim planejado anterior ao início.")
    return values

def validate_problem_link(db, problem_id, record_id=None):
    if problem_id is None:
        return
    row = db.execute("SELECT id,kind FROM records WHERE id=?", (problem_id,)).fetchone()
    if row is None or row["kind"] != "problem" or problem_id == record_id:
        raise ValueError("Problema relacionado inválido.")

def get_record(path, record_id):
    with connect(path) as db:
        return row_dict(db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone())

def create_record(path, kind, data, actor="local"):
    if kind not in KINDS:
        raise ValueError("Tipo de registro inválido.")
    from itsm import sla, cmdb
    raw = dict(data)
    ci_ids = raw.pop("ci_ids", [])
    values = clean_record(raw, is_new=True)
    explicit_sla = "sla_policy_id" in values
    sla_id = values.pop("sla_policy_id", None)
    now = utc_now()
    with connect(path) as db:
        validate_problem_link(db, values.get("problem_id"))
        payload = {
            "kind": kind, "title": values["title"],
            "status": INITIAL_STATUS[kind], "created_at": now, "updated_at": now,
            **values,
        }
        columns = ", ".join(payload)
        marks = ", ".join("?" for _ in payload)
        cur = db.execute(f"INSERT INTO records({columns}) VALUES({marks})", tuple(payload.values()))
        record_id = cur.lastrowid
        code = f"{KINDS[kind][0]}-{record_id:06d}"
        db.execute("UPDATE records SET code=? WHERE id=?", (code, record_id))
        sla.assign_record(db, record_id, kind, values.get("priority", "P3"),
                          requested=sla_id, automatic=not explicit_sla, at=now)
        if ci_ids:
            cmdb._set_record_cis(db, record_id, ci_ids, actor)
        after = row_dict(db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone())
        record_audit(db, "record", record_id, "created", actor, {}, after)
    return record_id

def update_record(path, record_id, data, actor="local"):
    from itsm import sla, cmdb
    raw = dict(data)
    explicit_cis = "ci_ids" in raw
    ci_ids = raw.pop("ci_ids", [])
    values = clean_record(raw)
    explicit_sla = "sla_policy_id" in values
    sla_id = values.pop("sla_policy_id", None)
    if not values and not explicit_sla and not explicit_cis:
        return
    with connect(path) as db:
        before = row_dict(db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone())
        if before is None:
            raise ValueError("Registro não encontrado.")
        if "problem_id" in values:
            validate_problem_link(db, values["problem_id"], record_id)
        changed = {key: val for key, val in values.items() if before[key] != val}
        # Se a prioridade mudou, a política atual deve continuar compatível.
        # A troca de SLA exige decisão explícita; não trocar silenciosamente.
        if "priority" in changed and before["sla_policy_snapshot"] and not explicit_sla:
            snapshot = json.loads(before["sla_policy_snapshot"])
            if snapshot["priority"] not in ("*", changed["priority"]):
                raise ValueError(
                    "Prioridade mudou: selecione uma política SLA compatível ou Sem SLA."
                )
        if not changed and not explicit_sla and not explicit_cis:
            return
        if changed:
            changed["updated_at"] = utc_now()
            assignments = ", ".join(f"{key}=?" for key in changed)
            db.execute(f"UPDATE records SET {assignments} WHERE id=?",
                       (*changed.values(), record_id))
        if explicit_sla:
            effective_priority = changed.get("priority", before["priority"])
            sla.assign_record(db, record_id, before["kind"], effective_priority,
                              requested=sla_id, automatic=False)
        if explicit_cis:
            cmdb._set_record_cis(db, record_id, ci_ids, actor)
        after = row_dict(db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone())
        record_audit(db, "record", record_id, "updated", actor, before, after)

def allowed_next(record):
    options = TRANSITIONS[record["kind"]][record["status"]]
    if record["kind"] == "request" and record["status"] == "approval_pending":
        return ()
    if record["kind"] == "change" and record["status"] == "awaiting_approval":
        return ("scheduled",) if record["approval_status"] == "approved" else ()
    return options

def set_status(path, record_id, status, actor="local"):
    with connect(path) as db:
        before = row_dict(db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone())
        if before is None:
            raise ValueError("Registro não encontrado.")
        if status not in allowed_next(before):
            raise ValueError(f"Transição não permitida: {before['status']} -> {status}")
        changes = {"status": status, "updated_at": utc_now()}
        if status in ("approval_pending", "awaiting_approval"):
            changes.update(approval_status="pending", approved_by="", approved_at="")
        if before["kind"] == "change" and status == "implementing":
            if not before["implementation_plan"] or not before["rollback_plan"]:
                raise ValueError("Mudança exige plano de implementação e de reversão.")
        if before["kind"] == "change" and status == "scheduled":
            if not before["planned_start"] or not before["planned_end"]:
                raise ValueError("Mudança exige janela planejada para agendamento.")
        assignments = ", ".join(f"{k}=?" for k in changes)
        db.execute(f"UPDATE records SET {assignments} WHERE id=?",
                   (*changes.values(), record_id))
        after = row_dict(db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone())
        record_audit(db, "record", record_id, "status", actor, before, after)

def decide_approval(path, record_id, approve: bool, approver: str):
    approver = str(approver).strip()
    if not approver:
        raise ValueError("Identificação do aprovador obrigatória.")
    with connect(path) as db:
        before = row_dict(db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone())
        if before is None:
            raise ValueError("Registro não encontrado.")
        kind, status = before["kind"], before["status"]
        if not ((kind == "request" and status == "approval_pending") or
                (kind == "change" and status == "awaiting_approval")):
            raise ValueError("Registro não está aguardando aprovação.")
        if before["approval_status"] != "pending":
            raise ValueError("Esta aprovação já foi decidida.")
        new_status = status if kind == "change" and approve else (
            "approved" if approve else "rejected"
        )
        now = utc_now()
        db.execute(
            "UPDATE records SET status=?,approval_status=?,approved_by=?,approved_at=?,updated_at=? WHERE id=?",
            (new_status, "approved" if approve else "rejected", approver, now, now, record_id),
        )
        after = row_dict(db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone())
        record_audit(db, "record", record_id, "approved" if approve else "rejected",
                     approver, before, after)

def list_records(path, kind=None, query=""):
    if kind is not None and kind not in KINDS:
        raise ValueError("Tipo inválido.")
    sql = (
        "SELECT r.*, a.tag AS asset_tag, p.code AS problem_code, "
        "(SELECT count(*) FROM record_cis rc WHERE rc.record_id=r.id) AS ci_count "
        "FROM records r LEFT JOIN assets a ON a.id=r.asset_id "
        "LEFT JOIN records p ON p.id=r.problem_id WHERE 1=1"
    )
    args = []
    if kind:
        sql += " AND r.kind=?"
        args.append(kind)
    if query:
        sql += " AND (r.code LIKE ? OR r.title LIKE ? OR r.requester LIKE ? OR r.assignee LIKE ?)"
        args.extend([f"%{query}%"] * 4)
    sql += " ORDER BY r.updated_at DESC, r.id DESC"
    with connect(path) as db:
        return [dict(row) for row in db.execute(sql, args)]

def list_assets(path, query=""):
    sql = "SELECT * FROM assets WHERE 1=1"
    args = []
    if query:
        sql += " AND (tag LIKE ? OR name LIKE ? OR serial LIKE ? OR owner LIKE ?)"
        args = [f"%{query}%"] * 4
    sql += " ORDER BY name COLLATE NOCASE, id"
    with connect(path) as db:
        return [dict(row) for row in db.execute(sql, args)]

def get_asset(path, asset_id):
    with connect(path) as db:
        return row_dict(db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone())

def clean_asset(payload, is_new=False):
    if set(payload) - set(ASSET_FIELDS):
        raise ValueError("Campo de ativo inválido.")
    data = {k: str(v or "").strip() for k, v in payload.items()}
    if (is_new or "tag" in data) and not data.get("tag"):
        raise ValueError("Patrimônio/identificador do ativo é obrigatório.")
    if (is_new or "name" in data) and not data.get("name"):
        raise ValueError("Nome do ativo é obrigatório.")
    if "status" in data and data["status"] not in ASSET_STATUSES:
        raise ValueError("Status do ativo inválido.")
    return data

def create_asset(path, data, actor="local"):
    values = clean_asset(data, is_new=True)
    now = utc_now()
    values.update(created_at=now, updated_at=now)
    with connect(path) as db:
        cols = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        cur = db.execute(f"INSERT INTO assets({cols}) VALUES({placeholders})",
                         tuple(values.values()))
        asset_id = cur.lastrowid
        after = row_dict(db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone())
        record_audit(db, "asset", asset_id, "created", actor, {}, after)
    return asset_id

def update_asset(path, asset_id, data, actor="local"):
    values = clean_asset(data)
    with connect(path) as db:
        before = row_dict(db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone())
        if before is None:
            raise ValueError("Ativo não encontrado.")
        changed = {k: v for k, v in values.items() if before[k] != v}
        if not changed:
            return
        changed["updated_at"] = utc_now()
        assignments = ", ".join(f"{k}=?" for k in changed)
        db.execute(f"UPDATE assets SET {assignments} WHERE id=?", (*changed.values(), asset_id))
        after = row_dict(db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone())
        record_audit(db, "asset", asset_id, "updated", actor, before, after)

def list_audit(path, limit=300):
    with connect(path) as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)
        )]

def dashboard(path):
    with connect(path) as db:
        totals = {kind: 0 for kind in KINDS}
        for row in db.execute("SELECT kind,COUNT(*) AS n FROM records GROUP BY kind"):
            totals[row["kind"]] = row["n"]
        active_assets = db.execute(
            "SELECT COUNT(*) FROM assets WHERE status='active'").fetchone()[0]
        pending = db.execute(
            "SELECT COUNT(*) FROM records WHERE approval_status='pending'").fetchone()[0]
        open_count = db.execute(
            "SELECT COUNT(*) FROM records WHERE status NOT IN ('closed','cancelled','rejected')"
        ).fetchone()[0]
        overdue = db.execute(
            "SELECT COUNT(*) FROM records WHERE target_at<>'' AND target_at<date('now','localtime') "
            "AND status NOT IN ('closed','cancelled','rejected','resolved','fulfilled')"
        ).fetchone()[0]
    return dict(totals, active_assets=active_assets, pending_approvals=pending,
                open_records=open_count, overdue=overdue)
