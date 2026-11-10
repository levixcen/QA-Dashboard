"""One time: copy every image in backend/evidence into the evidence_files table.

Run from the backend folder with DATABASE_URL loaded:
    python migrate_evidence_to_db.py

Safe to run twice (existing names are overwritten with the same bytes).
"""
import mimetypes
from pathlib import Path

import database

EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"
ALLOWED = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def main():
    database.init_db()
    if not EVIDENCE_DIR.is_dir():
        print(f"No folder at {EVIDENCE_DIR}, nothing to copy.")
        return
    files = [p for p in sorted(EVIDENCE_DIR.iterdir()) if p.is_file() and p.suffix.lower() in ALLOWED]
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        total = 0
        for p in files:
            data = p.read_bytes()
            database.save_evidence(cur, p.name, mimetypes.guess_type(p.name)[0], data)
            total += len(data)
        conn.commit()
        cur.execute("SELECT COUNT(*) AS n, COALESCE(SUM(size), 0) AS bytes FROM evidence_files")
        row = cur.fetchone()
    finally:
        conn.close()
        database.close_pool()
    print(f"Images found in folder: {len(files)}")
    print(f"Images now in database: {row['n']} ({row['bytes'] / 1024 / 1024:.1f} MB)")
    print("RESULT: all copied" if row["n"] >= len(files) else "RESULT: SOME MISSING")


if __name__ == "__main__":
    main()