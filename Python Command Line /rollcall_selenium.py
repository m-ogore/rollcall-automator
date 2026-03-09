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

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
SESSION_DURATION      = 90
LATE_JOIN_THRESHOLD   = 15
MIN_DURATION_FRACTION = 0.75
CLICKS_FOR = {"present": 1, "absent": 2, "late": 3}

CANVAS_BASE = os.getenv("CANVAS_BASE_URL", "https://alueducation.instructure.com")
TOKEN       = os.getenv("CANVAS_ACCESS_TOKEN", "")


# ──────────────────────────────────────────────
# CANVAS API  — auto-discover IDs
# ──────────────────────────────────────────────
def canvas_get(path, params=None):
    """Paginated Canvas API GET. Returns list of all results."""
    headers = {"Authorization": f"Bearer {TOKEN}"}
    url     = f"{CANVAS_BASE}/api/v1/{path}"
    results = []
    while url:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url    = r.links.get("next", {}).get("url")
        params = None
    return results


def discover_ids(course_id):
    """
    Use Canvas API to find:
      - assignment_id: the Roll Call Attendance assignment
      - section_id:    the first section of the course
    Returns (assignment_id, section_id) or raises on failure.
    """
    if not TOKEN:
        raise ValueError("CANVAS_ACCESS_TOKEN not set in .env")

    print(f"\n  🔍 Querying Canvas API for course {course_id}...")

    # ── Find Roll Call assignment ──
    assignments = canvas_get(f"courses/{course_id}/assignments", {"per_page": 100})
    assignment_id   = None
    assignment_name = None
    for a in assignments:
        name = a.get("name", "")
        if "roll call" in name.lower() or "attendance" in name.lower():
            assignment_id   = a["id"]
            assignment_name = name
            break

    if not assignment_id:
        names = [a.get("name") for a in assignments[:15]]
        raise ValueError(f"Could not find Roll Call assignment. Found: {names}")

    print(f"  ✅ Assignment : '{assignment_name}' (ID: {assignment_id})")

    # ── Find section ID ──
    sections   = canvas_get(f"courses/{course_id}/sections", {"per_page": 100})
    section_id = None
    for s in sections:
        section_id = s["id"]
        print(f"  ✅ Section    : '{s['name']}' (ID: {section_id})")
        break

    if not section_id:
        raise ValueError(f"No sections found for course {course_id}")

    return assignment_id, section_id


# ──────────────────────────────────────────────
# TIME / DATE HELPERS
# ──────────────────────────────────────────────
def normalize_time(t):
    t = t.strip()
    t = re.sub(r'(\d)(AM|PM|am|pm)', r'\1 \2', t)
    return t.upper()


def parse_filename_datetime(filepath):
    """Auto-detect session date + start time from the CSV filename."""
    filename = os.path.basename(filepath)
    print(f"  🔍 Reading date from: {filename}")

    # YYYY_MM_DD_HH_MM
    m = re.search(r'(20\d\d)_(\d{2})_(\d{2})_(\d{2})_(\d{2})', filename)
    if m:
        Y, Mo, D, h, mi = m.groups()
        dt = datetime(int(Y), int(Mo), int(D), int(h), int(mi))
        print(f"  ✅ Date + time detected: {dt.strftime('%Y-%m-%d')} {dt.strftime('%I:%M %p').lstrip('0')}")
        return dt.strftime("%Y-%m-%d"), dt.strftime("%I:%M %p").lstrip("0")

    # YYYY-MM-DD_HH-MM
    m = re.search(r'(20\d\d)-(\d{2})-(\d{2})_(\d{2})-(\d{2})', filename)
    if m:
        Y, Mo, D, h, mi = m.groups()
        dt = datetime(int(Y), int(Mo), int(D), int(h), int(mi))
        print(f"  ✅ Date + time detected: {dt.strftime('%Y-%m-%d')} {dt.strftime('%I:%M %p').lstrip('0')}")
        return dt.strftime("%Y-%m-%d"), dt.strftime("%I:%M %p").lstrip("0")

    # YYYY_MM_DD (date only)
    m = re.search(r'(20\d\d)_(\d{2})_(\d{2})', filename)
    if m:
        Y, Mo, D = m.groups()
        dt = datetime(int(Y), int(Mo), int(D))
        print(f"  ✅ Date detected: {dt.strftime('%Y-%m-%d')} (no time in filename)")
        return dt.strftime("%Y-%m-%d"), None

    print(f"  ⚠️  No date found in filename: {filename}")
    return None, None


def earliest_join_time(students):
    """Derive session start from the earliest join time across all students."""
    times = []
    for s in students:
        t = s.get("time_joined", "").strip()
        if t:
            try:
                times.append(datetime.strptime(normalize_time(t), "%I:%M %p"))
            except Exception:
                pass
    if not times:
        return None
    return min(times).strftime("%I:%M %p").lstrip("0")


def parse_duration_minutes(s):
    h = re.search(r'(\d+)\s*hr',  s or "")
    m = re.search(r'(\d+)\s*min', s or "")
    return (int(h.group(1)) if h else 0) * 60 + (int(m.group(1)) if m else 0)


# ──────────────────────────────────────────────
# ATTENDANCE LOGIC
# ──────────────────────────────────────────────
def determine_status(time_joined_str, duration_str, session_date, session_start):
    min_needed = SESSION_DURATION * MIN_DURATION_FRACTION
    try:
        fmt       = "%Y-%m-%d %I:%M %p"
        start_dt  = datetime.strptime(f"{session_date} {normalize_time(session_start)}", fmt)
        joined_dt = datetime.strptime(f"{session_date} {normalize_time(time_joined_str)}", fmt)
        mins_late = (joined_dt - start_dt).total_seconds() / 60
        duration  = parse_duration_minutes(duration_str)
        is_late   = False
        reasons   = []
        if mins_late > LATE_JOIN_THRESHOLD:
            is_late = True
            reasons.append(f"joined {mins_late:.0f} min late")
        if duration < min_needed:
            is_late = True
            reasons.append(f"stayed {duration} min (min: {min_needed:.0f})")
        if is_late:
            return "late", " | ".join(reasons)
        return "present", f"+{max(0, mins_late):.0f} min late, stayed {duration} min"
    except Exception as e:
        return "late", f"Parse error: {e}"


def read_csv(filepath):
    students = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = row.get("Email", "").strip().lower()
            if not email or "*" in email or "@" not in email:
                print(f"  ⚠️  Skipping masked email: {row.get('Email', '')}")
                continue
            students.append({
                "email":       email,
                "name":        f"{row.get('First name', '')} {row.get('Last name', '')}".strip(),
                "duration":    row.get("Duration", "").strip(),
                "time_joined": row.get("Time joined", "").strip(),
                "time_exited": row.get("Time exited", "").strip(),
            })
    return students


# ──────────────────────────────────────────────
# BROWSER HELPERS  (Brave preferred, Chrome fallback)
# ──────────────────────────────────────────────
BROWSER_CONFIG = {
    "brave": {
        "Linux":   {"bin": ["/usr/bin/brave-browser", "/usr/bin/brave",
                            "/opt/brave.com/brave/brave-browser"],
                   "profile": "~/.config/BraveSoftware/Brave-Browser"},
        "Darwin":  {"bin": ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"],
                   "profile": "~/Library/Application Support/BraveSoftware/Brave-Browser"},
        "Windows": {"bin": [r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe",
                            r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"],
                   "profile": r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"},
    },
    "chrome": {
        "Linux":   {"bin": ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"],
                   "profile": "~/.config/google-chrome"},
        "Darwin":  {"bin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
                   "profile": "~/Library/Application Support/Google/Chrome"},
        "Windows": {"bin": [r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
                            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"],
                   "profile": r"%LOCALAPPDATA%\Google\Chrome\User Data"},
    },
}


def _resolve(p):
    return os.path.expandvars(os.path.expanduser(p))


def detect_browser():
    system = platform.system()
    for name in ["brave", "chrome"]:
        cfg    = BROWSER_CONFIG[name][system]
        bins   = [_shutil.which(name), _shutil.which(f"{name}-browser")] + cfg["bin"]
        binary = next((b for b in bins if b and os.path.exists(_resolve(b))), None)
        if binary:
            return name, _resolve(binary), _resolve(cfg["profile"])
    return None, None, None


def is_debug_port_open(port=9222):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def ensure_browser_with_debugging(binary, profile_path, profile_name="Default"):
    """
    If browser already has debug port open → attach immediately, no login needed.
    Otherwise close it and relaunch with --remote-debugging-port=9222.
    After the first run the port stays open forever — zero logins on repeat runs.
    """
    if is_debug_port_open():
        print("  ✅ Browser debug port already open — no login needed")
        return True

    print("  🚀 Launching browser with remote debugging on port 9222...")
    print(f"  🍪 Profile: {profile_path}/{profile_name}")

    system = platform.system()
    try:
        if system == "Linux":
            subprocess.run(["pkill", "--signal", "SIGTERM", "-f", "brave-browser"], capture_output=True)
            subprocess.run(["pkill", "--signal", "SIGTERM", "-f", "brave"],         capture_output=True)
            subprocess.run(["pkill", "--signal", "SIGTERM", "-f", "google-chrome"], capture_output=True)
        elif system == "Darwin":
            subprocess.run(["pkill", "-TERM", "-f", "Brave Browser"],  capture_output=True)
            subprocess.run(["pkill", "-TERM", "-f", "Google Chrome"],  capture_output=True)
        elif system == "Windows":
            subprocess.run(["taskkill", "/IM", "brave.exe"],  capture_output=True)
            subprocess.run(["taskkill", "/IM", "chrome.exe"], capture_output=True)
        time.sleep(2)
    except Exception:
        pass

    subprocess.Popen([
        binary,
        "--remote-debugging-port=9222",
        f"--user-data-dir={profile_path}",
        f"--profile-directory={profile_name}",
        "--no-first-run",
        "--no-default-browser-check",
        "--restore-last-session",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("  ⏳ Waiting for browser...", end="", flush=True)
    for _ in range(15):
        time.sleep(1)
        print(".", end="", flush=True)
        if is_debug_port_open():
            print(" ready!")
            return True
    print(" timed out")
    return False


def _get_chromedriver_path(binary):
    """
    Find a valid chromedriver executable. Tries:
    1. System PATH (chromedriver)
    2. webdriver-manager — but verifies it's actually an executable, not a txt file
    3. Common system install locations
    """
    import stat

    def is_executable(path):
        try:
            st = os.stat(path)
            return bool(st.st_mode & stat.S_IXUSR) and os.path.isfile(path)
        except Exception:
            return False

    # 1. System PATH
    system_cd = _shutil.which("chromedriver")
    if system_cd and is_executable(system_cd):
        return system_cd

    # 2. webdriver-manager — verify the returned path is actually executable
    try:
        wdm_path = ChromeDriverManager().install()
        if is_executable(wdm_path):
            return wdm_path
        # wdm returned a txt file — find the actual binary next to it
        wdm_dir = os.path.dirname(wdm_path)
        for fname in os.listdir(wdm_dir):
            candidate = os.path.join(wdm_dir, fname)
            if "chromedriver" in fname.lower() and is_executable(candidate):
                return candidate
    except Exception:
        pass

    # 3. Common Linux locations
    for p in ["/usr/bin/chromedriver", "/usr/local/bin/chromedriver",
              "/snap/bin/chromedriver"]:
        if is_executable(p):
            return p

    raise FileNotFoundError(
        "Could not find a valid chromedriver executable.\n"
        "Install it with:  sudo apt install chromium-driver\n"
        "or:               pip install --upgrade webdriver-manager"
    )


def get_driver(binary):
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    options.binary_location = binary
    print("  🔌 Attaching Selenium to browser...")

    chromedriver = _get_chromedriver_path(binary)
    print(f"  🔧 chromedriver: {chromedriver}")

    for attempt in range(6):
        try:
            driver = webdriver.Chrome(
                service=Service(chromedriver),
                options=options
            )
            print(f"  ✅ Attached — {driver.current_url}")
            return driver
        except Exception as e:
            if attempt < 5:
                print(f"  ⏳ Not ready, retrying ({attempt + 1}/6)...")
                time.sleep(2)
            else:
                raise e


# ──────────────────────────────────────────────
# ROLL CALL NAVIGATION
# ──────────────────────────────────────────────
def open_rollcall(driver, course_id, assignment_id, section_id):
    """
    Two-step authenticated open:
      Step 1 — Canvas assignment page  (creates the LTI session cookie)
      Step 2 — rollcall-eu.instructure.com/sections/{id}  (uses that cookie)
    """
    assignment_url = f"{CANVAS_BASE}/courses/{course_id}/assignments/{assignment_id}"
    rollcall_url   = f"https://rollcall-eu.instructure.com/sections/{section_id}"

    # ── Step 1: Canvas assignment page ──
    print(f"\n  📋 Step 1 — Canvas assignment page (LTI auth):")
    print(f"     {assignment_url}")
    driver.get(assignment_url)
    time.sleep(3)

    if "login" in driver.current_url.lower():
        print("  ⚠️  Login required — please log in then press Enter")
        input("  Press Enter once logged in... ")

    print(f"  ✅ Canvas page loaded")

    # ── Step 2: Roll Call direct URL ──
    print(f"\n  🎯 Step 2 — Roll Call direct URL:")
    print(f"     {rollcall_url}")
    driver.get(rollcall_url)
    time.sleep(3)

    body = driver.find_element(By.TAG_NAME, "body").text.strip().lower()

    if "please launch this tool from canvas" in body:
        print("  ⚠️  LTI error — trying iframe fallback on assignment page...")
        driver.get(assignment_url)
        time.sleep(3)
        try:
            iframe = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "iframe[src*='rollcall'], iframe[title*='Roll'], iframe[title*='Attendance']"
                ))
            )
            driver.switch_to.frame(iframe)
            print("  ✅ Switched into Roll Call iframe")
            time.sleep(2)
        except TimeoutException:
            print("  ❌ iframe not found — please navigate to Roll Call manually")
            input("  Press Enter once Roll Call student list is visible... ")
        return True

    print(f"  ✅ Roll Call opened: {driver.current_url}")
    return True


def wait_for_rollcall_load(driver, timeout=60):
    print("  ⏳ Waiting for student list...")
    try:
        WebDriverWait(driver, timeout).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.student-toggle")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "ol.student-list-display")),
                EC.presence_of_element_located((By.CSS_SELECTOR, ".student-name")),
            )
        )
        time.sleep(1)
        print("  ✅ Student list loaded")
        return True
    except TimeoutException:
        print(f"  ❌ Student list not found (URL: {driver.current_url})")
        return False


def navigate_to_date(driver, session_date):
    """Navigate to date using the Roll Call calendar date picker (ui-datepicker)."""
    target = datetime.strptime(session_date, "%Y-%m-%d")
    print(f"  📅 Navigating to date: {target.strftime('%a %b %d %Y')}")

    try:
        # Wait for calendar icon to be present
        print("  ⏳ Waiting for date picker...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img.ui-datepicker-trigger"))
        )
        time.sleep(0.5)

        # Click calendar icon to open date picker
        calendar_icon = driver.find_element(By.CSS_SELECTOR, "img.ui-datepicker-trigger")
        driver.execute_script("arguments[0].click();", calendar_icon)
        time.sleep(1)
        print("  📆 Calendar opened")

        # Wait for datepicker widget to appear
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ui-datepicker"))
        )

        # Navigate to the correct month/year
        for _ in range(24):  # max 24 months navigation
            try:
                header = driver.find_element(By.CSS_SELECTOR, ".ui-datepicker-title")
                header_text = header.text.strip()  # e.g. "March 2026"
                month_str = target.strftime("%B %Y")  # e.g. "March 2026"

                if month_str.lower() in header_text.lower():
                    # On correct month — click the day
                    day_cells = driver.find_elements(By.CSS_SELECTOR,
                        ".ui-datepicker-calendar td a.ui-state-default, "
                        ".ui-datepicker-calendar td a"
                    )
                    for cell in day_cells:
                        if cell.text.strip() == str(target.day):
                            driver.execute_script("arguments[0].click();", cell)
                            time.sleep(0.5)
                            print(f"  ✅ Date selected: {target.strftime('%a %b %d %Y')}")
                            return True
                    print(f"  ⚠️  Day {target.day} not found in calendar")
                    break

                # Navigate forward or backward
                try:
                    # Parse current month to determine direction
                    from datetime import datetime as dt2
                    current_month = dt2.strptime(header_text, "%B %Y")
                    if current_month < target.replace(day=1):
                        driver.find_element(By.CSS_SELECTOR,
                            ".ui-datepicker-next, [title='Next']"
                        ).click()
                    else:
                        driver.find_element(By.CSS_SELECTOR,
                            ".ui-datepicker-prev, [title='Prev']"
                        ).click()
                    time.sleep(0.3)
                except Exception:
                    break

            except Exception as e:
                print(f"  ⚠️  Calendar nav error: {str(e)[:50]}")
                break

    except TimeoutException:
        print("  ⚠️  ui-datepicker not found — trying arrow navigation fallback")
        _navigate_by_arrows(driver, session_date)
        return False

    return False


def _navigate_by_arrows(driver, session_date):
    """Fallback: navigate using prev/next arrow buttons."""
    target = datetime.strptime(session_date, "%Y-%m-%d")
    DATE_FORMATS = [
        "%a %b %d %Y", "%A, %B %d %Y", "%b %d, %Y",
        "%a %b %d",    "%A, %B %d",    "%b %d",
    ]
    for _ in range(60):
        try:
            date_el = driver.find_element(By.CSS_SELECTOR,
                "[class*='date'], .date-display, #date-label"
            )
            current_text = date_el.text.strip()
        except NoSuchElementException:
            print("  ⚠️  No date element found")
            break

        current = None
        for fmt in DATE_FORMATS:
            try:
                parse_str = current_text if str(target.year) in current_text \
                            else f"{current_text} {target.year}"
                current = datetime.strptime(parse_str,
                    fmt + (" %Y" if parse_str != current_text else "")
                ).replace(year=target.year)
                break
            except ValueError:
                continue

        if current is None:
            print(f"  ⚠️  Could not parse '{current_text}'")
            break

        diff = (target - current).days
        if diff == 0:
            print(f"  ✅ On correct date: {current_text}")
            break

        arrow = "[class*='prev'], button[aria-label*='prev']" if diff < 0 \
                else "[class*='next'], button[aria-label*='next']"
        try:
            driver.find_element(By.CSS_SELECTOR, arrow).click()
            time.sleep(0.4)
        except NoSuchElementException:
            print("  ⚠️  Arrow not found")
            break


def find_student_button(driver, name):
    """Find the a.student-toggle element for a student by name."""
    name_parts = name.lower().split()
    for link in driver.find_elements(By.CSS_SELECTOR, "a.student-toggle"):
        if all(p in link.text.lower() for p in name_parts):
            return link
    # fallback: search inside list items
    for li in driver.find_elements(By.CSS_SELECTOR, "ol.student-list-display li"):
        if all(p in li.text.lower() for p in name_parts):
            try:
                return li.find_element(By.CSS_SELECTOR, "a.student-toggle")
            except NoSuchElementException:
                pass
    return None


def click_to_status(driver, element, target_status):
    for _ in range(CLICKS_FOR[target_status]):
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        driver.execute_script("arguments[0].click();", element)
        time.sleep(0.25)
    time.sleep(0.2)


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def run(csv_path, course_url, section_id_override=None, start_time_override=None, dry_run=False):
    print("\n" + "═" * 62)
    print("  ROLL CALL ATTENDANCE AUTOMATION")
    print("═" * 62)

    # ── Extract course ID ──
    m = re.search(r'/courses/(\d+)', course_url)
    if not m:
        print(f"  ❌ Cannot extract course ID from: {course_url}")
        return
    course_id = m.group(1)
    print(f"\n  🎓 Course ID : {course_id}")

    # ── Auto-discover assignment + section IDs via API ──
    try:
        assignment_id, section_id = discover_ids(course_id)
    except Exception as e:
        print(f"  ❌ API error: {e}")
        return

    if section_id_override:
        section_id = section_id_override
        print(f"  ℹ️  Section ID overridden: {section_id}")

    print(f"\n  🔗 Canvas assignment : {CANVAS_BASE}/courses/{course_id}/assignments/{assignment_id}")
    print(f"  🔗 Roll Call URL     : https://rollcall-eu.instructure.com/sections/{section_id}")

    # ── Read CSV ──
    csv_students = read_csv(csv_path)
    print(f"\n  📄 File      : {os.path.basename(csv_path)}")
    print(f"  👥 Students  : {len(csv_students)}")

    # ── Auto-detect date + time from filename (never prompts) ──
    session_date, session_start = parse_filename_datetime(csv_path)

    if not session_date:
        print("  ❌ No date in filename. Rename CSV to include YYYY_MM_DD_HH_MM")
        session_date = input("  Enter date (YYYY-MM-DD): ").strip()

    if not session_start:
        if start_time_override:
            session_start = start_time_override
        else:
            raw = input("  🕐 Enter session start time [default: 11:30 AM]: ").strip()
            session_start = raw if raw else "11:30 AM"

    session_start = normalize_time(session_start)
    print(f"  📅 Date      : {session_date}")
    print(f"  🕐 Start     : {session_start}")

    # ── Calculate attendance status ──
    print(f"\n{'─' * 62}")
    print(f"  {'Name':<30} {'Status':<10} Reason")
    print(f"{'─' * 62}")

    status_map = {}
    for s in csv_students:
        status, reason = determine_status(
            s["time_joined"], s["duration"], session_date, session_start
        )
        status_map[s["email"]] = (status, reason)
        icons = {"present": "✅", "late": "⚠️ ", "absent": "❌"}
        print(f"  {s['name']:<30} {icons[status]} {status:<8} {reason}")

    counts = {k: sum(1 for st, _ in status_map.values() if st == k)
              for k in ["present", "late", "absent"]}
    print(f"\n  ✅ Present: {counts['present']}  ⚠️  Late: {counts['late']}  ❌ Absent: {counts['absent']}")

    if dry_run:
        print("\n  🔍 DRY RUN — browser not opened.\n")
        return

    # ── Launch browser ──
    print(f"\n{'─' * 62}")
    browser_name, binary, profile_path = detect_browser()
    if not binary:
        print("  ❌ Could not find Brave or Chrome")
        return

    profile_name = os.getenv("BROWSER_PROFILE_NAME", "Default")
    print(f"  🌐 Browser : {browser_name.title()} → {binary}")

    if not ensure_browser_with_debugging(binary, profile_path, profile_name):
        print("  ❌ Could not connect to browser debug port")
        return

    driver = get_driver(binary)

    try:
        # ── Open Roll Call (2-step: Canvas assignment → Roll Call URL) ──
        if not open_rollcall(driver, course_id, assignment_id, section_id):
            return

        if not wait_for_rollcall_load(driver, timeout=60):
            print("  ❌ Student list did not appear")
            return

        # ── Navigate to correct date ──
        navigate_to_date(driver, session_date)
        time.sleep(1)

        # ── Mark attendance ──
        print(f"\n  🔧 Marking attendance...")
        results = {"present": 0, "late": 0, "absent": 0, "not_found": 0}

        for idx, s in enumerate(csv_students):
            status, _ = status_map.get(s["email"], ("present", ""))
            print(f"  [{idx+1:>2}/{len(csv_students)}] {s['name']:<30} → {status}...", end=" ", flush=True)

            btn = find_student_button(driver, s["name"])
            if btn is None:
                print("❌ not found")
                results["not_found"] += 1
                continue

            # Reset to unmarked (4 clicks = full cycle back to start)
            for _ in range(4):
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.15)

            click_to_status(driver, btn, status)
            results[status] += 1
            print("✅")
            time.sleep(0.2)

        # ── Summary ──
        print(f"\n{'═' * 62}")
        print(f"  📊 DONE — {session_date}")
        print(f"{'═' * 62}")
        print(f"  ✅ Present   : {results['present']}")
        print(f"  ⚠️  Late      : {results['late']}")
        print(f"  ❌ Absent    : {results['absent']}")
        if results["not_found"]:
            print(f"  ❓ Not found : {results['not_found']} — mark manually")
        print(f"{'═' * 62}")
        print("\n  Browser left open — verify then close manually.\n")

    except Exception as e:
        print(f"\n  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        print("  Browser left open for debugging.")


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Roll Call Attendance Automation")
    parser.add_argument("--csv",        required=True,       help="Zoom/Teams attendance CSV")
    parser.add_argument("--course-url", required=True,       help="Canvas course URL e.g. https://alueducation.instructure.com/courses/2571")
    parser.add_argument("--start-time",  default=None,        help="Session start time e.g. '11:14 AM' (prompted if not set, defaults to 11:30 AM)")
    parser.add_argument("--section-id",  default=None,        help="Override section ID (auto-detected by default)")
    parser.add_argument("--dry-run",    action="store_true", help="Preview without opening browser")
    args = parser.parse_args()

    run(args.csv, args.course_url,
        section_id_override=args.section_id,
        start_time_override=args.start_time,
        dry_run=args.dry_run)