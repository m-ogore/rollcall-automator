# main.py
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .course_manager import CourseManager
import csv
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

course_manager = CourseManager()

SESSION_DURATION      = 90   # minutes
LATE_JOIN_THRESHOLD   = 15   # minutes
MIN_DURATION_FRACTION = 0.75

def parse_duration_minutes(duration_str: str) -> float:
    """Convert '1h 23m 45s' or '45m 12s' or '45m' to total minutes."""
    import re
    if not duration_str:
        return 0.0
    hours   = sum(int(x) for x in re.findall(r'(\d+)\s*h', duration_str))
    minutes = sum(int(x) for x in re.findall(r'(\d+)\s*m', duration_str))
    seconds = sum(int(x) for x in re.findall(r'(\d+)\s*s', duration_str))
    return hours * 60 + minutes + seconds / 60

def parse_join_minutes(time_joined: str, session_start: str) -> float:
    """Return how many minutes after session_start the student joined. 0 if unknown."""
    from datetime import datetime
    for fmt in ("%I:%M %p", "%H:%M", "%I:%M:%S %p", "%H:%M:%S"):
        try:
            t_join  = datetime.strptime(time_joined.strip(),  fmt)
            t_start = datetime.strptime(session_start.strip(), fmt)
            diff = (t_join - t_start).total_seconds() / 60
            return max(diff, 0.0)
        except Exception:
            continue
    return 0.0

def calculate_status(duration_str: str, time_joined: str, session_start: str) -> str:
    duration_mins = parse_duration_minutes(duration_str)
    threshold     = SESSION_DURATION * MIN_DURATION_FRACTION
    if duration_mins < threshold:
        return "absent"
    if session_start:
        join_offset = parse_join_minutes(time_joined, session_start)
        if join_offset > LATE_JOIN_THRESHOLD:
            return "late"
    return "present"

@app.post("/api/set_course")
async def set_course(request: Request):
    data = await request.json()
    name = data.get("name")
    url = data.get("url")
    if not name or not url:
        return JSONResponse({"message": "Name and URL required."}, status_code=400)
    course_manager.add_course(name, url)
    return JSONResponse({"message": f"Course '{name}' added."})

@app.post("/api/remove_course")
async def remove_course(request: Request):
    data = await request.json()
    name = data.get("name")
    course_manager.remove_course(name)
    return JSONResponse({"message": f"Course '{name}' removed."})

@app.get("/api/courses")
def get_courses():
    courses = course_manager.get_courses()
    return JSONResponse(courses)

@app.post("/api/upload_csv")
async def upload_csv(request: Request, file: UploadFile = File(...)):
    session_start = request.query_params.get("session_start", "")
    content = await file.read()
    csv_data = io.StringIO(content.decode("utf-8-sig"))
    reader = csv.DictReader(csv_data)
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
        "students": rows
    })

# Serve frontend static files (index.html, style.css, app.js)
import os
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "web-frontend")
app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")