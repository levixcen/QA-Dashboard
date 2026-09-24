import re
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional
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
    """A project's progress bar is never set directly by the client. It's
    derived from whichever of two signals the project actually has:
    checklist completion (done items / total items) and test-case
    completion (tc_done / tc_total). When both exist, pct is their
    average, so neither signal alone can overstate progress. When only
    one exists, that one alone drives it. Called after every mutation
    that could change either input: checklist add/toggle/delete and the
    test-case edit endpoint."""
    cur.execute("SELECT tc_done, tc_total FROM projects WHERE id = ?", (project_id,))
    proj = cur.fetchone()
    if proj is None:
        return None

    cur.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done FROM project_checklist WHERE project_id = ?",
        (project_id,),
    )
    checklist = cur.fetchone()

    ratios = []
    if checklist["total"] > 0:
        ratios.append(checklist["done"] / checklist["total"] * 100)
    if proj["tc_total"] and proj["tc_total"] > 0:
        ratios.append(min(proj["tc_done"], proj["tc_total"]) / proj["tc_total"] * 100)

    pct = round(sum(ratios) / len(ratios)) if ratios else 0
    cur.execute("UPDATE projects SET pct = ? WHERE id = ?", (pct, project_id))
    return pct

def _next_defect_code(cur):
    cur.execute("SELECT COUNT(*) AS c FROM defects")
    n = cur.fetchone()["c"] + 1
    return f"DEF-{n:03d}"


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


class LoginRequest(BaseModel):
    username: str
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


class ChecklistItemUpdate(BaseModel):
    done: bool


class FeatureCreate(BaseModel):
    name: str


class FeatureArchiveUpdate(BaseModel):
    archived: bool

class DefectCreate(BaseModel):
    description: str
    severity: str
    status: Optional[str] = "open"
    owner: Optional[str] = None
    raised_date: Optional[str] = None
    eta: Optional[str] = None
    impacted_tc_count: Optional[int] = 0
    module: Optional[str] = None


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


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request):
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    key = (request.client.host if request.client else "unknown", payload.username.lower())
    check_login_allowed(key)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (payload.username,))
        user = cur.fetchone()
    finally:
        conn.close()

    valid = verify_password(payload.password, user["password_hash"] if user else DUMMY_HASH)
    if not user or not valid:
        _login_failures[key].append(time.time())
        raise HTTPException(status_code=401, detail="Incorrect username or password")

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

    cur.execute("INSERT OR IGNORE INTO features (name, archived) VALUES (?, 0)", (name,))

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
    username: str = Depends(get_current_user),
):
    conn = get_connection()
    cur = conn.cursor()
    if month:
        cur.execute("SELECT * FROM projects WHERE substr(target_date, 1, 7) = ?", (month,))
    else:
        cur.execute("SELECT * FROM projects")
    rows = [dict(r) for r in cur.fetchall()]

    for row in rows:
        cur.execute(
            "SELECT id, text, done, evidence_path, evidence_type FROM project_checklist WHERE project_id = ? ORDER BY id",
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
    cur.execute("""
        INSERT INTO projects
            (name, module, owner, status, color, pct, tc_done, tc_failed, tc_total, target_date, note)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
    """, (
        payload.name.strip(), payload.module, payload.owner, status,
        color_for_status(status), payload.tc_done, payload.tc_failed, payload.tc_total,
        payload.target_date, payload.note,
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
        "SELECT id, text, done FROM project_checklist WHERE project_id = ? ORDER BY id",
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
        "SELECT id, text, done, evidence_path, evidence_type FROM project_checklist WHERE project_id = ? ORDER BY id",
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

    cur.execute("DELETE FROM project_checklist WHERE project_id = ?", (project_id,))
    cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
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

    cur.execute(
        "INSERT INTO project_checklist (project_id, text, done) VALUES (?, ?, 0)",
        (project_id, payload.text.strip()),
    )
    conn.commit()
    new_id = cur.lastrowid

    pct = recompute_project_pct(cur, project_id)
    conn.commit()

    cur.execute("SELECT id, text, done FROM project_checklist WHERE id = ?", (new_id,))
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

    cur.execute("SELECT project_id FROM project_checklist WHERE id = ?", (item_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Checklist item not found")

    cur.execute(
        "UPDATE project_checklist SET done = ? WHERE id = ?",
        (1 if payload.done else 0, item_id),
    )
    conn.commit()

    pct = recompute_project_pct(cur, existing["project_id"])
    conn.commit()

    cur.execute("SELECT id, text, done FROM project_checklist WHERE id = ?", (item_id,))
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
        "SELECT id, text, done, evidence_path, evidence_type FROM project_checklist WHERE id = ?",
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


@app.get("/api/tasks")
def list_tasks(username: str = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


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
            SELECT uuid, name, status, error_message, run_date
            FROM test_results
            WHERE module = ? AND substr(run_date, 1, 7) = ?
            ORDER BY name
        """, (module_name, month))
    else:
        cur.execute("""
            SELECT uuid, name, status, error_message, run_date
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
            SELECT id, status, description, period, evidence_path, evidence_type
            FROM manual_entries
            WHERE feature_name = ? AND period = ?
            ORDER BY id
        """, (module_name, month))
    else:
        cur.execute("""
            SELECT id, status, description, period, evidence_path, evidence_type
            FROM manual_entries
            WHERE feature_name = ?
            ORDER BY id
        """, (module_name,))

    for m in cur.fetchall():
        tests.append({
            "uuid": f"manual-{m['id']}",
            "name": m["description"] or "Manual entry",
            "status": m["status"],
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