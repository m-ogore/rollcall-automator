# course_manager.py for FastAPI backend
import json
import os

COURSES_FILE = "courses.json"

class CourseManager:
    def __init__(self, storage_path=COURSES_FILE):
        self.storage_path = storage_path
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, 'w') as f:
                json.dump({}, f)

    def add_course(self, name, url):
        courses = self._load_courses()
        courses[name] = url
        self._save_courses(courses)

    def remove_course(self, name):
        courses = self._load_courses()
        if name in courses:
            del courses[name]
            self._save_courses(courses)

    def get_courses(self):
        return self._load_courses()

    def _load_courses(self):
        with open(self.storage_path, 'r') as f:
            return json.load(f)

    def _save_courses(self, courses):
        with open(self.storage_path, 'w') as f:
            json.dump(courses, f, indent=2)

# Example usage:
# manager = CourseManager()
# manager.add_course('Math', 'https://example.com/math')
# manager.remove_course('Math')
# print(manager.get_courses())
