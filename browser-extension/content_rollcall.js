/**
 * content_rollcall.js — Roll Call Automator Content Script
 *
 * Injected into every frame matching *://rollcall-eu.instructure.com/*
 * (including when rendered as an iframe inside a Canvas assignment page).
 *
 * Flow:
 *   1. Signals background.js that the Roll Call page is loaded and ready
 *   2. Waits for a `run_job` message containing job details
 *   3. Waits for the student list to appear (it loads asynchronously)
 *   4. Navigates the date picker to the session date
 *   5. Clicks each student toggle the right number of times to reach the
 *      requested status (present / late / absent)
 *   6. Sends `job_done` so the background script can close the tab
 */

// ── Utilities ────────────────────────────────────────────────────────────────

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function log(msg) {
  chrome.runtime.sendMessage({ type: 'log', message: msg });
}

/** Poll for `selector` until it appears or `timeout` ms elapses. */
async function waitFor(selector, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const el = document.querySelector(selector);
    if (el) return el;
    await sleep(300);
  }
  return null;
}

// ── Date navigation ──────────────────────────────────────────────────────────

const MONTH_NAMES = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December'
];

async function navigateToDate(dateStr) {
  const [year, month, day] = dateStr.split('-').map(Number);

  const trigger = document.querySelector('img.ui-datepicker-trigger');
  if (!trigger) {
    log('⚠️ Date picker not found — using current date');
    return;
  }

  trigger.click();
  await sleep(500);

  const picker = await waitFor('.ui-datepicker', 3000);
  if (!picker) {
    log('⚠️ Date picker did not open');
    return;
  }

  for (let i = 0; i < 24; i++) {
    const titleEl = document.querySelector('.ui-datepicker-title');
    if (!titleEl) break;

    const parts    = titleEl.textContent.trim().split(' ');
    const curMonth = MONTH_NAMES.indexOf(parts[0]);
    const curYear  = parseInt(parts[1], 10);

    if (curYear === year && curMonth === month - 1) {
      // Correct month — click the day
      const cells = document.querySelectorAll('.ui-datepicker-calendar td a');
      for (const cell of cells) {
        if (parseInt(cell.textContent.trim(), 10) === day) {
          cell.click();
          await sleep(500);
          log(`✅ Date set to ${dateStr}`);
          return;
        }
      }
      log(`⚠️ Day ${day} not found in calendar`);
      return;
    }

    // Navigate forward or back
    const curDate    = new Date(curYear, curMonth, 1);
    const targetDate = new Date(year, month - 1, 1);
    const navSel     = curDate < targetDate ? '.ui-datepicker-next' : '.ui-datepicker-prev';
    const navBtn     = document.querySelector(navSel);
    if (!navBtn) break;
    navBtn.click();
    await sleep(300);
  }

  log('⚠️ Could not navigate to the target date');
}

// ── Student lookup ───────────────────────────────────────────────────────────

function findStudentButton(name) {
  const parts = name.toLowerCase().split(/\s+/).filter(Boolean);

  for (const link of document.querySelectorAll('a.student-toggle')) {
    const text = link.textContent.toLowerCase();
    if (parts.every(p => text.includes(p))) return link;
  }

  // Fallback: search list items for the name then find the nested toggle
  for (const li of document.querySelectorAll('ol.student-list-display li')) {
    const text = li.textContent.toLowerCase();
    if (parts.every(p => text.includes(p))) {
      const toggle = li.querySelector('a.student-toggle');
      if (toggle) return toggle;
    }
  }

  return null;
}

// ── Status clicking ──────────────────────────────────────────────────────────

// Roll Call cycles: unset → present (1 click) → absent (2 clicks) → late (3 clicks)
const CLICKS_FOR = { present: 1, absent: 2, late: 3 };

async function clickToStatus(btn, status) {
  const clicks = CLICKS_FOR[status] ?? 1;
  for (let i = 0; i < clicks; i++) {
    btn.scrollIntoView({ block: 'center' });
    btn.click();
    await sleep(300);
  }
  await sleep(200);
}

// ── Main automation ──────────────────────────────────────────────────────────

async function runAutomation(job) {
  log('⏳ Waiting for student list to load...');

  const firstToggle = await waitFor('a.student-toggle', 30000);
  if (!firstToggle) {
    log('❌ Student list did not load within 30 s — aborting');
    chrome.runtime.sendMessage({ type: 'job_done' });
    return;
  }
  await sleep(500);
  log('✅ Student list loaded');

  await navigateToDate(job.session_date);
  await sleep(800);

  const students = job.students || [];
  log(`👥 Marking ${students.length} students...`);

  let marked = 0;
  let missing = 0;

  for (const student of students) {
    const btn = findStudentButton(student.name);
    if (!btn) {
      log(`⚠️  Not found in Roll Call: ${student.name}`);
      missing++;
      continue;
    }
    await clickToStatus(btn, student.status);
    log(`✅ ${student.name} → ${student.status}`);
    marked++;
    await sleep(100);
  }

  log(`🎉 Done! Marked: ${marked}${missing ? `, not found: ${missing}` : ''}`);
  chrome.runtime.sendMessage({ type: 'job_done' });
}

// ── Announce ready; wait for job ─────────────────────────────────────────────

chrome.runtime.sendMessage({ type: 'rollcall_ready', url: location.href });

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'run_job') {
    runAutomation(msg.job);
  }
});
