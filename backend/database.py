import sqlite3
from datetime import datetime
from pathlib import Path

# Canonical DB location (project root). parse_allure.py resolves to the same path.
DB_PATH = Path(__file__).resolve().parent.parent / "qa_dashboard.db"

# Bump when a migration is appended to MIGRATIONS below.
LATEST_VERSION = 6


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # SQLite ignores foreign keys unless this is switched on per connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# Baseline tables. Every statement is CREATE IF NOT EXISTS or a guarded ALTER,
# so it is safe on both a fresh and an existing database. Structural changes
# (foreign keys and so on) live in the numbered migrations further down.
# ---------------------------------------------------------------------------

def _create_baseline(conn):
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS features (
            name TEXT PRIMARY KEY,
            archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Same definitions as parse_allure.py so the tables always exist, even
    # before the first Allure import.
    cur.execute("""
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
            start_ts INTEGER,
            stop_ts INTEGER,
            duration_ms INTEGER,
            run_date TEXT,
            error_message TEXT,
            severity TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_uuid TEXT,
            attachment_name TEXT,
            file_path TEXT,
            type TEXT,
            FOREIGN KEY (test_uuid) REFERENCES test_results (uuid)
        )
    """)
    try:
        cur.execute("ALTER TABLE test_results ADD COLUMN severity TEXT")
    except sqlite3.OperationalError:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS manual_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feature_name TEXT NOT NULL,
            period TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('passed', 'failed')),
            description TEXT,
            evidence_path TEXT,
            evidence_type TEXT,
            evidence_size INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (feature_name) REFERENCES features(name)
        )
    """)
    try:
        cur.execute("ALTER TABLE manual_entries ADD COLUMN severity TEXT")
    except sqlite3.OperationalError:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS defects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            defect_code TEXT UNIQUE,
            description TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            owner TEXT,
            raised_date TEXT,
            eta TEXT,
            impacted_tc_count INTEGER DEFAULT 0,
            module TEXT,
            created_at TEXT,
            closed_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            created_at TEXT DEFAULT (date('now'))
        )
    """)
    try:
        cur.execute("ALTER TABLE projects ADD COLUMN tc_failed INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            assignee TEXT,
            priority TEXT,
            label TEXT,
            due_date TEXT,
            column_name TEXT
        )
    """)
    for column, coltype in (("completed_at", "TEXT"), ("archived", "INTEGER DEFAULT 0")):
        try:
            cur.execute(f"ALTER TABLE tasks ADD COLUMN {column} {coltype}")
        except sqlite3.OperationalError:
            pass

    # Tasks already in Done before completed_at existed get their due date as
    # an approximate completion date, so they appear in monthly productivity.
    cur.execute("""
        UPDATE tasks
        SET completed_at = COALESCE(due_date, date('now')) || 'T00:00:00'
        WHERE column_name = 'Done' AND completed_at IS NULL
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS module_meta (
            module TEXT PRIMARY KEY,
            pic TEXT,
            mitigation_plan TEXT,
            planned_tc_count INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_checklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    for column, coltype in (
        ("evidence_path", "TEXT"),
        ("evidence_type", "TEXT"),
        ("evidence_size", "INTEGER"),
        ("assignees", "TEXT"),
    ):
        try:
            cur.execute(f"ALTER TABLE project_checklist ADD COLUMN {column} {coltype}")
        except sqlite3.OperationalError:
            pass

    conn.commit()


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

def _canonical_feature(conn, raw, fallback=None):
    """Return the registered feature name a free text module value refers to.
    Exact match first, then case and whitespace insensitive. A name that
    matches nothing is registered as an ARCHIVED feature, so no data is lost
    and it never shows up in dropdowns or reports until someone restores it."""
    name = (raw or "").strip() or fallback
    if not name:
        return None
    row = conn.execute("SELECT name FROM features WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        "SELECT name FROM features WHERE lower(name) = lower(?)", (name,)
    ).fetchone()
    if row:
        return row[0]
    conn.execute("INSERT INTO features (name, archived) VALUES (?, 1)", (name,))
    print(f'[migration] registered unknown feature "{name}" as archived')
    return name


def _migration_1_feature_links(conn):
    """defects.module and manual_entries.feature_name become real foreign keys
    to features(name). ON UPDATE CASCADE makes a feature rename flow through.
    Deleting a feature that still has defects is refused (RESTRICT); manual
    entries are removed with their feature (CASCADE)."""
    # 1. Make every existing value point at a registered feature.
    for row in conn.execute("SELECT id, module FROM defects").fetchall():
        canon = _canonical_feature(conn, row["module"])
        if canon != row["module"]:
            conn.execute("UPDATE defects SET module = ? WHERE id = ?", (canon, row["id"]))

    for row in conn.execute("SELECT id, feature_name FROM manual_entries").fetchall():
        canon = _canonical_feature(conn, row["feature_name"], fallback="Unassigned")
        if canon != row["feature_name"]:
            conn.execute(
                "UPDATE manual_entries SET feature_name = ? WHERE id = ?", (canon, row["id"])
            )

    # 2. Rebuild the tables with the foreign keys (SQLite cannot add one in place).
    conn.execute("""
        CREATE TABLE defects_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            closed_at TEXT
        )
    """)
    conn.execute("""
        INSERT INTO defects_new
            (id, defect_code, description, severity, status, owner, raised_date,
             eta, impacted_tc_count, module, created_at, closed_at)
        SELECT id, defect_code, description, severity, status, owner, raised_date,
               eta, impacted_tc_count, module, created_at, closed_at
        FROM defects
    """)
    conn.execute("DROP TABLE defects")
    conn.execute("ALTER TABLE defects_new RENAME TO defects")

    conn.execute("""
        CREATE TABLE manual_entries_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feature_name TEXT NOT NULL
                REFERENCES features(name) ON UPDATE CASCADE ON DELETE CASCADE,
            period TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('passed', 'failed')),
            description TEXT,
            evidence_path TEXT,
            evidence_type TEXT,
            evidence_size INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            severity TEXT
        )
    """)
    conn.execute("""
        INSERT INTO manual_entries_new
            (id, feature_name, period, status, description, evidence_path,
             evidence_type, evidence_size, created_at, severity)
        SELECT id, feature_name, period, status, description, evidence_path,
               evidence_type, evidence_size, created_at, severity
        FROM manual_entries
    """)
    conn.execute("DROP TABLE manual_entries")
    conn.execute("ALTER TABLE manual_entries_new RENAME TO manual_entries")


def _migration_2_defect_links(conn):
    conn.execute("ALTER TABLE defects ADD COLUMN source_ref TEXT")
    conn.execute("ALTER TABLE defects ADD COLUMN cluster_id TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX idx_defects_source_ref "
        "ON defects(source_ref) WHERE source_ref IS NOT NULL"
    )


def _migration_3_checklist_assignees(conn):
    """Each project checklist item can list one or more people (comma-separated).
    projects.owner is already TEXT and is now treated as a multi-person list
    at the API layer — no column change needed there."""
    try:
        conn.execute("ALTER TABLE project_checklist ADD COLUMN assignees TEXT")
    except sqlite3.OperationalError:
        # Column already present (e.g. baseline ALTER ran on a fresh DB).
        pass


def _migration_4_task_archive(conn):
    """Tasks can be archived (hidden from the active board without deleting)."""
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN archived INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.execute(
        "UPDATE tasks SET archived = 0 WHERE archived IS NULL"
    )


def _migration_5_tasks_into_projects(conn):
    """Tasks is retired as a standalone page. Every existing task becomes a
    lightweight project instead (title -> name, assignee -> owner, due_date ->
    target_date, priority/label folded into note, column_name -> status).
    projects gains its own archived flag, replacing the one tasks had. The
    tasks table is dropped once its rows are copied over."""
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN archived INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.execute("UPDATE projects SET archived = 0 WHERE archived IS NULL")

    status_map = {"To Do": "Not Started", "In Progress": "In Progress", "Done": "Completed"}

    rows = conn.execute("SELECT * FROM tasks").fetchall()
    for r in rows:
        note_parts = []
        if r["priority"]:
            note_parts.append(f"{r['priority']} priority")
        if r["label"]:
            note_parts.append(r["label"])
        note = " \u00b7 ".join(note_parts) or None
        status = status_map.get(r["column_name"], "Not Started")

        conn.execute(
            """INSERT INTO projects
               (name, module, owner, status, color, pct, tc_done, tc_failed, tc_total, target_date, note, archived)
               VALUES (?, NULL, ?, ?, 'gray', 0, 0, 0, 0, ?, ?, ?)""",
            (r["title"], r["assignee"], status, r["due_date"], note, r["archived"] or 0),
        )
        print(f'[migration] moved task "{r["title"]}" into projects')

    conn.execute("DROP TABLE IF EXISTS tasks")


def _migration_6_project_velocity_dates(conn):
    """Adds the timestamps needed to plot project progress over time:
    projects.created_at (when the project started, used as the pace-line
    origin) and project_checklist.completed_at (when each item was checked
    off). Existing rows get a same-day fallback so there is at least one
    valid data point immediately; history from here on is stamped exactly."""
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN created_at TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute("UPDATE projects SET created_at = date('now') WHERE created_at IS NULL")

    try:
        conn.execute("ALTER TABLE project_checklist ADD COLUMN completed_at TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute(
        "UPDATE project_checklist SET completed_at = date('now') WHERE done = 1 AND completed_at IS NULL"
    )


MIGRATIONS = [
    (1, _migration_1_feature_links),
    (2, _migration_2_defect_links),
    (3, _migration_3_checklist_assignees),
    (4, _migration_4_task_archive),
    (5, _migration_5_tasks_into_projects),
    (6, _migration_6_project_velocity_dates),
]


def _current_version():
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _backup_database():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = DB_PATH.with_name(f"{DB_PATH.name}.bak-{stamp}")
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    print(f"[migration] backup written to {dest}")
    return dest


def _run_migrations():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        pending = [(v, fn) for v, fn in MIGRATIONS if v > version]
        if not pending:
            return

        # Table rebuilds need enforcement off; it cannot be changed inside a
        # transaction, so it is set here and verified with foreign_key_check.
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DROP VIEW IF EXISTS executions")

        for v, fn in pending:
            conn.execute("BEGIN")
            try:
                fn(conn)
                broken = conn.execute("PRAGMA foreign_key_check").fetchall()
                if broken:
                    raise RuntimeError(
                        f"migration {v} left {len(broken)} broken foreign key reference(s)"
                    )
                conn.execute(f"PRAGMA user_version = {int(v)}")
                conn.execute("COMMIT")
                print(f"[migration] applied version {v}")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# View, indexes and feature sync (idempotent, run on every startup)
# ---------------------------------------------------------------------------

def _ensure_views_and_indexes(conn):
    # Drop must be committed before CREATE on the same connection;
    # otherwise SQLite can still see the old view and raise "already exists".
    conn.execute("DROP VIEW IF EXISTS executions")
    conn.commit()
    conn.execute("""
        CREATE VIEW executions AS
        SELECT 'automated' AS source,
               uuid AS ref,
               module,
               name,
               status,
               severity,
               error_message,
               run_date,
               substr(run_date, 1, 7) AS period
        FROM test_results
        UNION ALL
        SELECT 'manual' AS source,
               'manual-' || id AS ref,
               feature_name AS module,
               COALESCE(NULLIF(description, ''), 'Manual entry') AS name,
               status,
               COALESCE(severity, 'normal') AS severity,
               NULL AS error_message,
               period || '-01' AS run_date,
               period
        FROM manual_entries
    """)

    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_test_results_module ON test_results(module)",
        "CREATE INDEX IF NOT EXISTS idx_test_results_run_date ON test_results(run_date)",
        "CREATE INDEX IF NOT EXISTS idx_manual_entries_feature ON manual_entries(feature_name, period)",
        "CREATE INDEX IF NOT EXISTS idx_defects_module_status ON defects(module, status)",
        "CREATE INDEX IF NOT EXISTS idx_defects_cluster ON defects(cluster_id)",
        "CREATE INDEX IF NOT EXISTS idx_projects_archived ON projects(archived)",
    ):
        conn.execute(stmt)
    conn.commit()


def sync_features_from_results(conn):
    """Registers every module name found in the Allure results as a feature.
    Existing rows, archived or not, are left alone."""
    conn.execute("""
        INSERT OR IGNORE INTO features (name, archived)
        SELECT DISTINCT module, 0 FROM test_results WHERE COALESCE(module, '') != ''
    """)
    conn.commit()


def init_db():
    existed = DB_PATH.exists() and DB_PATH.stat().st_size > 0

    # Safety copy before anything structural happens to an existing database.
    if existed and _current_version() < LATEST_VERSION:
        _backup_database()

    conn = get_connection()
    try:
        _create_baseline(conn)
    finally:
        conn.close()

    _run_migrations()

    conn = get_connection()
    try:
        _ensure_views_and_indexes(conn)
        sync_features_from_results(conn)
    finally:
        conn.close()


def seed_if_empty():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM projects")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            """INSERT INTO projects
               (name, module, owner, status, color, pct, tc_done, tc_failed, tc_total, target_date, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                ("Support Feature Refinement", "Support", "Dara", "In Progress", "orange",
                 60, 18, 0, 30, "2026-09-25", "Reworking warranty claim category flow.", "2026-09-05"),
                ("Login OTP Redesign", "Login", "Mario", "In Review", "orange",
                 80, 16, 0, 20, "2026-09-19", "New OTP screen, awaiting sign off.", "2026-09-01"),
                ("Explore Language Switcher", "Explore", "Mario", "Done", "green",
                 100, 9, 0, 9, "2026-09-10", "Shipped and automated.", "2026-08-20"),
                ("Smart Gate Access Pilot", "Smart Gate", "Dara", "Blocked", "red",
                 20, 3, 0, 15, "2026-10-03", "Waiting on hardware vendor response.", "2026-09-10"),
            ],
        )

    conn.commit()
    conn.close()