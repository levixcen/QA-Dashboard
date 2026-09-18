import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DEFAULT_JSON_OUT = SCRIPT_DIR / "backend" / "public" / "dashboard_data.json"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_EVIDENCE_DIR = SCRIPT_DIR / "backend" / "evidence"


MODULE_MAP = {
    "test_login": "Login",
    "test_register": "Register",
    "test_my_unit": "My Unit",
    "test_support": "Support",
    "test_property": "Property",
    "test_hotline": "Hotline",
    "test_community": "Community",
    "test_guest": "Guest",
    "test_my_bills": "My Bills",
    "test_profile": "Profile",
    "test_residents": "Residents",
    "test_smart_gate": "Smart Gate",
    "test_forgot_password": "Forgot Password",
}


def load_result_files(input_dir: Path):
    results = []
    for path in sorted(input_dir.glob("*-result.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_source_path"] = path
                results.append(data)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Skipped {path.name}, could not read it: {e}")
    return results


def get_label(labels, name, default=""):
    for label in labels or []:
        if label.get("name") == name:
            return label.get("value", default)
    return default


def get_param(parameters, name, default=""):
    for p in parameters or []:
        if p.get("name") == name:
            return str(p.get("value", default)).strip("'\"")
    return default


def auto_module_name(suite: str, package: str) -> str:
    raw = (suite or package or "unknown").strip()
    raw = raw.split(".")[-1]
    if raw.startswith("test_"):
        raw = raw[len("test_"):]
    words = raw.replace("_", " ").split()
    return " ".join(w.capitalize() for w in words) if words else "Unknown"


def resolve_module(suite: str, package: str) -> str:
    key = (suite or package or "").strip().lower()
    if key in MODULE_MAP:
        return MODULE_MAP[key]
    return auto_module_name(suite, package)


def extract_error_message(result: dict) -> str:
    details = result.get("statusDetails") or {}
    message = details.get("message", "")
    return message[:500] if message else ""


def collect_attachments(result: dict):
    found = []
    for att in result.get("attachments", []):
        found.append(att)
    for step in result.get("steps", []):
        for att in step.get("attachments", []):
            found.append(att)
    return found


def init_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
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
            error_message TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_uuid TEXT,
            attachment_name TEXT,
            file_path TEXT,
            type TEXT,
            FOREIGN KEY (test_uuid) REFERENCES test_results (uuid)
        )
    """)
    conn.commit()
    return conn


def compute_module_summary(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT module FROM test_results ORDER BY module")
    modules = [row[0] for row in cur.fetchall()]

    summary = []
    for i, module in enumerate(modules, start=1):
        cur.execute("""
            SELECT status, COUNT(*) FROM test_results
            WHERE module = ? GROUP BY status
        """, (module,))
        counts = dict(cur.fetchall())
        total = sum(counts.values())
        passed = counts.get("passed", 0)
        failing = sum(v for k, v in counts.items() if k in ("failed", "broken"))
        pct = round((passed / total) * 100) if total else 0

        if total == 0:
            status, color = "Not Started", "gray"
        elif pct >= 95:
            status, color = "Healthy", "green"
        elif pct >= 85:
            status, color = "Watch", "orange"
        else:
            status, color = "Needs Attention", "red"

        cur.execute("""
            SELECT name, error_message FROM test_results
            WHERE module = ? AND status IN ('failed', 'broken')
        """, (module,))
        details = [{"name": name, "count": 1, "error": err or ""} for name, err in cur.fetchall()]

        summary.append({
            "id": i,
            "name": module,
            "pct": pct,
            "status": status,
            "failing": failing,
            "color": color,
            "details": details,
        })
    return summary


def export_dashboard_json(conn: sqlite3.Connection, out_path: Path):
    summary = compute_module_summary(conn)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"modules": summary, "generated_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)
    print(f"Dashboard data written to {out_path}")


def parse(input_dir: Path, db_path: Path, evidence_dir: Path, json_out: Path = None):
    evidence_dir.mkdir(parents=True, exist_ok=True)
    conn = init_db(db_path)
    cur = conn.cursor()

    results = load_result_files(input_dir)
    if not results:
        print(f"No *-result.json files found in {input_dir}")
        return

    auto_added_suites = set()
    inserted = 0
    missing_screenshots = 0

    for result in results:
        uuid = result.get("uuid", "")
        labels = result.get("labels", [])
        suite = get_label(labels, "suite")
        package = get_label(labels, "package")
        epic = get_label(labels, "epic")
        story = get_label(labels, "story")
        feature = get_label(labels, "feature")
        tc_id = get_param(result.get("parameters"), "tc_id")

        key = (suite or package or "").strip().lower()
        module = resolve_module(suite, package)
        if key not in MODULE_MAP:
            auto_added_suites.add(f"{suite or package or 'unknown'} -> {module}")

        start_ts = result.get("start", 0)
        stop_ts = result.get("stop", 0)
        run_date = ""
        if start_ts:
            run_date = datetime.fromtimestamp(
                start_ts / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d")

        cur.execute("""
            INSERT OR REPLACE INTO test_results
            (uuid, name, full_name, status, module, suite, epic, story,
             feature, tc_id, start_ts, stop_ts, duration_ms, run_date, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            uuid,
            result.get("name", ""),
            result.get("fullName", ""),
            result.get("status", "unknown"),
            module,
            suite,
            epic,
            story,
            feature,
            tc_id,
            start_ts,
            stop_ts,
            stop_ts - start_ts if start_ts and stop_ts else 0,
            run_date,
            extract_error_message(result),
        ))

        cur.execute("DELETE FROM attachments WHERE test_uuid = ?", (uuid,))

        for att in collect_attachments(result):
            source_name = att.get("source", "")
            source_path = result["_source_path"].parent / source_name
            if not source_path.exists():
                missing_screenshots += 1
                continue
            dest_name = f"{uuid}_{source_name}"
            dest_path = evidence_dir / dest_name
            shutil.copyfile(source_path, dest_path)
            cur.execute("""
                INSERT INTO attachments (test_uuid, attachment_name, file_path, type)
                VALUES (?, ?, ?, ?)
            """, (uuid, att.get("name", ""), str(dest_path), att.get("type", "")))

        inserted += 1

    conn.commit()

    print(f"\nParsed {inserted} test results from {input_dir}")
    print(f"Database: {db_path}")
    print(f"Evidence folder: {evidence_dir}")
    if missing_screenshots:
        print(f"Warning: {missing_screenshots} attachment(s) referenced in result JSON were not found on disk.")
    if auto_added_suites:
        print(f"\nNew modules added automatically:")
        for s in sorted(auto_added_suites):
            print(f"  - {s}")

    cur.execute("""
        SELECT module, status, COUNT(*) FROM test_results
        GROUP BY module, status ORDER BY module, status
    """)
    print("\nModule breakdown:")
    for module, status, count in cur.fetchall():
        print(f"  {module:20s} {status:10s} {count}")

    export_dashboard_json(conn, Path(json_out) if json_out else Path("public/dashboard_data.json"))
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse Allure results into the QA dashboard database.")
    parser.add_argument("--input", required=True, help="Path to Mario's allure-results folder")
    parser.add_argument("--db", default="qa_dashboard.db", help="Output SQLite file")
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE_DIR), help="Output folder for copied screenshots")
    parser.add_argument("--json-out", default="public/dashboard_data.json", help="Where to write the JSON the dashboard reads")
    args = parser.parse_args()

    parse(Path(args.input), Path(args.db), Path(args.evidence), Path(args.json_out))