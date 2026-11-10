"""One time copy of the old SQLite database into PostgreSQL.

Usage (from the backend folder, with DATABASE_URL set):
    python migrate_sqlite_to_postgres.py                 # reads ../qa_dashboard.db
    python migrate_sqlite_to_postgres.py path/to/file.db

It never changes the SQLite file. It refuses to run if PostgreSQL already has
data in its tables, so running it twice cannot create duplicates. To start
over, empty the PostgreSQL tables first (see GUIDE in the chat).
"""
import sqlite3
import sys
from pathlib import Path

import database

TABLES = [
    "features", "users", "test_results", "attachments", "manual_entries",
    "defects", "projects", "project_checklist", "module_meta",
]
ID_TABLES = ["users", "attachments", "manual_entries", "defects", "projects", "project_checklist"]
BATCH = 1000


def main():
    default = Path(__file__).resolve().parent.parent / "qa_dashboard.db"
    src_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    if not src_path.exists():
        sys.exit(f"SQLite file not found: {src_path}")

    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    database.init_db()
    pg = database.get_connection()
    cur = pg.cursor()

    # Safety: do not copy into tables that already hold data.
    for t in TABLES:
        cur.execute(f"SELECT COUNT(*) AS c FROM {t}")
        if cur.fetchone()["c"]:
            sys.exit(f"PostgreSQL table '{t}' already has rows. Nothing was copied.")

    report = []
    registered_extra = []

    def pg_columns(table):
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ?", (table,))
        return [r["column_name"] for r in cur.fetchall()]

    for table in TABLES:
        have = {r["name"] for r in src.execute(f"PRAGMA table_info({table})")}
        if not have:
            report.append((table, 0, 0, 0))
            continue
        cols = [c for c in pg_columns(table) if c in have]
        rows = src.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()

        skipped = 0
        batch = []
        valid_features = None
        valid_tests = None
        valid_projects = None
        if table in ("defects", "manual_entries"):
            cur.execute("SELECT name FROM features")
            valid_features = {r["name"] for r in cur.fetchall()}
        if table == "attachments":
            cur.execute("SELECT uuid FROM test_results")
            valid_tests = {r["uuid"] for r in cur.fetchall()}
        if table == "project_checklist":
            cur.execute("SELECT id FROM projects")
            valid_projects = {r["id"] for r in cur.fetchall()}

        insert = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
        for r in rows:
            values = [r[c] for c in cols]
            rec = dict(zip(cols, values))

            if table == "attachments" and rec.get("test_uuid") not in valid_tests:
                skipped += 1
                continue
            if table == "project_checklist" and rec.get("project_id") not in valid_projects:
                skipped += 1
                continue
            feature_col = {"defects": "module", "manual_entries": "feature_name"}.get(table)
            if feature_col and rec.get(feature_col):
                name = rec[feature_col]
                if name not in valid_features:
                    # Same rule as the old migration: keep the data, register
                    # the unknown feature as archived.
                    cur.execute("INSERT INTO features (name, archived) VALUES (?, 1) ON CONFLICT DO NOTHING", (name,))
                    valid_features.add(name)
                    registered_extra.append(name)
            elif feature_col and table == "manual_entries":
                skipped += 1
                continue
            batch.append(values)
            if len(batch) >= BATCH:
                cur.executemany(insert, batch)
                batch = []
        if batch:
            cur.executemany(insert, batch)
        pg.commit()
        report.append((table, len(rows), len(rows) - skipped, skipped))

    # Identity columns must continue after the highest copied id.
    for table in ID_TABLES:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table}"
        )
    # Defect codes (DEF-001 ...) continue after the highest copied code.
    cur.execute(
        "SELECT COALESCE(MAX(NULLIF(regexp_replace(defect_code, '[^0-9]', '', 'g'), '')::int), 0) AS m FROM defects"
    )
    highest = cur.fetchone()["m"]
    if highest:
        cur.execute("SELECT setval('defect_code_seq', ?, true)", (highest,))
    pg.commit()

    print(f"\n{'table':20s} {'in SQLite':>10s} {'copied':>8s} {'skipped':>8s}")
    ok = True
    for table, n_src, n_copied, n_skip in report:
        flag = "" if n_skip == 0 else "   <-- check"
        print(f"{table:20s} {n_src:10d} {n_copied:8d} {n_skip:8d}{flag}")
        if n_copied + n_skip != n_src:
            ok = False
    if registered_extra:
        print(f"\nRegistered as archived features (used by data but missing): {sorted(set(registered_extra))}")

    # Same question asked of both databases: does the combined view agree?
    try:
        s_n = src.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
        cur.execute("SELECT COUNT(*) AS c FROM executions")
        p_n = cur.fetchone()["c"]
        print(f"\nexecutions view: SQLite {s_n}, PostgreSQL {p_n}", "OK" if s_n == p_n else "DIFFERENT, check")
        ok = ok and s_n == p_n
        for status, in src.execute("SELECT DISTINCT status FROM executions ORDER BY 1"):
            s_c = src.execute("SELECT COUNT(*) FROM executions WHERE status = ?", (status,)).fetchone()[0]
            cur.execute("SELECT COUNT(*) AS c FROM executions WHERE status = ?", (status,))
            p_c = cur.fetchone()["c"]
            print(f"  {str(status):10s} SQLite {s_c:6d}  PostgreSQL {p_c:6d}", "" if s_c == p_c else "  <-- DIFFERENT")
            ok = ok and s_c == p_c
    except sqlite3.OperationalError:
        print("\n(The SQLite file has no executions view, skipped that check.)")

    pg.close()
    database.close_pool()
    print("\nRESULT:", "all counts match" if ok else "SOME COUNTS DIFFER, do not switch over yet")


if __name__ == "__main__":
    main()