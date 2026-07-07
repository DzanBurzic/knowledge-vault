// Shared dashboard behavior: status polling (R15), confirmations (R54),
// queue actions (R22, R56).

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// ---------------------------------------------------------- status area
async function refreshStatus() {
  try {
    const r = await fetch('/api/status');
    const s = await r.json();
    document.getElementById('st-queue').textContent = s.queue_count;
    const currentRow = document.getElementById('st-current-row');
    if (s.current_label) {
      currentRow.style.display = '';
      document.getElementById('st-current').textContent =
        s.current_label.length > 32 ? s.current_label.slice(0, 32) + '…' : s.current_label;
      document.getElementById('st-stage').textContent = s.current_stage || '';
    } else {
      currentRow.style.display = 'none';
    }
    const ollama = document.getElementById('st-ollama');
    ollama.textContent = s.ollama_ok ? 'running ✓' : 'not reachable ✗';
    ollama.className = s.ollama_ok ? 'st-ok' : 'st-bad';
    const inbox = document.getElementById('st-inbox');
    if (s.inbox_ok === null) { inbox.textContent = 'not set up'; inbox.className = 'st-na'; }
    else if (s.inbox_ok) { inbox.textContent = 'reachable ✓'; inbox.className = 'st-ok'; }
    else { inbox.textContent = 'unreachable ✗'; inbox.className = 'st-bad'; }
    const cloud = document.getElementById('st-cloud');
    if (cloud) {
      const pend = s.cloud_pending ? ` (${s.cloud_pending} to send)` : '';
      if (s.cloud_ok === null) { cloud.textContent = 'not set up'; cloud.className = 'st-na'; }
      else if (s.cloud_ok) { cloud.textContent = 'synced ✓' + pend; cloud.className = 'st-ok'; }
      else { cloud.textContent = 'sync pending ✗' + pend; cloud.className = 'st-bad'; }
    }
    document.getElementById('st-poll').textContent =
      s.last_poll ? s.last_poll.slice(11, 19) : 'never';
    const warning = document.getElementById('st-warning');
    if (!s.ollama_ok) { warning.style.display = ''; warning.textContent = s.ollama_message; }
    else if (s.inbox_ok === false) { warning.style.display = ''; warning.textContent = s.inbox_message; }
    else { warning.style.display = 'none'; }
  } catch (e) { /* server restarting; try again next tick */ }
}
refreshStatus();
setInterval(refreshStatus, 3000);

// ------------------------------------------------- two-step confirmation
function confirmAction(text, onConfirm) {
  const modal = document.getElementById('modal');
  document.getElementById('modal-text').textContent = text;
  modal.style.display = '';
  const confirmBtn = document.getElementById('modal-confirm');
  const cancelBtn = document.getElementById('modal-cancel');
  const close = () => { modal.style.display = 'none'; confirmBtn.onclick = cancelBtn.onclick = null; };
  confirmBtn.onclick = () => { close(); onConfirm(); };
  cancelBtn.onclick = close;
}

async function postAction(url, successMsg, redirect, formFields) {
  let body;
  if (formFields) {
    body = new FormData();
    for (const [k, v] of Object.entries(formFields)) body.append(k, v);
  }
  const r = await fetch(url, {method: 'POST', body});
  const data = await r.json();
  if (data.ok) {
    if (redirect) location.href = redirect; else location.reload();
  } else {
    alert(data.error || 'Something went wrong.');
  }
}

async function retryQueue(id) {
  await fetch(`/api/queue/${id}/retry`, {method: 'POST'});
  location.reload();
}

// needs_input paste forms on the home page (R22)
document.addEventListener('submit', async (e) => {
  const form = e.target.closest('.supply-form');
  if (!form) return;
  e.preventDefault();
  const body = new FormData(form);
  const r = await fetch(`/api/queue/${form.dataset.queueId}/supply`, {method: 'POST', body});
  const data = await r.json();
  if (data.ok) location.reload(); else alert(data.error || 'Something went wrong.');
});
