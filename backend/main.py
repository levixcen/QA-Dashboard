from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import get_connection, init_db, seed_if_empty
from auth import verify_password, create_token, decode_token

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
app.mount("/evidence", StaticFiles(directory=EVIDENCE_DIR), name="evidence")


@app.on_event("startup")
def startup():
    init_db()
    seed_if_empty()


class LoginRequest(BaseModel):
    username: str
    password: str


def get_current_user(authorization: str = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    username = decode_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return username


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (payload.username,))
    user = cur.fetchone()
    conn.close()

    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    token = create_token(user["username"])
    return {"token": token, "username": user["username"]}


@app.get("/api/auth/me")
def me(username: str = Depends(get_current_user)):
    return {"username": username}


@app.get("/api/projects")
def list_projects(username: str = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM projects")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.get("/api/tasks")
def list_tasks(username: str = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.get("/api/modules/{module_name}/tests")
def list_module_tests(module_name: str, username: str = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
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
                "url": f"/evidence/{Path(a['file_path']).name}",
            }
            for a in cur.fetchall()
        ]

    conn.close()
    return tests