const API = '';
let currentStudents = [];
let currentCourseUrl = '';
let currentSessionDate = '';

// ── Toast ────────────────────────────────────────────────────────────────────
function toast(msg) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 3000);
}

// ── Step navigation ──────────────────────────────────────────────────────────
function goTo(step) {
    document.querySelectorAll('.panel').forEach(p => p.classList.add('hidden'));
    document.getElementById(`panel-${step}`).classList.remove('hidden');
    document.querySelectorAll('.step').forEach(s => {
        const n = +s.dataset.step;
        s.classList.toggle('active', n === step);
        s.classList.toggle('done',   n < step);
    });
}
document.querySelectorAll('.step').forEach(s =>
    s.addEventListener('click', () => goTo(+s.dataset.step))
);

// ── Courses ──────────────────────────────────────────────────────────────────
async function loadCourses() {
    const res  = await fetch(`${API}/api/courses`);
    const data = await res.json();
    const list   = document.getElementById('course-list');
    const select = document.getElementById('course-select');
    list.innerHTML   = '';
    select.innerHTML = '<option value="">— Select a course —</option>';

    const entries = Object.entries(data);
    if (!entries.length) {
        list.innerHTML = '<p style="color:var(--muted);font-size:.85rem">No courses yet. Add one above.</p>';
    }
    entries.forEach(([name, url]) => {
        // Dropdown
        const opt = document.createElement('option');
        opt.value = url; opt.textContent = name;
        select.appendChild(opt);
        // Card
        const card = document.createElement('div');
        card.className = 'course-card';
        const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
        card.innerHTML = `
            <div class="course-card-info">
                <div class="course-card-name">${name}</div>
                <div class="course-card-url">${url}</div>
            </div>
            <button class="btn-remove" data-name="${name}">Remove</button>`;
        card.querySelector('.btn-remove').addEventListener('click', () => removeCourse(name));
        list.appendChild(card);
    });
}

async function removeCourse(name) {
    await fetch(`${API}/api/remove_course`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    });
    toast(`Removed "${name}"`);
    loadCourses();
}

document.getElementById('course-form').addEventListener('submit', async function(e) {
    e.preventDefault();
    const name = document.getElementById('course-name').value.trim();
    const url  = document.getElementById('course-url').value.trim();
    const res  = await fetch(`${API}/api/set_course`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, url })
    });
    const data = await res.json();
    toast(data.message);
    this.reset();
    loadCourses();
});

// ── File drop ────────────────────────────────────────────────────────────────
const fileDrop = document.getElementById('file-drop');
const fileInput = document.getElementById('csv-file');

fileDrop.addEventListener('dragover', e => { e.preventDefault(); fileDrop.classList.add('drag-over'); });
fileDrop.addEventListener('dragleave', () => fileDrop.classList.remove('drag-over'));
fileDrop.addEventListener('drop', e => {
    e.preventDefault();
    fileDrop.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) {
        fileInput.files = e.dataTransfer.files;
        document.getElementById('file-name').textContent = e.dataTransfer.files[0].name;
    }
});
fileInput.addEventListener('change', function() {
    document.getElementById('file-name').textContent = this.files[0]?.name || 'Click or drag a CSV file here';
});

// ── CSV upload ────────────────────────────────────────────────────────────────
document.getElementById('csv-form').addEventListener('submit', async function(e) {
    e.preventDefault();
    if (!fileInput.files[0]) { toast('Please choose a CSV file.'); return; }

    currentCourseUrl = document.getElementById('course-select').value;
    currentSessionDate = document.getElementById('session-date').value;
    const sessionTime = document.getElementById('session-start').value;

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    let url = `${API}/api/upload_csv`;
    if (sessionTime) {
        const [h, m] = sessionTime.split(':').map(Number);
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12  = h % 12 || 12;
        url += `?session_start=${encodeURIComponent(`${h12}:${String(m).padStart(2,'0')} ${ampm}`)}`;
    }

    const res  = await fetch(url, { method: 'POST', body: formData });
    const data = await res.json();
    currentStudents = data.students || [];
    renderResults(data);
    goTo(3);
});

// ── Roll Call renderer ────────────────────────────────────────────────────────
function renderResults(data) {
    // Badges
    const present = currentStudents.filter(s => s.status === 'present').length;
    const late    = currentStudents.filter(s => s.status === 'late').length;
    const absent  = currentStudents.filter(s => s.status === 'absent').length;
    document.getElementById('summary-badges').innerHTML = `
        <span class="badge badge-present">✓ ${present} Present</span>
        <span class="badge badge-late">◷ ${late} Late</span>
        <span class="badge badge-absent">✗ ${absent} Absent</span>`;

    // Roll Call grid
    const grid = document.getElementById('rollcall-grid');
    grid.innerHTML = '';
    currentStudents.forEach((s, i) => {
        const initials = s.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || '?';
        const card = document.createElement('div');
        card.className = `rc-card ${s.status}`;
        card.dataset.index = i;
        card.innerHTML = `
            <div style="display:flex;align-items:center;gap:8px">
                <div class="rc-avatar">${initials}</div>
                <div style="overflow:hidden">
                    <div class="rc-name">${s.name || '—'}</div>
                    <div class="rc-email">${s.email}</div>
                </div>
            </div>
            <div class="rc-status-row">
                <button class="rc-btn" data-s="present">P</button>
                <button class="rc-btn" data-s="late">L</button>
                <button class="rc-btn" data-s="absent">A</button>
            </div>`;
        card.querySelectorAll('.rc-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const idx = +card.dataset.index;
                currentStudents[idx].status = btn.dataset.s;
                card.className = `rc-card ${btn.dataset.s}`;
                updateBadges();
                updateTableRow(idx, btn.dataset.s);
            });
        });
        grid.appendChild(card);
    });

    // Table
    const tbody = document.getElementById('results-body');
    tbody.innerHTML = '';
    currentStudents.forEach((s, i) => {
        const tr = document.createElement('tr');
        tr.dataset.index = i;
        tr.innerHTML = `
            <td>${s.name}</td>
            <td>${s.email}</td>
            <td>${s.time_joined}</td>
            <td>${s.duration}</td>
            <td class="s-${s.status}">${s.status.toUpperCase()}</td>`;
        tbody.appendChild(tr);
    });

    // Reset result banner and any canvas badges from a previous submission
    document.getElementById('rollcall-log').classList.add('hidden');
    document.getElementById('rc-log-body').textContent = '';
}

function updateBadges() {
    const present = currentStudents.filter(s => s.status === 'present').length;
    const late    = currentStudents.filter(s => s.status === 'late').length;
    const absent  = currentStudents.filter(s => s.status === 'absent').length;
    document.getElementById('summary-badges').innerHTML = `
        <span class="badge badge-present">✓ ${present} Present</span>
        <span class="badge badge-late">◷ ${late} Late</span>
        <span class="badge badge-absent">✗ ${absent} Absent</span>`;
}

function updateTableRow(idx, status) {
    const tr = document.querySelector(`#results-body tr[data-index="${idx}"]`);
    if (tr) tr.lastElementChild.className = `s-${status}`, tr.lastElementChild.textContent = status.toUpperCase();
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Run Roll Call (Browser Automation) ───────────────────────────────────
async function runRollCall() {
    if (!currentCourseUrl) { toast('No course selected.'); return; }
    if (!currentSessionDate) { toast('Please set a session date in Step 2.'); return; }
    if (!currentStudents.length) { toast('No students loaded.'); return; }

    const btn     = document.getElementById('rollcall-btn');
    const logBox  = document.getElementById('rollcall-log');
    const logBody = document.getElementById('rc-log-body');

    btn.disabled = true;
    btn.innerHTML = `<span class="btn-spinner"></span> Running…`;
    logBody.textContent = '';
    logBox.classList.remove('hidden');
    logBox.scrollIntoView({ behavior: 'smooth' });

    const appendLog = (line) => {
        logBody.textContent += line + '\n';
        logBox.scrollTop = logBox.scrollHeight;
    };

    appendLog(`▶ Starting Roll Call automation for ${currentSessionDate}...`);

    try {
        const res = await fetch(`${API}/api/run_rollcall`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                course_url:   currentCourseUrl,
                session_date: currentSessionDate,
                students:     currentStudents
            })
        });

        if (!res.ok) {
            const err = await res.json();
            appendLog(`❌ Error: ${err.error}`);
            btn.disabled = false;
            btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg> Run Roll Call (Browser)`;
            return;
        }

        const reader  = res.body.getReader();
        const decoder = new TextDecoder();
        let   buffer  = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const msg = line.slice(6);
                    if (msg === '__DONE__') break;
                    appendLog(msg);
                }
            }
        }
        appendLog('✔ Done!');
    } catch (err) {
        appendLog(`❌ Network error: ${err.message}`);
    }

    btn.disabled = false;
    btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg> Run Roll Call (Browser)`;
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadCourses();

