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
            tc_total INTEGER DEFAULT 0,
            target_date TEXT,
            note TEXT
        )
    """)

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

    conn.commit()
    conn.close()


def seed_if_empty():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM projects")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            """INSERT INTO projects
               (name, module, owner, status, color, pct, tc_done, tc_total, target_date, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                ("Support Feature Refinement", "Support", "Dara", "In Progress", "orange",
                 60, 18, 30, "2026-09-25", "Reworking warranty claim category flow."),
                ("Login OTP Redesign", "Login", "Mario", "In Review", "orange",
                 80, 16, 20, "2026-09-19", "New OTP screen, awaiting sign off."),
                ("Explore Language Switcher", "Explore", "Mario", "Done", "green",
                 100, 9, 9, "2026-09-10", "Shipped and automated."),
                ("Smart Gate Access Pilot", "Smart Gate", "Dara", "Blocked", "red",
                 20, 3, 15, "2026-10-03", "Waiting on hardware vendor response."),
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