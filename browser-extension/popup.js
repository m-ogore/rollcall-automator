const dot      = document.getElementById('status-dot');
const statusTx = document.getElementById('status-text');
const urlInput = document.getElementById('backend-url');
const idRow    = document.getElementById('id-row');

async function load() {
  const stored = await chrome.storage.local.get(['client_id', 'backend_url']);
  const backend = stored.backend_url || 'http://localhost:8001';
  urlInput.value = backend;

  if (stored.client_id) {
    idRow.textContent = `ID: ${stored.client_id.slice(0, 16)}…`;
  }

  // Check connection by calling /api/agent/status
  try {
    const res  = await fetch(`${backend}/api/agent/status?client_id=${stored.client_id || ''}`);
    const data = await res.json();
    if (data.connected) {
      dot.className = 'dot connected';
      statusTx.textContent = 'Connected to backend ✓';
    } else {
      dot.className = 'dot connecting';
      statusTx.textContent = 'Extension seen — backend not yet reached';
    }
  } catch (_) {
    dot.className = 'dot error';
    statusTx.textContent = `Cannot reach ${backend}`;
  }
}

document.getElementById('save-btn').addEventListener('click', async () => {
  const url = urlInput.value.trim().replace(/\/$/, '');
  await chrome.storage.local.set({ backend_url: url });
  statusTx.textContent = 'Saved — polling will use new URL';
  dot.className = 'dot connecting';
});

load();
