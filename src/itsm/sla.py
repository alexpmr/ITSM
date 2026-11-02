"""Mecanismo transversal de SLA para o MVP PT2VHF ITSM.

Políticas versionadas por snapshot no registro. A medição é reconstituída
a partir dos estados auditados; relógio de negócio em America/Sao_Paulo.
Não substitui gestão contratual de SLA, OLA ou XLA.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from itsm import db

TIMEZONE = "America/Sao_Paulo"
CALENDARS = ("24x7", "business")
STOP_STATES = {
    "incident": frozenset(("resolved", "closed", "cancelled")),
    "request": frozenset(("fulfilled", "closed", "rejected", "cancelled")),
    "change": frozenset(("closed", "cancelled")),
    "problem": frozenset(("resolved", "closed", "cancelled")),
}
COMPLETE_STATES = {
    "incident": frozenset(("resolved", "closed")),
    "request": frozenset(("fulfilled", "closed")),
    "change": frozenset(("closed",)),
    "problem": frozenset(("resolved", "closed")),
}
INITIAL = {"incident": "new", "request": "new", "change": "draft", "problem": "new"}
DEFAULT_PAUSE = {
    "incident": ("waiting",),
    "request": ("waiting", "approval_pending"),
    "change": ("awaiting_approval", "scheduled"),
    "problem": (),
}
POLICY_FIELDS = (
    "code", "name", "kind", "priority", "response_minutes", "resolution_minutes",
    "calendar", "start_hour", "end_hour", "weekdays", "holidays",
    "pause_states", "active",
)
POLICY_SCHEMA = """
CREATE TABLE IF NOT EXISTS sla_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    priority TEXT NOT NULL,
    response_minutes INTEGER NOT NULL CHECK(response_minutes > 0),
    resolution_minutes INTEGER NOT NULL CHECK(resolution_minutes > 0),
    calendar TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
    start_hour TEXT NOT NULL,
    end_hour TEXT NOT NULL,
    weekdays TEXT NOT NULL,
    holidays TEXT NOT NULL DEFAULT '',
    pause_states TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sla_match ON sla_policies(kind,priority,active);
"""

def init_schema(conn):
    """Migração idempotente sem sobrescrever nem descartar registros existentes."""
    conn.executescript(POLICY_SCHEMA)
    current = {
        row["name"] for row in conn.execute("PRAGMA table_info(records)")
    }
    if "sla_policy_id" not in current:
        conn.execute("ALTER TABLE records ADD COLUMN sla_policy_id INTEGER")
    if "sla_policy_snapshot" not in current:
        conn.execute("ALTER TABLE records ADD COLUMN sla_policy_snapshot TEXT NOT NULL DEFAULT ''")
    if "sla_started_at" not in current:
        conn.execute("ALTER TABLE records ADD COLUMN sla_started_at TEXT NOT NULL DEFAULT ''")
    conn.execute("PRAGMA user_version=2")

def parse_datetime(value):
    moment = datetime.fromisoformat(str(value))
    if moment.tzinfo is None:
        raise ValueError("Timestamp deve conter fuso horário.")
    return moment.astimezone(timezone.utc)

def clock(time_str):
    return time.fromisoformat(time_str)

def parse_weekdays(value):
    try:
        weekdays = tuple(sorted(set(int(x.strip()) for x in value.split(",") if x.strip())))
    except (TypeError, ValueError) as error:
        raise ValueError("Dias da semana: use 0,1,2,3,4 (segunda a sexta).") from error
    if not weekdays or any(d < 0 or d > 6 for d in weekdays):
        raise ValueError("Dias úteis inválidos: escolha números de 0 a 6.")
    return weekdays

def parse_holidays(value):
    if not value.strip():
        return set()
    try:
        return {date.fromisoformat(item.strip()) for item in value.split(",") if item.strip()}
    except ValueError as error:
        raise ValueError("Feriados: use AAAA-MM-DD separados por vírgula.") from error

def validate_policy(payload):
    if not isinstance(payload, dict) or set(payload) - set(POLICY_FIELDS):
        raise ValueError("Campos de política inválidos.")
    p = {
        "code": str(payload.get("code", "")).strip().upper(),
        "name": str(payload.get("name", "")).strip(),
        "kind": str(payload.get("kind", "*")).strip(),
        "priority": str(payload.get("priority", "*")).strip(),
        "calendar": str(payload.get("calendar", "business")).strip(),
        "start_hour": str(payload.get("start_hour", "09:00")).strip(),
        "end_hour": str(payload.get("end_hour", "18:00")).strip(),
        "weekdays": str(payload.get("weekdays", "0,1,2,3,4")).strip(),
        "holidays": str(payload.get("holidays", "")).strip(),
    }
    if not p["code"] or not p["name"]:
        raise ValueError("Código e nome da política são obrigatórios.")
    if p["kind"] not in (*db.KINDS, "*"):
        raise ValueError("Prática de SLA inválida.")
    if p["priority"] not in (*db.PRIORITIES, "*"):
        raise ValueError("Prioridade de SLA inválida.")
    if p["calendar"] not in CALENDARS:
        raise ValueError("Calendário inválido.")
    for attr in ("response_minutes", "resolution_minutes"):
        try:
            p[attr] = int(payload.get(attr))
        except (TypeError, ValueError) as error:
            raise ValueError("Metas devem ser minutos inteiros positivos.") from error
        if p[attr] <= 0 or p[attr] > 5256000:
            raise ValueError("As metas devem ser superiores a 0 e inferiores a 10 anos.")
    if p["resolution_minutes"] < p["response_minutes"]:
        raise ValueError("A meta de resolução não pode ser menor que a de resposta.")
    try:
        start, end = clock(p["start_hour"]), clock(p["end_hour"])
    except ValueError as error:
        raise ValueError("Horário deve usar HH:MM.") from error
    if start >= end:
        raise ValueError("O fim do expediente deve ser posterior ao início.")
    parse_weekdays(p["weekdays"])
    parse_holidays(p["holidays"])
    default_pause = DEFAULT_PAUSE.get(p["kind"], ()) if p["kind"] != "*" else ()
    pause = payload.get("pause_states", list(default_pause))
    if isinstance(pause, str):
        pause = [item.strip() for item in pause.split(",") if item.strip()]
    if not isinstance(pause, (tuple, list)) or any(not isinstance(s, str) for s in pause):
        raise ValueError("Estados de pausa devem ser uma lista.")
    valid = {s for kind, states in db.TRANSITIONS.items()
             if kind == p["kind"] or p["kind"] == "*"
             for s in states}
    if not set(pause) <= valid:
        raise ValueError("Há estados de pausa desconhecidos para esta prática.")
    p["pause_states"] = json.dumps(sorted(set(pause)), ensure_ascii=False)
    p["active"] = int(bool(payload.get("active", True)))
    p["timezone"] = TIMEZONE
    return p

def create_policy(path, payload, actor="local"):
    p = validate_policy(payload)
    now = db.utc_now()
    p.update(created_at=now, updated_at=now)
    with db.connect(path) as conn:
        cols = ", ".join(p)
        marks = ", ".join("?" for _ in p)
        cur = conn.execute(f"INSERT INTO sla_policies ({cols}) VALUES ({marks})",
                           tuple(p.values()))
        row = dict(conn.execute("SELECT * FROM sla_policies WHERE id=?",
                                (cur.lastrowid,)).fetchone())
        db.record_audit(conn, "sla_policy", cur.lastrowid, "created", actor, {}, row)
        return cur.lastrowid

def update_policy(path, policy_id, payload, actor="local"):
    p = validate_policy(payload)
    with db.connect(path) as conn:
        before_row = conn.execute("SELECT * FROM sla_policies WHERE id=?", (policy_id,)).fetchone()
        if before_row is None:
            raise ValueError("Política não encontrada.")
        before = dict(before_row)
        p["updated_at"] = db.utc_now()
        assignments = ", ".join(f"{key}=?" for key in p)
        conn.execute(f"UPDATE sla_policies SET {assignments} WHERE id=?",
                     (*p.values(), policy_id))
        after = dict(conn.execute("SELECT * FROM sla_policies WHERE id=?",
                                  (policy_id,)).fetchone())
        db.record_audit(conn, "sla_policy", policy_id, "updated", actor, before, after)

def list_policies(path, active_only=False):
    with db.connect(path) as conn:
        sql = "SELECT * FROM sla_policies"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY active DESC, kind, priority, code"
        return [dict(row) for row in conn.execute(sql)]

def get_policy(path, policy_id):
    with db.connect(path) as conn:
        row = conn.execute("SELECT * FROM sla_policies WHERE id=?", (policy_id,)).fetchone()
        return dict(row) if row else None

def select_default(conn, kind, priority):
    """Preferência por escopo específico, sem multiplicar relógios automaticamente."""
    return conn.execute(
        "SELECT * FROM sla_policies WHERE active=1 AND kind IN (?, '*') "
        "AND priority IN (?, '*') "
        "ORDER BY (kind=?) DESC, (priority=?) DESC, id ASC LIMIT 1",
        (kind, priority, kind, priority),
    ).fetchone()

def assign_record(conn, record_id, kind, priority, requested=None, automatic=True, at=None):
    """requested=0 remove SLA; None + automatic aplica política preferencial."""
    if automatic:
        policy = select_default(conn, kind, priority)
    elif not requested:
        policy = None
    else:
        policy = conn.execute(
            "SELECT * FROM sla_policies WHERE id=? AND active=1", (int(requested),)
        ).fetchone()
        if policy is None:
            raise ValueError("Política inexistente ou inativa.")
        if policy["kind"] not in ("*", kind) or policy["priority"] not in ("*", priority):
            raise ValueError("Política incompatível com tipo ou prioridade.")
    if policy is None:
        conn.execute(
            "UPDATE records SET sla_policy_id=NULL,sla_policy_snapshot='',sla_started_at='' WHERE id=?",
            (record_id,),
        )
        return
    snapshot = dict(policy)
    started = at or db.utc_now()
    conn.execute(
        "UPDATE records SET sla_policy_id=?, sla_policy_snapshot=?,sla_started_at=? WHERE id=?",
        (policy["id"], json.dumps(snapshot, ensure_ascii=False), started, record_id),
    )

def intervals(conn, record_id, record, start, now):
    """Interpreta linha do tempo de transições com timestamps UTC de auditoria."""
    events = [
        (parse_datetime(row["created_at"]),
         json.loads(row["after_json"]).get("status"))
        for row in conn.execute(
            "SELECT created_at,after_json FROM audit WHERE entity_type='record' "
            "AND entity_id=? AND action IN ('status','approved','rejected') ORDER BY id",
            (record_id,),
        )
    ]
    current = INITIAL[record["kind"]]
    cursor = parse_datetime(record["created_at"])
    for time_at, new_status in events:
        if time_at <= start and new_status is not None:
            current = new_status
            cursor = start
    cursor = start
    for time_at, new_status in events:
        if time_at <= start or new_status is None:
            continue
        if time_at > now:
            break
        if time_at > cursor:
            yield cursor, time_at, current
        current = new_status
        cursor = time_at
    if now > cursor:
        yield cursor, now, current

def minutes_between(begin, end, policy):
    """Minutos úteis no intervalo semiaberto [begin,end), inclusive segundos."""
    if end <= begin:
        return 0.0
    if policy["calendar"] == "24x7":
        return (end - begin).total_seconds() / 60.0
    zone = ZoneInfo(policy.get("timezone") or TIMEZONE)
    local_begin, local_end = begin.astimezone(zone), end.astimezone(zone)
    weekdays = set(parse_weekdays(policy["weekdays"]))
    holidays = parse_holidays(policy["holidays"])
    shift_start, shift_end = clock(policy["start_hour"]), clock(policy["end_hour"])
    result = 0.0
    day = local_begin.date()
    while day <= local_end.date():
        if day.weekday() in weekdays and day not in holidays:
            d1 = datetime.combine(day, shift_start, tzinfo=zone)
            d2 = datetime.combine(day, shift_end, tzinfo=zone)
            lo = max(begin, d1.astimezone(timezone.utc))
            hi = min(end, d2.astimezone(timezone.utc))
            if hi > lo:
                result += (hi - lo).total_seconds() / 60.0
        day += timedelta(days=1)
    return result

def add_minutes(begin, minutes, policy):
    """Retorna instante UTC após N minutos de calendário; para previsão sem pausas futuras."""
    if minutes <= 0:
        return begin
    if policy["calendar"] == "24x7":
        return begin + timedelta(minutes=minutes)
    zone = ZoneInfo(policy.get("timezone") or TIMEZONE)
    weekdays = set(parse_weekdays(policy["weekdays"]))
    holidays = parse_holidays(policy["holidays"])
    shift_start, shift_end = clock(policy["start_hour"]), clock(policy["end_hour"])
    remaining = float(minutes)
    day = begin.astimezone(zone).date()
    for _ in range(3660):  # segurança contra configuração impraticável
        if day.weekday() in weekdays and day not in holidays:
            window_start = datetime.combine(day, shift_start, tzinfo=zone).astimezone(timezone.utc)
            window_end = datetime.combine(day, shift_end, tzinfo=zone).astimezone(timezone.utc)
            lo = max(begin, window_start)
            available = max(0.0, (window_end - lo).total_seconds() / 60.0)
            if available >= remaining:
                return lo + timedelta(minutes=remaining)
            remaining -= available
        day += timedelta(days=1)
    raise ValueError("Calendário não oferece horas suficientes para esta meta.")

def _measure(conn, row, now):
    snapshot = row.get("sla_policy_snapshot") or ""
    if not snapshot:
        return None
    policy = json.loads(snapshot)
    start = parse_datetime(row["sla_started_at"] or row["created_at"])
    now = parse_datetime(now) if isinstance(now, str) else now.astimezone(timezone.utc)
    if now < start:
        raise ValueError("Instante de avaliação anterior à atribuição do SLA.")

    pause = set(json.loads(policy["pause_states"]))
    completed = COMPLETE_STATES[row["kind"]]
    stopped = STOP_STATES[row["kind"]]
    response_status = INITIAL[row["kind"]]
    elapsed_response = elapsed_resolution = 0.0
    response_at = completion_at = None
    current_state = INITIAL[row["kind"]]
    cursor = start
    audit = conn.execute(
        "SELECT action,created_at,after_json FROM audit WHERE entity_type='record' "
        "AND entity_id=? AND action IN ('status','approved','rejected') ORDER BY id",
        (row["id"],),
    ).fetchall()
    # Estados anteriores à atribuição não podem iniciar ou concluir o SLA novo.
    all_events = []
    for event in audit:
        event_at = parse_datetime(event["created_at"])
        status = json.loads(event["after_json"]).get("status")
        if status and event_at <= start:
            current_state = status
        elif status and event_at <= now:
            all_events.append((event_at, status))
    # Primeiro atendimento é a primeira transição operacional após início da contagem.
    for moment, new_state in [*all_events, (now, None)]:
        if moment < cursor:
            continue
        working = minutes_between(cursor, moment, policy)
        if current_state not in pause and current_state not in stopped:
            elapsed_resolution += working
        if response_at is None and current_state not in pause and current_state not in stopped:
            elapsed_response += working
        if new_state is not None:
            if response_at is None and new_state != response_status and new_state not in (
                "cancelled", "rejected"
            ):
                response_at = moment
            if new_state in completed:
                completion_at = moment
            if new_state in ("reopened", "implementing", "in_progress", "investigating"):
                if current_state in completed:
                    completion_at = None
            current_state = new_state
            cursor = moment

    cancelled = current_state in ("cancelled", "rejected")
    result = {}
    for name, elapsed, limit, finished in (
        ("response", elapsed_response, policy["response_minutes"], response_at is not None),
        ("resolution", elapsed_resolution, policy["resolution_minutes"],
         current_state in completed),
    ):
        breached = elapsed > float(limit) + 1e-7
        remaining = max(0.0, float(limit) - elapsed)
        paused = not finished and current_state in pause
        due = None
        if not finished and not paused and not cancelled and not breached:
            due = add_minutes(now, remaining, policy).isoformat(timespec="seconds")
        result[name] = {
            "elapsed_minutes": round(elapsed, 2),
            "target_minutes": int(limit),
            "remaining_minutes": round(remaining, 2),
            "breached": breached,
            "completed": finished,
            "paused": paused,
            "deadline_at": due,
            "state": "cancelled" if cancelled else
                     ("breached" if breached else "met" if finished else
                      "paused" if paused else "running"),
        }
    return {
        "policy_code": policy["code"], "policy_name": policy["name"],
        "started_at": start.isoformat(timespec="seconds"),
        "response": result["response"], "resolution": result["resolution"],
        "status": "breached" if any(metric["breached"] for metric in result.values())
                  else "on_track",
    }

def evaluate(path, record_id, now=None):
    with db.connect(path) as conn:
        row = conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
        if row is None:
            raise ValueError("Registro não encontrado.")
        return _measure(conn, dict(row), now or db.utc_now())

def evaluate_rows(path, records, now=None):
    when = now or db.utc_now()
    with db.connect(path) as conn:
        return {
            record["id"]: _measure(conn, record, when)
            for record in records
        }

def overview(path, now=None):
    with db.connect(path) as conn:
        records = [dict(row) for row in conn.execute(
            "SELECT * FROM records WHERE sla_policy_id IS NOT NULL"
        )]
        active = breached = paused = 0
        for row in records:
            status = _measure(conn, row, now or db.utc_now())
            if status is None:
                continue
            if status["status"] == "breached":
                breached += 1
            if (status["response"]["paused"] or status["resolution"]["paused"]):
                paused += 1
            if not (status["resolution"]["completed"] or
                    status["resolution"]["state"] == "cancelled"):
                active += 1
    return {"assigned": len(records), "active": active, "breached": breached, "paused": paused}
