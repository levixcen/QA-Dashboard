import glob
import sqlite3

from database import DB_PATH

print("Database file used by the app:")
print("  ", DB_PATH)
print("   exists:", DB_PATH.exists())
if not DB_PATH.exists():
    raise SystemExit("The app would create a brand new empty database here.")

conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

print("\nMigration version (1 means the new code has run):",
      conn.execute("PRAGMA user_version").fetchone()[0])

backups = sorted(glob.glob(str(DB_PATH) + ".bak-*"))
print("Backups next to it:", len(backups))

tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name")]
print("\nTables and views:", ", ".join(tables))

print("\nRow counts:")
for t in ("features", "defects", "manual_entries", "test_results", "projects", "tasks"):
    if t in tables:
        print(f"   {t:16s}", conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    else:
        print(f"   {t:16s} MISSING")

if "defects" in tables:
    print("\nDefects:")
    rows = conn.execute("SELECT id, defect_code, status, module, description FROM defects").fetchall()
    for r in rows:
        print("  ", r["defect_code"], r["status"], "|", r["module"], "|", (r["description"] or "")[:40])
    if not rows:
        print("   (none stored)")

print("\nFeatures:")
for r in conn.execute("SELECT name, archived FROM features ORDER BY name"):
    print("  ", r["name"], "(archived)" if r["archived"] else "")
conn.close()