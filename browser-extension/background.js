/**
 * background.js — Roll Call Automator Service Worker
 *
 * Responsibilities:
 *   1. Generate + persist a unique client_id for this browser installation
 *   2. Send periodic heartbeats to the backend so the web app can show
 *      "Extension connected ✓"
 *   3. Poll the backend for pending jobs every 2 seconds
 *   4. When a job arrives: discover Canvas assignment/section IDs, open the
 *      Canvas assignment page in a background tab, then forward the job to the
 *      Roll Call content script (content_rollcall.js) once the iframe is ready
 *   5. Relay log messages from the content script back to the backend
 *   6. Close the automation tab when the job finishes
 */

// ── State ───────────────────────────────────────────────────────────────────

let clientId = null;
// tabId → { job, backend } for in-flight automation tabs
const pendingTabJobs = {};

// ── Init ────────────────────────────────────────────────────────────────────

async function init() {
  const stored = await chrome.storage.local.get(['client_id', 'backend_url']);

  if (!stored.client_id) {
    const id = crypto.randomUUID();
    await chrome.storage.local.set({ client_id: id });
    clientId = id;
  } else {
    clientId = stored.client_id;
  }
}

async function getBackend() {
  const r = await chrome.storage.local.get(['backend_url']);
  return (r.backend_url || 'http://localhost:8001').replace(/\/$/, '');
}

// ── Heartbeat (every 5 s) ───────────────────────────────────────────────────

setInterval(async () => {
  if (!clientId) return;
  const backend = await getBackend();
  fetch(`${backend}/api/agent/heartbeat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_id: clientId }),
  }).catch(() => {});
}, 5000);

// ── Job poll (every 2 s) ────────────────────────────────────────────────────

setInterval(async () => {
  if (!clientId) return;
  const backend = await getBackend();
  try {
    const res = await fetch(`${backend}/api/agent/job?client_id=${clientId}`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.job) handleJob(data.job, backend);
  } catch (_) {}
}, 2000);

// ── Job handler ─────────────────────────────────────────────────────────────

async function handleJob(job, backend) {
  const courseUrl = job.course_url || '';
  const courseMatch = courseUrl.match(/\/courses\/(\d+)/);
  if (!courseMatch) {
    await postLog(backend, '❌ Invalid course URL — cannot extract course ID');
    await postLog(backend, '__DONE__');
    return;
  }
  const courseId   = courseMatch[1];
  const canvasBase = courseUrl.split('/courses/')[0]; // e.g. https://alueducation.instructure.com

  await postLog(backend, `🎓 Course ID: ${courseId}`);
  await postLog(backend, `📅 Session date: ${job.session_date}`);
  await postLog(backend, `👥 Students: ${job.students.length}`);
  await postLog(backend, 'Querying Canvas API...');

  // Discover assignment_id + section_id using the user's existing Canvas session
  let assignmentId, sectionId;
  try {
    const [aRes, sRes] = await Promise.all([
      fetch(`${canvasBase}/api/v1/courses/${courseId}/assignments?per_page=100`, { credentials: 'include' }),
      fetch(`${canvasBase}/api/v1/courses/${courseId}/sections?per_page=100`,    { credentials: 'include' }),
    ]);

    if (!aRes.ok) throw new Error(`Assignments API returned ${aRes.status} — are you logged into Canvas?`);
    if (!sRes.ok) throw new Error(`Sections API returned ${sRes.status}`);

    const assignments = await aRes.json();
    const sections    = await sRes.json();

    const rc = assignments.find(a => /roll\s*call|attendance/i.test(a.name || ''));
    if (!rc) {
      const names = assignments.slice(0, 10).map(a => a.name).join(', ');
      await postLog(backend, `❌ No Roll Call assignment found. Assignments: ${names}`);
      await postLog(backend, '__DONE__');
      return;
    }
    assignmentId = rc.id;
    await postLog(backend, `✅ Assignment: "${rc.name}" (ID: ${assignmentId})`);

    if (!sections.length) {
      await postLog(backend, '❌ No sections found for this course');
      await postLog(backend, '__DONE__');
      return;
    }
    sectionId = sections[0].id;
    await postLog(backend, `✅ Section ID: ${sectionId}`);
  } catch (err) {
    await postLog(backend, `❌ Canvas API error: ${err.message}`);
    await postLog(backend, '__DONE__');
    return;
  }

  // Open the Canvas assignment page — this triggers the LTI auth and loads the
  // Roll Call iframe which content_rollcall.js will inject into automatically.
  const canvasAssignmentUrl = `${canvasBase}/courses/${courseId}/assignments/${assignmentId}`;
  await postLog(backend, `📋 Opening Roll Call via Canvas: ${canvasAssignmentUrl}`);

  const tab = await chrome.tabs.create({ url: canvasAssignmentUrl, active: false });
  pendingTabJobs[tab.id] = { ...job, backend, sectionId };
}

// ── Message bus (content scripts → background) ──────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender) => {
  const tabId  = sender.tab?.id;
  const jobCtx = pendingTabJobs[tabId];

  if (msg.type === 'rollcall_ready') {
    // content_rollcall.js has loaded inside the Roll Call iframe
    if (jobCtx) {
      postLog(jobCtx.backend, '✅ Roll Call page ready — starting automation...');
      // Forward the job to that specific frame
      chrome.tabs.sendMessage(
        tabId,
        { type: 'run_job', job: jobCtx },
        { frameId: sender.frameId }
      );
    }
    return;
  }

  if (msg.type === 'log') {
    if (jobCtx) postLog(jobCtx.backend, msg.message);
    return;
  }

  if (msg.type === 'job_done') {
    if (jobCtx) {
      postLog(jobCtx.backend, '__DONE__');
      delete pendingTabJobs[tabId];
      // Give the last log a moment to POST before closing the tab
      setTimeout(() => chrome.tabs.remove(tabId), 1500);
    }
    return;
  }
});

// ── Log helper ───────────────────────────────────────────────────────────────

async function postLog(backend, message) {
  if (!clientId) return;
  try {
    await fetch(`${backend}/api/agent/log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: clientId, message }),
    });
  } catch (_) {}
}

// ── Boot ─────────────────────────────────────────────────────────────────────

init();
