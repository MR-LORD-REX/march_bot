const state = {
  view: 'overview',
  me: null,
  summary: null,
  reports: [],
  selected: null,
  userPage: 0,
  userTotal: 0,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

function toast(message, isError = false) {
  const node = $('#toast');
  node.textContent = message;
  node.classList.toggle('error', isError);
  node.classList.add('show');
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => node.classList.remove('show'), 3600);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 401) {
    window.location.href = '/admin/login-required';
    throw new Error('session expired');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}

function formatDate(value) {
  if (!value) return 'unknown time';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

function shortUser(user) {
  if (!user) return 'unknown';
  return user.username ? `@${user.username}` : user.display_name || String(user.telegram_id);
}

function setView(view) {
  state.view = view;
  $$('.nav-button').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  ['overview', 'reports', 'users', 'admins'].forEach((name) => {
    $(`#view-${name}`).classList.toggle('hidden', name !== view);
  });
  const titles = {
    overview: ['Overview', 'A quiet look at the bot’s live queues.'],
    reports: ['Reports', 'Read the context, reply, and close the loop.'],
    users: ['Users', 'Everyone the bot has seen.'],
    admins: ['Authority', 'Who can operate the bot.'],
  };
  $('#view-title').textContent = titles[view][0];
  $('#view-subtitle').textContent = titles[view][1];
  if (view === 'reports') loadReports();
  if (view === 'users') loadUsers();
  if (view === 'admins') loadAdmins();
}

function reportRow(report) {
  const id = Number(report.id);
  return `<button class="report-item" data-report-id="${id}" type="button">
    <span class="report-id">#${id}</span>
    <span><span class="report-title">${escapeHtml(report.report_type)} report</span>
      <span class="report-meta">UID ${escapeHtml(report.uid)} · ${escapeHtml(formatDate(report.created_at))}</span></span>
    <span class="chip">${escapeHtml(report.status)}</span>
  </button>`;
}

function wireReportButtons(root) {
  root.querySelectorAll('[data-report-id]').forEach((button) => {
    button.addEventListener('click', () => openReport(Number(button.dataset.reportId)));
  });
}

async function loadSummary() {
  try {
    const summary = await api('/admin/api/summary');
    state.summary = summary;
    state.me = summary.user;
    const authority = summary.user.authority;
    $('#authority-chip').textContent = authority;
    $('#authority-chip').classList.add('good');
    $('#identity').textContent = shortUser(summary.user);
    $('#stat-open').textContent = summary.reports.open;
    $('#stat-total').textContent = summary.reports.total;
    $('#stat-users').textContent = summary.users;
    $('#stat-admins').textContent = summary.admins ?? '—';
    $$('[data-capability]').forEach((button) => {
      button.classList.toggle('hidden', !summary.capabilities[button.dataset.capability]);
    });
    const overview = await api('/admin/api/reports?status=open&limit=5');
    const container = $('#overview-reports');
    container.innerHTML = overview.reports.length
      ? overview.reports.map(reportRow).join('')
      : '<div class="empty">No open reports. The queue is clear.</div>';
    wireReportButtons(container);
    container.querySelectorAll('[data-report-id]').forEach((button) => {
      button.addEventListener('click', () => { setView('reports'); });
    });
  } catch (error) {
    if (error.message !== 'session expired') toast(error.message, true);
  }
}

async function loadReports() {
  const container = $('#report-list');
  try {
    const status = $('#report-filter').value;
    const data = await api(`/admin/api/reports?status=${encodeURIComponent(status)}`);
    state.reports = data.reports;
    container.innerHTML = data.reports.length
      ? data.reports.map(reportRow).join('')
      : `<div class="empty">No ${escapeHtml(status)} reports.</div>`;
    wireReportButtons(container);
  } catch (error) {
    if (error.message !== 'session expired') container.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function openReport(reportId) {
  const detail = $('#report-detail');
  detail.innerHTML = '<div class="empty">Loading report…</div>';
  try {
    const data = await api(`/admin/api/reports/${reportId}`);
    state.selected = data;
    const report = data.report;
    const timeline = data.messages.length
      ? data.messages.map((message) => `<div class="bubble ${message.direction === 'admin' ? 'admin' : ''}">
          <div class="bubble-meta">${escapeHtml(message.direction)} · ${escapeHtml(formatDate(message.created_at))}${message.delivered ? '' : ' · not delivered'}</div>
          <div class="bubble-body">${escapeHtml(message.body)}</div>
        </div>`).join('')
      : '<div class="empty">No messages yet.</div>';
    detail.innerHTML = `<div class="detail stack">
      <div>
        <div class="row row-between">
          <h2>Report #${report.id}</h2><span class="chip">${escapeHtml(report.status)}</span>
        </div>
        <p class="muted">${escapeHtml(report.report_type)} · UID ${escapeHtml(report.uid)} · from ${escapeHtml(shortUser(data.reporter))}</p>
        <p class="muted">Created ${escapeHtml(formatDate(report.created_at))} · origin chat ${escapeHtml(report.origin_chat_id ?? 'unknown')}</p>
      </div>
      <div class="timeline">${timeline}</div>
      <div>
        <label class="card-label" for="reply-body">Reply to reporter</label>
        <textarea id="reply-body" maxlength="4000" placeholder="Write a concise update…"></textarea>
        <div class="row top-gap">
          <button id="send-reply" class="button primary compact" type="button">Send reply</button>
          <button id="resolve-report" class="button danger" type="button">Mark resolved</button>
        </div>
      </div>
    </div>`;
    $('#send-reply').addEventListener('click', sendReply);
    $('#resolve-report').addEventListener('click', resolveReport);
  } catch (error) {
    if (error.message !== 'session expired') detail.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function sendReply() {
  if (!state.selected) return;
  const body = $('#reply-body').value.trim();
  if (!body) return toast('Write a reply first.', true);
  const button = $('#send-reply');
  button.disabled = true;
  try {
    const result = await api(`/admin/api/reports/${state.selected.report.id}/reply`, {
      method: 'POST',
      body: JSON.stringify({ body }),
    });
    toast(result.delivered ? 'Reply delivered to the reporter.' : 'Reply recorded, but delivery failed.', !result.delivered);
    await openReport(state.selected.report.id);
    await loadReports();
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function resolveReport() {
  if (!state.selected) return;
  try {
    await api(`/admin/api/reports/${state.selected.report.id}/resolve`, { method: 'POST', body: '{}' });
    toast('Report marked resolved.');
    await openReport(state.selected.report.id);
    await loadReports();
    await loadSummary();
  } catch (error) {
    toast(error.message, true);
  }
}

async function loadUsers() {
  try {
    const data = await api(`/admin/api/users?page=${state.userPage}&per_page=25`);
    state.userTotal = data.total;
    $('#user-count').textContent = `${data.total} total`;
    const rows = data.users.length
      ? `<table class="table"><thead><tr><th>User</th><th>Telegram ID</th><th>Status</th></tr></thead><tbody>${data.users.map((user) => `<tr><td>${escapeHtml(shortUser(user))}</td><td>${escapeHtml(user.telegram_id)}</td><td>${user.banned ? '<span class="chip danger-chip">banned</span>' : '<span class="chip good">active</span>'}</td></tr>`).join('')}</tbody></table>`
      : '<div class="empty">No users on this page.</div>';
    $('#user-table-wrap').innerHTML = rows;
    $('#users-prev').disabled = state.userPage <= 0;
    $('#users-next').disabled = (state.userPage + 1) * data.per_page >= data.total;
  } catch (error) {
    if (error.message !== 'session expired') $('#user-table-wrap').innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function loadAdmins() {
  try {
    const data = await api('/admin/api/admins');
    const rows = data.admins.length
      ? `<table class="table"><thead><tr><th>Staff</th><th>Telegram ID</th><th>Authority</th></tr></thead><tbody>${data.admins.map((admin) => `<tr><td>${escapeHtml(shortUser(admin))}</td><td>${escapeHtml(admin.telegram_id)}</td><td><select data-admin-id="${admin.telegram_id}">${['basic', 'moderator', 'admin', 'owner'].map((level) => `<option value="${level}" ${level === admin.authority ? 'selected' : ''}>${level}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table>`
      : '<div class="empty">No staff rows yet.</div>';
    $('#admin-table-wrap').innerHTML = rows;
    $$('#admin-table-wrap select').forEach((select) => {
      select.addEventListener('change', () => updateAuthority(select));
    });
  } catch (error) {
    if (error.message !== 'session expired') $('#admin-table-wrap').innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function updateAuthority(select) {
  try {
    await api(`/admin/api/admins/${select.dataset.adminId}/authority`, {
      method: 'POST',
      body: JSON.stringify({ authority: select.value }),
    });
    toast('Authority updated.');
  } catch (error) {
    toast(error.message, true);
    await loadAdmins();
  }
}

$$('.nav-button').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
$('#report-filter').addEventListener('change', loadReports);
$('#users-prev').addEventListener('click', () => { state.userPage = Math.max(0, state.userPage - 1); loadUsers(); });
$('#users-next').addEventListener('click', () => { state.userPage += 1; loadUsers(); });
$('#logout').addEventListener('click', async () => {
  await fetch('/admin/api/logout', { method: 'POST', credentials: 'same-origin' });
  window.location.href = '/admin/login-required?error=signed_out';
});

loadSummary();