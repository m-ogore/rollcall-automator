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
