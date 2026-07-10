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

// ------------------------------------------------------------------ toast
let toastTimer = null;
function showToast(msg, isErr) {
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast'; t.className = 'toast'; t.setAttribute('role', 'status');
    t.setAttribute('aria-live', 'polite');
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.toggle('toast-err', !!isErr);
  requestAnimationFrame(() => t.classList.add('show'));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
}

// Plain-text block for the Copy action on the note page: title, description,
// main points, source URL — the same information a person would paste elsewhere.
function cardCopyText(title, desc, points, url) {
  const lines = [title || ''];
  if (desc) lines.push('', desc);
  if (points && points.length) {
    lines.push('', 'Main points:');
    points.forEach((p) =>
      lines.push('- ' + (p.name || '') + (p.description ? ': ' + p.description : '')));
  }
  lines.push('', 'Source: ' + (url || 'Pasted text'));
  return lines.join('\n');
}

// Whole-card click opens the detail; interactive children never trigger it.
document.addEventListener('click', (e) => {
  const card = e.target.closest('.result-card');
  if (card && card.dataset.open && !e.target.closest('button, a, input, label')) {
    location.href = card.dataset.open;
  }
});

// ---------------------------------------------- custom category picker (R1–R5)
function initCategoryPicker(root, onChange) {
  const btn = root.querySelector('.cat-picker-btn');
  const labelEl = root.querySelector('.cp-current');
  const hidden = root.querySelector('input[type="hidden"]');
  const panel = root.querySelector('.cat-picker-panel');
  let selectedPath = hidden.value || '';

  function setSelected(path) {
    selectedPath = path; hidden.value = path;
    labelEl.textContent = path || 'All categories';
    panel.querySelectorAll('.cat-picker-row').forEach((r) =>
      r.classList.toggle('selected', r.dataset.path === selectedPath));
  }
  function open() { panel.classList.add('open'); btn.setAttribute('aria-expanded', 'true'); }
  function close() { panel.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); }

  // Rows are divs (they contain the expand button, and buttons can't nest),
  // so give them explicit keyboard support to match the native select they
  // replaced: focusable, Enter/Space selects.
  function keyboardable(row) {
    row.tabIndex = 0;
    row.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); row.click(); }
    });
  }

  function makeAllRow() {
    const item = document.createElement('div');
    const row = document.createElement('div');
    row.className = 'cat-picker-row'; row.dataset.path = ''; row.setAttribute('role', 'option');
    row.style.paddingLeft = '10px';
    row.innerHTML = '<span class="cat-picker-twisty leaf"></span><span class="cp-name">All categories</span>';
    row.addEventListener('click', () => { setSelected(''); close(); if (onChange) onChange(''); });
    keyboardable(row);
    item.appendChild(row);
    return item;
  }
  function makeNode(cat, childrenOf) {
    const item = document.createElement('div');
    const row = document.createElement('div');
    row.className = 'cat-picker-row'; row.dataset.path = cat.path; row.setAttribute('role', 'option');
    row.style.paddingLeft = (10 + cat.depth * 16) + 'px';
    const kids = childrenOf[cat.id] || [];
    const tw = document.createElement('button');
    tw.type = 'button';
    tw.className = 'cat-picker-twisty' + (kids.length ? '' : ' leaf');
    tw.textContent = '▸';
    tw.setAttribute('aria-label', 'Expand ' + cat.name);
    const name = document.createElement('span');
    name.className = 'cp-name'; name.textContent = cat.name;
    const count = document.createElement('span');
    count.className = 'cp-count'; count.textContent = cat.total_note_count;
    row.append(tw, name, count);
    const childBox = document.createElement('div');
    childBox.style.display = 'none';
    kids.forEach((k) => childBox.appendChild(makeNode(k, childrenOf)));
    tw.addEventListener('click', (e) => {
      e.stopPropagation();
      const opening = childBox.style.display === 'none';
      childBox.style.display = opening ? 'block' : 'none';
      tw.classList.toggle('expanded', opening);
    });
    row.addEventListener('click', () => { setSelected(cat.path); close(); if (onChange) onChange(cat.path); });
    keyboardable(row);
    item.append(row, childBox);
    return item;
  }

  fetch('/api/categories').then((r) => r.json()).then((data) => {
    const cats = data.categories || [];
    const childrenOf = { root: [] };
    cats.forEach((c) => {
      const key = c.parent_id == null ? 'root' : c.parent_id;
      (childrenOf[key] = childrenOf[key] || []).push(c);
    });
    panel.innerHTML = '';
    panel.appendChild(makeAllRow());
    (childrenOf.root || []).forEach((c) => panel.appendChild(makeNode(c, childrenOf)));
    setSelected(selectedPath);
  });

  btn.addEventListener('click', () => (panel.classList.contains('open') ? close() : open()));
  document.addEventListener('click', (e) => { if (!root.contains(e.target)) close(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
}
window.initCategoryPicker = initCategoryPicker;
window.showToast = showToast;

// ------------------------------------------------- two-step confirmation
function confirmAction(text, onConfirm) {
  const modal = document.getElementById('modal');
  document.getElementById('modal-text').textContent = text;
  modal.classList.add('open');
  const confirmBtn = document.getElementById('modal-confirm');
  const cancelBtn = document.getElementById('modal-cancel');
  const close = () => { modal.classList.remove('open'); confirmBtn.onclick = cancelBtn.onclick = null; };
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

// -------------------------------------------------------- bulk selection
// Works on any page that renders .bulk-check checkboxes (category, search).
// Uses event delegation so it also picks up checkboxes rendered later by
// search.html's own JS.
const bulkSelected = new Set();

function updateBulkBar() {
  const bar = document.getElementById('bulk-bar');
  if (!bar) return;
  if (bulkSelected.size === 0) { bar.style.display = 'none'; return; }
  bar.style.display = '';
  document.getElementById('bulk-count').textContent = bulkSelected.size + ' selected';
}

document.addEventListener('change', (e) => {
  if (!e.target.classList || !e.target.classList.contains('bulk-check')) return;
  const id = Number(e.target.value);
  if (e.target.checked) bulkSelected.add(id); else bulkSelected.delete(id);
  updateBulkBar();
});

function clearBulkSelection() {
  bulkSelected.clear();
  document.querySelectorAll('.bulk-check').forEach((cb) => { cb.checked = false; });
  updateBulkBar();
}

async function loadBulkCategories() {
  const dl = document.getElementById('bulk-cat-datalist');
  if (!dl) return;
  const r = await fetch('/api/categories');
  const data = await r.json();
  dl.innerHTML = data.categories.map((c) => `<option value="${escapeHtml(c.path)}">`).join('');
}

const bulkTagBtn = document.getElementById('bulk-tag-btn');
if (bulkTagBtn) {
  loadBulkCategories();
  bulkTagBtn.addEventListener('click', async () => {
    const tags = document.getElementById('bulk-tag-input').value.trim();
    if (!tags || !bulkSelected.size) return;
    const body = new FormData();
    body.append('item_ids', [...bulkSelected].join(','));
    body.append('tags', tags);
    const r = await fetch('/api/bulk/tag', {method: 'POST', body});
    const data = await r.json();
    if (data.ok) { clearBulkSelection(); location.reload(); }
    else alert(data.error || 'Could not add tags.');
  });
  document.getElementById('bulk-move-btn').addEventListener('click', async () => {
    const category = document.getElementById('bulk-move-input').value.trim();
    if (!category || !bulkSelected.size) return;
    const body = new FormData();
    body.append('item_ids', [...bulkSelected].join(','));
    body.append('category', category);
    const r = await fetch('/api/bulk/move', {method: 'POST', body});
    const data = await r.json();
    if (data.ok) { clearBulkSelection(); location.reload(); }
    else alert(data.error || 'Could not move notes.');
  });
  document.getElementById('bulk-delete-btn').addEventListener('click', () => {
    if (!bulkSelected.size) return;
    const n = bulkSelected.size;
    confirmAction(`Delete ${n} note${n === 1 ? '' : 's'} — cannot be undone.`, async () => {
      const body = new FormData();
      body.append('item_ids', [...bulkSelected].join(','));
      const r = await fetch('/api/bulk/delete', {method: 'POST', body});
      const data = await r.json();
      if (data.ok) { clearBulkSelection(); location.reload(); }
      else alert(data.error || 'Could not delete notes.');
    });
  });
  document.getElementById('bulk-clear-btn').addEventListener('click', clearBulkSelection);
}

// ----------------------------------------------------------------- theme
// Light/dark toggle. The inline script in base.html already set
// document.documentElement.dataset.theme before first paint (no flash); this
// wires up the Settings control, persists the choice, keeps the theme-color/
// color-scheme meta tags in sync, and tells the graph page to re-pick its
// canvas palette (canvas draws with plain hex, so it can't follow CSS vars).
function currentTheme() {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('nv-theme', theme); } catch (e) {}
  const themeColor = document.querySelector('meta[name="theme-color"]');
  if (themeColor) themeColor.setAttribute('content', theme === 'light' ? '#ffffff' : '#050505');
  const colorScheme = document.querySelector('meta[name="color-scheme"]');
  if (colorScheme) colorScheme.setAttribute('content', theme);
  document.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
}
function syncThemeControls() {
  const isLight = currentTheme() === 'light';
  document.querySelectorAll('[data-theme-toggle]').forEach((el) => {
    if (el.type === 'checkbox') el.checked = isLight;
    else el.setAttribute('aria-pressed', String(isLight));
  });
}
function initThemeToggle() {
  applyTheme(currentTheme()); // sync meta tags with what the inline script already applied
  syncThemeControls();
  document.querySelectorAll('[data-theme-toggle]').forEach((el) => {
    const evt = el.type === 'checkbox' ? 'change' : 'click';
    el.addEventListener(evt, () => {
      applyTheme(currentTheme() === 'light' ? 'dark' : 'light');
      syncThemeControls();
    });
  });
}
initThemeToggle();
