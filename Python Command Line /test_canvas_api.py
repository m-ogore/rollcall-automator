#!/usr/bin/env python3

import sys
sys.path.insert(0, '/home/seer/Documents/attendance-app')

from rollcall_selenium import get_rollcall_url_from_course
import os
from dotenv import load_dotenv

load_dotenv('/home/seer/Documents/attendance-app/.env')

token = os.getenv("CANVAS_ACCESS_TOKEN")
course_url = "https://alueducation.instructure.com/courses/2571"

print("=" * 62)
print("Testing Canvas API Auto-Discovery")
print("=" * 62)
print(f"Token: {token[:20]}...")
print(f"Course URL: {course_url}")
print()

result = get_rollcall_url_from_course(course_url, token)
print(f"\nDiscovered Roll Call URL: {result}")
