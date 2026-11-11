const state = {
  view: 'overview',
  me: null,
  summary: null,
  reports: [],
  selected: null,
  selectedUser: null,
  userPage: 0,
  userTotal: 0,
  broadcasts: [],
  commands: [],
  scopes: [],
  assets: [],
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

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function shortUser(user) {
  if (!user) return 'unknown';
  return user.username ? `@${user.username}` : user.display_name || String(user.telegram_id);
}

function setView(view) {
  state.view = view;
  $$('.nav-button').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  ['overview', 'reports', 'users', 'broadcast', 'commands', 'server', 'admins'].forEach((name) => {
    $(`#view-${name}`).classList.toggle('hidden', name !== view);
  });
  const titles = {
    overview: ['Overview', "A quiet look at the bot's live queues."],
    reports: ['Reports', 'Read the context, reply, and close the loop.'],
    users: ['Users', 'Inspect an account and act within your authority.'],
    broadcast: ['Broadcast', 'Queue an announcement and watch delivery land.'],
    commands: ['Bot options', 'Tune runtime commands and Telegram quick access.'],
    server: ['Server options', 'Bot assets and game-data refreshes.'],
    admins: ['Authority', 'Who can operate the bot.'],
  };
  $('#view-title').textContent = titles[view][0];
  $('#view-subtitle').textContent = titles[view][1];
  if (view === 'reports') loadReports();
  if (view === 'users') loadUsers();
  if (view === 'broadcast') loadBroadcasts();
  if (view === 'commands') loadCommands();
  if (view === 'server') loadAssets();
  if (view === 'admins') loadAdmins();
}

function reportRow(report) {
  const id = Number(report.id);
  return `<button class="report-item" data-report-id="${id}" type="button">
    <span class="report-id">#${id}</span>
    <span><span class="report-title">${escapeHtml(report.report_type)} report</span>
      <span class="report-meta">UID ${escapeHtml(report.uid)} &middot; ${escapeHtml(formatDate(report.created_at))}</span></span>
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
    $('#stat-users').textContent = summary.users;
    $('#stat-groups').textContent = summary.groups ?? '—';
    $('#stat-broadcasts').textContent = summary.broadcasts ?? '—';
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
      button.addEventListener('click', () => setView('reports'));
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
  detail.innerHTML = '<div class="empty">Loading report...</div>';
  try {
    const data = await api(`/admin/api/reports/${reportId}`);
    state.selected = data;
    const report = data.report;
    const timeline = data.messages.length
      ? data.messages.map((message) => `<div class="bubble ${message.direction === 'admin' ? 'admin' : ''}">
          <div class="bubble-meta">${escapeHtml(message.direction)} &middot; ${escapeHtml(formatDate(message.created_at))}${message.delivered ? '' : ' &middot; not delivered'}</div>
          <div class="bubble-body">${escapeHtml(message.body)}</div>
        </div>`).join('')
      : '<div class="empty">No messages yet.</div>';
    detail.innerHTML = `<div class="detail stack">
      <div>
        <div class="row row-between">
          <h2>Report #${report.id}</h2><span class="chip">${escapeHtml(report.status)}</span>
        </div>
        <p class="muted">${escapeHtml(report.report_type)} &middot; UID ${escapeHtml(report.uid)} &middot; from <span data-reporter-name>${escapeHtml(shortUser(data.reporter))}</span></p>
        <p class="muted">Created ${escapeHtml(formatDate(report.created_at))} &middot; origin chat ${escapeHtml(report.origin_chat_id ?? 'unknown')}</p>
      </div>
      <div class="timeline">${timeline}</div>
      <div>
        <label class="card-label" for="reply-body">Reply to reporter</label>
        <textarea id="reply-body" maxlength="4000" placeholder="Write a concise update..."></textarea>
        <div class="row top-gap">
          <button id="send-reply" class="button primary compact" type="button">Send reply</button>
          <button id="resolve-report" class="button danger" type="button">Mark resolved</button>
        </div>
      </div>
    </div>`;
    $('#send-reply').addEventListener('click', sendReply);
    $('#resolve-report').addEventListener('click', resolveReport);
    const reporterName = detail.querySelector('[data-reporter-name]');
    if (state.summary?.capabilities?.reports && reporterName) {
      const link = document.createElement('button');
      link.type = 'button';
      link.className = 'link-button';
      link.textContent = shortUser(data.reporter);
      link.addEventListener('click', () => {
        setView('users');
        openUser(Number(report.reporter_id));
      });
      reporterName.replaceWith(link);
    }
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
      ? `<table class="table"><thead><tr><th>User</th><th>Telegram ID</th><th>Status</th></tr></thead><tbody>${data.users.map((user) => `<tr data-user-row="${user.telegram_id}"><td><button class="link-button" data-user-id="${user.telegram_id}" type="button">${escapeHtml(shortUser(user))}</button></td><td>${escapeHtml(user.telegram_id)}</td><td>${user.banned ? '<span class="chip danger-chip">banned</span>' : '<span class="chip good">active</span>'}</td></tr>`).join('')}</tbody></table>`
      : '<div class="empty">No users on this page.</div>';
    $('#user-table-wrap').innerHTML = rows;
    $('#users-prev').disabled = state.userPage <= 0;
    $('#users-next').disabled = (state.userPage + 1) * data.per_page >= data.total;
    $$('#user-table-wrap [data-user-id]').forEach((button) => {
      button.addEventListener('click', () => openUser(Number(button.dataset.userId)));
    });
  } catch (error) {
    if (error.message !== 'session expired') $('#user-table-wrap').innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function openUser(telegramId) {
  const detail = $('#user-detail');
  detail.innerHTML = '<div class="empty">Loading user...</div>';
  try {
    const data = await api(`/admin/api/users/${telegramId}`);
    state.selectedUser = data;
    const user = data.user;
    const caps = data.capabilities;
    const games = data.game_ids.length
      ? data.game_ids.map((game) => `<div class="item-row"><span>UID ${escapeHtml(game.game_id)} ${game.active ? '<span class="chip good">active</span>' : ''}</span><span class="muted">${game.has_token ? 'cookies linked' : 'no cookies'}</span></div>`).join('')
      : '<div class="empty">No linked game accounts.</div>';
    const groups = data.groups.length
      ? data.groups.map((group) => `<div class="item-row"><span>${escapeHtml(group.group_name || group.group_id)}</span><span class="muted">${escapeHtml(group.group_id)}</span></div>`).join('')
      : '<div class="empty">No known group memberships.</div>';
    const reports = data.reports.length
      ? data.reports.map((report) => `<button class="item-row item-button" data-user-report="${report.id}" type="button"><span>#${report.id} ${escapeHtml(report.report_type)}</span><span class="chip">${escapeHtml(report.status)}</span></button>`).join('')
      : '<div class="empty">No reports from this user.</div>';
    const languageOptions = Object.entries(data.languages || { en: 'English' })
      .map(([code, label]) => `<option value="${escapeHtml(code)}" ${data.settings.lang === code ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('');
    detail.innerHTML = `<div class="detail stack">
      <div class="row row-between">
        <div><h2>${escapeHtml(user.display_name || user.telegram_id)}</h2>
        <p class="muted">${escapeHtml(shortUser(user))} &middot; ID ${escapeHtml(user.telegram_id)}</p></div>
        <span class="chip ${user.banned ? 'danger-chip' : 'good'}">${user.banned ? 'banned' : 'active'}</span>
      </div>
      <div class="stat-grid">
        <div><span class="card-label">Warns</span><strong>${escapeHtml(user.warns)}</strong></div>
        <div><span class="card-label">Accounts</span><strong>${data.game_ids.length}</strong></div>
        <div><span class="card-label">Reports</span><strong>${data.reports.length}</strong></div>
        <div><span class="card-label">Staff</span><strong>${data.staff ? escapeHtml(data.staff.authority) : 'no'}</strong></div>
      </div>
      <div><h3>Preferences</h3><div class="row">
        <label class="field-label" for="user-language">Language</label>
        <select id="user-language">${languageOptions}</select>
        <button id="save-language" class="button compact" type="button" ${caps.set_language ? '' : 'disabled'}>Save</button>
      </div></div>
      <div><h3>Game accounts</h3>${games}</div>
      <div><h3>Groups</h3>${groups}</div>
      <div><h3>Recent reports</h3>${reports}</div>
      <div class="row">
        ${caps.ban ? `<button id="toggle-ban" class="button ${user.banned ? '' : 'danger'}" type="button">${user.banned ? 'Unban user' : 'Ban user'}</button>` : ''}
        ${caps.warn ? '<button id="warn-user" class="button" type="button">Add warn</button>' : ''}
        ${caps.unwarn ? '<button id="unwarn-user" class="button" type="button">Remove warn</button>' : ''}
        ${caps.reset_warns ? '<button id="reset-warns" class="button" type="button">Reset warns</button>' : ''}
      </div>
    </div>`;
    $('#save-language')?.addEventListener('click', () => userAction(telegramId, 'set_language', $('#user-language').value));
    $('#toggle-ban')?.addEventListener('click', () => userAction(telegramId, user.banned ? 'unban' : 'ban'));
    $('#warn-user')?.addEventListener('click', () => userAction(telegramId, 'warn'));
    $('#unwarn-user')?.addEventListener('click', () => userAction(telegramId, 'unwarn'));
    $('#reset-warns')?.addEventListener('click', () => userAction(telegramId, 'reset_warns'));
    detail.querySelectorAll('[data-user-report]').forEach((button) => {
      button.addEventListener('click', () => { setView('reports'); openReport(Number(button.dataset.userReport)); });
    });
  } catch (error) {
    if (error.message !== 'session expired') detail.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function userAction(telegramId, action, value = null) {
  try {
    await api(`/admin/api/users/${telegramId}/action`, {
      method: 'POST',
      body: JSON.stringify({ action, value }),
    });
    toast('User updated.');
    await openUser(telegramId);
    await loadUsers();
  } catch (error) {
    toast(error.message, true);
  }
}

async function loadBroadcasts() {
  try {
    const data = await api('/admin/api/broadcasts');
    state.broadcasts = data.broadcasts;
    const audience = $('#broadcast-audience');
    const previous = audience.value;
    audience.innerHTML = data.audiences.map((item) => `<option value="${escapeHtml(item.value)}" ${previous === item.value ? 'selected' : ''}>${escapeHtml(item.label)} (${item.count})</option>`).join('');
    $('#broadcast-list').innerHTML = data.broadcasts.length
      ? data.broadcasts.map((item) => `<div class="item-row"><span><strong>#${item.id}</strong> ${escapeHtml(item.audience)}<br><span class="muted">${escapeHtml(formatDate(item.created_at))}</span></span><span class="chip ${item.failed_count ? 'danger-chip' : ''}">${escapeHtml(item.status)} &middot; ${item.sent_count}/${item.total_targets}</span></div>`).join('')
      : '<div class="empty">No broadcasts yet.</div>';
  } catch (error) {
    if (error.message !== 'session expired') $('#broadcast-list').innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

function updateBroadcastPreview() {
  const mode = $('#broadcast-mode').value;
  const body = $('#broadcast-body').value;
  const preview = $('#broadcast-preview');
  if (!body.trim()) {
    preview.textContent = 'Preview appears here.';
    return;
  }
  preview.textContent = mode === 'HTML'
    ? body
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(b|strong|i|em|u|s|code|pre|blockquote|tg-spoiler)>/gi, '')
      .replace(/<[^>]*>/g, '')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&')
    : body;
}

async function sendBroadcast() {
  const body = $('#broadcast-body').value.trim();
  if (!body) return toast('Write a message first.', true);
  const button = $('#broadcast-send');
  button.disabled = true;
  try {
    await api('/admin/api/broadcasts', {
      method: 'POST',
      body: JSON.stringify({
        audience: $('#broadcast-audience').value,
        body,
        parse_mode: $('#broadcast-mode').value === 'HTML' ? 'HTML' : null,
      }),
    });
    $('#broadcast-body').value = '';
    updateBroadcastPreview();
    toast('Broadcast queued.');
    await loadBroadcasts();
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function loadCommands() {
  try {
    const data = await api('/admin/api/commands');
    state.commands = data.commands;
    state.scopes = data.scopes;
    $('#command-list').innerHTML = data.commands.length
      ? data.commands.map((item) => `<div class="item-row"><span><strong>/${escapeHtml(item.command)}</strong><br><span class="muted">${escapeHtml(item.label)} &middot; ${escapeHtml(item.scope)}</span></span><label class="switch"><input type="checkbox" data-command="${escapeHtml(item.command)}" ${item.enabled ? 'checked' : ''}><span></span></label></div>`).join('')
      : '<div class="empty">No command metadata yet.</div>';
    $$('#command-list [data-command]').forEach((input) => {
      input.addEventListener('change', () => toggleCommand(input.dataset.command, input.checked));
    });
    $('#scope-list').innerHTML = data.scopes.map((scope) => `<label class="check-row"><input type="checkbox" data-scope="${escapeHtml(scope)}" checked> ${escapeHtml(scope)}</label>`).join('');
  } catch (error) {
    if (error.message !== 'session expired') $('#command-list').innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function toggleCommand(command, enabled) {
  try {
    await api(`/admin/api/commands/${encodeURIComponent(command)}`, {
      method: 'POST',
      body: JSON.stringify({ enabled, reason: enabled ? '' : 'Disabled from the admin panel.' }),
    });
    toast(`/${command} ${enabled ? 'enabled' : 'disabled'}.`);
  } catch (error) {
    toast(error.message, true);
    await loadCommands();
  }
}

async function syncCommands() {
  const scopes = $$('#scope-list [data-scope]:checked').map((input) => input.dataset.scope);
  const button = $('#commands-sync');
  button.disabled = true;
  try {
    const result = await api('/admin/api/commands/sync', {
      method: 'POST',
      body: JSON.stringify({ scopes }),
    });
    $('#sync-status').textContent = `Synchronized: ${result.synced.join(', ') || 'none'}${result.skipped.length ? `; skipped: ${result.skipped.join(', ')}` : ''}`;
    toast('Telegram command menus synchronized.');
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function loadAssets() {
  try {
    const data = await api('/admin/api/assets');
    state.assets = data.assets;
    $('#asset-list').innerHTML = data.assets.length
      ? data.assets.map((asset) => `<div class="item-row"><span><code>${escapeHtml(asset.path)}</code><br><span class="muted">${escapeHtml(formatSize(asset.size))}</span></span><button class="button danger compact" data-asset-delete="${escapeHtml(asset.path)}" type="button">Delete</button></div>`).join('')
      : '<div class="empty">No assets found.</div>';
    $$('#asset-list [data-asset-delete]').forEach((button) => {
      button.addEventListener('click', () => deleteAsset(button.dataset.assetDelete));
    });
  } catch (error) {
    if (error.message !== 'session expired') $('#asset-list').innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function uploadAsset() {
  const path = $('#asset-path').value.trim();
  const file = $('#asset-file').files[0];
  if (!path || !file) return toast('Enter a destination path and choose a file.', true);
  const body = new FormData();
  body.append('file', file);
  try {
    const response = await fetch(`/admin/api/assets/${path}`, {
      method: 'POST',
      credentials: 'same-origin',
      body,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Upload failed');
    toast('Asset uploaded.');
    $('#asset-path').value = '';
    $('#asset-file').value = '';
    await loadAssets();
  } catch (error) {
    toast(error.message, true);
  }
}

async function deleteAsset(path) {
  if (!window.confirm(`Delete ${path}?`)) return;
  try {
    const response = await fetch(`/admin/api/assets/${path}`, {
      method: 'DELETE',
      credentials: 'same-origin',
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Delete failed');
    toast('Asset deleted.');
    await loadAssets();
  } catch (error) {
    toast(error.message, true);
  }
}

async function refreshAssets() {
  const button = $('#assets-refresh');
  button.disabled = true;
  $('#assets-status').textContent = 'Refreshing game assets. This may take a while...';
  try {
    await api('/admin/api/assets/refresh', { method: 'POST', body: '{}' });
    $('#assets-status').textContent = 'Game assets refreshed.';
    toast('Game assets refreshed.');
  } catch (error) {
    $('#assets-status').textContent = error.message;
    toast(error.message, true);
  } finally {
    button.disabled = false;
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
$('#broadcast-body').addEventListener('input', updateBroadcastPreview);
$('#broadcast-mode').addEventListener('change', updateBroadcastPreview);
$('#broadcast-send').addEventListener('click', sendBroadcast);
$('#broadcast-refresh').addEventListener('click', loadBroadcasts);
$('#commands-sync').addEventListener('click', syncCommands);
$('#asset-upload').addEventListener('click', uploadAsset);
$('#assets-refresh').addEventListener('click', refreshAssets);
$('#logout').addEventListener('click', async () => {
  await fetch('/admin/api/logout', { method: 'POST', credentials: 'same-origin' });
  window.location.href = '/admin/login-required?error=signed_out';
});

loadSummary();