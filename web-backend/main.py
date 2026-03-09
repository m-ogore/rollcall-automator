# main.py for FastAPI backend




from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from course_manager import CourseManager
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
async def set_course(request: Request):
    data = await request.json()
    name = data.get("name")
    url = data.get("url")
    course_manager.add_course(name, url)
    return JSONResponse({"message": f"Course '{name}' added."})

@app.post("/api/remove_course")
async def remove_course(request: Request):
    data = await request.json()
    name = data.get("name")
    course_manager.remove_course(name)
    return JSONResponse({"message": f"Course '{name}' removed."})

@app.get("/api/courses")
async def get_courses():
    return JSONResponse(course_manager.get_courses())

@app.post("/api/upload_csv")
async def upload_csv(file: UploadFile = File(...)):
    content = await file.read()
    csv_data = io.StringIO(content.decode('utf-8'))
    reader = csv.reader(csv_data)
    # Process CSV here (not stored persistently)
    # ...existing rollcall logic...
    return JSONResponse({"message": "CSV processed successfully."})
