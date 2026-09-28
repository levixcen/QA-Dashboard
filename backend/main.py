
import os
import re
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Depends, Header, Request, Query, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import get_connection, init_db, seed_if_empty
import reports
from auth import verify_password, hash_password, create_token, decode_token

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EVIDENCE_DIR = Path(__file__).parent / "evidence"
EVIDENCE_DIR.mkdir(exist_ok=True)

DUMMY_HASH = hash_password("timing-equalizer")
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_ATTEMPTS = 5
_login_failures = defaultdict(deque)
ALLOWED_EVIDENCE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_EVIDENCE_BYTES = 2 * 1024 * 1024  # 2MB, strictly one image per manual entry
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
YEAR_PATTERN = r"^\d{4}$"
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}
ALLOWED_DEFECT_SEVERITIES = {"critical", "high", "medium", "low"}
ALLOWED_DEFECT_STATUSES = {"open", "in_progress", "retest", "reopened", "closed"}

STATUS_COLOR_MAP = {
    "not started": "gray",
    "in progress": "blue",
    "in review": "blue",
    "completed": "green",
    "done": "green",
    "delayed": "red",
    "blocked": "pink",
    "on hold": "pink",
}


def color_for_status(status):
    return STATUS_COLOR_MAP.get((status or "").strip().lower(), "gray")


def sync_project_colors():
    """One-time-per-startup backfill so every project's color reflects
    its status per the PRD legend, including rows written directly by
    seed_if_empty() before this mapping existed."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, status, color FROM projects")
        for row in cur.fetchall():
            correct = color_for_status(row["status"])
            if row["color"] != correct:
                cur.execute("UPDATE projects SET color = ? WHERE id = ?", (correct, row["id"]))
        conn.commit()
    finally:
        conn.close()


def check_login_allowed(key):
    now = time.time()
    q = _login_failures[key]
    while q and now - q[0] > LOGIN_WINDOW_SECONDS:
        q.popleft()
    if len(q) >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


def recompute_project_pct(cur, project_id):
    """Progress is driven only by checklist completion
    (done items / total items). Test-case counts are tracked separately
    and no longer affect the progress bar. Zero checklist items → 0%."""
    cur.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if cur.fetchone() is None:
        return None

    cur.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done FROM project_checklist WHERE project_id = ?",
        (project_id,),
    )
    checklist = cur.fetchone()
    pct = (
        round(checklist["done"] / checklist["total"] * 100)
        if checklist["total"] > 0
        else 0
    )
    cur.execute("UPDATE projects SET pct = ? WHERE id = ?", (pct, project_id))
    return pct


def recompute_all_project_pcts():
    """One-shot pass so existing rows pick up the checklist-only formula
    after a server restart (avoids leaving stale averages on the board)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM projects")
        for row in cur.fetchall():
            recompute_project_pct(cur, row["id"])
        conn.commit()
    finally:
        conn.close()

def _severity_for_defect(raw):
    normalized = reports.normalize_severity(raw)
    return "medium" if normalized == "normal" else normalized

def _next_defect_code(cur):
    # Based on the highest existing id, not the row count, so deleting a
    # defect can never cause a duplicate code (defect_code is UNIQUE).
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 AS n FROM defects")
    n = cur.fetchone()["n"]
    return f"DEF-{n:03d}"


DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date(value, field):
    if value and not DATE_PATTERN.match(value):
        raise HTTPException(status_code=400, detail=f"{field} must be YYYY-MM-DD")


def _normalize_assignees(raw):
    """Turn a free-text multi-person field into a clean comma-separated string.
    Empty / whitespace-only becomes None. Names are trimmed and de-duplicated
    while preserving first-seen order."""
    if raw is None:
        return None
    seen = set()
    names = []
    for part in str(raw).split(","):
        name = part.strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return ", ".join(names) if names else None


def _resolve_feature(cur, name):
    """Returns the registry name to store on a defect. Matching ignores case
    and surrounding spaces, so typing "support" reuses "Support". A name that
    is not in the registry yet is added to it, so users can log a defect
    against any feature without setting it up first. Archived features are
    still refused, since archiving is a deliberate choice."""
    name = (name or "").strip()
    if len(name) > 80:
        raise HTTPException(status_code=400, detail="Feature name must be 80 characters or fewer")
    cur.execute("SELECT name, archived FROM features WHERE lower(name) = lower(?)", (name,))
    row = cur.fetchone()
    if row:
        if row["archived"]:
            raise HTTPException(status_code=400, detail=f'Feature "{row["name"]}" is archived')
        return row["name"]
    cur.execute("INSERT INTO features (name, archived) VALUES (?, 0)", (name,))
    return name


def _validate_close(previous_status, new_status):
    if new_status == "closed" and previous_status not in ("retest", "closed"):
        raise HTTPException(
            status_code=400,
            detail="Status can only be Closed after Retest is completed and validated by the business user.",
        )


@app.on_event("startup")
def startup():
    init_db()
    seed_if_empty()
    sync_project_colors()
    recompute_all_project_pcts()


class LoginRequest(BaseModel):
    # Accounts are identified by email; the field keeps the name "username"
    # so the existing frontend and JWT subject keep working.
    username: str
    password: str


class SignupRequest(BaseModel):
    email: str
    password: str


class ModuleMetaUpdate(BaseModel):
    pic: Optional[str] = None
    mitigation_plan: Optional[str] = None
    planned_tc_count: Optional[int] = None


class ProjectCreate(BaseModel):
    name: str
    module: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = None
    color: Optional[str] = "gray"
    tc_done: Optional[int] = 0
    tc_failed: Optional[int] = 0
    tc_total: Optional[int] = 0
    target_date: Optional[str] = None
    note: Optional[str] = None


class ProjectTestCaseUpdate(BaseModel):
    tc_done: Optional[int] = None
    tc_failed: Optional[int] = None
    tc_total: Optional[int] = None


class ProjectStatusUpdate(BaseModel):
    status: str


class ChecklistItemCreate(BaseModel):
    text: str
    # Comma-separated names, e.g. "Dara, Mario". Optional.
    assignees: Optional[str] = None


class ChecklistItemUpdate(BaseModel):
    # Any combination of these may be sent; omitted fields are left unchanged.
    done: Optional[bool] = None
    text: Optional[str] = None
    assignees: Optional[str] = None


class ProjectUpdate(BaseModel):
    """Partial update for project-level fields. owner accepts a comma-separated
    multi-person list (e.g. \"Dara, Mario\")."""
    name: Optional[str] = None
    module: Optional[str] = None
    owner: Optional[str] = None
    note: Optional[str] = None
    target_date: Optional[str] = None
    archived: Optional[bool] = None


class FeatureCreate(BaseModel):
    name: str


class FeatureArchiveUpdate(BaseModel):
    archived: bool

class DefectCreate(BaseModel):
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = "open"
    owner: Optional[str] = None
    raised_date: Optional[str] = None
    eta: Optional[str] = None
    impacted_tc_count: Optional[int] = None
    module: Optional[str] = None
    source_ref: Optional[str] = None
    cluster_id: Optional[str] = None


class DefectClusterUpdate(BaseModel):
    defect_ids: List[int]
    cluster_id: Optional[str] = None


class DefectUpdate(BaseModel):
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    owner: Optional[str] = None
    raised_date: Optional[str] = None
    eta: Optional[str] = None
    impacted_tc_count: Optional[int] = None
    module: Optional[str] = None

def get_current_user(authorization: str = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    username = decode_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE username = ?", (username,))
        exists = cur.fetchone()
    finally:
        conn.close()
    if not exists:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return username


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_MIN = 8
PASSWORD_MAX_BYTES = 72  # bcrypt ignores everything past 72 bytes
# Optional: comma-separated list such as "sedayu.com,agungsedayu.com".
# Empty means anyone with a valid email can sign up.
ALLOWED_SIGNUP_DOMAINS = {
    d.strip().lower()
    for d in os.environ.get("QA_DASHBOARD_ALLOWED_DOMAINS", "").split(",")
    if d.strip()
}
_signup_attempts = defaultdict(deque)
SIGNUP_MAX_PER_HOUR = 10


@app.post("/api/auth/signup")
def signup(payload: SignupRequest, request: Request):
    email = (payload.email or "").strip().lower()
    password = payload.password or ""

    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if ALLOWED_SIGNUP_DOMAINS and email.rsplit("@", 1)[1] not in ALLOWED_SIGNUP_DOMAINS:
        raise HTTPException(status_code=403, detail="Sign up is limited to approved company email domains")
    if len(password) < PASSWORD_MIN:
        raise HTTPException(status_code=400, detail=f"Password must be at least {PASSWORD_MIN} characters")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Password is too long")

    ip = request.client.host if request.client else "unknown"
    now = time.time()
    q = _signup_attempts[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= SIGNUP_MAX_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many sign ups from this address. Try again later.")
    q.append(now)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE lower(username) = ?", (email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (email, hash_password(password)),
        )
        conn.commit()
    finally:
        conn.close()

    return {"token": create_token(email), "username": email}


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request):
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    email = payload.username.strip().lower()
    key = (request.client.host if request.client else "unknown", email)
    check_login_allowed(key)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE lower(username) = ?", (email,))
        user = cur.fetchone()
    finally:
        conn.close()

    valid = verify_password(payload.password, user["password_hash"] if user else DUMMY_HASH)
    if not user or not valid:
        _login_failures[key].append(time.time())
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    _login_failures.pop(key, None)
    token = create_token(user["username"])
    return {"token": token, "username": user["username"]}


@app.get("/api/auth/me")
def me(username: str = Depends(get_current_user)):
    return {"username": username}


@app.get("/api/reports/summary")
def report_summary(
    month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
    archived: bool = Query(default=False),
    username: str = Depends(get_current_user),
):
    return reports.get_summary(month, include_archived=archived)


@app.get("/api/reports/monthly")
def report_monthly(
    year: str = Query(pattern=YEAR_PATTERN),
    username: str = Depends(get_current_user),
):
    return reports.get_monthly_report(year)


@app.get("/api/reports/periods")
def report_periods(username: str = Depends(get_current_user)):
    return {"periods": reports.get_periods()}


@app.get("/api/reports/project-velocity")
def project_velocity(username: str = Depends(get_current_user)):
    """Status board for every active project: completion vs expected pace,
    days left or overdue, open defects on the linked feature, and a stable
    status flag. Points are still returned for older consumers; the board
    itself does not use them."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, module, owner, target_date, created_at, pct FROM projects "
        "WHERE COALESCE(archived, 0) = 0 ORDER BY id"
    )
    projects = [dict(r) for r in cur.fetchall()]

    today = datetime.now().strftime("%Y-%m-%d")
    today_d = datetime.strptime(today, "%Y-%m-%d")

    def elapsed_pct(date_str, start_d, end_d):
        if not (start_d and end_d):
            return None
        if end_d <= start_d:
            # Created on or after the deadline: 100 once the deadline has
            # arrived, 0 before it.
            d = datetime.strptime(date_str, "%Y-%m-%d")
            return 100 if d >= end_d else 0
        d = datetime.strptime(date_str, "%Y-%m-%d")
        fraction = (d - start_d).total_seconds() / (end_d - start_d).total_seconds()
        return round(max(0.0, min(1.0, fraction)) * 100)

    result = []
    for p in projects:
        start = p["created_at"] or today
        start_d = datetime.strptime(start, "%Y-%m-%d")
        end_d = datetime.strptime(p["target_date"], "%Y-%m-%d") if p["target_date"] else None

        cur.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done "
            "FROM project_checklist WHERE project_id = ?",
            (p["id"],),
        )
        checklist = cur.fetchone()
        items_total = checklist["total"]
        items_done = checklist["done"]

        cur.execute(
            """SELECT completed_at FROM project_checklist
               WHERE project_id = ? AND done = 1 AND completed_at IS NOT NULL
               ORDER BY completed_at""",
            (p["id"],),
        )
        completion_dates = [r["completed_at"] for r in cur.fetchall()]

        points = [{"date": start, "pct": 0, "elapsed_pct": elapsed_pct(start, start_d, end_d)}]
        if items_total > 0:
            for i, completed_date in enumerate(completion_dates, start=1):
                points.append({
                    "date": completed_date,
                    "pct": round(i / items_total * 100),
                    "elapsed_pct": elapsed_pct(completed_date, start_d, end_d),
                })
        if points[-1]["date"] != today:
            points.append({
                "date": today,
                "pct": p["pct"],
                "elapsed_pct": elapsed_pct(today, start_d, end_d),
            })

        open_defects = 0
        module = (p.get("module") or "").strip()
        if module:
            cur.execute(
                """SELECT COUNT(*) AS c FROM defects
                   WHERE lower(module) = lower(?) AND status != 'closed'""",
                (module,),
            )
            open_defects = cur.fetchone()["c"]

        pace_pct = None
        days_left = None
        gap = None
        if end_d:
            pace_pct = elapsed_pct(today, start_d, end_d)
            if today_d > end_d:
                pace_pct = 100
            days_left = (end_d - today_d).days
            gap = pace_pct - p["pct"]

        current = p["pct"] or 0
        if current >= 100:
            status_flag = "done"
        elif not end_d:
            status_flag = "no_deadline"
        elif today_d > end_d and current < 100:
            status_flag = "overdue"
        elif gap is not None and gap <= 0:
            status_flag = "on_track"
        elif gap is not None and gap <= 15:
            status_flag = "at_risk"
        else:
            status_flag = "behind"

        result.append({
            "id": p["id"],
            "name": p["name"],
            "module": p.get("module"),
            "owner": p["owner"],
            "target_date": p["target_date"],
            "created_at": p["created_at"],
            "current_pct": current,
            "items_total": items_total,
            "items_done": items_done,
            "open_defects": open_defects,
            "pace_pct": pace_pct,
            "days_left": days_left,
            "gap": gap,
            "status_flag": status_flag,
            "points": points,
        })

    conn.close()
    return {"projects": result}


@app.post("/api/features")
def create_feature(payload: FeatureCreate, username: str = Depends(get_current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Feature name is required")
    if len(name) > 80:
        raise HTTPException(status_code=400, detail="Feature name must be 80 characters or fewer")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT name FROM features WHERE lower(name) = lower(?)", (name,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail=f'"{name}" already exists')

    cur.execute("INSERT INTO features (name, archived) VALUES (?, 0)", (name,))
    conn.commit()
    conn.close()
    return {"name": name, "archived": False}


@app.patch("/api/features/{name}/archive")
def set_feature_archived(
    name: str,
    payload: FeatureArchiveUpdate,
    username: str = Depends(get_current_user),
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT name FROM features WHERE name = ?", (name,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Feature not found")

    cur.execute(
        "UPDATE features SET archived = ? WHERE name = ?",
        (1 if payload.archived else 0, name),
    )
    conn.commit()
    conn.close()
    return {"name": name, "archived": payload.archived}


@app.delete("/api/features/{name}")
def delete_feature(name: str, username: str = Depends(get_current_user)):
    """Removes the feature from the registry and deletes its manual
    entries and evidence files. Does not touch test_results, so a module
    that also has automated history will simply reappear (unarchived) the
    next time reports.get_summary() re-registers known module names."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT name FROM features WHERE name = ?", (name,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Feature not found")

    cur.execute("SELECT COUNT(*) AS c FROM defects WHERE module = ?", (name,))
    defect_count = cur.fetchone()["c"]
    if defect_count:
        conn.close()
        raise HTTPException(
            status_code=409,
            detail=(
                f'"{name}" still has {defect_count} defect(s). Archive the feature instead, '
                "or delete or reassign those defects first."
            ),
        )

    cur.execute(
        "SELECT evidence_path FROM manual_entries WHERE feature_name = ? AND evidence_path IS NOT NULL",
        (name,),
    )
    evidence_files = [row["evidence_path"] for row in cur.fetchall()]

    cur.execute("DELETE FROM manual_entries WHERE feature_name = ?", (name,))
    cur.execute("DELETE FROM features WHERE name = ?", (name,))
    conn.commit()
    conn.close()

    for filename in evidence_files:
        try:
            (EVIDENCE_DIR / filename).unlink(missing_ok=True)
        except OSError:
            pass

    return {"deleted": True, "name": name}


@app.post("/api/features/ingest")
async def ingest_feature_entry(
    name: str = Form(...),
    period: str = Form(...),
    status: str = Form(...),
    description: str = Form(default=""),
    severity: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
    username: str = Depends(get_current_user),
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Feature name is required")
    if not re.match(MONTH_PATTERN, period or ""):
        raise HTTPException(status_code=400, detail="Period must be in YYYY-MM format")

    status = status.strip().lower()
    if status not in ("passed", "failed"):
        raise HTTPException(status_code=400, detail='Status must be "passed" or "failed"')

    if severity is not None:
        severity = severity.strip().lower()
        if severity not in ALLOWED_SEVERITIES:
            raise HTTPException(status_code=400, detail="Severity must be critical, high, medium, or low")

    description = description.strip()
    if len(description) > 2000:
        raise HTTPException(status_code=400, detail="Description must be 2000 characters or fewer")

    conn = get_connection()
    cur = conn.cursor()

    # Reuse the registered spelling of a feature ("login" resolves to "Login")
    # instead of silently creating a near duplicate.
    cur.execute("SELECT name FROM features WHERE lower(name) = lower(?)", (name,))
    existing_feature = cur.fetchone()
    if existing_feature:
        name = existing_feature["name"]
    else:
        cur.execute("INSERT INTO features (name, archived) VALUES (?, 0)", (name,))

    evidence_filename = None
    evidence_type = None
    evidence_size = None

    if file is not None:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EVIDENCE_EXT:
            conn.close()
            raise HTTPException(status_code=400, detail="Evidence must be a PNG, JPG, GIF, or WEBP image")

        contents = await file.read()
        if len(contents) == 0:
            conn.close()
            raise HTTPException(status_code=400, detail="Evidence file is empty")
        if len(contents) > MAX_EVIDENCE_BYTES:
            conn.close()
            raise HTTPException(status_code=400, detail="Evidence image must be 2MB or smaller")

        evidence_filename = f"{uuid.uuid4().hex}{ext}"
        (EVIDENCE_DIR / evidence_filename).write_bytes(contents)
        evidence_type = file.content_type
        evidence_size = len(contents)

    cur.execute("""
        INSERT INTO manual_entries
            (feature_name, period, status, description, severity, evidence_path, evidence_type, evidence_size)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name, period, status, description or None, severity,
        evidence_filename, evidence_type, evidence_size,
    ))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    return {
        "id": new_id,
        "feature_name": name,
        "period": period,
        "status": status,
        "description": description or None,
        "severity": severity,
        "evidence_url": f"/api/evidence/{evidence_filename}" if evidence_filename else None,
    }


@app.get("/api/projects")
def list_projects(
    month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
    archived: bool = Query(default=False),
    username: str = Depends(get_current_user),
):
    """Active board by default. Pass archived=true to list archived projects only."""
    conn = get_connection()
    cur = conn.cursor()
    archived_flag = 1 if archived else 0
    if month:
        cur.execute(
            "SELECT * FROM projects WHERE substr(target_date, 1, 7) = ? AND COALESCE(archived, 0) = ?",
            (month, archived_flag),
        )
    else:
        cur.execute("SELECT * FROM projects WHERE COALESCE(archived, 0) = ?", (archived_flag,))
    rows = [dict(r) for r in cur.fetchall()]

    for row in rows:
        cur.execute(
            "SELECT id, text, done, evidence_path, evidence_type, assignees FROM project_checklist WHERE project_id = ? ORDER BY id",
            (row["id"],),
        )
        row["checklist"] = [dict(c) for c in cur.fetchall()]

    conn.close()
    return rows


@app.post("/api/projects")
def create_project(payload: ProjectCreate, username: str = Depends(get_current_user)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Project name is required")

    conn = get_connection()
    cur = conn.cursor()

    status = payload.status or "Not Started"
    owner = _normalize_assignees(payload.owner)
    created_at = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        INSERT INTO projects
            (name, module, owner, status, color, pct, tc_done, tc_failed, tc_total, target_date, note, created_at)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
    """, (
        payload.name.strip(), payload.module, owner, status,
        color_for_status(status), payload.tc_done, payload.tc_failed, payload.tc_total,
        payload.target_date, payload.note, created_at,
    ))
    conn.commit()
    new_id = cur.lastrowid
    recompute_project_pct(cur, new_id)
    conn.commit()

    cur.execute("SELECT * FROM projects WHERE id = ?", (new_id,))
    row = dict(cur.fetchone())
    row["checklist"] = []
    conn.close()
    return row


@app.patch("/api/projects/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    username: str = Depends(get_current_user),
):
    """Partial update for project-level fields. owner accepts a comma-separated
    multi-person list (e.g. \"Dara, Mario\")."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        existing = cur.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Project not found")

        fields = payload.model_dump(exclude_unset=True)
        if "name" in fields:
            fields["name"] = (fields["name"] or "").strip()
            if not fields["name"]:
                raise HTTPException(status_code=400, detail="Project name is required")
        if "owner" in fields:
            fields["owner"] = _normalize_assignees(fields["owner"])
        if "target_date" in fields:
            fields["target_date"] = fields["target_date"] or None
            _check_date(fields["target_date"], "target_date")
        if "module" in fields:
            fields["module"] = (fields["module"] or "").strip() or None
        if "note" in fields:
            fields["note"] = (fields["note"] or "").strip() or None
        if "archived" in fields:
            fields["archived"] = 1 if fields["archived"] else 0

        if fields:
            assignments = ", ".join(f"{col} = ?" for col in fields)
            cur.execute(
                f"UPDATE projects SET {assignments} WHERE id = ?",
                (*fields.values(), project_id),
            )
            conn.commit()

        cur.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = dict(cur.fetchone())
        cur.execute(
            "SELECT id, text, done, evidence_path, evidence_type, assignees FROM project_checklist WHERE project_id = ? ORDER BY id",
            (project_id,),
        )
        row["checklist"] = [dict(c) for c in cur.fetchall()]
        return row
    finally:
        conn.close()


@app.patch("/api/projects/{project_id}/testcases")
def update_project_testcases(
    project_id: int,
    payload: ProjectTestCaseUpdate,
    username: str = Depends(get_current_user),
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT tc_done, tc_failed, tc_total FROM projects WHERE id = ?", (project_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")

    tc_done = payload.tc_done if payload.tc_done is not None else existing["tc_done"]
    tc_failed = payload.tc_failed if payload.tc_failed is not None else existing["tc_failed"]
    tc_total = payload.tc_total if payload.tc_total is not None else existing["tc_total"]

    for label, value in (("Passed", tc_done), ("Failed", tc_failed), ("Target", tc_total)):
        if value < 0:
            conn.close()
            raise HTTPException(status_code=400, detail=f"{label} cannot be negative")

    cur.execute(
        "UPDATE projects SET tc_done = ?, tc_failed = ?, tc_total = ? WHERE id = ?",
        (tc_done, tc_failed, tc_total, project_id),
    )
    recompute_project_pct(cur, project_id)
    conn.commit()

    cur.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = dict(cur.fetchone())
    cur.execute(
        "SELECT id, text, done, evidence_path, evidence_type, assignees FROM project_checklist WHERE project_id = ? ORDER BY id",
        (project_id,),
    )
    row["checklist"] = [dict(c) for c in cur.fetchall()]
    conn.close()
    return row


@app.patch("/api/projects/{project_id}/status")
def update_project_status(
    project_id: int,
    payload: ProjectStatusUpdate,
    username: str = Depends(get_current_user),
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")

    color = color_for_status(payload.status)
    cur.execute(
        "UPDATE projects SET status = ?, color = ? WHERE id = ?",
        (payload.status, color, project_id),
    )
    conn.commit()

    cur.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = dict(cur.fetchone())
    cur.execute(
        "SELECT id, text, done, evidence_path, evidence_type, assignees FROM project_checklist WHERE project_id = ? ORDER BY id",
        (project_id,),
    )
    row["checklist"] = [dict(c) for c in cur.fetchall()]
    conn.close()
    return row


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, username: str = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")

    cur.execute(
        "SELECT evidence_path FROM project_checklist WHERE project_id = ? AND evidence_path IS NOT NULL",
        (project_id,),
    )
    evidence_files = [row["evidence_path"] for row in cur.fetchall()]

    cur.execute("DELETE FROM project_checklist WHERE project_id = ?", (project_id,))
    cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

    for filename in evidence_files:
        try:
            (EVIDENCE_DIR / filename).unlink(missing_ok=True)
        except OSError:
            pass

    return {"deleted": True, "id": project_id}


@app.post("/api/projects/{project_id}/checklist")
def add_checklist_item(
    project_id: int,
    payload: ChecklistItemCreate,
    username: str = Depends(get_current_user),
):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Checklist text is required")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")

    assignees = _normalize_assignees(payload.assignees)
    cur.execute(
        "INSERT INTO project_checklist (project_id, text, done, assignees) VALUES (?, ?, 0, ?)",
        (project_id, payload.text.strip(), assignees),
    )
    conn.commit()
    new_id = cur.lastrowid

    pct = recompute_project_pct(cur, project_id)
    conn.commit()

    cur.execute(
        "SELECT id, text, done, evidence_path, evidence_type, assignees FROM project_checklist WHERE id = ?",
        (new_id,),
    )
    row = dict(cur.fetchone())
    row["project_pct"] = pct
    conn.close()
    return row


@app.patch("/api/projects/checklist/{item_id}")
def update_checklist_item(
    item_id: int,
    payload: ChecklistItemUpdate,
    username: str = Depends(get_current_user),
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT project_id, done FROM project_checklist WHERE id = ?", (item_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Checklist item not found")

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        cur.execute(
            "SELECT id, text, done, evidence_path, evidence_type, assignees FROM project_checklist WHERE id = ?",
            (item_id,),
        )
        row = dict(cur.fetchone())
        row["project_pct"] = None
        conn.close()
        return row

    if "text" in fields:
        fields["text"] = (fields["text"] or "").strip()
        if not fields["text"]:
            conn.close()
            raise HTTPException(status_code=400, detail="Checklist text is required")
    if "assignees" in fields:
        fields["assignees"] = _normalize_assignees(fields["assignees"])
    if "done" in fields:
        fields["done"] = 1 if fields["done"] else 0
        if fields["done"] and not existing["done"]:
            fields["completed_at"] = datetime.now().strftime("%Y-%m-%d")
        elif not fields["done"] and existing["done"]:
            fields["completed_at"] = None

    assignments = ", ".join(f"{col} = ?" for col in fields)
    cur.execute(
        f"UPDATE project_checklist SET {assignments} WHERE id = ?",
        (*fields.values(), item_id),
    )
    conn.commit()

    pct = None
    if "done" in fields:
        pct = recompute_project_pct(cur, existing["project_id"])
        conn.commit()

    cur.execute(
        "SELECT id, text, done, evidence_path, evidence_type, assignees FROM project_checklist WHERE id = ?",
        (item_id,),
    )
    row = dict(cur.fetchone())
    row["project_pct"] = pct
    conn.close()
    return row


@app.post("/api/projects/checklist/{item_id}/evidence")
async def upload_checklist_evidence(
    item_id: int,
    file: UploadFile = File(...),
    username: str = Depends(get_current_user),
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT project_id, evidence_path FROM project_checklist WHERE id = ?", (item_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Checklist item not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EVIDENCE_EXT:
        conn.close()
        raise HTTPException(status_code=400, detail="Evidence must be a PNG, JPG, GIF, or WEBP image")

    contents = await file.read()
    if len(contents) == 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Evidence file is empty")
    if len(contents) > MAX_EVIDENCE_BYTES:
        conn.close()
        raise HTTPException(status_code=400, detail="Evidence image must be 2MB or smaller")

    old_filename = existing["evidence_path"]
    evidence_filename = f"{uuid.uuid4().hex}{ext}"
    (EVIDENCE_DIR / evidence_filename).write_bytes(contents)

    cur.execute(
        "UPDATE project_checklist SET evidence_path = ?, evidence_type = ? WHERE id = ?",
        (evidence_filename, file.content_type, item_id),
    )
    conn.commit()

    if old_filename:
        try:
            (EVIDENCE_DIR / old_filename).unlink(missing_ok=True)
        except OSError:
            pass

    cur.execute(
        "SELECT id, text, done, evidence_path, evidence_type, assignees FROM project_checklist WHERE id = ?",
        (item_id,),
    )
    row = dict(cur.fetchone())
    conn.close()
    return row


@app.delete("/api/projects/checklist/{item_id}")
def delete_checklist_item(item_id: int, username: str = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT project_id, evidence_path FROM project_checklist WHERE id = ?", (item_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Checklist item not found")

    cur.execute("DELETE FROM project_checklist WHERE id = ?", (item_id,))
    conn.commit()

    pct = recompute_project_pct(cur, existing["project_id"])
    conn.commit()
    conn.close()

    if existing["evidence_path"]:
        try:
            (EVIDENCE_DIR / existing["evidence_path"]).unlink(missing_ok=True)
        except OSError:
            pass

    return {"deleted": True, "id": item_id, "project_pct": pct}


@app.get("/api/features")
def list_features(username: str = Depends(get_current_user)):
    """Master registry of feature names. Defects and Trends read from here.
    Includes open defect counts so Features stays the root of health."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name, archived FROM features ORDER BY name COLLATE NOCASE")
        features = cur.fetchall()
        cur.execute(
            """SELECT module, COUNT(*) AS open_defects
               FROM defects
               WHERE status IN ('open', 'in_progress', 'retest', 'reopened')
               GROUP BY module"""
        )
        open_by_module = {r["module"]: r["open_defects"] for r in cur.fetchall()}
        return [
            {
                "name": r["name"],
                "archived": bool(r["archived"]),
                "open_defects": open_by_module.get(r["name"], 0),
            }
            for r in features
        ]
    finally:
        conn.close()


@app.get("/api/defects")
def list_defects(username: str = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM defects ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/api/defects")
def create_defect(payload: DefectCreate, username: str = Depends(get_current_user)):
    conn = get_connection()
    try:
        cur = conn.cursor()

        source_row = None
        if payload.source_ref:
            cur.execute(
                "SELECT module, name, severity, status FROM executions WHERE ref = ?",
                (payload.source_ref,),
            )
            source_row = cur.fetchone()
            if not source_row or source_row["status"] not in reports.FAILING:
                raise HTTPException(status_code=404, detail="Unknown or non-failing test reference")
            cur.execute("SELECT id FROM defects WHERE source_ref = ?", (payload.source_ref,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="A defect has already been raised for this test")

        description = (payload.description or "").strip()
        if not description and source_row:
            description = source_row["name"]
        if not description:
            raise HTTPException(status_code=400, detail="Description is required")

        severity = payload.severity
        if not severity and source_row:
            severity = _severity_for_defect(source_row["severity"])
        if severity not in ALLOWED_DEFECT_SEVERITIES:
            raise HTTPException(status_code=400, detail="Invalid severity")

        status = payload.status or "open"
        if status not in ALLOWED_DEFECT_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        if status == "closed":
            raise HTTPException(status_code=400, detail="A new defect cannot start as Closed")

        module = (payload.module or "").strip()
        if not module and source_row:
            module = source_row["module"] or ""
        if not module:
            raise HTTPException(status_code=400, detail="Pick a feature for this defect")

        _check_date(payload.raised_date, "raised_date")
        _check_date(payload.eta, "eta")

        module = _resolve_feature(cur, module)
        code = _next_defect_code(cur)
        now = datetime.now().isoformat(timespec="seconds")
        raised = payload.raised_date or now[:10]
        impacted = payload.impacted_tc_count
        if impacted is None:
            impacted = 1 if source_row else 0

        cur.execute(
            """INSERT INTO defects
               (defect_code, description, severity, status, owner, raised_date,
                eta, impacted_tc_count, module, source_ref, cluster_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, description, severity, status, payload.owner,
             raised, payload.eta, max(impacted, 0), module,
             payload.source_ref, payload.cluster_id, now),
        )
        conn.commit()
        cur.execute("SELECT * FROM defects WHERE id = ?", (cur.lastrowid,))
        return dict(cur.fetchone())
    finally:
        conn.close()

@app.patch("/api/defects/{defect_id}")
def update_defect(
    defect_id: int,
    payload: DefectUpdate,
    username: str = Depends(get_current_user),
):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM defects WHERE id = ?", (defect_id,))
        existing = cur.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Defect not found")

        fields = payload.model_dump(exclude_unset=True)
        if "description" in fields:
            fields["description"] = (fields["description"] or "").strip()
            if not fields["description"]:
                raise HTTPException(status_code=400, detail="Description is required")
        if "severity" in fields and fields["severity"] not in ALLOWED_DEFECT_SEVERITIES:
            raise HTTPException(status_code=400, detail="Invalid severity")
        if "status" in fields:
            if fields["status"] not in ALLOWED_DEFECT_STATUSES:
                raise HTTPException(status_code=400, detail="Invalid status")
            _validate_close(existing["status"], fields["status"])
            if fields["status"] == "closed" and existing["status"] != "closed":
                fields["closed_at"] = datetime.now().isoformat(timespec="seconds")
            elif fields["status"] != "closed":
                fields["closed_at"] = None
        if "raised_date" in fields:
            _check_date(fields["raised_date"], "raised_date")
        if "eta" in fields:
            _check_date(fields["eta"], "eta")
        if "impacted_tc_count" in fields:
            fields["impacted_tc_count"] = max(fields["impacted_tc_count"] or 0, 0)
        if "module" in fields:
            module = (fields["module"] or "").strip()
            if not module:
                raise HTTPException(status_code=400, detail="Pick a feature for this defect")
            # Only re-validate when the feature actually changes, so older
            # defects pointing at a since-archived feature can still be edited.
            if module != existing["module"]:
                module = _resolve_feature(cur, module)
            fields["module"] = module

        if fields:
            assignments = ", ".join(f"{col} = ?" for col in fields)
            cur.execute(
                f"UPDATE defects SET {assignments} WHERE id = ?",
                (*fields.values(), defect_id),
            )
            conn.commit()

        cur.execute("SELECT * FROM defects WHERE id = ?", (defect_id,))
        return dict(cur.fetchone())
    finally:
        conn.close()


@app.delete("/api/defects/{defect_id}")
def delete_defect(defect_id: int, username: str = Depends(get_current_user)):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM defects WHERE id = ?", (defect_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Defect not found")
        cur.execute("DELETE FROM defects WHERE id = ?", (defect_id,))
        conn.commit()
        return {"deleted": True, "id": defect_id}
    finally:
        conn.close()

@app.get("/api/defects/candidates")
def list_defect_candidates(
    month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
    username: str = Depends(get_current_user),
):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if month:
            cur.execute(
                """SELECT e.ref, e.module, e.name, e.severity, e.error_message, e.run_date
                   FROM executions e
                   LEFT JOIN defects d ON d.source_ref = e.ref
                   WHERE e.status IN (?, ?) AND d.id IS NULL AND e.period = ?
                   ORDER BY e.run_date DESC""",
                (*reports.FAILING, month),
            )
        else:
            cur.execute(
                """SELECT e.ref, e.module, e.name, e.severity, e.error_message, e.run_date
                   FROM executions e
                   LEFT JOIN defects d ON d.source_ref = e.ref
                   WHERE e.status IN (?, ?) AND d.id IS NULL
                   ORDER BY e.run_date DESC""",
                reports.FAILING,
            )
        rows = cur.fetchall()
        return [
            {
                "ref": r["ref"],
                "module": r["module"],
                "name": r["name"],
                "defect_severity": _severity_for_defect(r["severity"]),
                "error_message": r["error_message"],
                "run_date": r["run_date"],
            }
            for r in rows
        ]
    finally:
        conn.close()


@app.post("/api/defects/from-failures")
def create_defects_from_failures(
    month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
    username: str = Depends(get_current_user),
):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if month:
            cur.execute(
                """SELECT e.ref, e.module, e.name, e.severity
                   FROM executions e
                   LEFT JOIN defects d ON d.source_ref = e.ref
                   WHERE e.status IN (?, ?) AND d.id IS NULL AND e.period = ?""",
                (*reports.FAILING, month),
            )
        else:
            cur.execute(
                """SELECT e.ref, e.module, e.name, e.severity
                   FROM executions e
                   LEFT JOIN defects d ON d.source_ref = e.ref
                   WHERE e.status IN (?, ?) AND d.id IS NULL""",
                reports.FAILING,
            )
        candidates = cur.fetchall()

        created = 0
        skipped = 0
        now = datetime.now().isoformat(timespec="seconds")
        for row in candidates:
            module = (row["module"] or "").strip()
            cur.execute("SELECT archived FROM features WHERE name = ?", (module,))
            feature = cur.fetchone()
            if not module or not feature or feature["archived"]:
                skipped += 1
                continue
            code = _next_defect_code(cur)
            cur.execute(
                """INSERT INTO defects
                   (defect_code, description, severity, status, owner, raised_date,
                    eta, impacted_tc_count, module, source_ref, cluster_id, created_at)
                   VALUES (?, ?, ?, 'open', NULL, ?, NULL, 1, ?, ?, NULL, ?)""",
                (code, row["name"], _severity_for_defect(row["severity"]),
                 now[:10], module, row["ref"], now),
            )
            created += 1
        conn.commit()
        return {"created": created, "skipped": skipped}
    finally:
        conn.close()


@app.post("/api/defects/cluster")
def cluster_defects(payload: DefectClusterUpdate, username: str = Depends(get_current_user)):
    if len(payload.defect_ids) < 2:
        raise HTTPException(status_code=400, detail="Pick at least two defects to cluster")

    conn = get_connection()
    try:
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in payload.defect_ids)
        cur.execute(f"SELECT id FROM defects WHERE id IN ({placeholders})", payload.defect_ids)
        found = {r["id"] for r in cur.fetchall()}
        missing = set(payload.defect_ids) - found
        if missing:
            raise HTTPException(status_code=404, detail=f"Defect(s) not found: {sorted(missing)}")

        cluster_id = payload.cluster_id or f"CLU-{uuid.uuid4().hex[:8]}"
        cur.execute(
            f"UPDATE defects SET cluster_id = ? WHERE id IN ({placeholders})",
            (cluster_id, *payload.defect_ids),
        )
        conn.commit()
        cur.execute(f"SELECT * FROM defects WHERE id IN ({placeholders})", payload.defect_ids)
        return {"cluster_id": cluster_id, "defects": [dict(r) for r in cur.fetchall()]}
    finally:
        conn.close()


@app.post("/api/defects/{defect_id}/uncluster")
def uncluster_defect(defect_id: int, username: str = Depends(get_current_user)):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM defects WHERE id = ?", (defect_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Defect not found")
        cur.execute("UPDATE defects SET cluster_id = NULL WHERE id = ?", (defect_id,))
        conn.commit()
        return {"id": defect_id, "cluster_id": None}
    finally:
        conn.close()

@app.get("/api/defects/penetration")
def defect_penetration(
    month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
    username: str = Depends(get_current_user),
):
    """Open defects as a share of executed test cases (automated + manual).
    Optional month (YYYY-MM) scopes both counts to that period so Trends
    and the dashboard stay aligned with the selected period."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if month:
            cur.execute(
                "SELECT COUNT(*) AS c FROM defects WHERE status != 'closed' AND substr(raised_date, 1, 7) = ?",
                (month,),
            )
            total_open = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM executions WHERE period = ?", (month,))
            executed = cur.fetchone()["c"]
        else:
            cur.execute("SELECT COUNT(*) AS c FROM defects WHERE status != 'closed'")
            total_open = cur.fetchone()["c"]
            cur.execute("SELECT COUNT(*) AS c FROM executions")
            executed = cur.fetchone()["c"]
        pct = round(total_open / executed * 100, 1) if executed else 0
        return {
            "total_open": total_open,
            "executed_tcs": executed,
            "penetration_pct": pct,
            "period": month,
        }
    finally:
        conn.close()


@app.get("/api/modules/{module_name}/tests")
def list_module_tests(
    module_name: str,
    month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
    username: str = Depends(get_current_user),
):
    conn = get_connection()
    cur = conn.cursor()
    if month:
        cur.execute("""
            SELECT uuid, name, status, error_message, run_date, severity
            FROM test_results
            WHERE module = ? AND substr(run_date, 1, 7) = ?
            ORDER BY name
        """, (module_name, month))
    else:
        cur.execute("""
            SELECT uuid, name, status, error_message, run_date, severity
            FROM test_results
            WHERE module = ?
            ORDER BY name
        """, (module_name,))
    tests = [dict(r) for r in cur.fetchall()]

    for test in tests:
        cur.execute("""
            SELECT attachment_name, file_path, type
            FROM attachments
            WHERE test_uuid = ?
        """, (test["uuid"],))
        test["attachments"] = [
            {
                "name": a["attachment_name"],
                "type": a["type"],
                "url": f"/api/evidence/{Path(a['file_path']).name}",
            }
            for a in cur.fetchall()
        ]

    if month:
        cur.execute("""
            SELECT id, status, description, period, evidence_path, evidence_type, severity
            FROM manual_entries
            WHERE feature_name = ? AND period = ?
            ORDER BY id
        """, (module_name, month))
    else:
        cur.execute("""
            SELECT id, status, description, period, evidence_path, evidence_type, severity
            FROM manual_entries
            WHERE feature_name = ?
            ORDER BY id
        """, (module_name,))

    for m in cur.fetchall():
        tests.append({
            "uuid": f"manual-{m['id']}",
            "name": m["description"] or "Manual entry",
            "status": m["status"],
            "severity": m["severity"],
            "error_message": None,
            "run_date": f"{m['period']}-01",
            "attachments": [
                {
                    "name": "Evidence",
                    "type": m["evidence_type"],
                    "url": f"/api/evidence/{m['evidence_path']}",
                }
            ] if m["evidence_path"] else [],
        })

    refs = [t["uuid"] for t in tests]
    defect_by_ref = {}
    if refs:
        placeholders = ",".join("?" for _ in refs)
        cur.execute(
            f"SELECT defect_code, source_ref FROM defects WHERE source_ref IN ({placeholders})",
            refs,
        )
        for d in cur.fetchall():
            defect_by_ref[d["source_ref"]] = {"code": d["defect_code"]}

    for t in tests:
        t["defect"] = defect_by_ref.get(t["uuid"])

    conn.close()
    return tests

@app.get("/api/evidence/{filename}")
def get_evidence(filename: str, username: str = Depends(get_current_user)):
    base = EVIDENCE_DIR.resolve()
    target = (base / filename).resolve()
    if target.parent != base or target.suffix.lower() not in ALLOWED_EVIDENCE_EXT or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target, headers={"X-Content-Type-Options": "nosniff"})


@app.get("/api/module-meta")
def list_module_meta(username: str = Depends(get_current_user)):
    """Returns manually-maintained per-module fields: PIC, mitigation plan,
    and planned test case count. Not derived from the Allure pipeline."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM module_meta")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.patch("/api/module-meta/{module_name}")
def update_module_meta(
    module_name: str,
    payload: ModuleMetaUpdate,
    username: str = Depends(get_current_user),
):
    """Partial update: only fields present in the request body are changed.
    Fields omitted (left as None) keep their existing stored value."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM module_meta WHERE module = ?", (module_name,))
    existing = cur.fetchone()

    pic = payload.pic if payload.pic is not None else (existing["pic"] if existing else None)
    mitigation_plan = (
        payload.mitigation_plan if payload.mitigation_plan is not None
        else (existing["mitigation_plan"] if existing else None)
    )
    planned_tc_count = (
        payload.planned_tc_count if payload.planned_tc_count is not None
        else (existing["planned_tc_count"] if existing else None)
    )

    cur.execute("""
        INSERT INTO module_meta (module, pic, mitigation_plan, planned_tc_count)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(module) DO UPDATE SET
            pic = excluded.pic,
            mitigation_plan = excluded.mitigation_plan,
            planned_tc_count = excluded.planned_tc_count
    """, (module_name, pic, mitigation_plan, planned_tc_count))
    conn.commit()

    cur.execute("SELECT * FROM module_meta WHERE module = ?", (module_name,))
    row = dict(cur.fetchone())
    conn.close()
    return row
