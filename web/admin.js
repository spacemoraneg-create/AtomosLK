/**
 * Atomos Administrative Command Console
 * 
 * Secure management portal for database metrics, debater data confirmation,
 * tournament ingestion/deletion, and automated integrity testing.
 */

(function () {
  'use strict';

  const TOKEN_KEY = 'atomos_admin_token';
  const API_BASE = window.location.origin;

  let currentStatusData = null;
  let pendingDeleteTarget = null;
  let pendingEditDatesTarget = null;

  // DOM Elements
  const lockView = document.getElementById('adminLockView');
  const dashboardView = document.getElementById('adminDashboardView');
  const passwordInput = document.getElementById('adminPasswordInput');
  const loginForm = document.getElementById('adminLoginForm');
  const loginBtn = document.getElementById('adminLoginBtn');
  const loginError = document.getElementById('adminLoginError');
  const lockBtn = document.getElementById('adminLockBtn');
  const refreshBtn = document.getElementById('adminRefreshBtn');

  // Helper for Headers
  function getHeaders() {
    const token = getStoredToken() || '';
    const ghToken = localStorage.getItem('atomos_gh_token') || sessionStorage.getItem('atomos_gh_token') || '';
    const headers = {
      'Content-Type': 'application/json',
      'X-Admin-Token': token,
    };
    if (ghToken) {
      headers['X-GitHub-Token'] = ghToken;
    }
    return headers;
  }

  // Safe JSON Parser avoiding Unexpected token '<' crashes on 502/504 HTML
  async function parseFetchResponse(res) {
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      try {
        return await res.json();
      } catch (e) {
        throw new Error('Malformed JSON payload received from server.');
      }
    }
    const text = await res.text();
    if (res.status === 504 || res.status === 502) {
      throw new Error(`Server gateway timeout (HTTP ${res.status}). The operation is running in the background.`);
    }
    const titleMatch = text.match(/<title>(.*?)<\/title>/i);
    const title = titleMatch ? titleMatch[1] : `HTTP ${res.status}`;
    throw new Error(`Server returned non-JSON response (${title}).`);
  }

  // =========================================================================
  // 1. AUTHENTICATION & SESSION MANAGEMENT
  // =========================================================================

  function getStoredToken() {
    return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
  }

  function setStoredToken(token) {
    if (token) {
      sessionStorage.setItem(TOKEN_KEY, token);
      try { localStorage.setItem(TOKEN_KEY, token); } catch (e) {}
    } else {
      sessionStorage.removeItem(TOKEN_KEY);
      try { localStorage.removeItem(TOKEN_KEY); } catch (e) {}
    }
  }

  function syncClientWithServerPat(serverToken, storedOnServer) {
    const cleanServer = (serverToken || '').trim();
    const ghTokenInput = document.getElementById('adminGhTokenInput');
    const statusLabel = document.getElementById('ghTokenServerStatusLabel');

    if (cleanServer) {
      try {
        localStorage.setItem('atomos_gh_token', cleanServer);
        sessionStorage.setItem('atomos_gh_token', cleanServer);
      } catch (e) {}
      if (ghTokenInput && ghTokenInput.value !== cleanServer) {
        ghTokenInput.value = cleanServer;
      }
      if (statusLabel) {
        statusLabel.textContent = 'Active on server & auto-loaded to this device';
        statusLabel.style.color = '#ffffff';
      }
    } else {
      // If server has no token yet, but this browser has one, push it up to the server automatically
      const localTok = (localStorage.getItem('atomos_gh_token') || sessionStorage.getItem('atomos_gh_token') || '').trim();
      if (localTok) {
        if (ghTokenInput && !ghTokenInput.value) ghTokenInput.value = localTok;
        fetch(`${API_BASE}/api/admin/github/token`, {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({ token: localTok }),
        }).catch(() => {});
      } else if (statusLabel && storedOnServer === false) {
        statusLabel.textContent = 'No token stored on server yet';
        statusLabel.style.color = 'rgba(255, 255, 255, 0.72)';
      }
    }
  }

  async function verifySession() {
    const token = getStoredToken();
    if (!token) {
      showLockScreen();
      return false;
    }

    try {
      const res = await fetch(`${API_BASE}/api/admin/verify`, {
        headers: { 'X-Admin-Token': token },
      });
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        if (data && (data.github_token || data.stored_on_server !== undefined)) {
          syncClientWithServerPat(data.github_token, data.stored_on_server);
        }
        showDashboard();
        return true;
      }
    } catch (e) {
      console.warn('Session verification error:', e);
    }

    setStoredToken(null);
    showLockScreen();
    return false;
  }

  function showLockScreen() {
    if (lockView) lockView.classList.remove('hidden');
    if (dashboardView) dashboardView.classList.add('hidden');
    if (passwordInput) {
      passwordInput.value = '';
      passwordInput.focus();
    }
    if (loginError) {
      loginError.classList.add('hidden');
      loginError.textContent = '';
    }
  }

  function showDashboard() {
    if (lockView) lockView.classList.add('hidden');
    if (dashboardView) dashboardView.classList.remove('hidden');
    fetchAdminStatus();
  }

  async function handleLogin() {
    const password = (passwordInput ? passwordInput.value : '').trim();
    if (!password) {
      showLoginError('Please enter the administrative password.');
      return;
    }

    if (loginBtn) {
      loginBtn.disabled = true;
      loginBtn.textContent = 'AUTHENTICATING...';
    }
    if (loginError) loginError.classList.add('hidden');

    try {
      const res = await fetch(`${API_BASE}/api/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });

      const data = await res.json();
      if (res.ok && data.success && data.token) {
        setStoredToken(data.token);
        if (data.github_token || data.stored_on_server !== undefined) {
          syncClientWithServerPat(data.github_token, data.stored_on_server);
        }
        showDashboard();
      } else {
        showLoginError(data.error || 'Invalid administrative password. Access denied.');
        if (passwordInput) {
          passwordInput.select();
          passwordInput.classList.add('input-error-shake');
          setTimeout(() => passwordInput.classList.remove('input-error-shake'), 600);
        }
      }
    } catch (err) {
      showLoginError('Network or server connection failure during authentication.');
    } finally {
      if (loginBtn) {
        loginBtn.disabled = false;
        loginBtn.textContent = 'AUTHENTICATE & UNLOCK CONSOLE';
      }
    }
  }

  function showLoginError(msg) {
    if (!loginError) return;
    loginError.textContent = msg;
    loginError.classList.remove('hidden');
  }

  function handleLogout() {
    setStoredToken(null);
    showLockScreen();
  }

  // Check 401 response and drop to lock
  function handleUnauthorized() {
    setStoredToken(null);
    showLockScreen();
    showLoginError('Administrative session expired. Please re-authenticate.');
  }

  // =========================================================================
  // 2. TAB NAVIGATION
  // =========================================================================

  function initTabs() {
    const tabBtns = document.querySelectorAll('.admin-tab-btn');
    tabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const targetPaneId = btn.getAttribute('data-tab');
        tabBtns.forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');

        document.querySelectorAll('.admin-tab-pane').forEach((pane) => {
          pane.classList.remove('active');
        });

        const activePane = document.getElementById(targetPaneId);
        if (activePane) activePane.classList.add('active');
      });
    });
  }

  // =========================================================================
  // 3. TAB 1: SYSTEM & DATABASE STATUS
  // =========================================================================

  function clearClientExportCaches() {
    try {
      const keysToRemove = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        if (k && (k.startsWith('atomos_cache_') || k === 'atomos_manifest_version')) {
          keysToRemove.push(k);
        }
      }
      keysToRemove.forEach((k) => sessionStorage.removeItem(k));
    } catch (e) {}
  }

  async function fetchAdminStatus() {
    clearClientExportCaches();
    try {
      const res = await fetch(`${API_BASE}/api/admin/status`, {
        headers: getHeaders(),
      });
      if (res.status === 401) {
        handleUnauthorized();
        return;
      }
      if (!res.ok) throw new Error('Status query failed');

      const data = await res.json();
      currentStatusData = data;
      if (data.github_token || data.stored_on_server !== undefined) {
        syncClientWithServerPat(data.github_token, data.stored_on_server);
      }
      renderDatabaseVitals(data.database);
      renderTournamentsTable(data.tournaments);
      renderOpsQuickTournaments(data.tournaments);
      updateTournamentDropdown(data.tournaments);
      fetchGitHubSyncStatus();
    } catch (e) {
      console.error('Failed to load admin status:', e);
    }
  }

  function renderOpsQuickTournaments(tournaments) {
    const container = document.getElementById('opsTournamentsQuickList');
    if (!container) return;

    if (!tournaments || tournaments.length === 0) {
      container.innerHTML = `<div style="text-align: center; padding: 24px; color: rgba(255, 255, 255, 0.78);">No tournaments ingested in database.</div>`;
      return;
    }

    container.innerHTML = tournaments
      .map((t) => {
        return `
          <div class="ops-tour-card">
            <div class="ops-tour-main">
              <div class="ops-tour-title-row">
                <span class="ops-tour-order monospace">#${t.chrono_order ?? t.id}</span>
                <span class="ops-tour-name">${escapeHtml(t.official_name || t.name)}</span>
                <span class="badge-count monospace" style="font-size: 10px;">${escapeHtml(t.slug)}</span>
              </div>
              <div class="ops-tour-meta monospace">
                <span>${t.hosting_dates ? escapeHtml(t.hosting_dates) : '2026'}</span>
                <span>&bull;</span>
                <span>${t.debate_count ?? 0} debates</span>
                <span>&bull;</span>
                <span>${t.team_count ?? 0} teams</span>
                <span>&bull;</span>
                <span>${t.speech_count ?? 0} speeches</span>
              </div>
            </div>
            <div class="ops-tour-actions">
              <button
                class="admin-btn admin-btn-secondary admin-btn-sm btn-ops-edit-dates"
                data-id="${t.id}"
                data-slug="${escapeHtml(t.slug)}"
                data-name="${escapeHtml(t.official_name || t.name)}"
                data-dates="${escapeHtml(t.hosting_dates || '')}"
              >
                EDIT DATES
              </button>
              <button
                class="admin-btn admin-btn-danger admin-btn-sm btn-ops-delete"
                data-id="${t.id}"
                data-slug="${escapeHtml(t.slug)}"
                data-name="${escapeHtml(t.official_name || t.name)}"
              >
                DELETE
              </button>
            </div>
          </div>
        `;
      })
      .join('');

    container.querySelectorAll('.btn-ops-edit-dates').forEach((btn) => {
      btn.addEventListener('click', () => {
        openEditDatesModal(
          btn.getAttribute('data-id'),
          btn.getAttribute('data-slug'),
          btn.getAttribute('data-name'),
          btn.getAttribute('data-dates')
        );
      });
    });

    container.querySelectorAll('.btn-ops-delete').forEach((btn) => {
      btn.addEventListener('click', () => {
        openDeleteConfirmation(
          btn.getAttribute('data-id'),
          btn.getAttribute('data-slug'),
          btn.getAttribute('data-name')
        );
      });
    });
  }

  function renderDatabaseVitals(db) {
    if (!db) return;

    // KPI Tiles
    setText('kpiTournaments', db.tournaments_count ?? '--');
    const kpiDebatesEl = document.getElementById('kpiDebates');
    if (kpiDebatesEl) {
      kpiDebatesEl.innerHTML = `${db.contested_debates ?? '--'} <span style="font-size: 14px; opacity: 0.6; font-family: var(--font-mono);">/ ${db.debates_count ?? '--'}</span>`;
    }
    setText('kpiDebaters', db.persons_count ?? '--');
    setText('kpiBallots', db.ballots_count ?? '--');
    setText('kpiSpeeches', db.speeches_count ?? '--');
    setText('kpiFallback', db.fallback_ballots ?? '0');
    setText('kpiIntegrity', (db.integrity_check || 'ok').toUpperCase());
    setText('kpiDbSize', `${db.file_size_mb ?? '--'} MB`);

    // Infrastructure List
    setText('dbFilePath', db.file_path || '--');
    setText('dbLastModified', db.last_modified || '--');
    setText('dbDebatesBreakdown', `${db.contested_debates ?? 0} Contested | ${db.walkover_debates ?? 0} Walkovers`);
    setText('dbTeamsInstitutions', `${db.teams_count ?? 0} Teams | ${db.institutions_count ?? 0} Institutions`);
    setText('dbNationalPool', `${db.national_pool_count ?? 0} Debaters with Active National Pool Designation`);
    setText('dbPragmaCheck', `PRAGMA integrity_check: ${db.integrity_check || 'ok'}`);
  }

  function renderTournamentsTable(tournaments) {
    const tbody = document.getElementById('adminTournamentsTableBody');
    if (!tbody) return;

    if (!tournaments || tournaments.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 24px; color: rgba(255, 255, 255, 0.78);">No tournaments ingested in database.</td></tr>`;
      return;
    }

    tbody.innerHTML = tournaments
      .map((t) => {
        return `
          <tr>
            <td class="monospace" style="color: #ffffff; font-weight: 700;">#${t.chrono_order ?? t.id}</td>
            <td class="monospace">${escapeHtml(t.slug)}</td>
            <td style="font-weight: 500;">
              <div>${escapeHtml(t.official_name || t.name)}</div>
              <div style="font-size: 11px; color: #ffffff; font-family: var(--font-mono); margin-top: 2px;">
                ${t.hosting_dates ? escapeHtml(t.hosting_dates) : '2026'} · ${t.source_url ? escapeHtml(t.source_url) : 'Local Tab Archive'}
              </div>
            </td>
            <td class="monospace">${t.year || '--'}</td>
            <td class="monospace" style="font-weight: 600;">${t.debate_count ?? 0}</td>
            <td class="monospace">${t.round_count ?? 0}</td>
            <td class="monospace">${t.team_count ?? 0}</td>
            <td class="monospace">${t.speech_count ?? 0}</td>
            <td style="text-align: center; white-space: nowrap;">
              <button
                class="admin-btn admin-btn-secondary admin-btn-sm btn-edit-dates-row"
                data-id="${t.id}"
                data-slug="${escapeHtml(t.slug)}"
                data-name="${escapeHtml(t.official_name || t.name)}"
                data-dates="${escapeHtml(t.hosting_dates || '')}"
                style="margin-right: 6px;"
                title="Edit tournament hosting dates"
              >
                EDIT DATES
              </button>
              <button
                class="admin-btn admin-btn-danger admin-btn-sm btn-delete-row"
                data-id="${t.id}"
                data-slug="${escapeHtml(t.slug)}"
                data-name="${escapeHtml(t.name)}"
                title="Purge tournament from database"
              >
                DELETE
              </button>
            </td>
          </tr>
        `;
      })
      .join('');

    // Attach row handlers
    tbody.querySelectorAll('.btn-edit-dates-row').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-id');
        const slug = btn.getAttribute('data-slug');
        const name = btn.getAttribute('data-name');
        const dates = btn.getAttribute('data-dates');
        openEditDatesModal(id, slug, name, dates);
      });
    });

    tbody.querySelectorAll('.btn-delete-row').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-id');
        const slug = btn.getAttribute('data-slug');
        const name = btn.getAttribute('data-name');
        openDeleteConfirmation(id, slug, name);
      });
    });
  }

  function openEditDatesModal(id, slug, name, currentDates) {
    pendingEditDatesTarget = { id, slug, name, currentDates };
    const modal = document.getElementById('adminEditDatesModal');
    const nameEl = document.getElementById('editDatesTournamentName');
    const inputEl = document.getElementById('editTournamentDatesInput');
    const statusBox = document.getElementById('editDatesStatusBox');

    if (nameEl) nameEl.textContent = `${name} (${slug})`;
    if (inputEl) {
      inputEl.value = currentDates || '';
      inputEl.focus();
    }
    if (statusBox) {
      statusBox.classList.add('hidden');
      statusBox.textContent = '';
    }
    if (modal) modal.classList.remove('hidden');
  }

  function updateTournamentDropdown(tournaments) {
    const select = document.getElementById('deleteTournamentSelect');
    if (!select) return;

    select.innerHTML = '<option value="">-- Choose Tournament to Purge --</option>';
    if (tournaments) {
      tournaments.forEach((t) => {
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = `[ID: ${t.id}] ${t.name} (${t.slug}) - ${t.debate_count} debates`;
        opt.dataset.slug = t.slug;
        opt.dataset.name = t.name;
        select.appendChild(opt);
      });
    }
  }

  // =========================================================================
  // 3.1 DATA PERSISTENCE & GITHUB REPOSITORY SYNC
  // =========================================================================

  function downloadDatabase() {
    const token = getStoredToken();
    if (!token) return;
    const a = document.createElement('a');
    a.href = `${API_BASE}/api/admin/database/download?token=${encodeURIComponent(token)}`;
    a.download = 'atomos.db';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function downloadWebExport() {
    const token = getStoredToken();
    if (!token) return;
    const a = document.createElement('a');
    a.href = `${API_BASE}/api/admin/export/download?token=${encodeURIComponent(token)}`;
    a.download = 'atomos_web_export.zip';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  async function fetchGitHubSyncStatus() {
    const badge = document.getElementById('githubSyncBadge');
    try {
      const res = await fetch(`${API_BASE}/api/admin/github/status`, {
        headers: getHeaders(),
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.github_token || data.stored_on_server !== undefined) {
        syncClientWithServerPat(data.github_token, data.stored_on_server);
      }
      if (!badge) return;
      if (data.configured) {
        const shaSuffix = data.head_sha ? ` @ ${data.head_sha}` : '';
        const st = data.sync_state || {};
        if (st.in_progress) {
          badge.textContent = `SYNCING: ${data.repo} (${data.branch})...`;
        } else {
          badge.textContent = `SYNC READY: ${data.repo} (${data.branch}${shaSuffix})`;
        }
        badge.style.color = '#ffffff';
        badge.style.background = 'rgba(255, 255, 255, 0.12)';
      } else {
        badge.textContent = 'GITHUB TOKEN NOT CONFIGURED';
        badge.style.color = 'rgba(255, 255, 255, 0.88)';
        badge.style.background = 'rgba(255, 255, 255, 0.12)';
      }
    } catch (e) {
      if (badge) {
        badge.textContent = 'GITHUB STATUS UNKNOWN';
      }
    }
  }

  async function triggerGitHubSync() {
    const statusBox = document.getElementById('githubSyncStatusBox');
    const syncBtns = [
      document.getElementById('adminSyncGithubBtn'),
      document.getElementById('paneSyncGithubBtn'),
    ].filter(Boolean);

    let customToken = localStorage.getItem('atomos_gh_token') || sessionStorage.getItem('atomos_gh_token') || '';
    try {
      const checkRes = await fetch(`${API_BASE}/api/admin/github/status`, {
        headers: getHeaders(),
      });
      if (checkRes.ok) {
        const checkData = await checkRes.json();
        if (checkData.github_token) {
          customToken = checkData.github_token;
          syncClientWithServerPat(checkData.github_token, checkData.stored_on_server);
        }
        if (!checkData.configured && !customToken) {
          const entered = window.prompt(
            'GitHub Personal Access Token is required to commit directly to GitHub repository.\n\nEnter GitHub Personal Access Token (Fine-grained Contents: Read/Write, or Classic repo scope):'
          );
          if (!entered || !entered.trim()) {
            if (statusBox) {
              showStatusBox(statusBox, 'error', 'GitHub sync cancelled: token was not provided.');
            }
            return;
          }
          customToken = entered.trim();
          localStorage.setItem('atomos_gh_token', customToken);
          sessionStorage.setItem('atomos_gh_token', customToken);
          const ghInput = document.getElementById('adminGhTokenInput');
          if (ghInput) ghInput.value = customToken;
        }
      }
    } catch (e) {
      // Proceed to try sync
    }

    syncBtns.forEach((b) => {
      b.disabled = true;
      b.textContent = 'SYNCING...';
    });

    if (statusBox) {
      showStatusBox(statusBox, 'loading', 'Re-exporting all web datasets and pushing atomos.db + web_export files to GitHub...');
    }

    try {
      const payload = {};
      if (customToken) {
        payload.github_token = customToken;
      }
      const res = await fetch(`${API_BASE}/api/admin/github/sync`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      clearClientExportCaches();
      if (res.ok && data.success) {
        const filesCount = data.synced_files ? data.synced_files.length : 'all';
        const shaInfo = data.commit_sha ? ` [commit ${String(data.commit_sha).slice(0, 7)}]` : '';
        if (statusBox) {
          showStatusBox(statusBox, 'success', `[SUCCESS] ${data.message || `Synchronized ${filesCount} file(s) to GitHub repository (${data.repo} @ ${data.branch})`}${shaInfo}.`);
        }
        fetchGitHubSyncStatus();
      } else {
        if (statusBox) {
          showStatusBox(statusBox, 'error', `[SYNC ERROR] ${data.error || 'Failed to synchronize with GitHub'}`);
        }
      }
    } catch (e) {
      if (statusBox) {
        showStatusBox(statusBox, 'error', `[NETWORK ERROR] ${e.message}`);
      }
    } finally {
      syncBtns.forEach((b) => {
        b.disabled = false;
      });
      const adminBtn = document.getElementById('adminSyncGithubBtn');
      if (adminBtn) adminBtn.textContent = 'SYNC TO GITHUB';
      const paneBtn = document.getElementById('paneSyncGithubBtn');
      if (paneBtn) paneBtn.textContent = 'PUSH DATABASE TO GITHUB';
    }
  }

  function initDataPersistence() {
    const adminDbBtn = document.getElementById('adminDownloadDbBtn');
    const paneDbBtn = document.getElementById('paneDownloadDbBtn');
    const adminExportBtn = document.getElementById('adminDownloadExportBtn');
    const paneExportBtn = document.getElementById('paneDownloadExportBtn');
    const adminSyncBtn = document.getElementById('adminSyncGithubBtn');
    const paneSyncBtn = document.getElementById('paneSyncGithubBtn');

    if (adminDbBtn) adminDbBtn.addEventListener('click', downloadDatabase);
    if (paneDbBtn) paneDbBtn.addEventListener('click', downloadDatabase);
    if (adminExportBtn) adminExportBtn.addEventListener('click', downloadWebExport);
    if (paneExportBtn) paneExportBtn.addEventListener('click', downloadWebExport);
    if (adminSyncBtn) adminSyncBtn.addEventListener('click', triggerGitHubSync);
    if (paneSyncBtn) paneSyncBtn.addEventListener('click', triggerGitHubSync);

    // GitHub PAT configuration input
    const ghTokenInput = document.getElementById('adminGhTokenInput');
    const toggleGhTokenVisBtn = document.getElementById('toggleGhTokenVisBtn');
    const saveGhTokenBtn = document.getElementById('saveGhTokenBtn');
    const clearGhTokenBtn = document.getElementById('clearGhTokenBtn');
    const statusBox = document.getElementById('githubSyncStatusBox');
    const statusLabel = document.getElementById('ghTokenServerStatusLabel');

    const existingToken = localStorage.getItem('atomos_gh_token') || sessionStorage.getItem('atomos_gh_token') || '';
    if (ghTokenInput && existingToken) {
      ghTokenInput.value = existingToken;
    }

    if (toggleGhTokenVisBtn && ghTokenInput) {
      toggleGhTokenVisBtn.addEventListener('click', () => {
        if (ghTokenInput.type === 'password') {
          ghTokenInput.type = 'text';
          toggleGhTokenVisBtn.textContent = 'Hide';
        } else {
          ghTokenInput.type = 'password';
          toggleGhTokenVisBtn.textContent = 'Show';
        }
      });
    }

    if (saveGhTokenBtn) {
      saveGhTokenBtn.addEventListener('click', async () => {
        const val = (ghTokenInput ? ghTokenInput.value : '').trim();
        if (!val) {
          if (statusBox) showStatusBox(statusBox, 'error', 'Please provide a valid GitHub token before saving.');
          return;
        }
        localStorage.setItem('atomos_gh_token', val);
        sessionStorage.setItem('atomos_gh_token', val);
        try {
          const res = await fetch(`${API_BASE}/api/admin/github/token`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ token: val }),
          });
          if (res.ok) {
            const data = await res.json();
            syncClientWithServerPat(data.github_token || val, true);
          }
        } catch (e) {}
        if (statusBox) {
          showStatusBox(
            statusBox,
            'success',
            'GitHub Personal Access Token saved to server database. Any device that unlocks Admin will now automatically receive this token.'
          );
        }
        fetchGitHubSyncStatus();
      });
    }

    if (clearGhTokenBtn) {
      clearGhTokenBtn.addEventListener('click', async () => {
        localStorage.removeItem('atomos_gh_token');
        sessionStorage.removeItem('atomos_gh_token');
        if (ghTokenInput) ghTokenInput.value = '';
        if (statusLabel) {
          statusLabel.textContent = 'Cleared from server & browser';
          statusLabel.style.color = 'rgba(255, 255, 255, 0.72)';
        }
        try {
          await fetch(`${API_BASE}/api/admin/github/token`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ token: '' }),
          });
        } catch (e) {}
        if (statusBox) showStatusBox(statusBox, 'success', 'GitHub Personal Access Token cleared from server and browser.');
        fetchGitHubSyncStatus();
      });
    }
  }

  // =========================================================================
  // 4. TAB 2: DATA CONFIRMATION // BIO ENGINE AUDIT
  // =========================================================================

  let debaterSearchTimeout = null;
  let debaterSearchController = null;

  function initBioAudit() {
    const input = document.getElementById('adminBioSearchInput');
    const clearBtn = document.getElementById('adminBioClearBtn');
    const suggestions = document.getElementById('adminBioSuggestions');

    if (input) {
      input.addEventListener('input', () => {
        const q = input.value.trim();
        if (clearBtn) clearBtn.classList.toggle('hidden', !q);
        clearTimeout(debaterSearchTimeout);
        debaterSearchTimeout = setTimeout(() => searchDebaters(q), 120);
      });

      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const q = input.value.trim();
          if (q) loadDebaterAudit(q);
        }
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (input) input.value = '';
        clearBtn.classList.add('hidden');
        if (suggestions) suggestions.classList.add('hidden');
      });
    }

    // Quick Audit Chips
    document.querySelectorAll('.admin-chip-btn').forEach((chip) => {
      chip.addEventListener('click', () => {
        const name = chip.getAttribute('data-name');
        if (input) input.value = name;
        if (clearBtn) clearBtn.classList.remove('hidden');
        if (suggestions) suggestions.classList.add('hidden');
        loadDebaterAudit(name);
      });
    });
  }

  async function searchDebaters(query) {
    const suggestions = document.getElementById('adminBioSuggestions');
    if (!suggestions) return;

    if (!query) {
      suggestions.classList.add('hidden');
      suggestions.innerHTML = '';
      return;
    }

    if (debaterSearchController) {
      debaterSearchController.abort();
    }
    debaterSearchController = new AbortController();

    try {
      const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(query)}&type=debater&limit=8`, {
        signal: debaterSearchController.signal
      });
      if (!res.ok) return;
      const data = await res.json();
      const results = data.results || [];

      if (results.length === 0) {
        suggestions.innerHTML = '<div style="padding: 12px; color: rgba(255, 255, 255, 0.78); font-size: 13px; text-align: center;">No matching debaters found in database.</div>';
        suggestions.classList.remove('hidden');
        return;
      }

      suggestions.innerHTML = results
        .map((r) => {
          return `
            <div class="bio-autocomplete-item" data-name="${escapeHtml(r.canonical_name || r.name)}">
              <div class="bio-ac-name">${escapeHtml(r.canonical_name || r.name)}</div>
              <div class="bio-ac-inst">${escapeHtml(r.institution || 'Independent')} ${r.national_level ? `&bull; <span style="color: #ffffff;">${escapeHtml(r.national_level)}</span>` : ''}</div>
            </div>
          `;
        })
        .join('');

      suggestions.querySelectorAll('.bio-autocomplete-item').forEach((item) => {
        item.addEventListener('click', () => {
          const name = item.getAttribute('data-name');
          const input = document.getElementById('adminBioSearchInput');
          if (input) input.value = name;
          suggestions.classList.add('hidden');
          loadDebaterAudit(name);
        });
      });

      suggestions.classList.remove('hidden');
    } catch (e) {
      console.warn('Debater search failure:', e);
    }
  }

  async function loadDebaterAudit(name) {
    const container = document.getElementById('adminBioProfileContainer');
    const suggestions = document.getElementById('adminBioSuggestions');
    if (suggestions) suggestions.classList.add('hidden');
    if (!container) return;

    container.innerHTML = `
      <div style="text-align: center; padding: 40px; color: #ffffff; font-family: var(--font-mono);">
        Loading career profile and ballot breakdown for ${escapeHtml(name)}...
      </div>
    `;

    try {
      const res = await fetch(`${API_BASE}/api/debaters/${encodeURIComponent(name)}?compact=false`);
      if (!res.ok) {
        container.innerHTML = `
          <div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.85); font-family: var(--font-mono);">
            Debater '${escapeHtml(name)}' not found in database.
          </div>
        `;
        return;
      }

      const p = await res.json();
      renderDebaterAuditDossier(p);
    } catch (err) {
      container.innerHTML = `
        <div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.85); font-family: var(--font-mono);">
          Error connecting to API server: ${escapeHtml(err.message)}
        </div>
      `;
    }
  }

  function renderDebaterAuditDossier(p) {
    const container = document.getElementById('adminBioProfileContainer');
    if (!container) return;

    const pos = p.positions_breakdown || {
      '1st': { count: 0, avg: null },
      '2nd': { count: 0, avg: null },
      '3rd': { count: 0, avg: null },
      'Reply': { count: 0, avg: null },
      'total_substantive': 0,
      'total_speeches': 0,
    };

    const natBadge = p.national_level
      ? `<span class="badge-count" style="background: rgba(255, 255, 255, 0.12); color: #ffffff; margin-left: 8px;">${escapeHtml(p.national_level)}</span>`
      : '';

    const tournaments = p.tournaments || [];

    container.innerHTML = `
      <div class="admin-dossier-card">
        
        <!-- Header -->
        <div class="admin-dossier-header">
          <div>
            <div class="admin-dossier-name">
              ${escapeHtml(p.canonical_name)}
              ${natBadge}
            </div>
            <div class="admin-dossier-meta">
              <span>Institution: <strong>${escapeHtml(p.institution || 'Independent')}</strong></span>
              ${p.teams_debated && p.teams_debated.length > 0 ? `<span>Teams: ${escapeHtml(p.teams_debated.join(', '))}</span>` : ''}
              <span>ID: #${p.person_id}</span>
            </div>
          </div>
          <div style="text-align: right;">
            <span class="badge-count" style="background: rgba(255, 255, 255, 0.12); color: #ffffff; font-weight: 700;">
              BALLOT VERIFIED: ZERO SYNTHETICS
            </span>
          </div>
        </div>

        <!-- 8 Core Metrics Grid -->
        <div class="bio-stats-grid" style="margin-bottom: 24px;">
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #ffffff;">${(p.tab_rank || p.master_tab_rank) ? '#' + (p.tab_rank || p.master_tab_rank) : 'UR'}</div>
            <div class="bio-stat-lbl">Official Tab Rank</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${p.speech_average ? p.speech_average.toFixed(2) : (p.overall_substantive_avg ? p.overall_substantive_avg.toFixed(2) : '--')}</div>
            <div class="bio-stat-lbl">Cumulative Speech Avg</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${p.avg_of_avgs ? p.avg_of_avgs.toFixed(2) : '--'}</div>
            <div class="bio-stat-lbl">Average of Averages</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${p.win_rate !== undefined ? p.win_rate.toFixed(1) + '%' : '--'}</div>
            <div class="bio-stat-lbl">Career Win Rate</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${p.prelim_rounds_debated ?? 0}</div>
            <div class="bio-stat-lbl">Prelim Debates</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${p.total_debates ?? 0}</div>
            <div class="bio-stat-lbl">Total Debates (All Rounds)</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${p.break_rate !== undefined ? p.break_rate.toFixed(1) + '%' : '--'}</div>
            <div class="bio-stat-lbl">Break Rate</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #ffffff;">${pos.total_speeches ?? (p.total_speeches ?? '--')}</div>
            <div class="bio-stat-lbl">Total Speech Records</div>
          </div>
        </div>

        <!-- EXACT SPEAKER POSITION BREAKDOWN AUDIT -->
        <div class="admin-box" style="margin-bottom: 24px; background: rgba(18, 32, 92, 0.45);">
          <div class="admin-box-title" style="display: flex; justify-content: space-between; align-items: center;">
            <span>SPEAKER POSITION BREAKDOWN AUDIT</span>
            <span style="font-size: 11px; color: rgba(255, 255, 255, 0.78); font-weight: 400; text-transform: none;">
              Counted strictly from official tournament scoresheets
            </span>
          </div>

          <div class="admin-positions-grid">
            <div class="admin-pos-tile">
              <div class="admin-pos-badge" style="background: rgba(255, 255, 255, 0.12); color: #ffffff;">1st SPEECH</div>
              <div class="admin-pos-count">${pos['1st']?.count ?? 0}</div>
              <div class="admin-pos-sub">Avg: ${pos['1st']?.avg !== null && pos['1st']?.avg !== undefined ? pos['1st'].avg.toFixed(2) : '--'} pts</div>
            </div>
            <div class="admin-pos-tile">
              <div class="admin-pos-badge" style="background: rgba(255, 255, 255, 0.14); color: #ffffff;">2nd SPEECH</div>
              <div class="admin-pos-count">${pos['2nd']?.count ?? 0}</div>
              <div class="admin-pos-sub">Avg: ${pos['2nd']?.avg !== null && pos['2nd']?.avg !== undefined ? pos['2nd'].avg.toFixed(2) : '--'} pts</div>
            </div>
            <div class="admin-pos-tile">
              <div class="admin-pos-badge" style="background: rgba(255, 255, 255, 0.14); color: rgba(255, 255, 255, 0.88);">3rd SPEECH</div>
              <div class="admin-pos-count">${pos['3rd']?.count ?? 0}</div>
              <div class="admin-pos-sub">Avg: ${pos['3rd']?.avg !== null && pos['3rd']?.avg !== undefined ? pos['3rd'].avg.toFixed(2) : '--'} pts</div>
            </div>
            <div class="admin-pos-tile">
              <div class="admin-pos-badge" style="background: rgba(255, 255, 255, 0.14); color: #ffffff; border: 1px solid rgba(255, 255, 255, 0.25);">REPLY SPEECH</div>
              <div class="admin-pos-count">${pos['Reply']?.count ?? 0}</div>
              <div class="admin-pos-sub">Avg: ${pos['Reply']?.avg !== null && pos['Reply']?.avg !== undefined ? pos['Reply'].avg.toFixed(2) : '--'} pts</div>
            </div>
          </div>
        </div>

        <!-- TOURNAMENT TRAJECTORY & PERFORMANCE BREAKDOWN -->
        <div class="bio-section-heading">CHRONOLOGICAL TOURNAMENT TRAJECTORY (${tournaments.length} TOURNAMENTS)</div>
        <div class="table-responsive">
          <table class="leaderboard-table">
            <thead>
              <tr>
                <th style="width: 240px;">TOURNAMENT</th>
                <th style="width: 140px;">TEAM</th>
                <th style="width: 90px;">STATUS</th>
                <th>PRELIM SCORES</th>
                <th style="width: 85px;">AVG</th>
                <th style="width: 130px;">STAGE REACHED</th>
              </tr>
            </thead>
            <tbody>
              ${tournaments.length === 0 ? '<tr><td colspan="6" style="text-align: center; padding: 18px; color: rgba(255, 255, 255, 0.78);">No tournament entries recorded.</td></tr>' : ''}
              ${tournaments
                .map((t) => {
                  const qualBadge = t.is_eligible
                    ? '<span class="nat-tag nat-direct" style="font-size: 10px;">QUALIFIED</span>'
                    : '<span class="nat-tag" style="background: rgba(255, 255, 255, 0.12); color: #ffffff; border: 1px solid rgba(255, 255, 255, 0.25); font-size: 10px;">INELIGIBLE</span>';
                  const scoresList = (t.prelim_substantive_scores || []).map((s) => s.toFixed(1)).join(', ') || 'None';

                  return `
                    <tr>
                      <td style="font-weight: 500;">
                        ${escapeHtml(t.tournament_name)}
                      </td>
                      <td class="monospace">${escapeHtml(t.team_name || '--')}</td>
                      <td>${qualBadge}</td>
                      <td class="monospace" style="font-size: 12px; color: #ffffff;">${scoresList}</td>
                      <td class="monospace" style="font-weight: 600; color: #ffffff;">
                        ${t.tournament_average !== null && t.tournament_average !== undefined ? t.tournament_average.toFixed(2) : '--'}
                      </td>
                      <td style="font-size: 12px; color: #ffffff; font-weight: 600;">${escapeHtml(t.highest_stage || '--')}</td>
                    </tr>
                  `;
                })
                .join('')}
            </tbody>
          </table>
        </div>

      </div>
    `;
  }

  // =========================================================================
  // 5. TAB 3: TOURNAMENT OPERATIONS (IMPORT / DELETE)
  // =========================================================================

  function initTournamentOperations() {
    // Ingestion
    const startImportBtn = document.getElementById('startImportBtn');
    const importTargetInput = document.getElementById('importTargetInput');
    const importDatesInput = document.getElementById('importDatesInput');
    const skipExtractCheck = document.getElementById('skipExtractCheck');
    const importStatusBox = document.getElementById('importStatusBox');

    if (startImportBtn) {
      startImportBtn.addEventListener('click', async () => {
        const target = (importTargetInput ? importTargetInput.value : '').trim();
        const hostingDates = (importDatesInput ? importDatesInput.value : '').trim();
        const skipExtract = skipExtractCheck ? skipExtractCheck.checked : false;

        if (!target) {
          showStatusBox(importStatusBox, 'error', 'Please provide a valid Tabbycat URL or local raw slug.');
          return;
        }

        startImportBtn.disabled = true;
        startImportBtn.textContent = 'RUNNING INGESTION PIPELINE...';
        showStatusBox(
          importStatusBox,
          'loading',
          `[PIPELINE ACTIVE] Initializing ingestion pipeline for '${target}'...`
        );

        let pollInterval = null;
        let idleTicks = 0;

        const pollStatus = async () => {
          try {
            const statusRes = await fetch(`${API_BASE}/api/admin/tournaments/import/status`, {
              headers: getHeaders(),
            });
            if (statusRes.status === 401) {
              clearInterval(pollInterval);
              handleUnauthorized();
              return;
            }
            const job = await parseFetchResponse(statusRes);
            if (job.status === 'running') {
              idleTicks = 0;
              showStatusBox(
                importStatusBox,
                'loading',
                `[PIPELINE ACTIVE] ${job.message || 'Processing tournament data...'}`
              );
            } else if (job.status === 'success') {
              clearInterval(pollInterval);
              const am = (job.data && job.data.auto_merge) || {};
              const amSuffix = am.total_merged ? ` Auto-merged ${am.total_merged} duplicate identities.` : '';
              showStatusBox(importStatusBox, 'success', `[SUCCESS] ${job.message}${amSuffix}`);
              if (importTargetInput) importTargetInput.value = '';
              if (importDatesInput) importDatesInput.value = '';
              startImportBtn.disabled = false;
              startImportBtn.textContent = 'START INGESTION PIPELINE';
              fetchAdminStatus();
              fetchMergeSuggestions(true);
            } else if (job.status === 'error') {
              clearInterval(pollInterval);
              showStatusBox(importStatusBox, 'error', `[ERROR] ${job.error || job.message || 'Ingestion failed.'}`);
              startImportBtn.disabled = false;
              startImportBtn.textContent = 'START INGESTION PIPELINE';
            } else if (job.status === 'idle') {
              idleTicks += 1;
              if (idleTicks >= 4) {
                clearInterval(pollInterval);
                startImportBtn.disabled = false;
                startImportBtn.textContent = 'START INGESTION PIPELINE';
                showStatusBox(importStatusBox, 'success', '[COMPLETED] Ingestion pipeline finished. Refreshing tournament registry...');
                fetchAdminStatus();
                fetchMergeSuggestions(true);
              }
            }
          } catch (err) {
            console.warn('Status poll warning:', err);
          }
        };

        try {
          const res = await fetch(`${API_BASE}/api/admin/tournaments/import`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ target, skip_extract: skipExtract, hosting_dates: hostingDates }),
          });

          if (res.status === 401) {
            handleUnauthorized();
            startImportBtn.disabled = false;
            startImportBtn.textContent = 'START INGESTION PIPELINE';
            return;
          }

          const data = await parseFetchResponse(res);
          if (res.ok && data.success) {
            showStatusBox(importStatusBox, 'loading', `[PIPELINE ACTIVE] ${data.message}`);
            pollInterval = setInterval(pollStatus, 1500);
          } else {
            showStatusBox(importStatusBox, 'error', `[ERROR] ${data.error || 'Ingestion failed.'}`);
            startImportBtn.disabled = false;
            startImportBtn.textContent = 'START INGESTION PIPELINE';
          }
        } catch (e) {
          showStatusBox(importStatusBox, 'error', `[NETWORK ERROR] ${e.message}`);
          startImportBtn.disabled = false;
          startImportBtn.textContent = 'START INGESTION PIPELINE';
        }
      });
    }

    // Edit Dates Modal
    const editDatesModal = document.getElementById('adminEditDatesModal');
    const cancelEditDatesBtn = document.getElementById('cancelEditDatesBtn');
    const confirmEditDatesBtn = document.getElementById('confirmEditDatesBtn');
    const editTournamentDatesInput = document.getElementById('editTournamentDatesInput');
    const editDatesStatusBox = document.getElementById('editDatesStatusBox');

    if (cancelEditDatesBtn) {
      cancelEditDatesBtn.addEventListener('click', () => {
        if (editDatesModal) editDatesModal.classList.add('hidden');
        pendingEditDatesTarget = null;
      });
    }

    if (confirmEditDatesBtn) {
      confirmEditDatesBtn.addEventListener('click', async () => {
        if (!pendingEditDatesTarget) return;

        const updatedDates = (editTournamentDatesInput ? editTournamentDatesInput.value : '').trim();
        confirmEditDatesBtn.disabled = true;
        confirmEditDatesBtn.textContent = 'SAVING DATES...';
        showStatusBox(editDatesStatusBox, 'loading', 'Updating hosting dates in database...');

        try {
          const res = await fetch(`${API_BASE}/api/admin/tournaments/${encodeURIComponent(pendingEditDatesTarget.id)}/dates`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ hosting_dates: updatedDates }),
          });

          if (res.status === 401) {
            handleUnauthorized();
            return;
          }

          const data = await res.json();
          if (res.ok && data.success) {
            showStatusBox(editDatesStatusBox, 'success', `[SUCCESS] ${data.message}`);
            setTimeout(() => {
              if (editDatesModal) editDatesModal.classList.add('hidden');
              pendingEditDatesTarget = null;
              fetchAdminStatus();
            }, 600);
          } else {
            showStatusBox(editDatesStatusBox, 'error', `[ERROR] ${data.error || 'Failed to update dates.'}`);
          }
        } catch (e) {
          showStatusBox(editDatesStatusBox, 'error', `[NETWORK ERROR] ${e.message}`);
        } finally {
          confirmEditDatesBtn.disabled = false;
          confirmEditDatesBtn.textContent = 'SAVE DATES';
        }
      });
    }

    // Delete Modal
    const openDeleteModalBtn = document.getElementById('openDeleteModalBtn');
    const deleteSelect = document.getElementById('deleteTournamentSelect');
    const deleteStatusBox = document.getElementById('deleteStatusBox');

    if (openDeleteModalBtn) {
      openDeleteModalBtn.addEventListener('click', () => {
        const val = deleteSelect ? deleteSelect.value : '';
        if (!val) {
          showStatusBox(deleteStatusBox, 'error', 'Please select a tournament to purge from the dropdown.');
          return;
        }
        const opt = deleteSelect.options[deleteSelect.selectedIndex];
        openDeleteConfirmation(val, opt.dataset.slug || val, opt.dataset.name || val);
      });
    }

    // Modal Action Buttons
    const modal = document.getElementById('adminDeleteModal');
    const cancelDeleteBtn = document.getElementById('cancelDeleteBtn');
    const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');

    if (cancelDeleteBtn) {
      cancelDeleteBtn.addEventListener('click', () => {
        if (modal) modal.classList.add('hidden');
        pendingDeleteTarget = null;
      });
    }

    if (confirmDeleteBtn) {
      confirmDeleteBtn.addEventListener('click', async () => {
        if (!pendingDeleteTarget) return;

        confirmDeleteBtn.disabled = true;
        confirmDeleteBtn.textContent = 'PURGING FROM DATABASE...';

        try {
          const res = await fetch(`${API_BASE}/api/admin/tournaments/${encodeURIComponent(pendingDeleteTarget.id)}`, {
            method: 'DELETE',
            headers: getHeaders(),
          });

          if (res.status === 401) {
            handleUnauthorized();
            return;
          }

          const data = await res.json();
          if (res.ok && data.success) {
            if (modal) modal.classList.add('hidden');
            showStatusBox(deleteStatusBox, 'success', `[PURGED] ${data.message}`);
            fetchAdminStatus(); // Refresh table and stats
          } else {
            alert(`Failed to delete tournament: ${data.error || 'Unknown error'}`);
          }
        } catch (e) {
          alert(`Network error deleting tournament: ${e.message}`);
        } finally {
          confirmDeleteBtn.disabled = false;
          confirmDeleteBtn.textContent = 'CONFIRM PERMANENT DELETE';
          pendingDeleteTarget = null;
        }
      });
    }
  }

  function openDeleteConfirmation(id, slug, name) {
    pendingDeleteTarget = { id, slug, name };
    const modal = document.getElementById('adminDeleteModal');
    const msg = document.getElementById('deleteModalMessage');

    if (msg) {
      msg.innerHTML = `Are you sure you want to permanently delete tournament <strong>'${escapeHtml(name)}' (${escapeHtml(slug)})</strong>?`;
    }
    if (modal) modal.classList.remove('hidden');
  }

  function showStatusBox(el, type, msg) {
    if (!el) return;
    el.classList.remove('hidden', 'status-box-success', 'status-box-error', 'status-box-loading');

    if (type === 'success') {
      el.classList.add('status-box-success');
    } else if (type === 'error') {
      el.classList.add('status-box-error');
    } else {
      el.classList.add('status-box-loading');
    }

    el.textContent = msg;
  }

  // =========================================================================
  // 6. TAB 4: DIAGNOSTIC TESTING
  // =========================================================================

  function initDiagnosticTests() {
    const btnIntegrity = document.getElementById('btnRunIntegrity');
    const btnAccuracy = document.getElementById('btnRunAccuracy');
    const btnAllTests = document.getElementById('btnRunAllTests');
    const btnClearTerminal = document.getElementById('btnClearTerminal');

    if (btnIntegrity) {
      btnIntegrity.addEventListener('click', () => runTestSuite('integrity'));
    }
    if (btnAccuracy) {
      btnAccuracy.addEventListener('click', () => runTestSuite('accuracy'));
    }
    if (btnAllTests) {
      btnAllTests.addEventListener('click', () => runTestSuite('all'));
    }
    if (btnClearTerminal) {
      btnClearTerminal.addEventListener('click', () => {
        const term = document.getElementById('adminTerminalBody');
        const badge = document.getElementById('testStatusBadge');
        if (term) term.textContent = 'Select a test suite above to execute diagnostic validation...';
        if (badge) {
          badge.className = 'admin-terminal-badge';
          badge.textContent = 'IDLE';
        }
      });
    }
  }

  async function runTestSuite(suite) {
    const term = document.getElementById('adminTerminalBody');
    const badge = document.getElementById('testStatusBadge');

    if (badge) {
      badge.className = 'admin-terminal-badge badge-running';
      badge.textContent = 'RUNNING...';
    }
    if (term) {
      term.textContent = `[COMMAND] Initializing test suite '${suite}'...\n[SYSTEM] Running diagnostic tests against active database...\n`;
    }

    // Disable all test buttons during execution
    const btns = [document.getElementById('btnRunIntegrity'), document.getElementById('btnRunAccuracy'), document.getElementById('btnRunAllTests')];
    btns.forEach((b) => b && (b.disabled = true));

    try {
      const res = await fetch(`${API_BASE}/api/admin/run_tests`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ suite }),
      });

      if (res.status === 401) {
        handleUnauthorized();
        return;
      }

      const data = await res.json();
      if (res.ok) {
        if (badge) {
          if (data.success) {
            badge.className = 'admin-terminal-badge badge-pass';
            badge.textContent = `PASSED (${data.duration_seconds}s)`;
          } else {
            badge.className = 'admin-terminal-badge badge-fail';
            badge.textContent = `FAILED (${data.duration_seconds}s)`;
          }
        }

        let outputContent = '';
        if (data.report) {
          outputContent = data.report;
        } else if (data.output) {
          outputContent = data.output;
        } else {
          outputContent = JSON.stringify(data, null, 2);
        }

        if (term) {
          term.textContent = `[RESULT] Suite '${suite}' completed in ${data.duration_seconds} seconds.\nExit Code: ${data.exit_code ?? (data.success ? 0 : 1)}\n\n${outputContent}`;
        }
      } else {
        if (badge) {
          badge.className = 'admin-terminal-badge badge-fail';
          badge.textContent = 'ERROR';
        }
        if (term) {
          term.textContent = `[ERROR] Server error running test suite: ${data.error || 'Unknown error'}`;
        }
      }
    } catch (e) {
      if (badge) {
        badge.className = 'admin-terminal-badge badge-fail';
        badge.textContent = 'NETWORK ERROR';
      }
      if (term) {
        term.textContent = `[NETWORK ERROR] Could not connect to API test runner: ${e.message}`;
      }
    } finally {
      btns.forEach((b) => b && (b.disabled = false));
    }
  }

  // =========================================================================
  // 6. TAB 5: IDENTITY RESOLVER & MERGER TOOL
  // =========================================================================

  let mergeSuggestionsData = { persons: [], teams: [], confirmed_merges: [] };
  let activeMergeFilter = 'all'; // 'all', 'person', 'team'

  function initIdentityMerger() {
    const btnAll = document.getElementById('btnFilterAllMerges');
    const btnPersons = document.getElementById('btnFilterPersonMerges');
    const btnTeams = document.getElementById('btnFilterTeamMerges');
    const btnAutoMerge = document.getElementById('btnAutoMergeAll');
    const btnRefresh = document.getElementById('btnRefreshMerges');

    if (btnAll) {
      btnAll.addEventListener('click', () => {
        activeMergeFilter = 'all';
        updateFilterButtons();
        renderMergeSuggestions();
      });
    }
    if (btnPersons) {
      btnPersons.addEventListener('click', () => {
        activeMergeFilter = 'person';
        updateFilterButtons();
        renderMergeSuggestions();
      });
    }
    if (btnTeams) {
      btnTeams.addEventListener('click', () => {
        activeMergeFilter = 'team';
        updateFilterButtons();
        renderMergeSuggestions();
      });
    }
    if (btnAutoMerge) {
      btnAutoMerge.addEventListener('click', async () => {
        const statusBox = document.getElementById('mergeStatusBox');
        btnAutoMerge.disabled = true;
        const origText = btnAutoMerge.innerHTML;
        btnAutoMerge.textContent = 'AUTO-MERGING...';
        if (statusBox) {
          showStatusBox(statusBox, 'loading', 'Scanning database and auto-merging all high-confidence (>=90%) duplicate identities...');
        }
        try {
          const res = await fetch(`${API_BASE}/api/admin/merges/auto`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ min_confidence: 90.0 }),
          });
          if (res.status === 401) {
            handleUnauthorized();
            return;
          }
          const data = await parseFetchResponse(res);
          if (res.ok && data.success) {
            const total = data.total_merged || 0;
            if (statusBox) {
              if (total > 0) {
                showStatusBox(
                  statusBox,
                  'success',
                  `[AUTO-MERGE COMPLETE] Automatically merged ${data.merged_persons_count || 0} person duplicate(s) and ${data.merged_teams_count || 0} team duplicate(s).`
                );
              } else {
                showStatusBox(
                  statusBox,
                  'success',
                  '[AUTO-MERGE COMPLETE] All high-confidence (>=90%) duplicate identities are already resolved.'
                );
              }
            }
            await fetchMergeSuggestions(true);
            fetchAdminStatus();
          } else {
            if (statusBox) {
              showStatusBox(statusBox, 'error', `[ERROR] ${data.error || 'Auto-merge failed.'}`);
            }
          }
        } catch (err) {
          if (statusBox) {
            showStatusBox(statusBox, 'error', `[NETWORK ERROR] ${err.message}`);
          }
        } finally {
          btnAutoMerge.disabled = false;
          btnAutoMerge.innerHTML = origText;
        }
      });
    }
    if (btnRefresh) {
      btnRefresh.addEventListener('click', () => fetchMergeSuggestions());
    }

    function updateFilterButtons() {
      if (btnAll) btnAll.className = activeMergeFilter === 'all' ? 'admin-btn admin-btn-primary' : 'admin-btn admin-btn-secondary';
      if (btnPersons) btnPersons.className = activeMergeFilter === 'person' ? 'admin-btn admin-btn-primary' : 'admin-btn admin-btn-secondary';
      if (btnTeams) btnTeams.className = activeMergeFilter === 'team' ? 'admin-btn admin-btn-primary' : 'admin-btn admin-btn-secondary';
    }

    initInstitutionTeamExplorer();
    initManualMergeAutocomplete();
  }

  async function fetchMergeSuggestions(silent = false) {
    const container = document.getElementById('mergeSuggestionsContainer');
    if (container && !silent) {
      container.innerHTML = `<div style="text-align: center; padding: 32px; color: rgba(255, 255, 255, 0.78);"><div class="spinner"></div> Scanning database for candidate duplicate identities...</div>`;
    }

    try {
      const res = await fetch(`${API_BASE}/api/admin/merges/suggestions`, {
        headers: getHeaders(),
      });
      if (res.status === 401) {
        handleUnauthorized();
        return;
      }
      if (!res.ok) throw new Error('Failed to fetch suggestions');

      const data = await res.json();
      mergeSuggestionsData = {
        persons: data.persons || [],
        teams: data.teams || [],
        confirmed_merges: data.confirmed_merges || [],
      };

      setText('mergePersonCount', mergeSuggestionsData.persons.length);
      setText('mergeTeamCount', mergeSuggestionsData.teams.length);

      renderMergeSuggestions();
      renderRecentConfirmedMerges();
    } catch (e) {
      if (container && !silent) {
        container.innerHTML = `<div style="text-align: center; padding: 24px; color: rgba(255, 255, 255, 0.85);">Failed to load candidate suggestions: ${escapeHtml(e.message)}</div>`;
      }
    }
  }

  function renderRecentConfirmedMerges() {
    const section = document.getElementById('recentConfirmedMergesSection');
    const listEl = document.getElementById('recentConfirmedMergesList');
    if (!section || !listEl) return;

    const list = mergeSuggestionsData.confirmed_merges || [];
    setText('confirmedMergeCount', list.length);
    if (list.length === 0) {
      section.classList.add('hidden');
      return;
    }

    section.classList.remove('hidden');
    listEl.innerHTML = list
      .map((m) => {
        return `
          <div class="confirmed-merge-pill">
            <div class="confirmed-merge-names">
              <strong style="color: #ffffff;">${escapeHtml(m.canonical_name)}</strong>
              <span style="color: rgba(255, 255, 255, 0.65); margin: 0 6px;">&larr;</span>
              <span style="color: rgba(255, 255, 255, 0.85);">${escapeHtml(m.alias_name)}</span>
            </div>
            <div class="confirmed-merge-meta monospace">
              <span>${escapeHtml(m.institution || 'Independent')}</span>
              <span>&bull;</span>
              <span>#${m.person_id}</span>
            </div>
          </div>
        `;
      })
      .join('');
  }

  function renderMergeSuggestions() {
    const container = document.getElementById('mergeSuggestionsContainer');
    if (!container) return;

    let items = [];
    if (activeMergeFilter === 'all') {
      items = [...mergeSuggestionsData.persons, ...mergeSuggestionsData.teams];
    } else if (activeMergeFilter === 'person') {
      items = mergeSuggestionsData.persons;
    } else if (activeMergeFilter === 'team') {
      items = mergeSuggestionsData.teams;
    }

    if (items.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.78); font-family: var(--font-mono);">
          No candidate duplicate suggestions found for this category. All identities appear resolved.
        </div>
      `;
      return;
    }

    container.innerHTML = items.map((s, idx) => {
      const p = s.primary;
      const d = s.duplicate;
      const pName = s.type === 'person' ? p.canonical_name : p.name;
      const dName = s.type === 'person' ? d.canonical_name : d.name;
      const pInst = p.institution || p.institution_name || 'Independent';
      const dInst = d.institution || d.institution_name || 'Independent';

      return `
        <div class="merge-card" id="mergeCard_${s.type}_${p.id}_${d.id}">
          <div class="merge-card-header">
            <div>
              <div class="merge-card-type">
                <span class="badge-count" style="background: rgba(255, 255, 255, 0.10); color: #ffffff;">${escapeHtml(s.type.toUpperCase())}</span>
                <span style="font-weight: 600; color: #ffffff; font-size: 13px;">${escapeHtml(s.match_type)}</span>
              </div>
              ${s.reason ? `<div style="font-size: 11px; color: rgba(255, 255, 255, 0.78); margin-top: 4px;">${escapeHtml(s.reason)}</div>` : ''}
            </div>
            <div class="merge-card-conf" style="font-family: var(--font-mono); font-size: 11.5px; color: #ffffff; font-weight: 700;">
              ${s.confidence}% MATCH
            </div>
          </div>

          <div class="merge-clash-grid">
            <!-- Target / Primary to Keep -->
            <div class="merge-entity-box target">
              <div class="merge-role-tag" style="color: #ffffff;">CANONICAL TARGET (KEEP)</div>
              <div class="merge-entity-name">${escapeHtml(pName)}</div>
              <div class="merge-entity-sub">ID: #${p.id} · ${escapeHtml(pInst)}</div>
              <div class="merge-entity-stats">
                <span>${p.speech_count ?? 0} speeches</span>
                ${p.tour_count !== undefined ? `<span>${p.tour_count} tournaments</span>` : ''}
              </div>
            </div>

            <!-- Arrow Indicator -->
            <div class="merge-arrow-col">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"></line>
                <polyline points="12 5 19 12 12 19"></polyline>
              </svg>
            </div>

            <!-- Duplicate to Merge & Delete -->
            <div class="merge-entity-box duplicate">
              <div class="merge-role-tag" style="color: rgba(255, 255, 255, 0.85);">DUPLICATE VARIANT (MERGE)</div>
              <div class="merge-entity-name">${escapeHtml(dName)}</div>
              <div class="merge-entity-sub">ID: #${d.id} · ${escapeHtml(dInst)}</div>
              <div class="merge-entity-stats">
                <span>${d.speech_count ?? 0} speeches</span>
                ${d.tour_count !== undefined ? `<span>${d.tour_count} tournaments</span>` : ''}
              </div>
            </div>
          </div>

          <div class="merge-actions-row">
            <button
              class="admin-btn admin-btn-primary admin-btn-sm btn-action-merge"
              data-type="${escapeHtml(s.type)}"
              data-primary-id="${p.id}"
              data-duplicate-id="${d.id}"
              data-primary-name="${escapeHtml(pName)}"
              data-dup-name="${escapeHtml(dName)}"
            >
              MERGE INTO #${p.id}
            </button>
            <button
              class="admin-btn admin-btn-outline admin-btn-sm btn-action-dismiss"
              data-type="${escapeHtml(s.type)}"
              data-a="${p.id}"
              data-b="${d.id}"
            >
              DISMISS
            </button>
          </div>
        </div>
      `;
    }).join('');

    // Attach merge click handlers
    container.querySelectorAll('.btn-action-merge').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const type = btn.getAttribute('data-type');
        const primaryId = btn.getAttribute('data-primary-id');
        const duplicateId = btn.getAttribute('data-duplicate-id');
        const primaryName = btn.getAttribute('data-primary-name');
        // Immediate responsive button feedback & prevent double clicking
        btn.disabled = true;
        const originalText = btn.innerHTML;
        btn.innerHTML = `<span class="spinner" style="width: 12px; height: 12px; display: inline-block; vertical-align: middle; margin-right: 6px;"></span> MERGING...`;

        const card = document.getElementById(`mergeCard_${type}_${primaryId}_${duplicateId}`);
        if (card) {
          card.querySelectorAll('button').forEach((b) => (b.disabled = true));
          card.style.opacity = '0.5';
        }

        const success = await executeMerge(type, primaryId, duplicateId);
        if (!success) {
          btn.disabled = false;
          btn.innerHTML = originalText;
          if (card) {
            card.querySelectorAll('button').forEach((b) => (b.disabled = false));
            card.style.opacity = '1';
          }
        }
      });
    });

    // Attach dismiss click handlers
    container.querySelectorAll('.btn-action-dismiss').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const type = btn.getAttribute('data-type');
        const a = btn.getAttribute('data-a');
        const b = btn.getAttribute('data-b');
        btn.disabled = true;
        const card = btn.closest('.merge-card');
        if (card) card.style.opacity = '0.4';
        await dismissMerge(type, a, b);
      });
    });
  }

  async function executeMerge(type, primaryId, duplicateId) {
    const statusBox = document.getElementById('mergeStatusBox');
    if (statusBox) {
      statusBox.className = 'admin-status-box';
      statusBox.textContent = `Executing transactional merge for ${type} #${duplicateId} -> #${primaryId}...`;
      statusBox.classList.remove('hidden');
    }

    try {
      const res = await fetch(`${API_BASE}/api/admin/merges/execute`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
          type,
          primary_id: primaryId,
          duplicate_id: duplicateId,
        }),
      });

      if (res.status === 401) {
        handleUnauthorized();
        return false;
      }

      const data = await res.json();
      if (res.ok && data.success) {
        if (statusBox) {
          statusBox.className = 'admin-status-box status-success';
          statusBox.textContent = data.message;
        }

        // Optimistically purge duplicate record cards immediately from local UI state
        const numPri = parseInt(primaryId, 10);
        const numDup = parseInt(duplicateId, 10);

        if (type === 'person') {
          mergeSuggestionsData.persons = mergeSuggestionsData.persons.filter(
            (s) => s.primary.id !== numDup && s.duplicate.id !== numDup
          );
          setText('mergePersonCount', mergeSuggestionsData.persons.length);
        } else {
          mergeSuggestionsData.teams = mergeSuggestionsData.teams.filter(
            (s) => s.primary.id !== numDup && s.duplicate.id !== numDup
          );
          setText('mergeTeamCount', mergeSuggestionsData.teams.length);
        }

        renderMergeSuggestions();

        // Refresh suggestions & database status in background without locking UI
        fetchMergeSuggestions(true);
        fetchAdminStatus();
        return true;
      } else {
        if (statusBox) {
          statusBox.className = 'admin-status-box status-error';
          statusBox.textContent = `Merge note: ${data.error || 'Operation encountered an issue'}`;
        }
        // If the record was already merged or does not exist, purge the stale card
        if (data.error && (data.error.includes('does not exist') || data.error.includes('already merged'))) {
          const numDup = parseInt(duplicateId, 10);
          if (type === 'person') {
            mergeSuggestionsData.persons = mergeSuggestionsData.persons.filter(
              (s) => s.primary.id !== numDup && s.duplicate.id !== numDup
            );
            setText('mergePersonCount', mergeSuggestionsData.persons.length);
          } else {
            mergeSuggestionsData.teams = mergeSuggestionsData.teams.filter(
              (s) => s.primary.id !== numDup && s.duplicate.id !== numDup
            );
            setText('mergeTeamCount', mergeSuggestionsData.teams.length);
          }
          renderMergeSuggestions();
          return true;
        }
        return false;
      }
    } catch (e) {
      if (statusBox) {
        statusBox.className = 'admin-status-box status-error';
        statusBox.textContent = `Network error during merge: ${e.message}`;
      }
      return false;
    }
  }

  async function dismissMerge(type, idA, idB) {
    try {
      const res = await fetch(`${API_BASE}/api/admin/merges/dismiss`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
          type,
          id_a: idA,
          id_b: idB,
        }),
      });

      if (res.status === 401) {
        handleUnauthorized();
        return;
      }

      if (res.ok) {
        // Remove from local dataset and re-render
        if (type === 'person') {
          mergeSuggestionsData.persons = mergeSuggestionsData.persons.filter(
            (s) => !(s.primary.id == idA && s.duplicate.id == idB) && !(s.primary.id == idB && s.duplicate.id == idA)
          );
          setText('mergePersonCount', mergeSuggestionsData.persons.length);
        } else {
          mergeSuggestionsData.teams = mergeSuggestionsData.teams.filter(
            (s) => !(s.primary.id == idA && s.duplicate.id == idB) && !(s.primary.id == idB && s.duplicate.id == idA)
          );
          setText('mergeTeamCount', mergeSuggestionsData.teams.length);
        }
        renderMergeSuggestions();
      }
    } catch (e) {
      console.warn('Failed to dismiss merge:', e);
    }
  }

  // -------------------------------------------------------------------------
  // Submodule A: Institution Team Names Explorer & Merger
  // -------------------------------------------------------------------------
  let instList = [];
  let currentInstData = null;
  let selectedTargetTeamName = null;
  let selectedVariantTeamName = null;

  async function initInstitutionTeamExplorer() {
    const searchInput = document.getElementById('instTeamExplorerInput');
    const loadBtn = document.getElementById('btnLoadInstTeams');
    const clearBtn = document.getElementById('btnClearInstTeams');
    const mergeBar = document.getElementById('instTeamsMergeBar');
    const confirmMergeBtn = document.getElementById('btnExecuteInstTeamMerge');
    const resetSelectionBtn = document.getElementById('btnResetInstTeamSelection');
    const clearTargetBtn = document.getElementById('btnClearSelectedTarget');
    const clearDuplicateBtn = document.getElementById('btnClearSelectedDuplicate');
    const chips = document.querySelectorAll('.inst-chip');

    // Modal elements
    const mergeModal = document.getElementById('instTeamMergeConfirmModal');
    const modalInstName = document.getElementById('modalInstName');
    const modalTargetName = document.getElementById('modalTargetName');
    const modalVariantName = document.getElementById('modalVariantName');
    const modalAffectedTours = document.getElementById('modalAffectedTours');
    const cancelModalBtn = document.getElementById('cancelInstTeamMergeBtn');
    const confirmModalBtn = document.getElementById('confirmInstTeamMergeModalBtn');

    // Populate datalist from /api/admin/institutions/list
    async function loadInstitutionDatalist() {
      try {
        const res = await fetch(`${API_BASE}/api/admin/institutions/list`, {
          headers: getHeaders(),
        });
        if (res.status === 401) {
          handleUnauthorized();
          return;
        }
        if (!res.ok) return;
        const data = await res.json();
        instList = data.institutions || [];
        const dl = document.getElementById('institutionsDatalist');
        if (dl) {
          dl.innerHTML = instList
            .map((inst) => `<option value="${escapeHtml(inst.name)}">${escapeHtml(inst.name)}${inst.code ? ` (${escapeHtml(inst.code)})` : ''} — ${inst.team_count} teams</option>`)
            .join('');
        }
      } catch (e) {
        console.warn('Failed to load institutions list:', e);
      }
    }

    loadInstitutionDatalist();

    // Load distinct team names for an institution
    async function fetchInstitutionTeams(identifier) {
      const trimmed = (identifier || '').trim();
      if (!trimmed) {
        alert('Please enter or select an institution.');
        return;
      }

      const container = document.getElementById('instTeamsResultsContainer');
      const statusBox = document.getElementById('instTeamsStatusBox');
      const auditSection = document.getElementById('instConfirmedMergesSection');

      if (container) {
        container.innerHTML = `<div style="text-align: center; padding: 36px; color: rgba(255, 255, 255, 0.78);"><div class="spinner"></div> Loading distinct team names for '${escapeHtml(trimmed)}'...</div>`;
      }

      try {
        const res = await fetch(`${API_BASE}/api/admin/institutions/${encodeURIComponent(trimmed)}/teams`, {
          headers: getHeaders(),
        });
        if (res.status === 401) {
          handleUnauthorized();
          return;
        }

        const data = await res.json();
        if (!res.ok || !data.success) {
          if (container) {
            container.innerHTML = `<div style="text-align: center; padding: 28px; color: rgba(255, 255, 255, 0.85); font-family: var(--font-mono);">${escapeHtml(data.error || 'Failed to find institution teams')}</div>`;
          }
          if (auditSection) auditSection.classList.add('hidden');
          return;
        }

        currentInstData = data;

        // Reset or maintain selections if they still exist
        if (selectedTargetTeamName && !data.team_names.some(tn => tn.name === selectedTargetTeamName)) {
          selectedTargetTeamName = null;
        }
        if (selectedVariantTeamName && !data.team_names.some(tn => tn.name === selectedVariantTeamName)) {
          selectedVariantTeamName = null;
        }

        if (clearBtn) clearBtn.classList.remove('hidden');
        renderInstitutionTeamNamesGrid();
        renderConfirmedMergesAudit();
        updateInstitutionMergeBar();
      } catch (err) {
        if (container) {
          container.innerHTML = `<div style="text-align: center; padding: 28px; color: rgba(255, 255, 255, 0.85);">Network error fetching institution teams: ${escapeHtml(err.message)}</div>`;
        }
      }
    }

    function renderInstitutionTeamNamesGrid() {
      const container = document.getElementById('instTeamsResultsContainer');
      if (!container || !currentInstData) return;

      const inst = currentInstData.institution;
      const teamNames = currentInstData.team_names || [];

      if (teamNames.length === 0) {
        container.innerHTML = `
          <div style="padding: 24px; text-align: center; color: rgba(255, 255, 255, 0.78); font-family: var(--font-mono);">
            No debate teams recorded for institution '${escapeHtml(inst.name)}'.
          </div>
        `;
        return;
      }

      let html = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 10px;">
          <div style="font-size: 15px; font-weight: 700; color: #ffffff;">
            ${escapeHtml(inst.name)} ${inst.code ? `<span class="badge-count" style="background: rgba(255, 255, 255, 0.10); color: #ffffff; margin-left: 6px;">${escapeHtml(inst.code)}</span>` : ''}
          </div>
          <div style="font-family: var(--font-mono); font-size: 12px; color: #ffffff; font-weight: 600;">
            ${teamNames.length} Distinct Team Names across ${currentInstData.total_instances || 0} Tournament Entries
          </div>
        </div>
        <div class="inst-teams-grid">
      `;

      teamNames.forEach((tn) => {
        const isTarget = selectedTargetTeamName === tn.name;
        const isVariant = selectedVariantTeamName === tn.name;

        let cardClass = 'inst-team-card';
        if (isTarget) cardClass += ' is-target';
        if (isVariant) cardClass += ' is-duplicate';

        html += `
          <div class="${cardClass}" id="instTeamNameCard_${escapeHtml(tn.name).replace(/\s+/g, '_')}">
            <div class="inst-team-header">
              <div>
                <div class="inst-team-name">
                  <span>${escapeHtml(tn.name)}</span>
                  ${tn.tier ? `<span class="badge-count" style="background: rgba(255, 255, 255, 0.10); color: #ffffff;">TIER ${escapeHtml(tn.tier)}</span>` : ''}
                </div>
                <div style="font-family: var(--font-mono); font-size: 11px; color: rgba(255, 255, 255, 0.78); margin-top: 3px;">
                  Fielded in ${tn.instance_count} ${tn.instance_count === 1 ? 'Tournament' : 'Tournaments'}
                </div>
              </div>
              <div>
                ${tn.is_merged 
                  ? `<span class="badge-count" style="background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.28); color: #ffffff; font-weight: 700;">MERGED INTO ${escapeHtml(tn.merged_into)}</span>` 
                  : (tn.merged_variants && tn.merged_variants.length > 0 
                      ? `<span class="badge-count" style="background: rgba(255, 255, 255, 0.24); border: 1px solid rgba(255, 255, 255, 0.32); color: #ffffff; font-weight: 800;">CANONICAL FLAGSHIP</span>` 
                      : (isTarget 
                          ? `<span class="badge-count" style="background: rgba(255, 255, 255, 0.18); border: 1px solid rgba(255, 255, 255, 0.35); color: #ffffff; font-weight: 800;">TARGET</span>` 
                          : (isVariant 
                              ? `<span class="badge-count" style="background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.32); color: #ffffff; font-weight: 800;">VARIANT</span>` 
                              : `<span class="badge-count" style="background: rgba(18, 34, 108, 0.78); border: 1px solid rgba(255, 255, 255, 0.25); color: #ffffff;">STANDALONE</span>`)))}
              </div>
            </div>

            <!-- Tournaments List -->
            <div style="margin: 2px 0 6px;">
              <div style="font-family: var(--font-mono); font-size: 10px; color: #ffffff; text-transform: uppercase; margin-bottom: 4px;">Tournaments Competed:</div>
              <div>
                ${tn.tournaments.map(tour => `<span class="inst-tour-tag">${escapeHtml(tour.name)}</span>`).join('')}
              </div>
            </div>

            <!-- Debaters / Members -->
            <div class="inst-team-members">
              <div class="inst-team-members-lbl">Debaters Roster</div>
              <div>${escapeHtml(tn.members || 'No debaters recorded in tab')}</div>
            </div>

            <!-- Stats -->
            <div class="inst-team-stats-row">
              <span>${tn.total_debates} Debates</span>
              <span>&bull;</span>
              <span>${tn.total_speeches} Speeches</span>
            </div>

            <!-- Confirmed Merged Variants Info -->
            ${tn.merged_variants && tn.merged_variants.length > 0 ? `
              <div class="inst-confirmed-merged-box">
                <span style="font-size: 10.5px; font-weight: 700; color: #ffffff; font-family: var(--font-mono); text-transform: uppercase;">Confirmed Merged Variants:</span>
                <div style="margin-top: 4px;">
                  ${tn.merged_variants.map(v => `<span class="badge-count" style="background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.28); color: #ffffff; font-weight: 700; margin-right: 4px; margin-bottom: 2px; display: inline-block;">${escapeHtml(v)}</span>`).join('')}
                </div>
              </div>
            ` : ''}

            <!-- Merged Into Info / Unmerge Option -->
            ${tn.is_merged ? `
              <div class="inst-merged-into-box">
                <div>
                  <span style="color: rgba(255, 255, 255, 0.78);">Merged Under:</span>
                  <strong style="color: #ffffff; margin-left: 6px;">${escapeHtml(tn.merged_into)}</strong>
                </div>
                <button class="admin-btn admin-btn-outline admin-btn-sm btn-inst-unmerge" data-variant-name="${escapeHtml(tn.name)}" style="padding: 4px 10px; font-size: 11px;">
                  UNMERGE
                </button>
              </div>
            ` : ''}

            <!-- Action Buttons -->
            ${!tn.is_merged ? `
              <div class="inst-team-actions">
                <button
                  class="admin-btn ${isTarget ? 'admin-btn-primary' : 'admin-btn-outline'} btn-inst-set-target"
                  data-team-name="${escapeHtml(tn.name)}"
                >
                  ${isTarget ? 'REMOVE TARGET' : 'SET AS TARGET (KEEP)'}
                </button>
                <button
                  class="admin-btn ${isVariant ? 'admin-btn-danger' : 'admin-btn-secondary'} btn-inst-set-variant"
                  data-team-name="${escapeHtml(tn.name)}"
                >
                  ${isVariant ? 'REMOVE VARIANT' : 'SET AS VARIANT (MERGE)'}
                </button>
              </div>
            ` : ''}
          </div>
        `;
      });

      html += '</div>';
      container.innerHTML = html;

      // Attach button events
      container.querySelectorAll('.btn-inst-set-target').forEach((btn) => {
        btn.addEventListener('click', () => {
          const tName = btn.getAttribute('data-team-name');
          if (selectedTargetTeamName === tName) {
            selectedTargetTeamName = null;
          } else {
            if (selectedVariantTeamName === tName) selectedVariantTeamName = null;
            selectedTargetTeamName = tName;
          }
          renderInstitutionTeamNamesGrid();
          updateInstitutionMergeBar();
        });
      });

      container.querySelectorAll('.btn-inst-set-variant').forEach((btn) => {
        btn.addEventListener('click', () => {
          const vName = btn.getAttribute('data-team-name');
          if (selectedVariantTeamName === vName) {
            selectedVariantTeamName = null;
          } else {
            if (selectedTargetTeamName === vName) selectedTargetTeamName = null;
            selectedVariantTeamName = vName;
          }
          renderInstitutionTeamNamesGrid();
          updateInstitutionMergeBar();
        });
      });

      container.querySelectorAll('.btn-inst-unmerge').forEach((btn) => {
        btn.addEventListener('click', () => {
          const vName = btn.getAttribute('data-variant-name');
          handleUnmergeTeamName(vName);
        });
      });
    }

    function renderConfirmedMergesAudit() {
      const section = document.getElementById('instConfirmedMergesSection');
      const listContainer = document.getElementById('instConfirmedMergesList');
      if (!section || !listContainer || !currentInstData) return;

      const merges = currentInstData.confirmed_merges || [];
      if (merges.length === 0) {
        section.classList.add('hidden');
        return;
      }

      section.classList.remove('hidden');
      listContainer.innerHTML = merges.map((m) => `
        <div class="inst-audit-row">
          <div>
            <strong style="color: #ffffff;">${escapeHtml(m.target_canonical_name)}</strong>
            <span style="color: #ffffff; margin: 0 8px;">&larr;</span>
            <strong style="color: rgba(255, 255, 255, 0.82);">${escapeHtml(m.variant_name)}</strong>
            <span class="badge-count" style="margin-left: 10px; background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.28); color: #ffffff; font-weight: 700;">CONFIRMED UNIFIED</span>
          </div>
          <div style="display: flex; align-items: center; gap: 12px;">
            <span style="color: rgba(255, 255, 255, 0.78); font-family: var(--font-mono); font-size: 11px;">${m.decided_at || ''}</span>
            <button class="admin-btn admin-btn-outline admin-btn-sm btn-inst-unmerge-audit" data-variant-name="${escapeHtml(m.variant_name)}" style="padding: 3px 8px; font-size: 11px;">
              UNMERGE
            </button>
          </div>
        </div>
      `).join('');

      listContainer.querySelectorAll('.btn-inst-unmerge-audit').forEach((btn) => {
        btn.addEventListener('click', () => {
          const vName = btn.getAttribute('data-variant-name');
          handleUnmergeTeamName(vName);
        });
      });
    }

    function updateInstitutionMergeBar() {
      if (!mergeBar) return;

      if (!selectedTargetTeamName && !selectedVariantTeamName) {
        mergeBar.classList.add('hidden');
        return;
      }

      mergeBar.classList.remove('hidden');

      const targetLbl = document.getElementById('instSelectedTargetLabel');
      const dupLbl = document.getElementById('instSelectedDuplicateLabel');

      if (selectedTargetTeamName) {
        targetLbl.innerHTML = `<strong>${escapeHtml(selectedTargetTeamName)}</strong> <span class="badge-count" style="background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.28); color: #ffffff; font-weight: 700;">KEEP</span>`;
        if (clearTargetBtn) clearTargetBtn.classList.remove('hidden');
      } else {
        targetLbl.textContent = 'None selected (Click [Set as Target] on any card)';
        if (clearTargetBtn) clearTargetBtn.classList.add('hidden');
      }

      if (selectedVariantTeamName) {
        dupLbl.innerHTML = `<strong>${escapeHtml(selectedVariantTeamName)}</strong> <span class="badge-count" style="background: rgba(255, 255, 255, 0.14); border: 1px solid rgba(255, 255, 255, 0.28); color: #ffffff; font-weight: 700;">UNIFY</span>`;
        if (clearDuplicateBtn) clearDuplicateBtn.classList.remove('hidden');
      } else {
        dupLbl.textContent = 'None selected (Click [Set as Variant] on any card)';
        if (clearDuplicateBtn) clearDuplicateBtn.classList.add('hidden');
      }

      if (confirmMergeBtn) {
        if (selectedTargetTeamName && selectedVariantTeamName) {
          if (selectedTargetTeamName === selectedVariantTeamName) {
            confirmMergeBtn.disabled = true;
            confirmMergeBtn.textContent = 'CANNOT MERGE IDENTICAL NAMES';
          } else {
            confirmMergeBtn.disabled = false;
            confirmMergeBtn.textContent = `MERGE '${selectedVariantTeamName}' INTO '${selectedTargetTeamName}'`;
          }
        } else {
          confirmMergeBtn.disabled = true;
          confirmMergeBtn.textContent = 'CONFIRM & MERGE TEAM NAMES';
        }
      }
    }

    // Open explicit confirmation modal before executing merge
    if (confirmMergeBtn) {
      confirmMergeBtn.addEventListener('click', () => {
        if (!selectedTargetTeamName || !selectedVariantTeamName || !currentInstData) return;

        const variantObj = (currentInstData.team_names || []).find(x => x.name === selectedVariantTeamName);
        const tourNames = variantObj ? variantObj.tournaments.map(t => t.name).join(', ') : 'All recorded tournaments';

        if (modalInstName) modalInstName.textContent = currentInstData.institution.name;
        if (modalTargetName) modalTargetName.textContent = selectedTargetTeamName;
        if (modalVariantName) modalVariantName.textContent = selectedVariantTeamName;
        if (modalAffectedTours) modalAffectedTours.textContent = tourNames;

        if (mergeModal) mergeModal.classList.remove('hidden');
      });
    }

    if (cancelModalBtn) {
      cancelModalBtn.addEventListener('click', () => {
        if (mergeModal) mergeModal.classList.add('hidden');
      });
    }

    // Confirm inside modal executes the merge
    if (confirmModalBtn) {
      confirmModalBtn.addEventListener('click', async () => {
        if (!selectedTargetTeamName || !selectedVariantTeamName || !currentInstData) return;

        confirmModalBtn.disabled = true;
        const originalText = confirmModalBtn.textContent;
        confirmModalBtn.textContent = 'EXECUTING MERGE...';

        try {
          const res = await fetch(`${API_BASE}/api/admin/institutions/merge_team_names`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({
              institution_id: currentInstData.institution.id,
              target_canonical_name: selectedTargetTeamName,
              variant_name: selectedVariantTeamName,
            }),
          });

          if (res.status === 401) {
            handleUnauthorized();
            return;
          }

          const data = await res.json();
          if (mergeModal) mergeModal.classList.add('hidden');

          const statusBox = document.getElementById('instTeamsStatusBox');
          if (res.ok && data.success) {
            if (statusBox) {
              statusBox.className = 'admin-status-box status-success';
              statusBox.textContent = data.message;
              statusBox.classList.remove('hidden');
            }
            selectedVariantTeamName = null;
            // Reload institution data to reflect confirmed merge
            await fetchInstitutionTeams(String(currentInstData.institution.id));
          } else {
            if (statusBox) {
              statusBox.className = 'admin-status-box status-error';
              statusBox.textContent = `Merge note: ${data.error || 'Operation failed'}`;
              statusBox.classList.remove('hidden');
            }
          }
        } catch (e) {
          if (mergeModal) mergeModal.classList.add('hidden');
          const statusBox = document.getElementById('instTeamsStatusBox');
          if (statusBox) {
            statusBox.className = 'admin-status-box status-error';
            statusBox.textContent = `Network error during team merge: ${e.message}`;
            statusBox.classList.remove('hidden');
          }
        } finally {
          confirmModalBtn.disabled = false;
          confirmModalBtn.textContent = originalText;
        }
      });
    }

    async function handleUnmergeTeamName(variantName) {
      if (!currentInstData) return;
      const ok = confirm(`Confirm Unmerge:\n\nRestore team name '${variantName}' as an independent standalone team identity for ${currentInstData.institution.name}?\n\nProceed?`);
      if (!ok) return;

      const statusBox = document.getElementById('instTeamsStatusBox');
      try {
        const res = await fetch(`${API_BASE}/api/admin/institutions/unmerge_team_name`, {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({
            institution_id: currentInstData.institution.id,
            variant_name: variantName,
          }),
        });

        if (res.status === 401) {
          handleUnauthorized();
          return;
        }

        const data = await res.json();
        if (res.ok && data.success) {
          if (statusBox) {
            statusBox.className = 'admin-status-box status-success';
            statusBox.textContent = data.message;
            statusBox.classList.remove('hidden');
          }
          await fetchInstitutionTeams(String(currentInstData.institution.id));
        } else {
          if (statusBox) {
            statusBox.className = 'admin-status-box status-error';
            statusBox.textContent = `Unmerge error: ${data.error || 'Failed to unmerge'}`;
            statusBox.classList.remove('hidden');
          }
        }
      } catch (e) {
        if (statusBox) {
          statusBox.className = 'admin-status-box status-error';
          statusBox.textContent = `Network error during unmerge: ${e.message}`;
          statusBox.classList.remove('hidden');
        }
      }
    }

    // Search button & Enter key
    if (loadBtn) {
      loadBtn.addEventListener('click', () => {
        fetchInstitutionTeams(searchInput ? searchInput.value : '');
      });
    }

    if (searchInput) {
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          fetchInstitutionTeams(searchInput.value);
        }
      });
    }

    // Quick chips
    chips.forEach((chip) => {
      chip.addEventListener('click', () => {
        const instName = chip.getAttribute('data-inst');
        if (searchInput) searchInput.value = instName;
        fetchInstitutionTeams(instName);
      });
    });

    // Clear & Reset buttons
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (searchInput) searchInput.value = '';
        currentInstData = null;
        selectedTargetTeamName = null;
        selectedVariantTeamName = null;
        updateInstitutionMergeBar();
        clearBtn.classList.add('hidden');
        const container = document.getElementById('instTeamsResultsContainer');
        if (container) {
          container.innerHTML = `
            <div style="text-align: center; padding: 36px 20px; color: #ffffff; font-family: var(--font-mono); font-size: 13px;">
              Type or select an institution above to inspect every name the school has competed under.
            </div>
          `;
        }
        const auditSection = document.getElementById('instConfirmedMergesSection');
        if (auditSection) auditSection.classList.add('hidden');
      });
    }

    if (clearTargetBtn) {
      clearTargetBtn.addEventListener('click', () => {
        selectedTargetTeamName = null;
        renderInstitutionTeamNamesGrid();
        updateInstitutionMergeBar();
      });
    }

    if (clearDuplicateBtn) {
      clearDuplicateBtn.addEventListener('click', () => {
        selectedVariantTeamName = null;
        renderInstitutionTeamNamesGrid();
        updateInstitutionMergeBar();
      });
    }

    if (resetSelectionBtn) {
      resetSelectionBtn.addEventListener('click', () => {
        selectedTargetTeamName = null;
        selectedVariantTeamName = null;
        renderInstitutionTeamNamesGrid();
        updateInstitutionMergeBar();
      });
    }
  }

  // -------------------------------------------------------------------------
  // Submodule B: Manual Merge with Live Search Autocomplete
  // -------------------------------------------------------------------------
  function initManualMergeAutocomplete() {
    const typeSelect = document.getElementById('manualMergeType');
    const primaryInput = document.getElementById('manualPrimaryInput');
    const primaryHidden = document.getElementById('manualPrimaryId');
    const primaryDropdown = document.getElementById('manualPrimaryDropdown');
    const primaryChip = document.getElementById('manualPrimarySelectedCard');

    const duplicateInput = document.getElementById('manualDuplicateInput');
    const duplicateHidden = document.getElementById('manualDuplicateId');
    const duplicateDropdown = document.getElementById('manualDuplicateDropdown');
    const duplicateChip = document.getElementById('manualDuplicateSelectedCard');

    const btnManualMerge = document.getElementById('btnExecuteManualMerge');

    function resetInputs() {
      if (primaryInput) primaryInput.value = '';
      if (primaryHidden) primaryHidden.value = '';
      if (primaryDropdown) primaryDropdown.classList.add('hidden');
      if (primaryChip) {
        primaryChip.innerHTML = '';
        primaryChip.classList.add('hidden');
      }

      if (duplicateInput) duplicateInput.value = '';
      if (duplicateHidden) duplicateHidden.value = '';
      if (duplicateDropdown) duplicateDropdown.classList.add('hidden');
      if (duplicateChip) {
        duplicateChip.innerHTML = '';
        duplicateChip.classList.add('hidden');
      }
    }

    if (typeSelect) {
      typeSelect.addEventListener('change', () => {
        resetInputs();
        const placeholder = typeSelect.value === 'person' 
          ? 'Type name, school, or ID to search...'
          : 'Type team name, school, or ID to search...';
        if (primaryInput) primaryInput.placeholder = placeholder;
        if (duplicateInput) duplicateInput.placeholder = placeholder;
      });
    }

    function bindAutocomplete(input, hidden, dropdown, chip, isTarget) {
      if (!input || !hidden || !dropdown || !chip) return;

      let debounceTimer = null;
      let abortController = null;

      input.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        if (abortController) abortController.abort();
        const query = input.value.trim();
        if (!query) {
          dropdown.classList.add('hidden');
          return;
        }

        debounceTimer = setTimeout(async () => {
          const type = typeSelect ? typeSelect.value : 'person';
          abortController = new AbortController();
          try {
            const res = await fetch(
              `${API_BASE}/api/admin/entities/search?type=${encodeURIComponent(type)}&q=${encodeURIComponent(query)}&limit=10`,
              { headers: getHeaders(), signal: abortController.signal }
            );
            if (res.status === 401) {
              handleUnauthorized();
              return;
            }
            if (!res.ok) return;

            const data = await res.json();
            const results = data.results || [];

            if (results.length === 0) {
              dropdown.innerHTML = `
                <div style="padding: 12px; font-family: var(--font-mono); font-size: 12px; color: rgba(255, 255, 255, 0.78); text-align: center;">
                  No matching ${escapeHtml(type)} records found.
                </div>
              `;
              dropdown.classList.remove('hidden');
              return;
            }

            dropdown.innerHTML = results.map((r) => {
              if (type === 'person') {
                const pName = r.canonical_name || 'Unnamed';
                const inst = r.institution || 'Independent';
                const speeches = r.speech_count ?? 0;
                return `
                  <div class="entity-auto-item" data-id="${r.id}" data-name="${escapeHtml(pName)}" data-sub="${escapeHtml(inst)}" data-stats="${speeches} speeches">
                    <div>
                      <div class="entity-auto-title">
                        <span>${escapeHtml(pName)}</span>
                        <span class="entity-auto-badge">#${r.id}</span>
                      </div>
                      <div class="entity-auto-sub">${escapeHtml(inst)} ${r.national_level ? `&bull; <span style="color: #ffffff;">${escapeHtml(r.national_level)}</span>` : ''}</div>
                    </div>
                    <div class="entity-auto-stats">${speeches} speeches</div>
                  </div>
                `;
              } else {
                const tName = r.name || 'Unnamed Team';
                const tour = r.official_tournament_name || r.tournament_name || 'Tournament';
                const inst = r.institution_name || 'Independent';
                const speeches = r.speech_count ?? 0;
                const members = r.members ? escapeHtml(r.members) : '';
                return `
                  <div class="entity-auto-item" data-id="${r.id}" data-name="${escapeHtml(tName)}" data-sub="${escapeHtml(tour)} &bull; ${escapeHtml(inst)}" data-stats="${speeches} speeches">
                    <div style="max-width: 80%;">
                      <div class="entity-auto-title">
                        <span>${escapeHtml(tName)}</span>
                        <span class="entity-auto-badge">#${r.id}</span>
                      </div>
                      <div class="entity-auto-sub">${escapeHtml(tour)} &bull; ${escapeHtml(inst)}</div>
                      ${members ? `<div style="font-size: 11px; color: rgba(255, 255, 255, 0.78); margin-top: 2px;">${members}</div>` : ''}
                    </div>
                    <div class="entity-auto-stats">${speeches} sp.</div>
                  </div>
                `;
              }
            }).join('');

            dropdown.querySelectorAll('.entity-auto-item').forEach((item) => {
              item.addEventListener('click', () => {
                const id = item.getAttribute('data-id');
                const name = item.getAttribute('data-name');
                const sub = item.getAttribute('data-sub');
                const stats = item.getAttribute('data-stats');

                selectEntity(id, name, sub, stats);
              });
            });

            dropdown.classList.remove('hidden');
          } catch (e) {
            console.warn('Entity search error:', e);
          }
        }, 200);
      });

      function selectEntity(id, name, sub, stats) {
        hidden.value = id;
        input.value = name;
        dropdown.classList.add('hidden');

        chip.innerHTML = `
          <div class="chip-content">
            <div class="chip-name">
              <span>${escapeHtml(name)}</span>
              <span class="badge-count" style="background: rgba(255, 255, 255, 0.14); color: ${isTarget ? '#ffffff' : 'rgba(255, 255, 255, 0.85)'}; font-weight: 700;">#${id}</span>
            </div>
            <div class="chip-sub">${sub} &bull; ${stats}</div>
          </div>
          <button type="button" class="chip-clear-btn" title="Remove selection">&times;</button>
        `;
        chip.classList.remove('hidden');

        const clearBtn = chip.querySelector('.chip-clear-btn');
        if (clearBtn) {
          clearBtn.addEventListener('click', () => {
            hidden.value = '';
            input.value = '';
            chip.innerHTML = '';
            chip.classList.add('hidden');
            input.focus();
          });
        }
      }

      // If user presses Enter or tabs out with a number, resolve ID directly
      input.addEventListener('change', async () => {
        const val = input.value.trim();
        if (/^\d+$/.test(val) && !hidden.value) {
          const type = typeSelect ? typeSelect.value : 'person';
          try {
            const res = await fetch(`${API_BASE}/api/admin/entities/search?type=${encodeURIComponent(type)}&q=${val}&limit=1`, {
              headers: getHeaders(),
            });
            if (res.ok) {
              const data = await res.json();
              if (data.results && data.results.length > 0) {
                const r = data.results[0];
                const name = type === 'person' ? r.canonical_name : r.name;
                const sub = type === 'person' ? (r.institution || 'Independent') : `${r.official_tournament_name || ''} · ${r.institution_name || ''}`;
                const stats = `${r.speech_count || 0} speeches`;
                selectEntity(r.id, name, sub, stats);
              }
            }
          } catch (e) {}
        }
      });
    }

    bindAutocomplete(primaryInput, primaryHidden, primaryDropdown, primaryChip, true);
    bindAutocomplete(duplicateInput, duplicateHidden, duplicateDropdown, duplicateChip, false);

    // Close dropdowns on outside click
    document.addEventListener('click', (e) => {
      if (primaryDropdown && !primaryDropdown.contains(e.target) && e.target !== primaryInput) {
        primaryDropdown.classList.add('hidden');
      }
      if (duplicateDropdown && !duplicateDropdown.contains(e.target) && e.target !== duplicateInput) {
        duplicateDropdown.classList.add('hidden');
      }
    });

    // Wire manual merge execution button
    if (btnManualMerge) {
      btnManualMerge.addEventListener('click', async () => {
        const type = (typeSelect ? typeSelect.value : 'person').trim();
        let primaryId = (primaryHidden ? primaryHidden.value : '').trim();
        let duplicateId = (duplicateHidden ? duplicateHidden.value : '').trim();

        // Fallbacks if user typed raw numbers without picking from dropdown
        if (!primaryId && primaryInput && /^\d+$/.test(primaryInput.value.trim())) {
          primaryId = primaryInput.value.trim();
        }
        if (!duplicateId && duplicateInput && /^\d+$/.test(duplicateInput.value.trim())) {
          duplicateId = duplicateInput.value.trim();
        }

        if (!primaryId || !duplicateId) {
          alert('Please search and select both a Canonical Target and a Duplicate entity.');
          return;
        }

        if (primaryId === duplicateId) {
          alert('Canonical Target ID and Duplicate ID cannot be the same entity.');
          return;
        }

        const priName = primaryInput ? primaryInput.value : `#${primaryId}`;
        const dupName = duplicateInput ? duplicateInput.value : `#${duplicateId}`;

        const ok = confirm(
          `Execute Manual ${type.toUpperCase()} Merge:\n\n` +
          `Target Entity (KEEP): '${priName}' (#${primaryId})\n` +
          `Duplicate Entity (DELETE & MERGE): '${dupName}' (#${duplicateId})\n\n` +
          `Proceed with permanent database merge?`
        );
        if (!ok) return;

        btnManualMerge.disabled = true;
        const originalText = btnManualMerge.textContent;
        btnManualMerge.textContent = 'EXECUTING MANUAL MERGE...';

        const success = await executeMerge(type, primaryId, duplicateId);
        btnManualMerge.disabled = false;
        btnManualMerge.textContent = originalText;

        if (success) {
          resetInputs();
        }
      });
    }
  }

  // =========================================================================
  // UTILITY HELPERS
  // =========================================================================

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // =========================================================================
  // INITIALIZATION
  // =========================================================================

  document.addEventListener('DOMContentLoaded', () => {
    // Form listeners
    if (loginForm) {
      loginForm.addEventListener('submit', (e) => {
        e.preventDefault();
        handleLogin();
      });
    }
    if (loginBtn) {
      loginBtn.addEventListener('click', handleLogin);
    }
    if (lockBtn) {
      lockBtn.addEventListener('click', handleLogout);
    }
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        fetchAdminStatus();
        fetchMergeSuggestions();
      });
    }

    // Init tab navigation
    initTabs();

    // Hook tab 5 click to load suggestions
    const tabBtnMerges = document.getElementById('tabBtnMerges');
    if (tabBtnMerges) {
      tabBtnMerges.addEventListener('click', () => {
        if (!mergeSuggestionsData.persons.length && !mergeSuggestionsData.teams.length) {
          fetchMergeSuggestions();
        }
      });
    }

    // Init subcomponents
    initBioAudit();
    initTournamentOperations();
    initDiagnosticTests();
    initIdentityMerger();
    initDataPersistence();

    // Verify session state or URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const authParam = urlParams.get('auth');
    const tabParam = urlParams.get('tab');
    const speakerParam = urlParams.get('speaker');
    const runParam = urlParams.get('run');

    if (authParam) {
      if (passwordInput) passwordInput.value = authParam;
      handleLogin().then(() => {
        if (getStoredToken()) {
          if (tabParam) {
            const tabBtn = document.querySelector(`.admin-tab-btn[data-tab="pane${tabParam.charAt(0).toUpperCase() + tabParam.slice(1)}"]`);
            if (tabBtn) tabBtn.click();
          }
          if (speakerParam) {
            loadDebaterAudit(speakerParam);
          }
          if (runParam) {
            runTestSuite(runParam);
          }
        }
      });
    } else {
      verifySession();
    }
  });
})();

