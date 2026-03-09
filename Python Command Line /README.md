# Roll Call Attendance Automation

Automate marking attendance directly in Canvas Roll Call from Zoom/Teams CSV exports.

## How to Run

### Prerequisites
- Python 3.8+
- **Brave Browser** installed ([download here](https://brave.com))
- Canvas account with Roll Call access
- Browser already logged into Canvas
- (Optional) Canvas API token for auto-discovery feature

### Download Meeting Records as CSV

#### From Zoom
1. Go to [Zoom Dashboard](https://zoom.us/signin)
2. Click **Meetings** → Select your recording
3. Click **Participants** tab
4. Click **Export** → **CSV**
5. Save file (use naming format: `CourseName_2026_03_06_11_14_CAT_Attendance_Attendees.csv`)

#### From Microsoft Teams
1. Open Teams meeting recording details
2. Click **Details** → **Export attendance**
3. Save as CSV file with date in filename

### Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### Usage

Run the script with your attendance CSV and any Roll Call URL:

```bash
python rollcall_selenium.py --csv "attendance.csv" --url "https://rollcall-eu.instructure.com/sections/5034"
```

#### Launch Roll Call from Canvas Course

The script opens your Canvas course, then opens Roll Call in a new tab:

**Setup: Add Canvas API Token to .env**
```bash
# Add this to your .env file
echo "CANVAS_ACCESS_TOKEN=your_token" >> .env
```

**Usage:**
```bash
python rollcall_selenium.py \
  --csv "attendance.csv" \
  --course-url "https://alueducation.instructure.com/courses/2571"
```

**What happens:**
1. ✅ Opens Canvas course in tab 1
2. ✅ Discovers Roll Call URL using Canvas API
3. ✅ Opens Roll Call in a NEW tab (tab 2)
4. ✅ Automatically marks attendance
5. ✅ Both tabs remain open for verification

No need to manually find the Roll Call URL!

#### Multiple Modules/Courses

Use the same script for different courses by just changing the URL:

**Module 1: Machine Learning**
```bash
python rollcall_selenium.py \
  --csv "ML_2026_03_06_11_14_Attendance.csv" \
  --course-url "https://alueducation.instructure.com/courses/2571"
```

**Module 2: Data Science**
```bash
python rollcall_selenium.py \
  --csv "DataScience_2026_03_06_14_30_Attendance.csv" \
  --course-url "https://alueducation.instructure.com/courses/2572"
```

**Module 3: Web Development**
```bash
python rollcall_selenium.py \
  --csv "WebDev_2026_03_07_10_00_Attendance.csv" \
  --course-url "https://alueducation.instructure.com/courses/2573"
```

#### Alternative: Using Canvas Assignment URL

Or use Canvas assignment URLs (Roll Call embedded in iframe):

```bash
python rollcall_selenium.py --csv "attendance.csv" --canvas-url "https://alueducation.instructure.com/courses/2571/assignments/35723"
```

### Quick Tips

- **CSV filename must include date** (e.g., `2026_03_06`) for auto-detection
- **Session start time** is auto-detected from earliest join time in CSV
- **Change URL** for each module — script works with any Roll Call link
- **Dry-run first** to verify before marking: add `--dry-run` flag

### Workflow for Multiple Modules

```bash
# 1. Export attendance CSV from Zoom/Teams
# 2. Run script with module-specific URL
python rollcall_selenium.py --csv "module_name_date.csv" --url "YOUR_ROLL_CALL_URL"

# Repeat for each module
```

| Option | Required | Description |
|--------|----------|-------------|
| `--csv` | ✅ Yes | Path to attendance CSV file |
| `--url` | ❌ No | Direct Roll Call URL |
| `--canvas-url` | ❌ No | Canvas assignment URL (Roll Call as iframe) |
| `--course-url` | ❌ No | Canvas course URL (auto-discovers Roll Call via API) |
| `--token` | ❌ No* | Canvas API access token (*required if using `--course-url`) |
| `--dry-run` | ❌ No | Preview attendance without opening browser |

**Note:** Provide either `--url`, `--canvas-url`, or `--course-url` (+ `--token`)

### Example: Dry Run (Preview Only)

```bash
python rollcall_selenium.py --csv "attendance.csv" --url "https://rollcall-eu.instructure.com/sections/5034" --dry-run
```

## How It Works

1. **Reads CSV** with attendance data from Zoom/Teams export
2. **Auto-detects date** from filename (e.g., `2026_03_06`)
3. **Calculates status**: present, late, or absent based on join time and duration
4. **Opens browser** using existing Canvas session
5. **Marks attendance** automatically for each student

## Attendance Rules

| Status  | Condition |
|---------|-----------|
| **Present** | Joined ≤ 15 min after start AND stayed ≥ 67.5 min |
| **Late** | Joined > 15 min late OR stayed < 67.5 min |
| **Absent** | Not in CSV |

## CSV Format

Expected columns from Zoom/Teams export:
```
First name | Last name | Email | Duration | Time joined | Time exited
```

**Filename must include date pattern:**
```
CourseName_-_2026_03_06_11_14_CAT_-_Attendance_-_Attendees.csv
```

## Screenshots

**1. Attendance Summary (Console Output)**
```
✅ Present: 47  |  ⚠️ Late: 11  |  ❌ Absent: 0
```

**2. Progress (Real-time Marking)**
```
🔧 Marking all students...
[1/59] Oreste Abizera: marking present... ✅
[2/59] James Jok Akuei: marking present... ✅
[7/59] Harerimana Egide: marking late... ✅
```

**3. Completion Report**
```
════════════════════════════════════════════════
  📊 DONE — 2026-03-06
════════════════════════════════════════════════
  ✅ Present   : 47
  ⚠️  Late      : 11
  ❌ Absent    : 0
════════════════════════════════════════════════
```

## Troubleshooting

**Problem:** "Could not find Brave or Chrome"
- Install **Brave Browser** from [brave.com](https://brave.com)
- Brave is required for this script. Chrome is not supported.

**Problem:** "Still on login page"
- Make sure browser is already logged into Canvas before running script
- Open Brave → log in to Canvas → then run the script

**Problem:** Some students not marked
- Verify student names in CSV match Roll Call exactly
- Check date navigation in Roll Call is correct

## Project Structure

```
attendance-app/
├── rollcall_selenium.py      # Main automation script
├── requirements.txt
├── README.md
└── backend/                  # Flask API (optional)
```
# rollcall-automator
