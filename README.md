# Roll Call Automator

Automates marking attendance in the **Canvas Roll Call LTI tool** from Zoom / Microsoft Teams CSV exports.

Upload a meeting attendance CSV, review each student's calculated status (Present / Late / Absent), adjust if needed, then click one button — the app opens the real Roll Call tool in your browser and clicks every student for you.

---

## How It Works

```
Zoom / Teams CSV
      │
      ▼
┌─────────────────────┐
│  FastAPI backend    │  Parses CSV, calculates attendance status
│  /api/upload_csv    │  based on join time + duration
└────────┬────────────┘
         │  students + statuses
         ▼
┌─────────────────────┐
│  Web UI (Step 3)    │  Roll Call grid — review & adjust statuses
│  Review screen      │
└────────┬────────────┘
         │  POST /api/run_rollcall
         ▼
┌─────────────────────────────────────────────────────────┐
│  rollcall_browser.py  (Selenium)                        │
│                                                         │
│  1. Canvas API  →  find Roll Call assignment + section  │
│  2. Open Canvas assignment page  (LTI session cookie)   │
│  3. Navigate to rollcall-eu.instructure.com/sections/…  │
│  4. Navigate calendar to session date                    │
│  5. Click each student toggle to Present / Late / Absent│
└─────────────────────────────────────────────────────────┘
         │
         ▼
  Canvas gradebook updates automatically via Roll Call
```

---

## Project Structure

```
attendance-app/
├── web_backend/              # FastAPI application
│   ├── main.py               # All API routes + attendance logic
│   ├── course_manager.py     # Course storage (Redis or in-memory)
│   ├── rollcall_browser.py   # Selenium browser automation
│   ├── api.py                # Mangum wrapper for Vercel deployment
│   └── requirements.txt
│
├── web-frontend/             # Static single-page app
│   ├── index.html            # 3-panel sidebar layout
│   ├── style.css             # Dark theme
│   └── app.js                # All frontend logic
│
├── python-cli/               # Original command-line version
│   ├── rollcall_selenium.py  # Standalone CLI script
│   └── README.md
│
├── .env                      # API credentials (never committed)
├── vercel.json               # Vercel deployment config
└── requirements.txt
```

---

## Attendance Logic

Defined in `web_backend/main.py`:

| Constant | Value | Meaning |
|---|---|---|
| `SESSION_DURATION` | 90 min | Expected total session length |
| `MIN_DURATION_FRACTION` | 0.75 | Must attend ≥ 67.5 min to not be absent |
| `LATE_JOIN_THRESHOLD` | 15 min | Joined > 15 min after start → late |

**Status rules (applied in order):**
1. If `duration < 90 × 0.75` (i.e. < 67.5 min) → **Absent**
2. If `time_joined − session_start > 15 min` → **Late**
3. Otherwise → **Present**

The CSV columns used are: `Email`, `First name`, `Last name`, `Time joined`, `Duration`.

---

## Running Locally

### Prerequisites
- Python 3.8+
- Chrome or Brave browser **already logged in to Canvas**
- `chromedriver` matching your browser version (`sudo apt install chromium-driver`)

### Setup

```bash
# Clone and enter the project
cd attendance-app

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r web_backend/requirements.txt uvicorn
```

### Environment Variables

Create a `.env` file in the project root:

```env
CANVAS_ACCESS_TOKEN=your_canvas_token_here
CANVAS_BASE_URL=https://alueducation.instructure.com
CHROME_PROFILE_NAME=Default          # optional, only if you use a named profile
```

**Getting a Canvas API token:**
1. Canvas → Account → Settings
2. Scroll to **Approved Integrations** → **New Access Token**
3. Copy the token into `.env`

### Start the Server

```bash
uvicorn web_backend.main:app --reload --port 8001
```

Open **http://localhost:8001** in your browser.

---

## Using the App

### Step 1 — Manage Courses
Add your Canvas course URLs once (e.g. `https://alueducation.instructure.com/courses/2571`).
They persist in memory for the session (or in Redis if configured).

### Step 2 — Upload CSV
- Select the course
- Set the **session date** (used to navigate Roll Call's calendar)
- Set the **session start time** (used to detect late arrivals)
- Upload the Zoom or Teams attendance CSV

**Exporting from Zoom:**
1. Zoom Dashboard → Meetings → select the meeting
2. Participants tab → Export → CSV

**Exporting from Microsoft Teams:**
1. Meeting details → Attendance → Export

### Step 3 — Review & Run Roll Call
- The **Roll Call grid** shows each student as a colour-coded card:
  - 🟢 Green = Present
  - 🟠 Orange = Late
  - 🔴 Red = Absent
- Click **P / L / A** on any card to override the calculated status
- Click **Run Roll Call (Browser)** to launch automation

**What the automation does:**
1. Queries the Canvas API to find the Roll Call assignment ID and section ID
2. Opens the Canvas assignment page in your browser (establishes the LTI session cookie)
3. Navigates to `rollcall-eu.instructure.com/sections/{section_id}`
4. Uses the date picker to navigate to the session date
5. For each student: resets their status (4 clicks), then clicks to the correct status
6. Leaves the browser open so you can verify before closing

A **live log terminal** at the bottom of the screen streams every step in real time.

---

## API Endpoints

All served by `web_backend/main.py`:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/courses` | Returns `{ name: url }` dict of saved courses |
| `POST` | `/api/set_course` | Body: `{ name, url }` — add or update a course |
| `POST` | `/api/remove_course` | Body: `{ name }` — delete a course |
| `POST` | `/api/upload_csv?session_start=HH:MM AM` | Multipart file upload — returns students with calculated statuses |
| `POST` | `/api/run_rollcall` | Body: `{ course_url, session_date, students }` — runs Selenium, streams log via SSE |

---

## Key Files Explained

### `web_backend/main.py`
The FastAPI application. Contains:
- `calculate_status()` — applies the attendance rules to determine Present / Late / Absent
- `parse_duration_minutes()` — parses `"1h 23m 45s"` format from the CSV
- `parse_join_minutes()` — calculates how many minutes after session start a student joined
- `/api/upload_csv` — reads the CSV, calls `calculate_status` for each row, returns the student list
- `/api/run_rollcall` — starts `rollcall_browser.run_rollcall_automation()` in a background thread and streams log output via Server-Sent Events

### `web_backend/rollcall_browser.py`
Pure Selenium automation. Contains:
- `discover_ids(course_id)` — Canvas API calls to find the Roll Call assignment ID and first section ID
- `detect_browser()` — finds Brave or Chrome binary and profile path on Linux / macOS / Windows
- `ensure_browser_with_debugging()` — launches the browser with `--remote-debugging-port=9222` if not already open; attaches on subsequent runs with no re-login
- `open_rollcall()` — two-step LTI auth: Canvas assignment page → `rollcall-eu.instructure.com/sections/{id}`
- `navigate_to_date()` — clicks the `ui-datepicker` calendar to reach the session date
- `find_student_button()` — finds the `a.student-toggle` element for a student by name
- `click_to_status()` — clicks the toggle the right number of times (Present=1, Absent=2, Late=3)
- `run_rollcall_automation()` — orchestrates all of the above; accepts a `log=` callback so the web server can stream output

### `web_backend/course_manager.py`
Thin storage layer with two backends:
- **Local / development** — plain Python `dict` in memory (courses reset on server restart)
- **Production (Vercel)** — Upstash Redis (`KV_REST_API_URL` + `KV_REST_API_TOKEN` in env); courses persist across restarts

### `web_backend/api.py`
One-liner Mangum wrapper (`handler = Mangum(app)`) that makes the FastAPI app work as a Vercel Python serverless function.

### `web-frontend/app.js`
- `goTo(step)` — shows/hides the three panels and updates sidebar step indicators
- `loadCourses()` — fetches `/api/courses` and populates both the course card list and the CSV form dropdown
- CSV form submit — POSTs to `/api/upload_csv`, receives the student list, builds the Roll Call grid and table, navigates to Step 3
- `renderResults()` — creates `.rc-card` elements with P/L/A toggle buttons; clicking a button updates `currentStudents[i].status` and re-colours the card in real time
- `runRollCall()` — POSTs to `/api/run_rollcall`, then reads the SSE stream line-by-line and appends each message to the log terminal

---

## Course Storage

Courses are stored **in memory by default** — they reset whenever you restart the server. To make them persist, set up an [Upstash Redis](https://upstash.com) database and add to `.env`:

```env
KV_REST_API_URL=https://your-db.upstash.io
KV_REST_API_TOKEN=your_token
```

`CourseManager` automatically detects whether Redis credentials are present and switches backends.

---

## Python CLI (Alternative)

`python-cli/rollcall_selenium.py` is the original standalone script — no web server needed.

```bash
cd python-cli
pip install -r requirements.txt  # selenium webdriver-manager python-dotenv requests

python rollcall_selenium.py \
  --csv "attendance.csv" \
  --course-url "https://alueducation.instructure.com/courses/2571"

# Preview without opening browser
python rollcall_selenium.py --csv "attendance.csv" --course-url "..." --dry-run
```

The CLI script reads the session date and start time directly from the CSV filename (format: `CourseName_2026_03_06_11_14_CAT_Attendance_Attendees.csv`).

---

## Deployment Notes

The **browser automation cannot run on serverless platforms** (Vercel, Netlify, etc.) — they have no display and short function timeouts. The app is designed to run locally so Selenium controls your own browser where you are already logged in to Canvas.

The `vercel.json` config is present for deploying the API routes and static frontend to Vercel as a read-only companion (course management + CSV parsing), but the Roll Call automation endpoint will not work in that environment.

**Recommended setup:** run `uvicorn` locally, open `http://localhost:8001`.
