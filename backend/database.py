import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "qa_dashboard.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

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
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
            note TEXT
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

    for column, coltype in (("evidence_path", "TEXT"), ("evidence_type", "TEXT"), ("evidence_size", "INTEGER")):
        try:
            cur.execute(f"ALTER TABLE project_checklist ADD COLUMN {column} {coltype}")
        except sqlite3.OperationalError:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS features (
            name TEXT PRIMARY KEY,
            archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

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
    

    conn.commit()
    conn.close()


def seed_if_empty():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM projects")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            """INSERT INTO projects
               (name, module, owner, status, color, pct, tc_done, tc_failed, tc_total, target_date, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                ("Support Feature Refinement", "Support", "Dara", "In Progress", "orange",
                 60, 18, 0, 30, "2026-09-25", "Reworking warranty claim category flow."),
                ("Login OTP Redesign", "Login", "Mario", "In Review", "orange",
                 80, 16, 0, 20, "2026-09-19", "New OTP screen, awaiting sign off."),
                ("Explore Language Switcher", "Explore", "Mario", "Done", "green",
                 100, 9, 0, 9, "2026-09-10", "Shipped and automated."),
                ("Smart Gate Access Pilot", "Smart Gate", "Dara", "Blocked", "red",
                 20, 3, 0, 15, "2026-10-03", "Waiting on hardware vendor response."),
            ],
        )

    cur.execute("SELECT COUNT(*) AS c FROM tasks")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            """INSERT INTO tasks
               (title, assignee, priority, label, due_date, column_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                ("Write TCs for Smart Gate", "Dara", "High", "QA", "2026-09-18", "To Do"),
                ("Fix flaky login test", "Mario", "High", "Automation", "2026-09-16", "In Progress"),
                ("Review Support refinement PR", "Dara", "Medium", "Review", "2026-09-19", "In Progress"),
                ("Automate My Bills TCs", "Mario", "Medium", "Automation", "2026-09-22", "To Do"),
                ("Set up Jira free path script", "Dara", "Low", "Integration", "2026-09-26", "To Do"),
                ("Explore module screenshots QA", "Mario", "Low", "QA", "2026-09-12", "Done"),
            ],
        )

    conn.commit()
    conn.close()