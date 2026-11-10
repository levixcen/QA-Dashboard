"""PostgreSQL database layer for the QA dashboard.

The rest of the app (main.py, reports.py, parse_allure.py) keeps writing SQL
the way it did for SQLite: "?" placeholders, rows readable by column name,
cursor.lastrowid after an INSERT. This module translates those calls for
PostgreSQL, so most of the application code did not have to change.

Setting (environment variable):
  DATABASE_URL   postgresql://user:password@host:5432/dbname?sslmode=require
  DB_POOL_MAX    optional, maximum open connections (default 10)

Rules:
1. Connections come from a pool, so many requests share a few connections.
2. Always close the connection you got from get_connection(). Closing returns
   it to the pool and rolls back anything that was not committed.
3. Schema changes go in MIGRATIONS (append only). The applied version is kept
   in the schema_version table.
"""
from __future__ import annotations

import os
import re
import threading

import psycopg
from psycopg_pool import ConnectionPool

# Bump nothing by hand: LATEST_VERSION follows the MIGRATIONS list.
ID_TABLES = {
    "users", "attachments", "manual_entries", "defects", "projects", "project_checklist",
}

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def database_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Example: "
            'export DATABASE_URL="postgresql://user:password@host/dbname?sslmode=require"'
        )
    # Some providers hand out the older "postgres://" prefix.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


# ---------------------------------------------------------------------------
# Rows that behave like sqlite3.Row: row["name"], row[0], dict(row), row.keys()
# ---------------------------------------------------------------------------

class Row:
    __slots__ = ("_keys", "_values")

    def __init__(self, keys, values):
        self._keys = keys
        self._values = values

    def __getitem__(self, item):
        if isinstance(item, (int, slice)):
            return self._values[item]
        try:
            return self._values[self._keys.index(item)]
        except ValueError:
            raise KeyError(item) from None

    def keys(self):
        return list(self._keys)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __contains__(self, item):
        return item in self._keys

    def __repr__(self):
        return f"Row({dict(zip(self._keys, self._values))})"


def _row_factory(cursor):
    if cursor.description is None:
        return lambda values: values
    keys = [c.name for c in cursor.description]
    return lambda values: Row(keys, tuple(values))


# ---------------------------------------------------------------------------
# SQLite style cursor and connection on top of psycopg
# ---------------------------------------------------------------------------

_INSERT_TABLE = re.compile(r"^\s*INSERT\s+INTO\s+([a-z_]+)", re.IGNORECASE)


def _translate(sql: str) -> str:
    """'?' placeholders become '%s'; literal '%' is escaped for psycopg."""
    return sql.replace("%", "%%").replace("?", "%s")


class Cursor:
    def __init__(self, raw):
        self._raw = raw
        self.lastrowid = None

    def execute(self, sql, params=None):
        text = _translate(sql)
        wants_id = False
        match = _INSERT_TABLE.match(sql)
        if (
            match
            and match.group(1).lower() in ID_TABLES
            and "RETURNING" not in sql.upper()
            and "ON CONFLICT" not in sql.upper()
        ):
            text = text.rstrip().rstrip(";") + " RETURNING id"
            wants_id = True
        self._raw.execute(text, tuple(params) if params is not None else None)
        if wants_id:
            row = self._raw.fetchone()
            self.lastrowid = row[0] if row else None
        return self

    def executemany(self, sql, seq):
        self._raw.executemany(_translate(sql), [tuple(p) for p in seq])
        return self

    def fetchone(self):
        return self._raw.fetchone()

    def fetchall(self):
        return self._raw.fetchall()

    def fetchmany(self, size=None):
        return self._raw.fetchmany(size) if size else self._raw.fetchmany()

    @property
    def rowcount(self):
        return self._raw.rowcount

    @property
    def description(self):
        return self._raw.description

    def __iter__(self):
        return iter(self._raw)

    def close(self):
        self._raw.close()


class Connection:
    """Stands in for the sqlite3 connection the old code expected."""

    def __init__(self, pool: ConnectionPool):
        self._pool = pool
        self._conn = pool.getconn()
        self._conn.row_factory = _row_factory
        self._released = False

    def cursor(self):
        return Cursor(self._conn.cursor())

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if self._released:
            return
        self._released = True
        try:
            self._conn.rollback()  # discards anything that was never committed
        finally:
            self._pool.putconn(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        self.close()

    def __del__(self):
        # Safety net: a code path that forgot close() must not leak the connection.
        try:
            self.close()
        except Exception:
            pass


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(
                    conninfo=database_url(),
                    min_size=1,
                    max_size=int(os.environ.get("DB_POOL_MAX", "10")),
                    kwargs={
                        # Needed for hosted poolers (Neon, Supabase) that do not
                        # keep server side prepared statements between requests.
                        "prepare_threshold": None,
                    },
                    check=ConnectionPool.check_connection,
                    open=True,
                    timeout=30,
                )
    return _pool


def get_connection() -> Connection:
    return Connection(_get_pool())


def close_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

UTC_NOW_TEXT = "to_char(now() at time zone 'utc', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')"

BASELINE_STATEMENTS = [
    f"""
    CREATE TABLE IF NOT EXISTS features (
        name TEXT PRIMARY KEY,
        archived INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT {UTC_NOW_TEXT},
        updated_at TEXT
    )""",
    f"""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT DEFAULT {UTC_NOW_TEXT}
    )""",
    """
    CREATE TABLE IF NOT EXISTS test_results (
        uuid TEXT PRIMARY KEY,
        name TEXT,
        full_name TEXT,
        status TEXT,
        module TEXT,
        suite TEXT,
        epic TEXT,
        story TEXT,
        feature TEXT,
        tc_id TEXT,
        start_ts BIGINT,
        stop_ts BIGINT,
        duration_ms BIGINT,
        run_date TEXT,
        error_message TEXT,
        severity TEXT
    )""",
    """
    CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        test_uuid TEXT REFERENCES test_results (uuid),
        attachment_name TEXT,
        file_path TEXT,
        type TEXT
    )""",
    f"""
    CREATE TABLE IF NOT EXISTS manual_entries (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        feature_name TEXT NOT NULL
            REFERENCES features(name) ON UPDATE CASCADE ON DELETE CASCADE,
        period TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('passed', 'failed')),
        description TEXT,
        evidence_path TEXT,
        evidence_type TEXT,
        evidence_size INTEGER,
        created_at TEXT DEFAULT {UTC_NOW_TEXT},
        severity TEXT,
        entry_date TEXT,
        updated_at TEXT
    )""",
    """
    CREATE TABLE IF NOT EXISTS defects (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        defect_code TEXT UNIQUE,
        description TEXT NOT NULL,
        severity TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        owner TEXT,
        raised_date TEXT,
        eta TEXT,
        impacted_tc_count INTEGER DEFAULT 0,
        module TEXT REFERENCES features(name) ON UPDATE CASCADE ON DELETE RESTRICT,
        created_at TEXT,
        closed_at TEXT,
        source_ref TEXT,
        cluster_id TEXT,
        updated_at TEXT
    )""",
    """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        name TEXT NOT NULL,
        module TEXT,
        owner TEXT,
        status TEXT,
        color TEXT,
        pct INTEGER DEFAULT 0,
        tc_done INTEGER DEFAULT 0,
        tc_failed INTEGER DEFAULT 0,
        tc_total INTEGER DEFAULT 0,
        target_date TEXT,
        note TEXT,
        created_at TEXT,
        archived INTEGER DEFAULT 0,
        updated_at TEXT
    )""",
    """
    CREATE TABLE IF NOT EXISTS module_meta (
        module TEXT PRIMARY KEY,
        pic TEXT,
        mitigation_plan TEXT,
        planned_tc_count INTEGER
    )""",
    """
    CREATE TABLE IF NOT EXISTS project_checklist (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id),
        text TEXT NOT NULL,
        done INTEGER DEFAULT 0,
        evidence_path TEXT,
        evidence_type TEXT,
        evidence_size INTEGER,
        assignees TEXT,
        created_at TEXT,
        updated_at TEXT,
        completed_at TEXT,
        due_date TEXT
    )""",
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        version INTEGER NOT NULL
    )""",
]

# Append only. Each entry is (version, list of SQL statements).
# Example for the future:
#   (2, ["ALTER TABLE projects ADD COLUMN budget INTEGER"]),
MIGRATIONS: list[tuple[int, list[str]]] = [
    # Version 2: evidence images live in the database, so a hosted server
    # needs no disk. name is the same file name the rest of the app already uses.
    (2, [
        """CREATE TABLE IF NOT EXISTS evidence_files (
            name TEXT PRIMARY KEY,
            content_type TEXT,
            size INTEGER,
            data BYTEA NOT NULL,
            created_at TEXT
        )""",
    ]),
]

LATEST_VERSION = max([1] + [v for v, _ in MIGRATIONS])

# The view. One result per logical test per Jakarta month: module plus
# (full_name if set, else name), newest start_ts wins, uuid breaks ties.
# DISTINCT ON does this in one pass, which stays fast on large tables.
VIEW_SQL = """
CREATE OR REPLACE VIEW executions AS
SELECT 'automated'::text AS source,
       a.uuid AS ref,
       a.module,
       a.name,
       a.status,
       a.severity,
       a.error_message,
       a.run_date,
       substr(a.run_date, 1, 7) AS period
FROM (
    SELECT DISTINCT ON (
               COALESCE(t.module, ''),
               COALESCE(NULLIF(t.full_name, ''), t.name, ''),
               substr(COALESCE(t.run_date, ''), 1, 7)
           )
           t.uuid, t.module, t.name, t.status, t.severity, t.error_message, t.run_date
    FROM test_results t
    ORDER BY COALESCE(t.module, ''),
             COALESCE(NULLIF(t.full_name, ''), t.name, ''),
             substr(COALESCE(t.run_date, ''), 1, 7),
             COALESCE(t.start_ts, 0) DESC,
             t.uuid DESC
) a
UNION ALL
SELECT 'manual'::text AS source,
       'manual-' || m.id AS ref,
       m.feature_name AS module,
       COALESCE(NULLIF(m.description, ''), 'Manual entry') AS name,
       m.status,
       COALESCE(m.severity, 'normal') AS severity,
       NULL::text AS error_message,
       COALESCE(m.entry_date, m.period || '-01') AS run_date,
       COALESCE(substr(m.entry_date, 1, 7), m.period) AS period
FROM manual_entries m
"""

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_test_results_module ON test_results(module)",
    "CREATE INDEX IF NOT EXISTS idx_test_results_run_date ON test_results(run_date)",
    "CREATE INDEX IF NOT EXISTS idx_test_results_latest "
    "ON test_results(module, full_name, name, start_ts)",
    "CREATE INDEX IF NOT EXISTS idx_attachments_test ON attachments(test_uuid)",
    "CREATE INDEX IF NOT EXISTS idx_manual_entries_feature ON manual_entries(feature_name, period)",
    "CREATE INDEX IF NOT EXISTS idx_defects_module_status ON defects(module, status)",
    "CREATE INDEX IF NOT EXISTS idx_defects_cluster ON defects(cluster_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_defects_source_ref "
    "ON defects(source_ref) WHERE source_ref IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_projects_archived ON projects(archived)",
    "CREATE INDEX IF NOT EXISTS idx_checklist_project ON project_checklist(project_id)",
]

# One number every worker process agrees on, so two servers starting at the
# same moment do not both try to create the schema.
_SCHEMA_LOCK_KEY = 74120931


def init_db():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_lock(?)", (_SCHEMA_LOCK_KEY,))
        try:
            for stmt in BASELINE_STATEMENTS:
                cur.execute(stmt)
            cur.execute(
                "INSERT INTO schema_version (id, version) VALUES (1, 1) "
                "ON CONFLICT (id) DO NOTHING"
            )
            cur.execute("SELECT version FROM schema_version WHERE id = 1")
            current = cur.fetchone()["version"]

            for version, statements in MIGRATIONS:
                if version <= current:
                    continue
                for stmt in statements:
                    cur.execute(stmt)
                cur.execute("UPDATE schema_version SET version = ? WHERE id = 1", (version,))
                print(f"[migration] applied version {version}")

            for stmt in INDEX_STATEMENTS:
                cur.execute(stmt)
            cur.execute(VIEW_SQL)

            # Defect codes (DEF-001, ...) come from a sequence. Make sure it
            # is never behind the highest code already stored.
            cur.execute("CREATE SEQUENCE IF NOT EXISTS defect_code_seq")
            cur.execute(
                "SELECT COALESCE(MAX(NULLIF(regexp_replace(defect_code, '[^0-9]', '', 'g'), '')::int), 0) AS m "
                "FROM defects"
            )
            highest = cur.fetchone()["m"]
            cur.execute("SELECT last_value, is_called FROM defect_code_seq")
            seq = cur.fetchone()
            current = seq["last_value"] if seq["is_called"] else 0
            if highest > current:
                cur.execute("SELECT setval('defect_code_seq', ?, true)", (highest,))
            conn.commit()
        finally:
            cur.execute("SELECT pg_advisory_unlock(?)", (_SCHEMA_LOCK_KEY,))
            conn.commit()
    finally:
        conn.close()

    conn = get_connection()
    try:
        sync_features_from_results(conn)
    finally:
        conn.close()


def sync_features_from_results(conn):
    """Registers every module name found in the Allure results as a feature.
    Existing rows, archived or not, are left alone."""
    conn.execute("""
        INSERT INTO features (name, archived)
        SELECT DISTINCT module, 0 FROM test_results WHERE COALESCE(module, '') != ''
        ON CONFLICT (name) DO NOTHING
    """)
    conn.commit()


def seed_if_empty():
    """Used to plant four sample projects. Real data only now: does nothing.
    Kept so main.py's startup call still works."""
    return None


# ---------------------------------------------------------------------------
# Evidence images (stored in the evidence_files table)
# ---------------------------------------------------------------------------
def save_evidence(cur, name: str, content_type, data: bytes) -> None:
    """Insert or replace one image. Runs inside the caller's transaction."""
    from timeutil import now_iso
    cur.execute(
        """INSERT INTO evidence_files (name, content_type, size, data, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (name) DO UPDATE SET
               content_type = EXCLUDED.content_type,
               size = EXCLUDED.size,
               data = EXCLUDED.data""",
        (name, content_type, len(data), data, now_iso()),
    )


def load_evidence(name: str):
    """Returns (content_type, bytes) or None."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT content_type, data FROM evidence_files WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            return None
        return row["content_type"], bytes(row["data"])
    finally:
        conn.close()


def delete_evidence(name: str) -> None:
    conn = get_connection()
    try:
        conn.cursor().execute("DELETE FROM evidence_files WHERE name = ?", (name,))
        conn.commit()
    finally:
        conn.close()