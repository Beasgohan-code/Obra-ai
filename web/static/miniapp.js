/* obra Mini App — verifies initData with the backend, then uses signed-token APIs. */
const tg = window.Telegram?.WebApp;
const $ = (s) => document.querySelector(s);
let TOKEN = null;
let AGENT = 'default';
let ME = null;

async function api(path) {
  const r = await fetch(path, { headers: { Authorization: 'Bearer ' + TOKEN } });
  if (r.status === 401) { $('#auth-err').textContent = 'Session expired — reopen the app.'; throw new Error('unauth'); }
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function boot() {
  if (!tg) { $('#auth-err').textContent = 'Open inside Telegram.'; return; }
  tg.ready(); tg.expand();
  const initData = tg.initData || '';
  try {
    const r = await fetch('/api/miniapp/verify', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ initData }),
    });
    const d = await r.json();
    if (!r.ok || !d.ok) throw new Error(d.detail || 'verify failed');
    TOKEN = d.token; ME = d.user;
  } catch (e) {
    $('#auth-err').textContent = 'Verification failed: ' + e.message;
    return;
  }
  $('#who').textContent = 'Hi, ' + (ME.first_name || 'user') + ' 👋';
  await refreshMe();
  await Promise.allSettled([loadMemory(), loadProjects(), loadSkills()]);
}

async function refreshMe() {
  try {
    const d = await api('/api/miniapp/me');
    const plan = $('#plan');
    plan.textContent = d.premium ? '⭐ Premium' : 'Free';
    plan.classList.toggle('prem', d.premium);
    $('#usage').innerHTML =
      `<div class="stat">Today <b>${d.usage.today[0]}</b> / ${d.usage.today[1]}</div><div class="meter"><div style="width:${Math.min(100, (d.usage.today[0] / Math.max(1, d.usage.today[1])) * 100)}%"></div></div>` +
      `<div class="stat">Month <b>${d.usage.month[0]}</b> / ${d.usage.month[1]}</div><div class="meter"><div style="width:${Math.min(100, (d.usage.month[0] / Math.max(1, d.usage.month[1])) * 100)}%"></div></div>` +
      `<div class="stat">Language: <code>${d.language}</code> · TTS: ${d.tts ? 'on' : 'off'} · BYOK: ${d.has_byok ? 'set' : '—'}</div>`;
  } catch (e) { /* token may be missing */ }
}

async function loadMemory() {
  try {
    const d = await api('/api/miniapp/memory');
    const m = d.memory || {};
    const prefs = Object.entries(m.preferences || {}).map(([k, v]) => `<div class="item"><code>${k}</code> = ${v}</div>`).join('');
    $('#memory').innerHTML = `<div class="item">Name: <b>${m.name || '—'}</b></div><div class="item">Notes: ${m.notes || '—'}</div>` + (prefs || '<div class="item" style="color:var(--muted)">No preferences yet — just tell obra in chat.</div>');
  } catch (e) {}
}

async function loadProjects() {
  try {
    const d = await api('/api/miniapp/projects');
    $('#projects').innerHTML = d.projects.length
      ? d.projects.slice(0, 10).map((p) => `<div class="item">📁 <b>${p.title}</b> <code>${p.chat_id}</code></div>`).join('')
      : '<div class="item" style="color:var(--muted)">No projects yet — name a chat with /project.</div>';
  } catch (e) {}
}

async function loadSkills() {
  try {
    const d = await api('/api/miniapp/skills');
    $('#skills').innerHTML = d.skills.length
      ? d.skills.slice(0, 10).map((s) => `<div class="item">⏰ #${s.id} <code>${s.instruction.slice(0, 90)}</code></div>`).join('')
      : '<div class="item" style="color:var(--muted)">No scheduled skills yet.</div>';
  } catch (e) {}
}

/* agent chips */
document.querySelectorAll('.chip[data-agent]').forEach((c) => c.addEventListener('click', () => {
  document.querySelectorAll('.chip[data-agent]').forEach((x) => x.classList.remove('active'));
  c.classList.add('active');
  AGENT = c.dataset.agent;
}));

async function send() {
  const ta = $('#prompt');
  const text = ta.value.trim();
  if (!text || !tg) return;
  const feed = $('#feed');
  const um = document.createElement('div'); um.className = 'msg user'; um.textContent = text; feed.appendChild(um);
  ta.value = '';
  $('#send').disabled = true;
  try {
    tg.sendData(JSON.stringify({ prompt: text, agent: AGENT }));
    const bm = document.createElement('div'); bm.className = 'msg bot';
    bm.textContent = '✅ Sent to your chat with obra — the reply will appear there.';
    feed.appendChild(bm);
  } finally {
    $('#send').disabled = false;
    feed.scrollTop = feed.scrollHeight;
  }
}

$('#send')?.addEventListener('click', send);
$('#prompt')?.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });

boot();
