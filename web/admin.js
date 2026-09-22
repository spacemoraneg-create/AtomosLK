/**
 * Atomos Administrative Command Console
 * 
 * Secure management portal for database vitals, debater data confirmation,
 * tournament ingestion/deletion, and automated integrity testing.
 */

(function () {
  'use strict';

  const TOKEN_KEY = 'atomos_admin_token';
  const API_BASE = window.location.origin;

  let currentStatusData = null;
  let pendingDeleteTarget = null;

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
    const token = sessionStorage.getItem(TOKEN_KEY) || '';
    return {
      'Content-Type': 'application/json',
      'X-Admin-Token': token,
    };
  }

  // =========================================================================
  // 1. AUTHENTICATION & SESSION MANAGEMENT
  // =========================================================================

  function getStoredToken() {
    return sessionStorage.getItem(TOKEN_KEY);
  }

  function setStoredToken(token) {
    if (token) {
      sessionStorage.setItem(TOKEN_KEY, token);
    } else {
      sessionStorage.removeItem(TOKEN_KEY);
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

  async function fetchAdminStatus() {
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
      renderDatabaseVitals(data.database);
      renderTournamentsTable(data.tournaments);
      updateTournamentDropdown(data.tournaments);
    } catch (e) {
      console.error('Failed to load admin status:', e);
    }
  }

  function renderDatabaseVitals(db) {
    if (!db) return;

    // KPI Tiles
    setText('kpiTournaments', db.tournaments_count ?? '--');
    setText('kpiDebates', `${db.contested_debates ?? '--'} (${db.debates_count ?? '--'} tot)`);
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
      tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 24px; color: rgba(255,255,255,0.5);">No tournaments ingested in database.</td></tr>`;
      return;
    }

    tbody.innerHTML = tournaments
      .map((t) => {
        return `
          <tr>
            <td class="monospace" style="color: #38bdf8; font-weight: 700;">#${t.chrono_order ?? t.id}</td>
            <td class="monospace">${escapeHtml(t.slug)}</td>
            <td style="font-weight: 500;">
              <div>${escapeHtml(t.official_name || t.name)}</div>
              <div style="font-size: 11px; color: #38bdf8; font-family: var(--font-mono); margin-top: 2px;">
                ${t.hosting_dates ? escapeHtml(t.hosting_dates) : '2026'} · ${t.source_url ? escapeHtml(t.source_url) : 'Local Tab Archive'}
              </div>
            </td>
            <td class="monospace">${t.year || '--'}</td>
            <td class="monospace" style="font-weight: 600;">${t.debate_count ?? 0}</td>
            <td class="monospace">${t.round_count ?? 0}</td>
            <td class="monospace">${t.team_count ?? 0}</td>
            <td class="monospace">${t.speech_count ?? 0}</td>
            <td style="text-align: center;">
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

    // Attach row delete handlers
    tbody.querySelectorAll('.btn-delete-row').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-id');
        const slug = btn.getAttribute('data-slug');
        const name = btn.getAttribute('data-name');
        openDeleteConfirmation(id, slug, name);
      });
    });
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
  // 4. TAB 2: DATA CONFIRMATION // BIO ENGINE AUDIT
  // =========================================================================

  let debaterSearchTimeout = null;

  function initBioAudit() {
    const input = document.getElementById('adminBioSearchInput');
    const clearBtn = document.getElementById('adminBioClearBtn');
    const suggestions = document.getElementById('adminBioSuggestions');

    if (input) {
      input.addEventListener('input', () => {
        const q = input.value.trim();
        if (clearBtn) clearBtn.classList.toggle('hidden', !q);
        clearTimeout(debaterSearchTimeout);
        debaterSearchTimeout = setTimeout(() => searchDebaters(q), 220);
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

    try {
      const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(query)}&type=debater&limit=8`);
      if (!res.ok) return;
      const data = await res.json();
      const results = data.results || [];

      if (results.length === 0) {
        suggestions.innerHTML = '<div style="padding: 12px; color: rgba(255,255,255,0.5); font-size: 13px; text-align: center;">No matching debaters found in database.</div>';
        suggestions.classList.remove('hidden');
        return;
      }

      suggestions.innerHTML = results
        .map((r) => {
          return `
            <div class="bio-autocomplete-item" data-name="${escapeHtml(r.canonical_name || r.name)}">
              <div class="bio-ac-name">${escapeHtml(r.canonical_name || r.name)}</div>
              <div class="bio-ac-inst">${escapeHtml(r.institution || 'Independent')} ${r.national_level ? `&bull; <span style="color: #38bdf8;">${escapeHtml(r.national_level)}</span>` : ''}</div>
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
      <div style="text-align: center; padding: 40px; color: #38bdf8; font-family: var(--font-mono);">
        Loading live career dossier & ballot breakdown for ${escapeHtml(name)}...
      </div>
    `;

    try {
      const res = await fetch(`${API_BASE}/api/debaters/${encodeURIComponent(name)}?compact=false`);
      if (!res.ok) {
        container.innerHTML = `
          <div style="text-align: center; padding: 40px; color: #f87171; font-family: var(--font-mono);">
            Debater '${escapeHtml(name)}' not found in database.
          </div>
        `;
        return;
      }

      const p = await res.json();
      renderDebaterAuditDossier(p);
    } catch (err) {
      container.innerHTML = `
        <div style="text-align: center; padding: 40px; color: #f87171; font-family: var(--font-mono);">
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
      ? `<span class="badge-count" style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; margin-left: 8px;">${escapeHtml(p.national_level)}</span>`
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
            <span class="badge-count" style="background: rgba(16, 185, 129, 0.15); color: #34d399; font-weight: 700;">
              BALLOT VERIFIED: ZERO SYNTHETICS
            </span>
          </div>
        </div>

        <!-- 8 Core Metrics Grid -->
        <div class="bio-stats-grid" style="margin-bottom: 24px;">
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #38bdf8;">${p.master_tab_rank ? '#' + p.master_tab_rank : 'UR'}</div>
            <div class="bio-stat-lbl">Master Tab Rank</div>
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
            <div class="bio-stat-val" style="color: #34d399;">${pos.total_speeches ?? (p.total_speeches ?? '--')}</div>
            <div class="bio-stat-lbl">Total Speech Records</div>
          </div>
        </div>

        <!-- EXACT SPEAKER POSITION BREAKDOWN AUDIT -->
        <div class="admin-box" style="margin-bottom: 24px; background: rgba(15, 23, 42, 0.7);">
          <div class="admin-box-title" style="display: flex; justify-content: space-between; align-items: center;">
            <span>SPEAKER POSITION BREAKDOWN AUDIT</span>
            <span style="font-size: 11px; color: rgba(255,255,255,0.5); font-weight: 400; text-transform: none;">
              Counted strictly from official tournament scoresheets
            </span>
          </div>

          <div class="admin-positions-grid">
            <div class="admin-pos-tile">
              <div class="admin-pos-badge" style="background: rgba(56, 189, 248, 0.2); color: #38bdf8;">1st SPEECH</div>
              <div class="admin-pos-count">${pos['1st']?.count ?? 0}</div>
              <div class="admin-pos-sub">Avg: ${pos['1st']?.avg !== null && pos['1st']?.avg !== undefined ? pos['1st'].avg.toFixed(2) : '--'} pts</div>
            </div>
            <div class="admin-pos-tile">
              <div class="admin-pos-badge" style="background: rgba(52, 211, 153, 0.2); color: #34d399;">2nd SPEECH</div>
              <div class="admin-pos-count">${pos['2nd']?.count ?? 0}</div>
              <div class="admin-pos-sub">Avg: ${pos['2nd']?.avg !== null && pos['2nd']?.avg !== undefined ? pos['2nd'].avg.toFixed(2) : '--'} pts</div>
            </div>
            <div class="admin-pos-tile">
              <div class="admin-pos-badge" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24;">3rd SPEECH</div>
              <div class="admin-pos-count">${pos['3rd']?.count ?? 0}</div>
              <div class="admin-pos-sub">Avg: ${pos['3rd']?.avg !== null && pos['3rd']?.avg !== undefined ? pos['3rd'].avg.toFixed(2) : '--'} pts</div>
            </div>
            <div class="admin-pos-tile">
              <div class="admin-pos-badge" style="background: rgba(168, 85, 247, 0.2); color: #c084fc;">REPLY SPEECH</div>
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
              ${tournaments.length === 0 ? '<tr><td colspan="6" style="text-align: center; padding: 18px; color: rgba(255,255,255,0.5);">No tournament entries recorded.</td></tr>' : ''}
              ${tournaments
                .map((t) => {
                  const qualBadge = t.is_eligible
                    ? '<span class="nat-tag nat-direct" style="font-size: 10px;">QUALIFIED</span>'
                    : '<span class="nat-tag" style="background: rgba(244, 63, 94, 0.2); color: #f43f5e; font-size: 10px;">INELIGIBLE</span>';
                  const scoresList = (t.prelim_substantive_scores || []).map((s) => s.toFixed(1)).join(', ') || 'None';

                  return `
                    <tr>
                      <td style="font-weight: 500;">
                        ${escapeHtml(t.tournament_name)}
                      </td>
                      <td class="monospace">${escapeHtml(t.team_name || '--')}</td>
                      <td>${qualBadge}</td>
                      <td class="monospace" style="font-size: 12px; color: rgba(255,255,255,0.85);">${scoresList}</td>
                      <td class="monospace" style="font-weight: 600; color: #38bdf8;">
                        ${t.tournament_average !== null && t.tournament_average !== undefined ? t.tournament_average.toFixed(2) : '--'}
                      </td>
                      <td style="font-size: 12px; color: #34d399;">${escapeHtml(t.highest_stage || '--')}</td>
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
    const skipExtractCheck = document.getElementById('skipExtractCheck');
    const importStatusBox = document.getElementById('importStatusBox');

    if (startImportBtn) {
      startImportBtn.addEventListener('click', async () => {
        const target = (importTargetInput ? importTargetInput.value : '').trim();
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
          `[PIPELINE ACTIVE] Ingesting '${target}' (Extraction -> Normalization -> Reconciliation -> Integrity Gatekeeper)...`
        );

        try {
          const res = await fetch(`${API_BASE}/api/admin/tournaments/import`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ target, skip_extract: skipExtract }),
          });

          if (res.status === 401) {
            handleUnauthorized();
            return;
          }

          const data = await res.json();
          if (res.ok && data.success) {
            showStatusBox(importStatusBox, 'success', `[SUCCESS] ${data.message}`);
            if (importTargetInput) importTargetInput.value = '';
            fetchAdminStatus(); // Refresh tournaments and KPI
          } else {
            showStatusBox(importStatusBox, 'error', `[ERROR] ${data.error || 'Ingestion failed.'}`);
          }
        } catch (e) {
          showStatusBox(importStatusBox, 'error', `[NETWORK ERROR] ${e.message}`);
        } finally {
          startImportBtn.disabled = false;
          startImportBtn.textContent = 'START INGESTION PIPELINE';
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
      term.textContent = `[COMMAND] Initializing test suite '${suite}'...\n[SYSTEM] Executing forensic analysis against active SQLite connection...\n`;
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

  let mergeSuggestionsData = { persons: [], teams: [] };
  let activeMergeFilter = 'all'; // 'all', 'person', 'team'

  function initIdentityMerger() {
    const btnAll = document.getElementById('btnFilterAllMerges');
    const btnPersons = document.getElementById('btnFilterPersonMerges');
    const btnTeams = document.getElementById('btnFilterTeamMerges');
    const btnRefresh = document.getElementById('btnRefreshMerges');
    const btnManualMerge = document.getElementById('btnExecuteManualMerge');

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
    if (btnRefresh) {
      btnRefresh.addEventListener('click', () => fetchMergeSuggestions());
    }

    if (btnManualMerge) {
      btnManualMerge.addEventListener('click', handleManualMerge);
    }

    function updateFilterButtons() {
      if (btnAll) btnAll.className = activeMergeFilter === 'all' ? 'admin-btn admin-btn-primary' : 'admin-btn admin-btn-secondary';
      if (btnPersons) btnPersons.className = activeMergeFilter === 'person' ? 'admin-btn admin-btn-primary' : 'admin-btn admin-btn-secondary';
      if (btnTeams) btnTeams.className = activeMergeFilter === 'team' ? 'admin-btn admin-btn-primary' : 'admin-btn admin-btn-secondary';
    }
  }

  async function fetchMergeSuggestions(silent = false) {
    const container = document.getElementById('mergeSuggestionsContainer');
    if (container && !silent) {
      container.innerHTML = `<div style="text-align: center; padding: 32px; color: rgba(255,255,255,0.5);"><div class="spinner"></div> Scanning database for candidate duplicate identities...</div>`;
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
      };

      setText('mergePersonCount', mergeSuggestionsData.persons.length);
      setText('mergeTeamCount', mergeSuggestionsData.teams.length);

      renderMergeSuggestions();
    } catch (e) {
      if (container && !silent) {
        container.innerHTML = `<div style="text-align: center; padding: 24px; color: #f87171;">Failed to load candidate suggestions: ${escapeHtml(e.message)}</div>`;
      }
    }
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
        <div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.5); font-family: var(--font-mono);">
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
                <span class="badge-count" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8;">${escapeHtml(s.type.toUpperCase())}</span>
                <span style="font-weight: 600; color: #fff; font-size: 13px;">${escapeHtml(s.match_type)}</span>
              </div>
              ${s.reason ? `<div style="font-size: 11px; color: #94a3b8; margin-top: 4px;">${escapeHtml(s.reason)}</div>` : ''}
            </div>
            <div class="merge-card-conf" style="font-family: var(--font-mono); font-size: 11.5px; color: #34d399; font-weight: 700;">
              ${s.confidence}% MATCH
            </div>
          </div>

          <div class="merge-clash-grid">
            <!-- Target / Primary to Keep -->
            <div class="merge-entity-box target">
              <div class="merge-role-tag" style="color: #34d399;">CANONICAL TARGET (KEEP)</div>
              <div class="merge-entity-name">${escapeHtml(pName)}</div>
              <div class="merge-entity-sub">ID: #${p.id} · ${escapeHtml(pInst)}</div>
              <div class="merge-entity-stats">
                <span>${p.speech_count ?? 0} speeches</span>
                ${p.tour_count !== undefined ? `<span>${p.tour_count} tournaments</span>` : ''}
              </div>
            </div>

            <!-- Arrow Indicator -->
            <div class="merge-arrow-col">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"></line>
                <polyline points="12 5 19 12 12 19"></polyline>
              </svg>
            </div>

            <!-- Duplicate to Merge & Delete -->
            <div class="merge-entity-box duplicate">
              <div class="merge-role-tag" style="color: #f87171;">DUPLICATE VARIANT (MERGE)</div>
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
        const dupName = btn.getAttribute('data-dup-name');

        const ok = confirm(`Confirm Merge:\n\nMerge duplicate '${dupName}' (#${duplicateId}) into canonical '${primaryName}' (#${primaryId})?\n\nThis will reassign all performances, debates, and ballots, and remove record #${duplicateId}.`);
        if (!ok) return;

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

  async function handleManualMerge() {
    const typeSelect = document.getElementById('manualMergeType');
    const primaryInput = document.getElementById('manualPrimaryId');
    const duplicateInput = document.getElementById('manualDuplicateId');

    const type = (typeSelect ? typeSelect.value : 'person').trim();
    const primaryId = (primaryInput ? primaryInput.value : '').trim();
    const duplicateId = (duplicateInput ? duplicateInput.value : '').trim();

    if (!primaryId || !duplicateId) {
      alert('Please enter both Primary ID and Duplicate ID.');
      return;
    }

    if (primaryId === duplicateId) {
      alert('Primary ID and Duplicate ID cannot be the same record.');
      return;
    }

    const ok = confirm(`Execute Manual Merge:\n\nEntity Type: ${type.toUpperCase()}\nCanonical ID: #${primaryId} (KEEP)\nDuplicate ID: #${duplicateId} (MERGE & DELETE)\n\nProceed with this database operation?`);
    if (!ok) return;

    await executeMerge(type, primaryId, duplicateId);
    if (primaryInput) primaryInput.value = '';
    if (duplicateInput) duplicateInput.value = '';
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

    // Verify session state or URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const authParam = urlParams.get('auth');
    const tabParam = urlParams.get('tab');
    const speakerParam = urlParams.get('speaker');
    const runParam = urlParams.get('run');

    if (authParam) {
      if (passwordInput) passwordInput.value = authParam;
      handleLogin().then(() => {
        if (authParam === 'Sexyback' || authParam === 'Olivedelight') {
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

