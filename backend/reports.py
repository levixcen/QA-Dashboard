from datetime import datetime, timezone

from database import get_connection

SEVERITY_LEVELS = ["critical", "high", "medium", "low", "normal"]
FAILING = ("failed", "broken")
SEVERITY_MAP = {
    "blocker": "critical",
    "critical": "critical",
    "high": "high",
    "normal": "medium",
    "medium": "medium",
    "minor": "low",
    "low": "low",
    "trivial": "low",
}


def normalize_severity(raw):
    return SEVERITY_MAP.get((raw or "").strip().lower(), "normal")


def severity_counts(rows):
    counts = {level: 0 for level in SEVERITY_LEVELS}
    for r in rows:
        counts[normalize_severity(r["severity"])] += 1
    return counts


def status_for(total, pct):
    if total == 0:
        return "Not Started", "gray"
    if pct >= 95:
        return "Healthy", "green"
    if pct >= 85:
        return "Watch", "orange"
    return "Needs Attention", "red"


def build_module(index, name, rows):
    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "passed")
    failed_rows = [r for r in rows if r["status"] in FAILING]
    pct = round(passed / total * 100) if total else 0
    status, color = status_for(total, pct)
    return {
        "id": index,
        "name": name,
        "pct": pct,
        "status": status,
        "failing": len(failed_rows),
        "color": color,
        "details": [
            {"name": r["name"], "count": 1, "error": r["error_message"] or ""}
            for r in failed_rows
        ],
        "total": total,
        "passed": passed,
        "severity": severity_counts(failed_rows),
    }


def build_overall(rows):
    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "passed")
    failed_rows = [r for r in rows if r["status"] in FAILING]
    return {
        "total": total,
        "passed": passed,
        "failed": len(failed_rows),
        "pct": round(passed / total * 100) if total else 0,
        "severity": severity_counts(failed_rows),
    }


def _manual_rows(cur, month=None):
    # severity column added for manual entries; falls back to NULL-safe
    # COALESCE so older rows without the column value still work.
    query = """
        SELECT feature_name AS module,
               COALESCE(NULLIF(description, ''), 'Manual entry') AS name,
               status,
               COALESCE(severity, 'normal') AS severity,
               NULL AS error_message
        FROM manual_entries
    """
    if month:
        cur.execute(query + " WHERE period = ?", (month,))
    else:
        cur.execute(query)
    return cur.fetchall()


def get_summary(month=None, include_archived=False):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if month:
            cur.execute(
                """SELECT module, name, status, severity, error_message
                   FROM test_results WHERE substr(run_date, 1, 7) = ?
                   ORDER BY module, name""",
                (month,),
            )
        else:
            cur.execute(
                """SELECT module, name, status, severity, error_message
                   FROM test_results ORDER BY module, name"""
            )
        automated_rows = cur.fetchall()

        cur.execute("SELECT DISTINCT module FROM test_results")
        for row in cur.fetchall():
            cur.execute(
                "INSERT OR IGNORE INTO features (name, archived) VALUES (?, 0)",
                (row["module"],),
            )
        conn.commit()

        manual_rows = _manual_rows(cur, month)

        cur.execute(
            "SELECT name FROM features WHERE archived = ?",
            (1 if include_archived else 0,),
        )
        visible_names = sorted(r["name"] for r in cur.fetchall())

        cur.execute("SELECT MAX(start_ts) AS t FROM test_results")
        latest = cur.fetchone()["t"]
    finally:
        conn.close()

    last_run = None
    if latest:
        last_run = datetime.fromtimestamp(latest / 1000, tz=timezone.utc).isoformat()

    by_module = {}
    for r in list(automated_rows) + list(manual_rows):
        by_module.setdefault(r["module"], []).append(r)

    modules = [
        build_module(i, name, by_module.get(name, []))
        for i, name in enumerate(visible_names, start=1)
    ]

    # Overall stats only reflect the currently visible set (active vs
    # archived), same split as the module list itself.
    overall_rows = [r for name in visible_names for r in by_module.get(name, [])]

    return {
        "period": month,
        "modules": modules,
        "overall": build_overall(overall_rows),
        "generated_at": last_run,
    }


def get_monthly_report(year):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT substr(run_date, 6, 2) AS m, status, COUNT(*) AS c
               FROM test_results
               WHERE substr(run_date, 1, 4) = ?
               GROUP BY m, status""",
            (year,),
        )
        auto_rows = cur.fetchall()
        cur.execute(
            """SELECT substr(period, 6, 2) AS m, status, COUNT(*) AS c
               FROM manual_entries
               WHERE substr(period, 1, 4) = ?
               GROUP BY m, status""",
            (year,),
        )
        manual_rows = cur.fetchall()
    finally:
        conn.close()

    months = {
        f"{i:02d}": {"month": f"{year}-{i:02d}", "total": 0, "passed": 0, "failed": 0, "pct": 0}
        for i in range(1, 13)
    }
    for r in list(auto_rows) + list(manual_rows):
        bucket = months.get(r["m"])
        if not bucket:
            continue
        bucket["total"] += r["c"]
        if r["status"] == "passed":
            bucket["passed"] += r["c"]
        elif r["status"] in FAILING:
            bucket["failed"] += r["c"]
    for b in months.values():
        b["pct"] = round(b["passed"] / b["total"] * 100) if b["total"] else 0
    return {"year": year, "months": list(months.values())}

def get_periods():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT DISTINCT p FROM (
                   SELECT substr(run_date, 1, 7) AS p FROM test_results WHERE run_date != ''
                   UNION
                   SELECT period AS p FROM manual_entries
               )
               ORDER BY p DESC"""
        )
        return [r["p"] for r in cur.fetchall()]
    finally:
        conn.close()