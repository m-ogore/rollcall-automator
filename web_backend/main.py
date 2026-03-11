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

@app.post("/api/set_course")
def set_course(request: Request):
    data = request.json()
    name = data.get("name")
    url = data.get("url")
    if not name or not url:
        return JSONResponse({"message": "Name and URL required."}, status_code=400)
    course_manager.add_course(name, url)
    return JSONResponse({"message": f"Course '{name}' added."})

@app.post("/api/remove_course")
def remove_course(request: Request):
    data = request.json()
    name = data.get("name")
    course_manager.remove_course(name)
    return JSONResponse({"message": f"Course '{name}' removed."})

@app.get("/api/courses")
def get_courses():
    courses = course_manager.get_courses()
    return JSONResponse(courses)

@app.post("/api/upload_csv")
async def upload_csv(file: UploadFile = File(...)):
    content = await file.read()
    csv_data = io.StringIO(content.decode("utf-8-sig"))
    reader = csv.DictReader(csv_data)
    rows = []
    for row in reader:
        email = row.get("Email", "").strip().lower()
        if not email or "*" in email or "@" not in email:
            continue
        rows.append({
            "email":       email,
            "name":        f"{row.get('First name', '')} {row.get('Last name', '')}".strip(),
            "duration":    row.get("Duration", "").strip(),
            "time_joined": row.get("Time joined", "").strip(),
        })
    return JSONResponse({"message": f"CSV parsed. {len(rows)} students found.", "students": rows})

# Serve frontend static files (index.html, style.css, app.js)
app.mount("/", StaticFiles(directory="web-frontend", html=True), name="frontend")