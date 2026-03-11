# main.py
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .course_manager import CourseManager
from dotenv import load_dotenv
import csv
import io
import os
import re
import queue
import threading
import time as _time
import uuid
import requests as http_requests

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

course_manager = CourseManager()

# ── Extension agent state (in-memory; swap for Redis in multi-instance deploys) ──
_agent_heartbeats: dict = {}   # client_id → timestamp
_pending_jobs: dict     = {}   # client_id → job dict
_job_logs: dict         = {}   # client_id → list[str]

SESSION_DURATION      = 90
LATE_JOIN_THRESHOLD   = 15
MIN_DURATION_FRACTION = 0.75

CANVAS_BASE  = os.getenv("CANVAS_BASE_URL", "https://alueducation.instructure.com")
CANVAS_TOKEN = os.getenv("CANVAS_ACCESS_TOKEN", "")

# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_duration_minutes(duration_str: str) -> float:
    if not duration_str:
        return 0.0
    hours   = sum(int(x) for x in re.findall(r'(\d+)\s*h', duration_str))
    minutes = sum(int(x) for x in re.findall(r'(\d+)\s*m', duration_str))
    seconds = sum(int(x) for x in re.findall(r'(\d+)\s*s', duration_str))
    return hours * 60 + minutes + seconds / 60

def parse_join_minutes(time_joined: str, session_start: str) -> float:
    from datetime import datetime
    for fmt in ("%I:%M %p", "%H:%M", "%I:%M:%S %p", "%H:%M:%S"):
        try:
            diff = (datetime.strptime(time_joined.strip(), fmt) -
                    datetime.strptime(session_start.strip(), fmt)).total_seconds() / 60
            return max(diff, 0.0)
        except Exception:
            continue
    return 0.0

def calculate_status(duration_str: str, time_joined: str, session_start: str) -> str:
    if parse_duration_minutes(duration_str) < SESSION_DURATION * MIN_DURATION_FRACTION:
        return "absent"
    if session_start and parse_join_minutes(time_joined, session_start) > LATE_JOIN_THRESHOLD:
        return "late"
    return "present"

def canvas_headers():
    return {"Authorization": f"Bearer {CANVAS_TOKEN}"}

def canvas_paginated_get(path: str, params: dict = None):
    url, results = f"{CANVAS_BASE}/api/v1/{path}", []
    while url:
        r = http_requests.get(url, headers=canvas_headers(), params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        results.extend(data if isinstance(data, list) else [data])
        url = r.links.get("next", {}).get("url")
        params = None
    return results

def extract_course_id(course_url: str) -> str:
    m = re.search(r'/courses/(\d+)', course_url)
    if not m:
        raise ValueError(f"Cannot parse course ID from: {course_url}")
    return m.group(1)

# ── Extension agent endpoints ─────────────────────────────────────────────────

@app.post("/api/agent/heartbeat")
async def agent_heartbeat(request: Request):
    """Called by the browser extension every ~5 s to signal it is alive."""
    data = await request.json()
    cid  = data.get("client_id")
    if cid:
        _agent_heartbeats[cid] = _time.time()
    return JSONResponse({"ok": True})


@app.get("/api/agent/status")
def agent_status(client_id: str = ""):
    """Returns {connected: bool} — true if extension sent a heartbeat within 15 s."""
    last      = _agent_heartbeats.get(client_id, 0)
    connected = (_time.time() - last) < 15
    return JSONResponse({"connected": connected})


@app.get("/api/agent/job")
def get_agent_job(client_id: str = ""):
    """Extension polls this. Returns and removes the pending job if one exists."""
    job = _pending_jobs.pop(client_id, None)
    return JSONResponse({"job": job})


@app.post("/api/agent/log")
async def post_agent_log(request: Request):
    """Extension streams individual log lines here as it runs the automation."""
    data = await request.json()
    cid  = data.get("client_id", "")
    msg  = data.get("message", "")
    if cid and msg:
        _job_logs.setdefault(cid, []).append(msg)
    return JSONResponse({"ok": True})


@app.get("/api/agent/logs")
def get_agent_logs(client_id: str = "", after: int = 0):
    """Frontend polls this to display automation progress."""
    logs = _job_logs.get(client_id, [])
    return JSONResponse({"logs": logs[after:], "total": len(logs)})


# ── Course endpoints ───────────────────────────────────────────────────────────

@app.post("/api/set_course")
async def set_course(request: Request):
    data = await request.json()
    name, url = data.get("name"), data.get("url")
    if not name or not url:
        return JSONResponse({"message": "Name and URL required."}, status_code=400)
    course_manager.add_course(name, url)
    return JSONResponse({"message": f"Course '{name}' added."})

@app.post("/api/remove_course")
async def remove_course(request: Request):
    data = await request.json()
    course_manager.remove_course(data.get("name"))
    return JSONResponse({"message": "Removed."})

@app.get("/api/courses")
def get_courses():
    return JSONResponse(course_manager.get_courses())

# ── CSV upload ─────────────────────────────────────────────────────────────────

@app.post("/api/upload_csv")
async def upload_csv(request: Request, file: UploadFile = File(...)):
    session_start = request.query_params.get("session_start", "")
    content  = await file.read()
    csv_data = io.StringIO(content.decode("utf-8-sig"))
    reader   = csv.DictReader(csv_data)
    rows = []
    for row in reader:
        email = row.get("Email", "").strip().lower()
        if not email or "*" in email or "@" not in email:
            continue
        duration    = row.get("Duration", "").strip()
        time_joined = row.get("Time joined", "").strip()
        rows.append({
            "email":       email,
            "name":        f"{row.get('First name', '')} {row.get('Last name', '')}".strip(),
            "duration":    duration,
            "time_joined": time_joined,
            "status":      calculate_status(duration, time_joined, session_start),
        })
    present = sum(1 for r in rows if r["status"] == "present")
    late    = sum(1 for r in rows if r["status"] == "late")
    absent  = sum(1 for r in rows if r["status"] == "absent")
    return JSONResponse({
        "message": f"{len(rows)} students — {present} present, {late} late, {absent} absent.",
        "students": rows,
    })

# ── Canvas marking ─────────────────────────────────────────────────────────────

@app.post("/api/mark_canvas")
async def mark_canvas(request: Request):
    """
    Body: { "course_url": "...", "students": [{"email":"...", "status":"present|late|absent"}, ...] }
    Steps:
      1. Find Roll Call assignment in course
      2. Load enrolled students, build email→canvas_id map
      3. Batch-submit grades (present=100, late=50, absent=0)
    """
    if not CANVAS_TOKEN:
        return JSONResponse({"error": "CANVAS_ACCESS_TOKEN not set."}, status_code=500)

    data       = await request.json()
    course_url = data.get("course_url", "")
    students   = data.get("students", [])

    try:
        course_id = extract_course_id(course_url)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # 1. Find Roll Call assignment
    assignments = canvas_paginated_get(f"courses/{course_id}/assignments", {"per_page": 100})
    assignment = next(
        (a for a in assignments if "roll call" in a.get("name", "").lower()
         or "attendance" in a.get("name", "").lower()), None
    )
    if not assignment:
        return JSONResponse({"error": "No Roll Call / Attendance assignment found in this course."}, status_code=404)
    assignment_id   = assignment["id"]
    assignment_name = assignment["name"]

    # 2. Enrolled students  email → canvas user id
    enrollments = canvas_paginated_get(
        f"courses/{course_id}/enrollments",
        {"type[]": "StudentEnrollment", "per_page": 100}
    )
    email_to_id = {}
    for e in enrollments:
        user = e.get("user", {})
        login = (user.get("login_id") or "").strip().lower()
        email_to_id[login] = user["id"]

    # 3. Build grade_data and submit
    GRADE_MAP = {"present": 100, "late": 50, "absent": 0}
    grade_data = {}
    matched, skipped = 0, []
    for s in students:
        uid = email_to_id.get(s["email"].lower())
        if uid:
            grade_data[str(uid)] = {"posted_grade": GRADE_MAP.get(s["status"], 0)}
            matched += 1
        else:
            skipped.append(s["email"])

    if not grade_data:
        return JSONResponse({"error": "No CSV students matched Canvas enrollment."}, status_code=404)

    url = f"{CANVAS_BASE}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/update_grades"
    r = http_requests.post(url, headers=canvas_headers(), json={"grade_data": grade_data}, timeout=30)

    if r.status_code not in (200, 201):
        return JSONResponse({"error": f"Canvas API error {r.status_code}: {r.text}"}, status_code=500)

    return JSONResponse({
        "message": f"✅ Marked {matched} students in '{assignment_name}'.",
        "skipped": skipped,
        "assignment": assignment_name,
        "matched": matched,
    })

# ── Roll Call browser automation (SSE stream) ─────────────────────────────────

@app.post("/api/run_rollcall")
async def run_rollcall(request: Request):
    """
    Mark Roll Call attendance.

    If `client_id` is supplied (extension mode): stores the job for the browser
    extension to pick up via GET /api/agent/job, then returns immediately.
    The frontend polls GET /api/agent/logs for progress.

    If no `client_id` (legacy/local mode): runs Selenium in a background thread
    and streams progress as SSE (text/event-stream).

    Body: { "course_url": "...", "session_date": "YYYY-MM-DD",
            "students": [{"name":"...", "email":"...", "status":"present|late|absent"}],
            "client_id": "<optional: extension UUID>" }
    """
    data         = await request.json()
    course_url   = data.get("course_url", "")
    session_date = data.get("session_date", "")
    students     = data.get("students", [])
    client_id    = data.get("client_id", "").strip()

    if not course_url:
        return JSONResponse({"error": "course_url required"}, status_code=400)
    if not session_date:
        return JSONResponse({"error": "session_date required (YYYY-MM-DD)"}, status_code=400)

    # ── Extension mode ────────────────────────────────────────────────────────
    if client_id:
        job_id = str(uuid.uuid4())
        _job_logs[client_id] = []          # clear previous logs
        _pending_jobs[client_id] = {
            "job_id":       job_id,
            "course_url":   course_url,
            "session_date": session_date,
            "students":     students,
        }
        return JSONResponse({"mode": "extension", "job_id": job_id})

    # ── Legacy Selenium mode (local only) ─────────────────────────────────────
    log_queue: queue.Queue = queue.Queue()

    def selenium_thread():
        try:
            from .rollcall_browser import run_rollcall_automation
            run_rollcall_automation(
                course_url, session_date, students,
                log=lambda msg: log_queue.put(str(msg))
            )
        except ImportError as e:
            log_queue.put(f"❌ selenium not installed: {e}")
            log_queue.put("Install with: pip install selenium webdriver-manager")
        except Exception as e:
            import traceback
            log_queue.put(f"❌ {e}")
            log_queue.put(traceback.format_exc())
        finally:
            log_queue.put(None)  # sentinel

    threading.Thread(target=selenium_thread, daemon=True).start()

    def generate():
        while True:
            item = log_queue.get()
            if item is None:
                yield "data: __DONE__\n\n"
                break
            safe = item.replace("\n", " | ")
            yield f"data: {safe}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})

# ── Static frontend ────────────────────────────────────────────────────────────

_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "web-frontend")
app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")

