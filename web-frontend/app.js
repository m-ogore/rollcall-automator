const API = '';

function toast(msg) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 3000);
}

async function loadCourses() {
    const res  = await fetch(`${API}/api/courses`);
    const data = await res.json();
    const list   = document.getElementById('course-list');
    const select = document.getElementById('course-select');
    list.innerHTML   = '';
    select.innerHTML = '<option value="">-- Select Course --</option>';
    Object.entries(data).forEach(([name, url]) => {
        const opt = document.createElement('option');
        opt.value = url;
        opt.textContent = name;
        select.appendChild(opt);

        const item = document.createElement('div');
        item.className = 'course-item';
        item.innerHTML = `<span><strong>${name}</strong> &mdash; ${url}</span>
            <button class="danger" data-name="${name}">Remove</button>`;
        item.querySelector('button').addEventListener('click', () => removeCourse(name));
        list.appendChild(item);
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

document.getElementById('csv-file').addEventListener('change', function() {
    document.getElementById('file-name').textContent =
        this.files[0] ? this.files[0].name : 'Choose CSV…';
});

document.getElementById('csv-form').addEventListener('submit', async function(e) {
    e.preventDefault();
    const fileInput    = document.getElementById('csv-file');
    const sessionStart = document.getElementById('session-start').value;
    if (!fileInput.files[0]) { toast('Please choose a CSV file.'); return; }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    let url = `${API}/api/upload_csv`;
    if (sessionStart) {
        const [h, m] = sessionStart.split(':').map(Number);
        const ampm = h >= 12 ? 'PM' : 'AM';
        const h12  = h % 12 || 12;
        url += `?session_start=${encodeURIComponent(`${h12}:${String(m).padStart(2,'0')} ${ampm}`)}`;
    }

    const res  = await fetch(url, { method: 'POST', body: formData });
    const data = await res.json();

    document.getElementById('summary').textContent = data.message;
    const tbody = document.getElementById('results-body');
    tbody.innerHTML = '';
    (data.students || []).forEach(s => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${s.name}</td>
            <td>${s.email}</td>
            <td>${s.time_joined}</td>
            <td>${s.duration}</td>
            <td class="status-${s.status}">${s.status.toUpperCase()}</td>`;
        tbody.appendChild(tr);
    });
    document.getElementById('results-section').style.display = 'block';
    document.getElementById('results-section').scrollIntoView({ behavior: 'smooth' });
});

loadCourses();
