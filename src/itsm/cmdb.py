"""CMDB transversal: CIs, vínculos M:N, dependências e análise de impacto.

Uma configuração representa um componente de serviço; um ativo representa
um recurso com ciclo patrimonial. Não existe criação implícita de ativos a
partir de CIs, nem reclassificação automática de impactos.
"""
from __future__ import annotations

from collections import deque
import sqlite3

from itsm import db

CI_TYPES = (
    "business_service", "technical_service", "application", "server",
    "database", "network", "cloud", "container", "endpoint", "other",
)
CI_STATUSES = ("planned", "active", "maintenance", "retired")
ENVIRONMENTS = ("production", "staging", "development", "test", "other")
CRITICALITIES = ("low", "medium", "high", "critical")
RELATION_TYPES = ("depends_on", "hosted_on", "supports", "connects_to")
RECORD_RELATIONS = ("affected", "target", "related")
CI_FIELDS = (
    "code", "name", "ci_type", "status", "environment", "criticality",
    "owner", "location", "service_name", "description", "asset_id",
)
DEPENDENCY = frozenset(("depends_on", "hosted_on"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS configuration_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    ci_type TEXT NOT NULL,
    status TEXT NOT NULL,
    environment TEXT NOT NULL,
    criticality TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    service_name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    asset_id INTEGER UNIQUE REFERENCES assets(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ci_name ON configuration_items(name);
CREATE INDEX IF NOT EXISTS ix_ci_service ON configuration_items(service_name);
CREATE TABLE IF NOT EXISTS ci_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_ci_id INTEGER NOT NULL REFERENCES configuration_items(id) ON DELETE RESTRICT,
    target_ci_id INTEGER NOT NULL REFERENCES configuration_items(id) ON DELETE RESTRICT,
    relation_type TEXT NOT NULL CHECK(
        relation_type IN ('depends_on','hosted_on','supports','connects_to')
    ),
    created_at TEXT NOT NULL,
    UNIQUE(source_ci_id, target_ci_id, relation_type),
    CHECK(source_ci_id != target_ci_id)
);
CREATE INDEX IF NOT EXISTS ix_ci_relation_target ON ci_relationships(target_ci_id);
CREATE TABLE IF NOT EXISTS record_cis (
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    ci_id INTEGER NOT NULL REFERENCES configuration_items(id) ON DELETE RESTRICT,
    link_type TEXT NOT NULL DEFAULT 'affected' CHECK(
        link_type IN ('affected','target','related')
    ),
    created_at TEXT NOT NULL,
    PRIMARY KEY(record_id, ci_id)
);
CREATE INDEX IF NOT EXISTS ix_record_cis_ci ON record_cis(ci_id);
"""

def init_schema(conn):
    """Migração incremental e idempotente: preserva v1/v2 e nunca apaga ativos."""
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA user_version=3")

def normalize_ci(data, new=False):
    if not isinstance(data, dict) or set(data) - set(CI_FIELDS):
        raise ValueError("Campos de CI inválidos.")
    fields = {}
    for key, value in data.items():
        if key == "asset_id":
            fields[key] = int(value) if value not in (None, "", 0, "0") else None
        else:
            fields[key] = str(value or "").strip()
    if "code" in fields:
        fields["code"] = fields["code"].upper()
    if new and (not fields.get("code") or not fields.get("name")):
        raise ValueError("Código e nome do CI são obrigatórios.")
    for key in ("code", "name"):
        if key in fields and not fields[key]:
            raise ValueError("Código e nome não podem ser vazios.")
    for key, allowed in (
        ("ci_type", CI_TYPES), ("status", CI_STATUSES),
        ("environment", ENVIRONMENTS), ("criticality", CRITICALITIES)
    ):
        if key in fields and fields[key] not in allowed:
            raise ValueError(f"Valor inválido para {key}: {fields[key]}")
    if new:
        defaults = {
            "ci_type": "other", "status": "active",
            "environment": "production", "criticality": "medium",
        }
        for key, value in defaults.items():
            fields.setdefault(key, value)
    return fields

def get_ci(path, ci_id):
    with db.connect(path) as con:
        row = con.execute("SELECT * FROM configuration_items WHERE id=?", (ci_id,)).fetchone()
        return dict(row) if row else None

def list_cis(path, query="", include_retired=True):
    sql = (
        "SELECT ci.*, a.tag AS asset_tag, "
        "(SELECT count(*) FROM record_cis rc WHERE rc.ci_id=ci.id) AS record_count "
        "FROM configuration_items ci LEFT JOIN assets a ON ci.asset_id=a.id WHERE 1=1"
    )
    args = []
    if query:
        sql += (" AND (ci.code LIKE ? OR ci.name LIKE ? OR ci.service_name LIKE ? "
                "OR ci.owner LIKE ? OR ci.ci_type LIKE ?)")
        args.extend([f"%{query}%"] * 5)
    if not include_retired:
        sql += " AND ci.status!='retired'"
    sql += " ORDER BY ci.name COLLATE NOCASE, ci.id"
    with db.connect(path) as con:
        return [dict(row) for row in con.execute(sql, args)]

def _require_ci(con, ci_id):
    row = con.execute("SELECT id FROM configuration_items WHERE id=?", (ci_id,)).fetchone()
    if row is None:
        raise ValueError(f"CI não encontrado: {ci_id}")

def create_ci(path, payload, actor="local"):
    fields = normalize_ci(payload, new=True)
    now = db.utc_now()
    fields.update(created_at=now, updated_at=now)
    with db.connect(path) as con:
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        cur = con.execute(f"INSERT INTO configuration_items({cols}) VALUES({marks})",
                          tuple(fields.values()))
        row = dict(con.execute("SELECT * FROM configuration_items WHERE id=?",
                               (cur.lastrowid,)).fetchone())
        db.record_audit(con, "ci", cur.lastrowid, "created", actor, {}, row)
        return cur.lastrowid

def update_ci(path, ci_id, payload, actor="local"):
    fields = normalize_ci(payload)
    with db.connect(path) as con:
        existing = con.execute("SELECT * FROM configuration_items WHERE id=?",
                               (ci_id,)).fetchone()
        if existing is None:
            raise ValueError("CI não encontrado.")
        before = dict(existing)
        updates = {key: val for key, val in fields.items() if val != before[key]}
        if not updates:
            return
        updates["updated_at"] = db.utc_now()
        sets = ", ".join(f"{key}=?" for key in updates)
        con.execute(f"UPDATE configuration_items SET {sets} WHERE id=?",
                    (*updates.values(), ci_id))
        after = dict(con.execute("SELECT * FROM configuration_items WHERE id=?",
                                 (ci_id,)).fetchone())
        db.record_audit(con, "ci", ci_id, "updated", actor, before, after)

def list_relations(path, ci_id=None):
    sql = (
        "SELECT rel.*, a.code AS source_code, a.name AS source_name, "
        "b.code AS target_code, b.name AS target_name "
        "FROM ci_relationships rel "
        "JOIN configuration_items a ON a.id=rel.source_ci_id "
        "JOIN configuration_items b ON b.id=rel.target_ci_id WHERE 1=1"
    )
    params = []
    if ci_id is not None:
        sql += " AND (rel.source_ci_id=? OR rel.target_ci_id=?)"
        params.extend([ci_id, ci_id])
    sql += " ORDER BY a.code, rel.relation_type, b.code"
    with db.connect(path) as con:
        return [dict(row) for row in con.execute(sql, params)]

def _dependency_edges(con):
    return [
        (row["source_ci_id"], row["target_ci_id"])
        for row in con.execute(
            "SELECT source_ci_id,target_ci_id FROM ci_relationships "
            "WHERE relation_type IN ('depends_on','hosted_on') "
            "UNION ALL SELECT target_ci_id,source_ci_id FROM ci_relationships "
            "WHERE relation_type='supports'"
        )
    ]

def _would_cycle(con, source, target):
    """Para dependência source -> target, proibir se target já depende de source."""
    adjacency = {}
    for a, b in _dependency_edges(con):
        adjacency.setdefault(a, set()).add(b)
    todo = [target]
    seen = set()
    while todo:
        node = todo.pop()
        if node == source:
            return True
        if node in seen:
            continue
        seen.add(node)
        todo.extend(adjacency.get(node, ()))
    return False

def add_relation(path, source, target, relation_type, actor="local"):
    source, target = int(source), int(target)
    if source == target:
        raise ValueError("Não é permitido relacionar um CI a ele próprio.")
    if relation_type not in RELATION_TYPES:
        raise ValueError("Tipo de relacionamento inválido.")
    with db.connect(path) as con:
        _require_ci(con, source)
        _require_ci(con, target)
        if relation_type == "connects_to":
            reverse = con.execute(
                "SELECT 1 FROM ci_relationships WHERE source_ci_id=? AND target_ci_id=? "
                "AND relation_type='connects_to'", (target, source)
            ).fetchone()
            if reverse:
                raise ValueError("O vínculo de conexão bidirecional já existe.")
        edge = (target, source) if relation_type == "supports" else (source, target)
        if relation_type != "connects_to" and _would_cycle(con, *edge):
            raise ValueError("O relacionamento criaria uma dependência circular.")
        cur = con.execute(
            "INSERT INTO ci_relationships(source_ci_id,target_ci_id,relation_type,created_at) "
            "VALUES(?,?,?,?)", (source, target, relation_type, db.utc_now())
        )
        after = dict(con.execute(
            "SELECT * FROM ci_relationships WHERE id=?", (cur.lastrowid,)
        ).fetchone())
        db.record_audit(con, "ci_relation", cur.lastrowid, "created", actor, {}, after)
        return cur.lastrowid

def remove_relation(path, relation_id, actor="local"):
    with db.connect(path) as con:
        row = con.execute("SELECT * FROM ci_relationships WHERE id=?", (relation_id,)).fetchone()
        if row is None:
            raise ValueError("Relacionamento não encontrado.")
        before = dict(row)
        con.execute("DELETE FROM ci_relationships WHERE id=?", (relation_id,))
        db.record_audit(con, "ci_relation", relation_id, "deleted", actor, before, {})

def normalize_record_links(items):
    """Entrada [(ci_id, tipo)] ou lista de IDs com tipo affected por padrão."""
    result = {}
    if not isinstance(items, (list, tuple)):
        raise ValueError("CIs do registro devem ser uma lista.")
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            ci_id, link_type = item
        else:
            ci_id, link_type = item, "affected"
        try:
            ci_id = int(ci_id)
        except (ValueError, TypeError) as error:
            raise ValueError("Identificador de CI inválido.") from error
        if ci_id < 1 or link_type not in RECORD_RELATIONS:
            raise ValueError("Vínculo de CI inválido.")
        if ci_id in result and result[ci_id] != link_type:
            raise ValueError("CI duplicado com tipos de vínculo conflitantes.")
        result[ci_id] = link_type
    return result

def _set_record_cis(con, record_id, items, actor):
    existing = {
        row["ci_id"]: row["link_type"]
        for row in con.execute(
            "SELECT ci_id,link_type FROM record_cis WHERE record_id=?", (record_id,)
        )
    }
    desired = normalize_record_links(items)
    for ci_id in desired:
        _require_ci(con, ci_id)
    if existing == desired:
        return False
    con.execute("DELETE FROM record_cis WHERE record_id=?", (record_id,))
    now = db.utc_now()
    for ci_id, link_type in desired.items():
        con.execute(
            "INSERT INTO record_cis(record_id,ci_id,link_type,created_at) VALUES(?,?,?,?)",
            (record_id, ci_id, link_type, now),
        )
    db.record_audit(con, "record_ci", record_id, "updated", actor,
                    [{"ci_id": k, "link_type": v} for k, v in sorted(existing.items())],
                    [{"ci_id": k, "link_type": v} for k, v in sorted(desired.items())])
    return True

def set_record_cis(path, record_id, items, actor="local"):
    with db.connect(path) as con:
        if con.execute("SELECT 1 FROM records WHERE id=?", (record_id,)).fetchone() is None:
            raise ValueError("Registro não encontrado.")
        _set_record_cis(con, record_id, items, actor)

def list_record_cis(path, record_id):
    with db.connect(path) as con:
        return [
            dict(row) for row in con.execute(
                "SELECT rc.*,ci.code,ci.name,ci.ci_type,ci.criticality "
                "FROM record_cis rc JOIN configuration_items ci ON ci.id=rc.ci_id "
                "WHERE rc.record_id=? ORDER BY ci.code", (record_id,),
            )
        ]

def list_ci_records(path, ci_id):
    with db.connect(path) as con:
        return [
            dict(row) for row in con.execute(
                "SELECT r.id,r.code,r.kind,r.title,r.status,r.priority,rc.link_type "
                "FROM record_cis rc JOIN records r ON r.id=rc.record_id "
                "WHERE rc.ci_id=? ORDER BY r.updated_at DESC", (ci_id,),
            )
        ]

def asset_cis(path, asset_id):
    with db.connect(path) as con:
        return [
            dict(row) for row in con.execute(
                "SELECT id,code,name,status FROM configuration_items "
                "WHERE asset_id=? ORDER BY code", (asset_id,)
            )
        ]

def impact(path, ci_id, max_depth=15):
    """CIs potencialmente afetados pela falha do CI escolhido (jusante).

    Um CI A 'depends_on' B implica que B pode impactar A.
    A 'supports' B implica que A pode impactar B.
    'connects_to' não implica dependência, logo não propaga impacto.
    """
    root_id = int(ci_id)
    with db.connect(path) as con:
        _require_ci(con, root_id)
        dependents = {}
        for dependent, dependency in _dependency_edges(con):
            dependents.setdefault(dependency, set()).add(dependent)
        depth = {root_id: 0}
        queue = deque([root_id])
        while queue:
            current = queue.popleft()
            if depth[current] >= max_depth:
                continue
            for downstream in sorted(dependents.get(current, ())):
                if downstream not in depth:
                    depth[downstream] = depth[current] + 1
                    queue.append(downstream)
        ids = sorted(depth)
        marks = ",".join("?" for _ in ids)
        cis = [
            dict(row) for row in con.execute(
                f"SELECT id,code,name,ci_type,status,criticality,service_name "
                f"FROM configuration_items WHERE id IN ({marks})", ids
            )
        ]
        records = [
            dict(row) for row in con.execute(
                f"SELECT DISTINCT r.id,r.code,r.kind,r.title,r.status,r.priority, "
                f"ci.code AS via_ci, rc.link_type "
                f"FROM record_cis rc JOIN records r ON r.id=rc.record_id "
                f"JOIN configuration_items ci ON ci.id=rc.ci_id "
                f"WHERE rc.ci_id IN ({marks}) ORDER BY r.code", ids
            )
        ]
    for item in cis:
        item["depth"] = depth[item["id"]]
    cis.sort(key=lambda ci: (ci["depth"], ci["code"]))
    return {"root_id": root_id, "cis": cis, "records": records}

def stats(path):
    with db.connect(path) as con:
        return {
            "cis": con.execute("SELECT COUNT(*) FROM configuration_items").fetchone()[0],
            "active": con.execute(
                "SELECT COUNT(*) FROM configuration_items WHERE status='active'"
            ).fetchone()[0],
            "relations": con.execute("SELECT COUNT(*) FROM ci_relationships").fetchone()[0],
            "linked_records": con.execute(
                "SELECT COUNT(DISTINCT record_id) FROM record_cis"
            ).fetchone()[0],
        }
