"""
Roll Call Attendance Automation
================================
Just provide a course URL — everything else is auto-discovered:
  1. Canvas API finds the Roll Call Attendance assignment ID
  2. Canvas API finds the section ID
  3. Browser opens the Canvas assignment page (establishes LTI session)
  4. Browser opens rollcall-eu.instructure.com/sections/{section_id}
  5. Attendance is marked from your CSV

Install:
    pip install selenium webdriver-manager python-dotenv requests

Usage:
    python rollcall_selenium.py --csv "attendance.csv" --course-url "https://alueducation.instructure.com/courses/2571"
    python rollcall_selenium.py --csv "attendance.csv" --course-url "https://alueducation.instructure.com/courses/2571" --dry-run
"""

import csv
import re
import os
import time
import socket
import platform
import argparse
import subprocess
import requests
import shutil as _shutil
from datetime import datetime
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

SESSION_DURATION      = 90
LATE_JOIN_THRESHOLD   = 15
MIN_DURATION_FRACTION = 0.75
CLICKS_FOR = {"present": 1, "absent": 2, "late": 3}

CANVAS_BASE = os.getenv("CANVAS_BASE_URL", "https://alueducation.instructure.com")
TOKEN       = os.getenv("CANVAS_ACCESS_TOKEN", "")

# ...existing code...
