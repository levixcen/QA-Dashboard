import argparse
import json
import mimetypes
import sys
from pathlib import Path
from datetime import datetime, timezone

# Resolve the backend folder from wherever this script lives, so
# "python parse_allure.py ..." works from the project root with no PYTHONPATH.
_HERE = Path(__file__).resolve().parent
if (_HERE / "database.py").exists():
    BACKEND_DIR = _HERE
    PROJECT_ROOT = _HERE.parent
else:
    BACKEND_DIR = _HERE / "backend"
    PROJECT_ROOT = _HERE
sys.path.insert(0, str(BACKEND_DIR))

from timeutil import run_date_from_start_ts, now_utc  # noqa: E402
import database  # noqa: E402  (reads DATABASE_URL)

# The database now comes from the DATABASE_URL setting (see database.py).
DEFAULT_JSON_OUT = PROJECT_ROOT / "public" / "dashboard_data.json"

SEVERITY_LEVELS = ["critical", "high", "medium", "low", "normal"]
ALLOWED_EVIDENCE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

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


def normalize_severity(raw: str) -> str:
    key = (raw or "").strip().lower()
    mapping = {
        "blocker": "critical",
        "critical": "critical",
        "high": "high",
        "normal": "medium",
        "medium": "medium",
        "minor": "low",
        "low": "low",
        "trivial": "low",
    }
    return mapping.get(key, "normal")


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


def init_db():
    """Makes sure the schema exists, then returns a pooled connection."""
    database.init_db()
    return database.get_connection()


def compute_module_summary(conn):
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

        cur.execute("""
            SELECT severity FROM test_results
            WHERE module = ? AND status IN ('failed', 'broken')
        """, (module,))
        severity_counts = {level: 0 for level in SEVERITY_LEVELS}
        for (raw_sev,) in cur.fetchall():
            severity_counts[normalize_severity(raw_sev)] += 1

        summary.append({
            "id": i,
            "name": module,
            "pct": pct,
            "status": status,
            "failing": failing,
            "color": color,
            "details": details,
            "total": total,
            "passed": passed,
            "severity": severity_counts,
        })
    return summary


def compute_overall_summary(conn):
    cur = conn.cursor()
    cur.execute("SELECT status, COUNT(*) FROM test_results GROUP BY status")
    counts = dict(cur.fetchall())
    total = sum(counts.values())
    passed = counts.get("passed", 0)
    failed = sum(v for k, v in counts.items() if k in ("failed", "broken"))
    pct = round((passed / total) * 100) if total else 0

    cur.execute("""
        SELECT severity FROM test_results
        WHERE status IN ('failed', 'broken')
    """)
    severity_counts = {level: 0 for level in SEVERITY_LEVELS}
    for (raw_sev,) in cur.fetchall():
        severity_counts[normalize_severity(raw_sev)] += 1

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pct": pct,
        "severity": severity_counts,
    }


def export_dashboard_json(conn, out_path: Path):
    summary = compute_module_summary(conn)
    overall = compute_overall_summary(conn)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "modules": summary,
            "overall": overall,
            "generated_at": now_utc().isoformat(),
        }, f, indent=2)
    print(f"Dashboard data written to {out_path}")


def parse(input_dir: Path, json_out: Path = None):
    conn = init_db()
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
        severity = get_label(labels, "severity")

        key = (suite or package or "").strip().lower()
        module = resolve_module(suite, package)
        if key not in MODULE_MAP:
            auto_added_suites.add(f"{suite or package or 'unknown'} -> {module}")

        start_ts = result.get("start", 0)
        stop_ts = result.get("stop", 0)
        # Jakarta calendar day — matches dashboard period filters
        run_date = run_date_from_start_ts(start_ts) if start_ts else ""

        cur.execute("""
            INSERT INTO test_results
            (uuid, name, full_name, status, module, suite, epic, story,
             feature, tc_id, start_ts, stop_ts, duration_ms, run_date, error_message, severity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (uuid) DO UPDATE SET
                name = EXCLUDED.name,
                full_name = EXCLUDED.full_name,
                status = EXCLUDED.status,
                module = EXCLUDED.module,
                suite = EXCLUDED.suite,
                epic = EXCLUDED.epic,
                story = EXCLUDED.story,
                feature = EXCLUDED.feature,
                tc_id = EXCLUDED.tc_id,
                start_ts = EXCLUDED.start_ts,
                stop_ts = EXCLUDED.stop_ts,
                duration_ms = EXCLUDED.duration_ms,
                run_date = EXCLUDED.run_date,
                error_message = EXCLUDED.error_message,
                severity = EXCLUDED.severity
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
            severity,
        ))

        cur.execute("DELETE FROM attachments WHERE test_uuid = ?", (uuid,))

        safe_uuid = Path(uuid).name
        for att in collect_attachments(result):
            source_name = Path(att.get("source", "")).name
            if Path(source_name).suffix.lower() not in ALLOWED_EVIDENCE_EXT:
                continue
            source_path = result["_source_path"].parent / source_name
            if not source_path.exists():
                missing_screenshots += 1
                continue
            dest_name = f"{safe_uuid}_{source_name}"
            # Screenshots are stored in the database, so a hosted server can show them.
            database.save_evidence(
                cur, dest_name,
                att.get("type") or mimetypes.guess_type(source_name)[0],
                source_path.read_bytes(),
            )
            cur.execute("""
                INSERT INTO attachments (test_uuid, attachment_name, file_path, type)
                VALUES (?, ?, ?, ?)
            """, (uuid, att.get("name", ""), dest_name, att.get("type", "")))

        inserted += 1

    database.sync_features_from_results(conn)
    conn.commit()

    print(f"\nParsed {inserted} test results from {input_dir}")
    print("Database: PostgreSQL (DATABASE_URL)")
    print("Screenshots: stored in the database")
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

    export_dashboard_json(conn, Path(json_out) if json_out else DEFAULT_JSON_OUT)
    conn.close()
    database.close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse Allure results into the QA dashboard database.")
    parser.add_argument("--input", required=True, help="Path to Mario's allure-results folder")
    parser.add_argument("--json-out", default=str(DEFAULT_JSON_OUT), help="Legacy JSON export path")
    args = parser.parse_args()

    parse(Path(args.input), Path(args.json_out))