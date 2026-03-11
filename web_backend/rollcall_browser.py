"""
rollcall_browser.py
====================
Browser automation for Roll Call LTI attendance marking.
Called from the web backend to drive the real Roll Call tool
at rollcall-eu.instructure.com, identical to the CLI approach.
"""

import os
import re
import time
import socket
import platform
import subprocess
import shutil as _shutil

import requests as http_requests
from dotenv import load_dotenv

load_dotenv()

CANVAS_BASE  = os.getenv("CANVAS_BASE_URL", "https://alueducation.instructure.com")
CANVAS_TOKEN = os.getenv("CANVAS_ACCESS_TOKEN", "")

CLICKS_FOR = {"present": 1, "absent": 2, "late": 3}


# ── Canvas API helpers ─────────────────────────────────────────────────────────

def _canvas_headers():
    return {"Authorization": f"Bearer {CANVAS_TOKEN}"}

def _canvas_get(path, params=None):
    url, results = f"{CANVAS_BASE}/api/v1/{path}", []
    while url:
        r = http_requests.get(url, headers=_canvas_headers(), params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        url    = r.links.get("next", {}).get("url")
        params = None
    return results

def discover_ids(course_id, log=print):
    if not CANVAS_TOKEN:
        raise ValueError("CANVAS_ACCESS_TOKEN not set in .env")
    log(f"Querying Canvas API for course {course_id}...")

    assignments = _canvas_get(f"courses/{course_id}/assignments", {"per_page": 100})
    assignment_id = assignment_name = None
    for a in assignments:
        name = a.get("name", "")
        if "roll call" in name.lower() or "attendance" in name.lower():
            assignment_id   = a["id"]
            assignment_name = name
            break
    if not assignment_id:
        names = [a.get("name") for a in assignments[:15]]
        raise ValueError(f"No Roll Call / Attendance assignment found. Assignments: {names}")
    log(f"✅ Assignment: '{assignment_name}' (ID: {assignment_id})")

    sections   = _canvas_get(f"courses/{course_id}/sections", {"per_page": 100})
    section_id = None
    for s in sections:
        section_id = s["id"]
        log(f"✅ Section: '{s['name']}' (ID: {section_id})")
        break
    if not section_id:
        raise ValueError(f"No sections found for course {course_id}")

    return assignment_id, section_id


# ── Browser helpers ────────────────────────────────────────────────────────────

BROWSER_CONFIG = {
    "brave": {
        "Linux":   {"bin": ["/usr/bin/brave-browser", "/usr/bin/brave",
                            "/opt/brave.com/brave/brave-browser"],
                   "profile": "~/.config/BraveSoftware/Brave-Browser"},
        "Darwin":  {"bin": ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"],
                   "profile": "~/Library/Application Support/BraveSoftware/Brave-Browser"},
        "Windows": {"bin": [r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"],
                   "profile": r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"},
    },
    "chrome": {
        "Linux":   {"bin": ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"],
                   "profile": "~/.config/google-chrome"},
        "Darwin":  {"bin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
                   "profile": "~/Library/Application Support/Google/Chrome"},
        "Windows": {"bin": [r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"],
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

def ensure_browser_with_debugging(binary, profile_path, profile_name="Default", log=print):
    if is_debug_port_open():
        log("✅ Browser debug port already open")
        return True
    log("🚀 Launching browser with remote debugging on port 9222...")
    system = platform.system()
    try:
        if system == "Linux":
            subprocess.run(["pkill", "--signal", "SIGTERM", "-f", "brave-browser"], capture_output=True)
            subprocess.run(["pkill", "--signal", "SIGTERM", "-f", "google-chrome"], capture_output=True)
        elif system == "Darwin":
            subprocess.run(["pkill", "-TERM", "-f", "Brave Browser"], capture_output=True)
            subprocess.run(["pkill", "-TERM", "-f", "Google Chrome"], capture_output=True)
        elif system == "Windows":
            subprocess.run(["taskkill", "/IM", "brave.exe"], capture_output=True)
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
    log("⏳ Waiting for browser to start...")
    for _ in range(15):
        time.sleep(1)
        if is_debug_port_open():
            log("✅ Browser ready")
            return True
    log("❌ Browser did not start in time")
    return False

def get_driver(binary, log=print):
    import stat
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    def is_executable(path):
        try:
            st = os.stat(path)
            return bool(st.st_mode & stat.S_IXUSR) and os.path.isfile(path)
        except Exception:
            return False

    chromedriver = _shutil.which("chromedriver")
    if not (chromedriver and is_executable(chromedriver)):
        try:
            wdm_path = ChromeDriverManager().install()
            if is_executable(wdm_path):
                chromedriver = wdm_path
            else:
                wdm_dir = os.path.dirname(wdm_path)
                for fname in os.listdir(wdm_dir):
                    candidate = os.path.join(wdm_dir, fname)
                    if "chromedriver" in fname.lower() and is_executable(candidate):
                        chromedriver = candidate
                        break
        except Exception:
            pass
    if not chromedriver:
        for p in ["/usr/bin/chromedriver", "/usr/local/bin/chromedriver", "/snap/bin/chromedriver"]:
            if is_executable(p):
                chromedriver = p
                break
    if not chromedriver:
        raise FileNotFoundError("chromedriver not found. Install with: sudo apt install chromium-driver")

    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    options.binary_location = binary
    log(f"🔌 Attaching Selenium to browser (chromedriver: {chromedriver})")
    for attempt in range(6):
        try:
            driver = webdriver.Chrome(service=Service(chromedriver), options=options)
            log(f"✅ Attached — {driver.current_url}")
            return driver
        except Exception as e:
            if attempt < 5:
                log(f"⏳ Retrying ({attempt+1}/6)...")
                time.sleep(2)
            else:
                raise e


# ── Roll Call navigation ───────────────────────────────────────────────────────

def open_rollcall(driver, course_id, assignment_id, section_id, log=print):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    assignment_url = f"{CANVAS_BASE}/courses/{course_id}/assignments/{assignment_id}"
    rollcall_url   = f"https://rollcall-eu.instructure.com/sections/{section_id}"

    log(f"📋 Step 1 — Canvas assignment page (LTI auth):")
    log(f"   {assignment_url}")
    driver.get(assignment_url)
    time.sleep(3)
    if "login" in driver.current_url.lower():
        log("⚠️  Login detected — please log in to Canvas in the browser")
        # Wait for user to log in (poll for up to 2 minutes)
        for _ in range(24):
            time.sleep(5)
            if "login" not in driver.current_url.lower():
                break
    log("✅ Canvas page loaded")

    log(f"🎯 Step 2 — Roll Call direct URL:")
    log(f"   {rollcall_url}")
    driver.get(rollcall_url)
    time.sleep(3)

    body = driver.find_element(By.TAG_NAME, "body").text.strip().lower()
    if "please launch this tool from canvas" in body:
        log("⚠️  LTI error — trying iframe on assignment page...")
        driver.get(assignment_url)
        time.sleep(3)
        try:
            iframe = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "iframe[src*='rollcall'], iframe[title*='Roll'], iframe[title*='Attendance']"))
            )
            driver.switch_to.frame(iframe)
            log("✅ Switched into Roll Call iframe")
            time.sleep(2)
        except TimeoutException:
            log("❌ Could not find Roll Call iframe")
            return False
    else:
        log(f"✅ Roll Call opened: {driver.current_url}")
    return True

def wait_for_rollcall_load(driver, log=print, timeout=60):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    log("⏳ Waiting for student list...")
    try:
        WebDriverWait(driver, timeout).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.student-toggle")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "ol.student-list-display")),
                EC.presence_of_element_located((By.CSS_SELECTOR, ".student-name")),
            )
        )
        time.sleep(1)
        log("✅ Student list loaded")
        return True
    except TimeoutException:
        log(f"❌ Student list not found (URL: {driver.current_url})")
        return False

def navigate_to_date(driver, session_date, log=print):
    from datetime import datetime
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    target = datetime.strptime(session_date, "%Y-%m-%d")
    log(f"📅 Navigating to date: {target.strftime('%a %b %d %Y')}")
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img.ui-datepicker-trigger"))
        )
        driver.execute_script(
            "arguments[0].click();",
            driver.find_element(By.CSS_SELECTOR, "img.ui-datepicker-trigger")
        )
        time.sleep(1)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".ui-datepicker"))
        )
        for _ in range(24):
            header_text = driver.find_element(By.CSS_SELECTOR, ".ui-datepicker-title").text.strip()
            if target.strftime("%B %Y").lower() in header_text.lower():
                for cell in driver.find_elements(By.CSS_SELECTOR,
                        ".ui-datepicker-calendar td a.ui-state-default, .ui-datepicker-calendar td a"):
                    if cell.text.strip() == str(target.day):
                        driver.execute_script("arguments[0].click();", cell)
                        time.sleep(0.5)
                        log(f"✅ Date selected: {target.strftime('%a %b %d %Y')}")
                        return True
                log(f"⚠️  Day {target.day} not found in calendar")
                break
            # Navigate in the right direction
            try:
                current_month = datetime.strptime(header_text, "%B %Y")
                btn_sel = ".ui-datepicker-next" if current_month < target.replace(day=1) else ".ui-datepicker-prev"
                driver.find_element(By.CSS_SELECTOR, btn_sel).click()
                time.sleep(0.3)
            except Exception:
                break
    except TimeoutException:
        log("⚠️  Date picker not found — please navigate to the correct date manually")
    return False

def find_student_button(driver, name):
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import NoSuchElementException
    name_parts = name.lower().split()
    for link in driver.find_elements(By.CSS_SELECTOR, "a.student-toggle"):
        if all(p in link.text.lower() for p in name_parts):
            return link
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


# ── Main entry point ───────────────────────────────────────────────────────────

def run_rollcall_automation(course_url, session_date, students, log=print):
    """
    Mark Roll Call attendance using pre-computed statuses.

    Arguments:
        course_url   — Canvas course URL (e.g. https://alueducation.instructure.com/courses/2571)
        session_date — "YYYY-MM-DD"
        students     — list of {name, email, status}  (status: present|late|absent)
        log          — callable for progress messages (default: print)
    """
    log("=" * 56)
    log("  ROLL CALL BROWSER AUTOMATION")
    log("=" * 56)

    m = re.search(r'/courses/(\d+)', course_url)
    if not m:
        log(f"❌ Cannot extract course ID from: {course_url}")
        return {"error": "Invalid course URL"}
    course_id = m.group(1)
    log(f"🎓 Course ID: {course_id}")
    log(f"📅 Date: {session_date}")
    log(f"👥 Students: {len(students)}")

    try:
        assignment_id, section_id = discover_ids(course_id, log=log)
    except Exception as e:
        log(f"❌ API error: {e}")
        return {"error": str(e)}

    browser_name, binary, profile_path = detect_browser()
    if not binary:
        log("❌ Brave or Chrome not found on this machine")
        return {"error": "Browser not found"}
    profile_name = os.getenv("BROWSER_PROFILE_NAME", os.getenv("CHROME_PROFILE_NAME", "Default"))
    log(f"🌐 Browser: {browser_name.title()} — {binary}")

    if not ensure_browser_with_debugging(binary, profile_path, profile_name, log=log):
        log("❌ Could not open browser with debug port")
        return {"error": "Browser debug port failed"}

    driver = get_driver(binary, log=log)

    results = {"present": 0, "late": 0, "absent": 0, "not_found": 0}
    try:
        if not open_rollcall(driver, course_id, assignment_id, section_id, log=log):
            return {"error": "Could not open Roll Call"}

        if not wait_for_rollcall_load(driver, log=log):
            return {"error": "Student list did not load"}

        navigate_to_date(driver, session_date, log=log)
        time.sleep(1)

        log(f"\n{'─' * 56}")
        log("  Marking attendance...")
        log(f"{'─' * 56}")

        for idx, s in enumerate(students):
            status = s.get("status", "present")
            name   = s.get("name", s.get("email", "?"))
            log(f"[{idx+1:>2}/{len(students)}] {name:<30} → {status}...")

            btn = find_student_button(driver, name)
            if btn is None:
                log(f"  ⚠️  Not found in Roll Call list")
                results["not_found"] += 1
                continue

            # Reset to unmarked (4 clicks = full cycle)
            for _ in range(4):
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.15)

            click_to_status(driver, btn, status)
            results[status] += 1
            log(f"  ✅ {status}")
            time.sleep(0.2)

        log(f"\n{'=' * 56}")
        log(f"  ✅ Present : {results['present']}")
        log(f"  ⏰ Late    : {results['late']}")
        log(f"  ❌ Absent  : {results['absent']}")
        if results["not_found"]:
            log(f"  ❓ Not found in Roll Call: {results['not_found']}")
        log(f"{'=' * 56}")
        log("  Browser left open — verify then close manually.")
        return results

    except Exception as e:
        import traceback
        log(f"❌ Error: {e}")
        log(traceback.format_exc())
        return {"error": str(e)}
