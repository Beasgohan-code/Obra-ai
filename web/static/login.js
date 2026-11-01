document.querySelector('form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const r = await fetch('/login', { method: 'POST', body: fd });
  if (r.redirected) location.href = r.url;
  else document.getElementById('e').textContent = 'Wrong secret or CSRF error';
});
