/* obra dashboard — talks to the real JSON APIs. CSRF token from data attr. */
const CSRF = document.querySelector('meta[name="csrf"]')?.content || '';
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'X-CSRF-Token': CSRF, 'Content-Type': 'application/json', ...(opts.headers || {}) },
    credentials: 'same-origin',
    ...opts,
  });
  if (res.status === 401) { location.href = '/'; throw new Error('unauthorized'); }
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

function toast(msg, bad = false) {
  let t = $('.toast');
  if (!t) { t = document.createElement('div'); t.className = 'toast'; document.body.appendChild(t); }
  t.textContent = msg;
  t.style.borderColor = bad ? 'var(--bad)' : 'var(--good)';
  t.style.opacity = 1;
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.style.opacity = 0), 2200);
}

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtTime = (iso) => iso ? new Date(iso.replace(' ', 'T') + 'Z').toLocaleString() : '—';

/* ---------- nav ---------- */
$$('.nav button').forEach((b) => b.addEventListener('click', () => {
  $$('.nav button').forEach((x) => x.classList.remove('active'));
  b.classList.add('active');
  $$('.section').forEach((s) => s.classList.remove('active'));
  $('#sec-' + b.dataset.sec).classList.add('active');
  loadSection(b.dataset.sec);
}));

/* ---------- theme ---------- */
const themeBtn = $('#themeBtn');
themeBtn?.addEventListener('click', () => {
  const el = document.documentElement;
  const next = el.dataset.theme === 'light' ? 'dark' : 'light';
  el.dataset.theme = next;
  localStorage.setItem('obra-theme', next);
  themeBtn.textContent = next === 'light' ? '🌙 Dark' : '☀️ Light';
});
document.documentElement.dataset.theme = localStorage.getItem('obra-theme') || 'dark';
if (themeBtn) themeBtn.textContent = document.documentElement.dataset.theme === 'light' ? '🌙 Dark' : '☀️ Light';

/* ---------- sections ---------- */
const loaders = {
  overview: loadOverview,
  providers: loadProviders,
  conversations: loadConversations,
  users: loadUsers,
  skills: loadSkills,
  logs: loadLogs,
  security: loadSecurity,
};
function loadSection(name) { (loaders[name] || loadOverview)().catch((e) => toast('Load failed: ' + e.message, true)); }

async function loadOverview() {
  const d = await api('/api/overview');
  $('#stat-users').textContent = d.stats.active_users;
  $('#stat-chats').textContent = d.stats.chats;
  $('#stat-msgs').textContent = d.stats.events.message || 0;
  $('#stat-replies').textContent = d.stats.events.reply || 0;
  $('#stat-blocked').textContent = d.stats.blocked;
  $('#stat-tools').textContent = d.tools;
  $('#stat-uptime').textContent = Math.floor(d.uptime_seconds / 3600) + 'h ' + Math.floor((d.uptime_seconds % 3600) / 60) + 'm';
  $('#stat-model').textContent = d.model;
  $('#stat-mode').textContent = d.mode + (d.rich ? ' · rich' : '');
  // provider pills
  $('#prov-pills').innerHTML = d.providers.length
    ? d.providers.map((p) => `<span class="badge info">${esc(p.name)}</span>`).join('')
    : '<span class="badge bad">no providers configured</span>';
  // bar chart of usage series
  const series = d.usage_series || [];
  const max = Math.max(1, ...series.map((s) => s.c));
  $('#chart').innerHTML = series.length
    ? series.map((s) => `<div class="bar-row"><span>${esc(s.day.slice(5))}</span><div style="background:var(--card2);border-radius:7px"><div class="bar" style="width:${(s.c / max) * 100}%"></div></div><span>${s.c}</span></div>`).join('')
    : '<div class="empty">No usage yet.</div>';
}

async function loadProviders() {
  const d = await api('/api/providers');
  const st = d.stats || {};
  $('#prov-table').innerHTML = d.chain.length ? `
    <table><thead><tr><th>#</th><th>Provider</th><th>Model</th><th>Base URL</th><th>OK</th><th>Fail</th><th>Status</th></tr></thead>
    <tbody>${d.chain.map((p, i) => {
      const s = st[p.name] || { ok: 0, fail: 0, cooling_down: false, last_error: '' };
      const status = s.cooling_down ? '<span class="badge warn">cooling down</span>' : (s.ok > 0 ? '<span class="badge ok">healthy</span>' : '<span class="badge info">idle</span>');
      return `<tr><td>${i + 1}</td><td><b>${esc(p.name)}</b></td><td><code>${esc(p.model)}</code></td><td><code>${esc(p.base_url)}</code></td><td>${s.ok}</td><td>${s.fail}</td><td>${status}${s.last_error ? `<div class="hint" title="${esc(s.last_error)}">${esc(s.last_error.slice(0, 60))}</div>` : ''}</td></tr>`;
    }).join('')}</tbody></table>` : '<div class="empty">No providers configured — set API keys in .env (see Api.md).</div>';
}

async function loadConversations() {
  const d = await api('/api/conversations');
  $('#conv-table').innerHTML = d.conversations.length ? `
    <table><thead><tr><th>Chat</th><th>Title</th><th>Type</th><th>Messages</th><th>Last active</th></tr></thead>
    <tbody>${d.conversations.map((c) => `<tr><td><code>${c.chat_id}</code></td><td>${esc(c.title || '—')}</td><td>${c.is_group ? '<span class="badge info">group</span>' : '<span class="badge">private</span>'}</td><td>${c.messages}</td><td>${fmtTime(c.last_active)}</td></tr>`).join('')}</tbody></table>`
    : '<div class="empty">No conversations yet.</div>';
}

async function loadUsers() {
  const d = await api('/api/users');
  $('#users-table').innerHTML = d.users.length ? `
    <table><thead><tr><th>User</th><th>Plan</th><th>State</th><th>Events (24h)</th><th>Last seen</th><th></th></tr></thead>
    <tbody>${d.users.map((u) => `<tr><td><code>${u.user_id}</code></td>
      <td>${u.premium ? '<span class="badge ok">⭐ premium</span>' : '<span class="badge info">free</span>'}</td>
      <td>${u.blocked ? '<span class="badge bad">blocked</span>' : '<span class="badge ok">active</span>'}</td>
      <td>${u.msgs}</td><td>${fmtTime(u.last_seen)}</td>
      <td><button class="icon-btn" onclick="toggleBlock(${u.user_id}, ${u.blocked})">${u.blocked ? 'Unblock' : 'Block'}</button></td></tr>`).join('')}</tbody></table>`
    : '<div class="empty">No active users in the last 24h.</div>';
}

async function loadSkills() {
  const d = await api('/api/skills');
  $('#skills-table').innerHTML = d.skills.length ? `
    <table><thead><tr><th>ID</th><th>User</th><th>Name</th><th>Instruction</th><th>Created</th></tr></thead>
    <tbody>${d.skills.map((s) => `<tr><td>#${s.id}</td><td><code>${s.user_id}</code></td><td>${esc(s.name)}</td><td><code>${esc(s.instruction.slice(0, 120))}</code></td><td>${fmtTime(s.created_at)}</td></tr>`).join('')}</tbody></table>`
    : '<div class="empty">No scheduled skills yet.</div>';
}

async function loadLogs() {
  const d = await api('/api/logs');
  $('#logs-table').innerHTML = d.events.length ? `
    <table><thead><tr><th>Time</th><th>User</th><th>Event</th><th>Meta</th></tr></thead>
    <tbody>${d.events.map((e) => `<tr><td>${fmtTime(e.created_at)}</td><td><code>${e.user_id ?? '—'}</code></td><td><span class="badge info">${esc(e.event)}</span></td><td><code>${esc((e.meta || '').slice(0, 140))}</code></td></tr>`).join('')}</tbody></table>`
    : '<div class="empty">No events logged yet.</div>';
}

async function loadSecurity() {
  const d = await api('/api/blocked');
  $('#blocked-table').innerHTML = d.blocked.length ? `
    <table><thead><tr><th>User</th><th>Reason</th><th>Since</th><th></th></tr></thead>
    <tbody>${d.blocked.map((b) => `<tr><td><code>${b.user_id}</code></td><td>${esc(b.reason)}</td><td>${fmtTime(b.created_at)}</td><td><button class="icon-btn" data-block="${b.user_id}" data-blocked="1">Unblock</button></td></tr>`).join('')}</tbody></table>`
    : '<div class="empty">Nobody is blocked.</div>';
}

window.toggleBlock = async (user_id, currentlyBlocked) => {
  try {
    const fd = new FormData();
    fd.append('user_id', String(user_id));
    if (!currentlyBlocked) fd.append('reason', 'dashboard');
    const res = await fetch(currentlyBlocked ? '/api/unblock' : '/api/block', {
      method: 'POST',
      headers: { 'X-CSRF-Token': CSRF },
      body: fd,
      credentials: 'same-origin',
    });
    if (!res.ok) throw new Error(await res.text());
    toast(currentlyBlocked ? `Unblocked ${user_id}` : `Blocked ${user_id}`);
    loadSection('users'); loadSection('security');
  } catch (e) { toast('Action failed: ' + e.message, true); }
};

/* ---------- boot ---------- */
loadOverview();
setInterval(() => { const a = $('.nav button.active'); if (a) loadSection(a.dataset.sec); }, 30000);
