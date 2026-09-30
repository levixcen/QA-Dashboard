from datetime import datetime, timezone

from database import get_connection, sync_features_from_results

SEVERITY_LEVELS = ["critical", "high", "medium", "low", "normal"]
FAILING = ("failed", "broken")
OPEN_DEFECT_STATUSES = ("open", "in_progress", "retest", "reopened")
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


def defect_severity_counts(defects):
    """Defect severities are already normalized (critical/high/medium/low)."""
    counts = {level: 0 for level in ("critical", "high", "medium", "low")}
    for d in defects:
        sev = (d["severity"] or "medium").strip().lower()
        if sev not in counts:
            sev = "medium"
        counts[sev] += 1
    return counts


def status_for(total, pct, open_defects=0, critical_or_high=0):
    """Feature health from executions + open defects.

    Features is the root: a module with zero tests can still be
    Needs Attention if it has open critical/high defects. Pass rate
    still drives the green/orange band when tests exist.
    """
    if critical_or_high > 0:
        return "Needs Attention", "red"
    if open_defects > 0 and total == 0:
        return "Needs Attention", "red"
    if total == 0:
        return "Not Started", "gray"
    if pct >= 95 and open_defects == 0:
        return "Healthy", "green"
    if pct >= 95 and open_defects > 0:
        return "Watch", "orange"
    if pct >= 85:
        return "Watch", "orange"
    return "Needs Attention", "red"


def build_module(index, name, rows, defects=None, failing_refs=None, defect_refs=None):
    defects = defects or []
    failing_refs = failing_refs or set()
    defect_refs = defect_refs or set()

    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "passed")
    failed_rows = [r for r in rows if r["status"] in FAILING]
    pct = round(passed / total * 100) if total else 0

    open_defects = len(defects)
    sev = defect_severity_counts(defects)
    critical_or_high = sev["critical"] + sev["high"]
    uncovered = len(failing_refs - defect_refs) if failing_refs else 0
    pass_pct = pct
    health = health_score(pass_pct, total, sev, uncovered)
    status, color = status_for(total, pass_pct, open_defects, critical_or_high)

    return {
        "id": index,
        "name": name,
        "pct": health,
        "pass_pct": pass_pct,
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
        "open_defects": open_defects,
        "defects_by_severity": sev,
        "uncovered_failures": uncovered,
    }


def health_score(pass_pct, total, defect_sev, uncovered=0):
    """Overall / module score shown on the ring and feature cards.

    Starts from execution pass rate, then subtracts a penalty for open
    defects (and uncovered failures). Adding a defect always lowers the
    score; closing it raises the score again.
    """
    if total == 0 and sum(defect_sev.values()) == 0:
        return 0
    base = pass_pct if total > 0 else 100
    penalty = (
        defect_sev.get("critical", 0) * 10
        + defect_sev.get("high", 0) * 6
        + defect_sev.get("medium", 0) * 3
        + defect_sev.get("low", 0) * 1
        + max(uncovered, 0) * 2
    )
    return max(0, min(100, round(base - penalty)))


def build_overall(rows, all_defects=None, uncovered_total=0):
    all_defects = all_defects or []
    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "passed")
    failed_rows = [r for r in rows if r["status"] in FAILING]
    open_defects = len(all_defects)
    sev = defect_severity_counts(all_defects)
    pass_pct = round(passed / total * 100) if total else 0
    health = health_score(pass_pct, total, sev, uncovered_total)
    return {
        "total": total,
        "passed": passed,
        "failed": len(failed_rows),
        "pct": health,
        "pass_pct": pass_pct,
        "severity": severity_counts(failed_rows),
        "open_defects": open_defects,
        "defects_by_severity": sev,
        "uncovered_failures": uncovered_total,
        "penetration_pct": round(open_defects / total * 100, 1) if total else 0,
    }


def _load_open_defects(cur):
    """Load open defects. Returns [] if the defects table/columns are missing
    so the dashboard ring still works from executions alone."""
    try:
        cur.execute(
            f"""SELECT id, module, severity, status, source_ref, defect_code
                FROM defects
                WHERE status IN ({",".join("?" for _ in OPEN_DEFECT_STATUSES)})""",
            OPEN_DEFECT_STATUSES,
        )
        return cur.fetchall()
    except Exception:
        try:
            # Pre-migration-2 schema: no source_ref
            cur.execute(
                f"""SELECT id, module, severity, status, defect_code
                    FROM defects
                    WHERE status IN ({",".join("?" for _ in OPEN_DEFECT_STATUSES)})""",
                OPEN_DEFECT_STATUSES,
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "module": r["module"],
                    "severity": r["severity"],
                    "status": r["status"],
                    "source_ref": None,
                    "defect_code": r["defect_code"],
                }
                for r in rows
            ]
        except Exception:
            return []


def get_summary(month=None, include_archived=False):
    conn = get_connection()
    try:
        cur = conn.cursor()

        # Makes sure every module in the Allure results is a registered feature.
        sync_features_from_results(conn)

        # One combined list of automated and manual executions (SQL view).
        # `ref` exists on the executions view (uuid / manual-{id}).
        if month:
            cur.execute(
                """SELECT ref, module, name, status, severity, error_message
                   FROM executions WHERE period = ?
                   ORDER BY module, name""",
                (month,),
            )
        else:
            cur.execute(
                """SELECT ref, module, name, status, severity, error_message
                   FROM executions ORDER BY module, name"""
            )
        execution_rows = cur.fetchall()

        cur.execute(
            "SELECT name FROM features WHERE archived = ?",
            (1 if include_archived else 0,),
        )
        visible_names = sorted(r["name"] for r in cur.fetchall())

        defect_rows = _load_open_defects(cur)

        cur.execute("SELECT MAX(start_ts) AS t FROM test_results")
        latest = cur.fetchone()["t"]
    finally:
        conn.close()

    last_run = None
    if latest:
        last_run = datetime.fromtimestamp(latest / 1000, tz=timezone.utc).isoformat()

    by_module = {}
    failing_refs_by_module = {}
    for r in execution_rows:
        mod = r["module"] or ""
        by_module.setdefault(mod, []).append(r)
        if r["status"] in FAILING:
            ref = r["ref"] if "ref" in r.keys() else None
            if ref:
                failing_refs_by_module.setdefault(mod, set()).add(ref)

    defects_by_module = {}
    defect_refs_by_module = {}
    for d in defect_rows:
        mod = d["module"] or ""
        defects_by_module.setdefault(mod, []).append(d)
        try:
            src = d["source_ref"]
        except (KeyError, IndexError, TypeError):
            src = d.get("source_ref") if isinstance(d, dict) else None
        if src:
            defect_refs_by_module.setdefault(mod, set()).add(src)

    modules = []
    uncovered_total = 0
    visible_defects = []
    for i, name in enumerate(visible_names, start=1):
        mod_defects = defects_by_module.get(name, [])
        failing_refs = failing_refs_by_module.get(name, set())
        defect_refs = defect_refs_by_module.get(name, set())
        uncovered = len(failing_refs - defect_refs)
        uncovered_total += uncovered
        visible_defects.extend(mod_defects)
        modules.append(
            build_module(
                i,
                name,
                by_module.get(name, []),
                defects=mod_defects,
                failing_refs=failing_refs,
                defect_refs=defect_refs,
            )
        )

    # Overall is only over visible (non-archived) features — same as module list.
    overall_rows = [r for name in visible_names for r in by_module.get(name, [])]

    return {
        "period": month,
        "modules": modules,
        "overall": build_overall(overall_rows, visible_defects, uncovered_total),
        "generated_at": last_run,
    }


def get_monthly_report(year):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT substr(period, 6, 2) AS m, status, COUNT(*) AS c
               FROM executions
               WHERE substr(period, 1, 4) = ?
               GROUP BY m, status""",
            (year,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    months = {
        f"{i:02d}": {"month": f"{year}-{i:02d}", "total": 0, "passed": 0, "failed": 0, "pct": 0}
        for i in range(1, 13)
    }
    for r in rows:
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
            "SELECT DISTINCT period AS p FROM executions WHERE period != '' ORDER BY p DESC"
        )
        return [r["p"] for r in cur.fetchall()]
    finally:
        conn.close()