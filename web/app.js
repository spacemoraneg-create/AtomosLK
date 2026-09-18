/**
 * ATOMOS V1 - CLIENT ENGINE & APPLICATION CONTROLLER
 * Powering Canva Home Page + Dedicated Tabbycat Subpages
 */

(function () {
  'use strict';

  // Global State
  const state = {
    criticalSpeakers: [],
    masterSpeakers: [],
    criticalTeams: [],
    masterTeams: [],
    institutions: [],
    activityDebaters: [],
    tournamentRankings: [],
    circuitSummary: null,
    searchIndex: [],
    activeFilter: 'all',
    searchQuery: '',
    prelimSearchQuery: '',
    isServerOnline: false,
    apiUrl: window.location.origin.includes('http') ? window.location.origin : 'http://127.0.0.1:5000',
  };

  // Debounce utility for silky-smooth responsive search
  function debounce(fn, delay = 50) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  // Helper: Format decimal numbers
  function fmt(val, decimals = 2) {
    if (val === undefined || val === null || isNaN(val)) return 'N/A';
    return Number(val).toFixed(decimals);
  }

  // Helper: National Status Tag HTML
  function getNatStatusTag(level) {
    if (!level) return '<span class="nat-tag nat-none">-</span>';
    const l = level.toLowerCase();
    if (l.includes('direct')) {
      return '<span class="nat-tag nat-direct">Nat Direct</span>';
    } else if (l.includes('trialed')) {
      return '<span class="nat-tag nat-trialed">Nat Trialed</span>';
    } else if (l.includes('trials')) {
      return '<span class="nat-tag nat-trials">Trials</span>';
    }
    return `<span class="nat-tag nat-trials">${level}</span>`;
  }

  // Helper: Rank Badge HTML
  function getRankBadge(rank) {
    let cls = 'rank-badge';
    if (rank === 1) cls += ' rank-1';
    else if (rank === 2) cls += ' rank-2';
    else if (rank === 3) cls += ' rank-3';
    return `<span class="${cls}">${rank}</span>`;
  }

  // Helper: Break Position Tag HTML
  function getBreakBadge(pos) {
    if (!pos || pos === '-') return '<span class="break-tag break-none">-</span>';
    const p = pos.trim().toLowerCase();
    if (p === 'champion') {
      return '<span class="break-tag break-champion">Champion</span>';
    } else if (p === 'finalist') {
      return '<span class="break-tag break-finalist">Finalist</span>';
    } else if (p === 'semifinalist') {
      return '<span class="break-tag break-semis">Semifinalist</span>';
    } else if (p === 'quarterfinalist') {
      return '<span class="break-tag break-quarters">Quarterfinalist</span>';
    } else if (p === 'octofinalist') {
      return '<span class="break-tag break-octos">Octofinalist</span>';
    } else if (p.includes('novice')) {
      return `<span class="break-tag break-novice">${escapeHtml(pos)}</span>`;
    }
    return `<span class="break-tag break-none">${escapeHtml(pos)}</span>`;
  }

  // Helper: Escape HTML
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Router / Initializer based on active page
  async function init() {
    await checkServerStatus();
    await loadInitialData();

    // Determine current page
    const path = window.location.pathname.toLowerCase();

    if (document.getElementById('criticalStatsTable') || path.endsWith('index.html') || path === '/' || path === '') {
      initHomePage();
    }
    if (document.getElementById('lbTableContainer') || path.includes('leaderboards')) {
      initLeaderboardsPage();
    }
    if (document.getElementById('bioProfileContainer') || path.includes('bio')) {
      initBioPage();
    }
    if (document.getElementById('h2hInputA') || document.getElementById('h2hSelectA') || path.includes('h2h')) {
      initH2HPage();
    }
    if (document.getElementById('chatMessages') || path.includes('chat')) {
      initChatPage();
    }
  }

  // Check if Flask Backend is online
  async function checkServerStatus() {
    try {
      const res = await fetch(`${state.apiUrl}/api/health`, { method: 'GET', signal: AbortSignal.timeout(1800) });
      if (res.ok) {
        state.isServerOnline = true;
        console.log('[ONLINE] Connected to Atomos Headless REST API Server');
      }
    } catch (e) {
      state.isServerOnline = false;
      console.log('[OFFLINE] Running in Static Archival Mode (offline JSON fallback)');
    }
  }

  // Fetch Core Datasets
  async function loadInitialData() {
    // 1. Critical Speaker Stats
    try {
      const res = await fetch('data/web_export/critical_speaker_stats.json');
      if (res.ok) state.criticalSpeakers = await res.json();
    } catch (e) {
      try {
        const res = await fetch('../data/web_export/critical_speaker_stats.json');
        if (res.ok) state.criticalSpeakers = await res.json();
      } catch (err) {}
    }

    if (state.criticalSpeakers.length === 0 && state.isServerOnline) {
      try {
        const res = await fetch(`${state.apiUrl}/api/leaderboard/speakers?limit=150`);
        if (res.ok) {
          const json = await res.json();
          state.criticalSpeakers = json.leaderboard || [];
        }
      } catch (e) {}
    }

    // 2. Circuit Summary
    try {
      const res = await fetch('data/web_export/circuit_summary.json');
      if (res.ok) state.circuitSummary = await res.json();
    } catch (e) {
      try {
        const res = await fetch('../data/web_export/circuit_summary.json');
        if (res.ok) state.circuitSummary = await res.json();
      } catch (err) {}
    }

    // 3. Master Speaker Tab
    try {
      const res = await fetch('data/web_export/master_speaker_tab.json');
      if (res.ok) state.masterSpeakers = await res.json();
    } catch (e) {
      try {
        const res = await fetch('../data/web_export/master_speaker_tab.json');
        if (res.ok) state.masterSpeakers = await res.json();
      } catch (err) {}
    }

    // 4. Institution Leaderboard
    try {
      const res = await fetch('data/web_export/institutional_power_index.json');
      if (res.ok) {
        const data = await res.json();
        state.institutions = Array.isArray(data.leaderboard) ? data.leaderboard : data;
      }
    } catch (e) {
      try {
        const res = await fetch('../data/web_export/institutional_power_index.json');
        if (res.ok) {
          const data = await res.json();
          state.institutions = Array.isArray(data.leaderboard) ? data.leaderboard : data;
        }
      } catch (err) {}
    }

    // 5. Team Leaderboard Datasets (Master & Critical)
    try {
      const res = await fetch('data/web_export/master_team_tab.json?v=2');
      if (res.ok) state.masterTeams = await res.json();
    } catch (e) {
      try {
        const res = await fetch('../data/web_export/master_team_tab.json?v=2');
        if (res.ok) state.masterTeams = await res.json();
      } catch (err) {}
    }

    try {
      const res = await fetch('data/web_export/critical_team_stats.json?v=2');
      if (res.ok) state.criticalTeams = await res.json();
    } catch (e) {
      try {
        const res = await fetch('../data/web_export/critical_team_stats.json?v=2');
        if (res.ok) state.criticalTeams = await res.json();
      } catch (err) {}
    }

    if (state.masterTeams.length === 0 && state.isServerOnline) {
      try {
        const res = await fetch(`${state.apiUrl}/api/leaderboard/teams?mode=master`);
        if (res.ok) {
          const json = await res.json();
          state.masterTeams = json.leaderboard || [];
        }
      } catch (e) {}
    }

    if (state.criticalTeams.length === 0 && state.isServerOnline) {
      try {
        const res = await fetch(`${state.apiUrl}/api/leaderboard/teams?mode=critical`);
        if (res.ok) {
          const json = await res.json();
          state.criticalTeams = json.leaderboard || [];
        }
      } catch (e) {}
    }

    // 6. Activity Leaderboard
    try {
      const res = await fetch('data/web_export/activity_leaderboard.json');
      if (res.ok) state.activityDebaters = await res.json();
    } catch (e) {
      try {
        const res = await fetch('../data/web_export/activity_leaderboard.json');
        if (res.ok) state.activityDebaters = await res.json();
      } catch (err) {}
    }
    if (state.activityDebaters.length === 0 && state.isServerOnline) {
      try {
        const res = await fetch(`${state.apiUrl}/api/leaderboard/activity`);
        if (res.ok) {
          const json = await res.json();
          state.activityDebaters = json.leaderboard || [];
        }
      } catch (e) {}
    }

    // 7. Tournament Quality Rankings
    try {
      const res = await fetch('data/web_export/tournament_rankings.json');
      if (res.ok) state.tournamentRankings = await res.json();
    } catch (e) {
      try {
        const res = await fetch('../data/web_export/tournament_rankings.json');
        if (res.ok) state.tournamentRankings = await res.json();
      } catch (err) {}
    }
    if (state.tournamentRankings.length === 0 && state.isServerOnline) {
      try {
        const res = await fetch(`${state.apiUrl}/api/leaderboard/tournaments`);
        if (res.ok) {
          const json = await res.json();
          state.tournamentRankings = json.leaderboard || [];
        }
      } catch (e) {}
    }
  }

  // ==========================================================================
  // 1. HOME PAGE LOGIC (Literal Canva Stack)
  // ==========================================================================
  function initHomePage() {
    updateVitals(state.circuitSummary);
    renderActivityTable();
    renderCriticalStatsTable();
    setupHomeFilters();
  }

  function updateVitals(data) {
    if (!data) return;
    const t = document.getElementById('vitalTournaments');
    const d = document.getElementById('vitalDebaters');
    const s = document.getElementById('vitalSpeeches');
    const r = document.getElementById('vitalRounds');
    const p = document.getElementById('vitalPrelims');
    const k = document.getElementById('vitalKnockouts');

    if (t) t.textContent = data.total_tournaments || 9;
    if (d) d.textContent = data.total_persons || 772;
    if (s) s.textContent = (data.total_valid_speeches ? Number(data.total_valid_speeches).toLocaleString() : '6,442');
    if (r) r.textContent = (data.total_debates_debated ? Number(data.total_debates_debated).toLocaleString() : '920');
    if (p) p.textContent = '760';
    if (k) k.textContent = '160';
  }

  function renderActivityTable() {
    const tbody = document.getElementById('activityStatsBody');
    if (!tbody) return;

    // Rank by prelim_rounds_debated descending across the entire circuit
    const allDebaters = (state.criticalSpeakers.length > 0 ? state.criticalSpeakers : state.masterSpeakers)
      .slice()
      .sort((a, b) => {
        const pDiff = (b.prelim_rounds_debated || 0) - (a.prelim_rounds_debated || 0);
        if (pDiff !== 0) return pDiff;
        const wDiff = (b.win_rate_debated || b.win_rate || 0) - (a.win_rate_debated || a.win_rate || 0);
        if (wDiff !== 0) return wDiff;
        return (b.speech_avg || b.avg || 0) - (a.speech_avg || a.avg || 0);
      });

    // Assign true overall rank in circuit
    const allWithRank = allDebaters.map((s, idx) => ({ ...s, prelimRank: idx + 1 }));

    let items = allWithRank;
    const q = (state.prelimSearchQuery || '').toLowerCase().trim();

    // If search entered, filter across ALL debaters in circuit (within and beyond top 20)
    if (q) {
      items = items.filter(
        (s) =>
          (s.speaker_name && s.speaker_name.toLowerCase().includes(q)) ||
          (s.institution && s.institution.toLowerCase().includes(q))
      );
    }

    // Default to Top 20 when search is empty; show all matches when searching
    const displayed = q ? items : items.slice(0, 20);

    const badge = document.getElementById('activityCountBadge');
    if (badge) {
      badge.textContent = q ? `${items.length} MATCHES` : 'TOP 20';
    }

    if (displayed.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 24px; color: rgba(255,255,255,0.6);">No debaters match "${escapeHtml(q)}".</td></tr>`;
      return;
    }

    tbody.innerHTML = displayed
      .map((s) => {
        const prelims = s.prelim_rounds_debated || 0;
        const win = fmt(s.win_rate_debated || s.win_rate, 1) + '%';
        const nat = getNatStatusTag(s.national_level);

        return `
        <tr class="clickable-row" onclick="window.location.href='bio.html?speaker=${encodeURIComponent(s.speaker_name)}'">
          <td>${getRankBadge(s.prelimRank)}</td>
          <td style="font-weight: 700; color: #ffffff;">${escapeHtml(s.speaker_name)}</td>
          <td style="color: rgba(255,255,255,0.75);">${escapeHtml(s.institution || 'Independent')}</td>
          <td style="text-align: right; font-family: var(--font-mono); font-weight: 800; color: #38bdf8; font-size: 13px;">${prelims}</td>
          <td style="text-align: right; font-family: var(--font-mono);">${win}</td>
          <td>${nat}</td>
        </tr>
      `;
      })
      .join('');
  }

  function renderCriticalStatsTable() {
    const tbody = document.getElementById('criticalStatsBody');
    if (!tbody) return;

    let items = state.criticalSpeakers.slice();
    const q = (state.searchQuery || '').toLowerCase().trim();

    // Search query: filters across ALL debaters in circuit (within and beyond top 50)
    if (q) {
      items = items.filter(
        (s) =>
          (s.speaker_name && s.speaker_name.toLowerCase().includes(q)) ||
          (s.institution && s.institution.toLowerCase().includes(q))
      );
    }

    // Default to Top 50 when search is empty; show all matches when searching
    const displayed = q ? items : items.slice(0, 50);

    const badge = document.getElementById('speakerCountBadge');
    if (badge) {
      badge.textContent = q ? `${items.length} MATCHES` : 'TOP 50';
    }

    if (displayed.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 24px; color: rgba(255,255,255,0.6);">No debaters match "${escapeHtml(q)}".</td></tr>`;
      return;
    }

    tbody.innerHTML = displayed
      .map((s, idx) => {
        const rank = s.rank || idx + 1;
        const avg = fmt(s.speech_avg || s.avg || s.cumulative_speech_avg);
        const win = fmt(s.win_rate_debated || s.win_rate, 1) + '%';
        const prelims = s.prelim_rounds_debated !== undefined ? s.prelim_rounds_debated : '-';
        const breakPct = s.break_percentage !== undefined ? fmt(s.break_percentage, 1) + '%' : '-';
        const nat = getNatStatusTag(s.national_level);
        const tourneys = s.eligible_tournaments !== undefined ? s.eligible_tournaments : (s.tournaments_debated || '-');

        return `
        <tr class="clickable-row" onclick="window.location.href='bio.html?speaker=${encodeURIComponent(s.speaker_name)}'">
          <td>${getRankBadge(rank)}</td>
          <td style="font-weight: 700; color: #ffffff;">${escapeHtml(s.speaker_name)}</td>
          <td style="color: rgba(255,255,255,0.75);">${escapeHtml(s.institution || 'Independent')}</td>
          <td>${nat}</td>
          <td style="text-align: right; font-family: var(--font-mono); font-weight: 800; color: #38bdf8;">${avg}</td>
          <td style="text-align: right; font-family: var(--font-mono);">${win}</td>
          <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${prelims}</td>
          <td style="text-align: right; font-family: var(--font-mono); color: #34d399;">${breakPct}</td>
          <td style="text-align: right; font-family: var(--font-mono); color: #38bdf8; font-weight: 700;">${tourneys}</td>
        </tr>
      `;
      })
      .join('');
  }

  function setupHomeFilters() {
    const speakerSearch = document.getElementById('speakerSearchInput');
    if (speakerSearch) {
      speakerSearch.addEventListener(
        'input',
        debounce((e) => {
          state.searchQuery = e.target.value.trim();
          renderCriticalStatsTable();
        }, 50)
      );
    }

    const prelimSearch = document.getElementById('prelimSearchInput');
    if (prelimSearch) {
      prelimSearch.addEventListener(
        'input',
        debounce((e) => {
          state.prelimSearchQuery = e.target.value.trim();
          renderActivityTable();
        }, 50)
      );
    }
  }

  // ==========================================================================
  // 2. LEADERBOARDS PAGE
  // ==========================================================================
  let activeLeaderboardTab = 'individual';
  let activeIndividualMode = 'master'; // 'master' or 'critical'

  function initLeaderboardsPage() {
    const tabBtns = document.querySelectorAll('.subpage-tab-btn');
    const modeSwitcher = document.getElementById('individualModeSwitcher');

    function updateSwitcherVisibility() {
      if (modeSwitcher) {
        modeSwitcher.style.display =
          (activeLeaderboardTab === 'individual' || activeLeaderboardTab === 'speakers')
            ? 'inline-flex'
            : 'none';
      }
    }

    // Support URL tab parameter or hash e.g. ?tab=teams or ?tab=institutions
    const urlParams = new URLSearchParams(window.location.search);
    const tabParam = urlParams.get('tab') || window.location.hash.replace('#', '');
    if (tabParam) {
      const matchBtn = Array.from(tabBtns).find(b => b.getAttribute('data-tab') === tabParam);
      if (matchBtn) {
        tabBtns.forEach(b => b.classList.remove('active'));
        matchBtn.classList.add('active');
        activeLeaderboardTab = tabParam;
        updateSwitcherVisibility();
      }
    }

    const modeParam = urlParams.get('mode');
    if (modeParam && (modeParam === 'master' || modeParam === 'critical')) {
      activeIndividualMode = modeParam;
    }

    tabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        tabBtns.forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        activeLeaderboardTab = btn.getAttribute('data-tab');
        updateSwitcherVisibility();
        renderLeaderboardView();
      });
    });

    const modeBtns = document.querySelectorAll('.mode-switch-btn');
    modeBtns.forEach((btn) => {
      if (btn.getAttribute('data-mode') === activeIndividualMode) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
      btn.addEventListener('click', () => {
        modeBtns.forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        activeIndividualMode = btn.getAttribute('data-mode');
        renderLeaderboardView();
      });
    });

    const searchInput = document.getElementById('lbSearchInput');
    const searchParam = urlParams.get('q') || urlParams.get('search');
    if (searchParam && searchInput) {
      searchInput.value = searchParam;
    }
    if (searchInput) {
      searchInput.addEventListener('input', debounce(renderLeaderboardView, 50));
    }

    renderLeaderboardView();
  }

  async function renderLeaderboardView() {
    const container = document.getElementById('lbTableContainer');
    const searchInput = document.getElementById('lbSearchInput');
    const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    const badge = document.getElementById('lbCountBadge');
    if (!container) return;

    if (activeLeaderboardTab === 'individual' || activeLeaderboardTab === 'speakers') {
      if (activeIndividualMode === 'master') {
        let speakers = state.masterSpeakers.slice();
        if (query) {
          speakers = speakers.filter(
            (s) =>
              (s.speaker_name && s.speaker_name.toLowerCase().includes(query)) ||
              (s.institution_name && s.institution_name.toLowerCase().includes(query)) ||
              (s.institution && s.institution.toLowerCase().includes(query))
          );
        }

        if (badge) {
          badge.textContent = query ? `${speakers.length} MATCHES` : `${speakers.length} DEBATERS`;
        }

        if (speakers.length === 0) {
          container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">No debaters match "${escapeHtml(query)}".</div>`;
          return;
        }

        container.innerHTML = `
          <div class="data-table-wrap">
            <table class="atomos-table">
              <thead>
                <tr>
                  <th style="width: 44px; text-align: center;">#</th>
                  <th style="width: 20%;">DEBATER</th>
                  <th style="width: 21%;">INSTITUTION</th>
                  <th style="width: 11%;">NAT STATUS</th>
                  <th style="width: 10%; text-align: right;">SPK AVG</th>
                  <th style="width: 8%; text-align: right;">WIN %</th>
                  <th style="width: 8%; text-align: right;">PRELIMS</th>
                  <th style="width: 9%; text-align: right;">BREAK %</th>
                  <th style="width: 10%; text-align: right;">TOURNAMENTS</th>
                </tr>
              </thead>
              <tbody>
                ${speakers.map((s, idx) => {
                  const rank = s.rank || idx + 1;
                  const avg = fmt(s.speaker_avg || s.speech_avg || s.master_score || s.speech_average);
                  const win = fmt(s.win_percentage || s.win_rate || s.win_rate_debated, 1) + '%';
                  const prelims = s.prelims !== undefined ? s.prelims : (s.total_rounds || s.prelim_rounds_debated || '-');
                  const breakPct = s.break_percentage !== undefined ? fmt(s.break_percentage, 1) + '%' : '-';
                  const nat = getNatStatusTag(s.national_level);
                  const tourneys = s.tournaments !== undefined ? s.tournaments : (s.eligible_tournaments || '-');
                  const spkName = s.speaker_name || '';
                  const instName = s.institution || s.institution_name || 'Independent';

                  return `
                  <tr class="clickable-row" onclick="window.location.href='bio.html?speaker=${encodeURIComponent(spkName)}'">
                    <td style="text-align: center;">${getRankBadge(rank)}</td>
                    <td style="font-weight: 700; color: #ffffff;" title="${escapeHtml(spkName)}">${escapeHtml(spkName)}</td>
                    <td style="color: rgba(255,255,255,0.75);" title="${escapeHtml(instName)}">${escapeHtml(instName)}</td>
                    <td>${nat}</td>
                    <td style="text-align: right; font-family: var(--font-mono); font-weight: 800; color: #38bdf8;">${avg}</td>
                    <td style="text-align: right; font-family: var(--font-mono);">${win}</td>
                    <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${prelims}</td>
                    <td style="text-align: right; font-family: var(--font-mono); color: #34d399;">${breakPct}</td>
                    <td style="text-align: right; font-family: var(--font-mono); color: #38bdf8; font-weight: 700;">${tourneys}</td>
                  </tr>
                `;
                }).join('')}
              </tbody>
            </table>
          </div>
        `;
      } else {
        // Critical Tab Individual Leaderboard (Minimum 3 eligible tournaments)
        let speakers = state.criticalSpeakers.slice();
        if (query) {
          speakers = speakers.filter(
            (s) =>
              (s.speaker_name && s.speaker_name.toLowerCase().includes(query)) ||
              (s.institution && s.institution.toLowerCase().includes(query)) ||
              (s.institution_name && s.institution_name.toLowerCase().includes(query))
          );
        }

        if (badge) {
          badge.textContent = query ? `${speakers.length} MATCHES` : `${speakers.length} DEBATERS`;
        }

        if (speakers.length === 0) {
          container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">No debaters match "${escapeHtml(query)}".</div>`;
          return;
        }

        container.innerHTML = `
          <div class="data-table-wrap">
            <table class="atomos-table">
              <thead>
                <tr>
                  <th style="width: 44px; text-align: center;">#</th>
                  <th style="width: 20%;">DEBATER</th>
                  <th style="width: 21%;">INSTITUTION</th>
                  <th style="width: 11%;">NAT STATUS</th>
                  <th style="width: 10%; text-align: right;">SPK AVG</th>
                  <th style="width: 8%; text-align: right;">WIN %</th>
                  <th style="width: 8%; text-align: right;">PRELIMS</th>
                  <th style="width: 9%; text-align: right;">BREAK %</th>
                  <th style="width: 10%; text-align: right;">TOURNAMENTS</th>
                </tr>
              </thead>
              <tbody>
                ${speakers.map((s, idx) => {
                  const rank = s.rank || idx + 1;
                  const avg = fmt(s.speaker_avg || s.speech_avg || s.avg || s.cumulative_speech_avg);
                  const win = fmt(s.win_percentage || s.win_rate_debated || s.win_rate, 1) + '%';
                  const prelims = s.prelims !== undefined ? s.prelims : (s.prelim_rounds_debated || '-');
                  const breakPct = s.break_percentage !== undefined ? fmt(s.break_percentage, 1) + '%' : '-';
                  const nat = getNatStatusTag(s.national_level);
                  const tourneys = s.tournaments !== undefined ? s.tournaments : (s.eligible_tournaments || '-');
                  const spkName = s.speaker_name || '';
                  const instName = s.institution || s.institution_name || 'Independent';

                  return `
                  <tr class="clickable-row" onclick="window.location.href='bio.html?speaker=${encodeURIComponent(spkName)}'">
                    <td style="text-align: center;">${getRankBadge(rank)}</td>
                    <td style="font-weight: 700; color: #ffffff;" title="${escapeHtml(spkName)}">${escapeHtml(spkName)}</td>
                    <td style="color: rgba(255,255,255,0.75);" title="${escapeHtml(instName)}">${escapeHtml(instName)}</td>
                    <td>${nat}</td>
                    <td style="text-align: right; font-family: var(--font-mono); font-weight: 800; color: #38bdf8;">${avg}</td>
                    <td style="text-align: right; font-family: var(--font-mono);">${win}</td>
                    <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${prelims}</td>
                    <td style="text-align: right; font-family: var(--font-mono); color: #34d399;">${breakPct}</td>
                    <td style="text-align: right; font-family: var(--font-mono); color: #38bdf8; font-weight: 700;">${tourneys}</td>
                  </tr>
                `;
                }).join('')}
              </tbody>
            </table>
          </div>
        `;
      }
    } else if (activeLeaderboardTab === 'teams') {
      // Team Leaderboard (Unified Tab: minimum 3 tournaments debated)
      if (state.masterTeams.length === 0) {
        try {
          const res = await fetch('data/web_export/master_team_tab.json?v=3');
          if (res.ok) state.masterTeams = await res.json();
        } catch (e) {
          try {
            const res = await fetch('../data/web_export/master_team_tab.json?v=3');
            if (res.ok) state.masterTeams = await res.json();
          } catch (err) {}
        }
      }

      let teams = state.masterTeams.slice();

      if (query) {
        teams = teams.filter((t) => {
          const name = (t.team_name || '').toLowerCase();
          const inst = (t.institution || '').toLowerCase();
          return name.includes(query) || inst.includes(query);
        });
      }

      if (badge) {
        badge.textContent = query ? `${teams.length} MATCHES` : `${teams.length} CIRCUIT TEAMS`;
      }

      if (teams.length === 0) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">No teams match "${escapeHtml(query)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 44px; text-align: center;">#</th>
                <th style="width: 24%;">TEAM</th>
                <th style="width: 10%; text-align: right;">ATSS</th>
                <th style="width: 10%; text-align: right;">WIN %</th>
                <th style="width: 10%; text-align: right;">BREAK %</th>
                <th style="width: 17%; text-align: center;">HIGHEST ACHIEVEMENT</th>
                <th style="width: 12%; text-align: right;">TOURNAMENTS</th>
                <th style="width: 13%; text-align: right;">WIN/LOSS MARGIN</th>
              </tr>
            </thead>
            <tbody>
              ${teams.map((t, idx) => {
                const rank = t.rank || idx + 1;
                const atss = fmt(t.atss, 2);
                const winPct = fmt(t.win_percentage, 1) + '%';
                const breakPct = fmt(t.break_percentage, 1) + '%';
                const achBadge = getBreakBadge(t.highest_achievement || t.highest_break);
                const tourneys = t.tournaments_debated !== undefined ? t.tournaments_debated : (t.tournaments_count || 0);

                // Single signed Net Margin formatting
                const netM = t.net_margin !== undefined ? t.net_margin : 0;
                let marginHtml = '';
                if (netM > 0) {
                  marginHtml = `<span class="margin-win">+${fmt(netM, 2)}</span>`;
                } else if (netM < 0) {
                  marginHtml = `<span class="margin-loss">${fmt(netM, 2)}</span>`;
                } else {
                  marginHtml = `<span class="margin-none">0.00</span>`;
                }

                return `
                  <tr class="clickable-row" onclick="window.location.href='h2h.html?team=${encodeURIComponent(t.team_name)}'">
                    <td style="text-align: center;">${getRankBadge(rank)}</td>
                    <td title="${escapeHtml(t.team_name)} (${escapeHtml(t.institution || 'Independent')})">
                      <div style="font-weight: 700; color: #ffffff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(t.team_name)}</div>
                      <div style="font-size: 11.5px; color: rgba(255,255,255,0.55); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(t.institution || 'Independent')}</div>
                    </td>
                    <td style="text-align: right; font-family: var(--font-mono); font-weight: 800; color: #38bdf8;">${atss}</td>
                    <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${winPct}</td>
                    <td style="text-align: right; font-family: var(--font-mono); color: #34d399; font-weight: 700;">${breakPct}</td>
                    <td style="text-align: center;">${achBadge}</td>
                    <td style="text-align: right; font-family: var(--font-mono); color: #38bdf8; font-weight: 700;">${tourneys}</td>
                    <td style="text-align: right;" class="margin-cell" title="Net Differential: ${t.net_margin >= 0 ? '+' : ''}${fmt(t.net_margin, 2)}">${marginHtml}</td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    } else if (activeLeaderboardTab === 'institutions') {
      let insts = state.institutions || [];
      if (!insts || insts.length === 0) {
        try {
          const res = await fetch('data/web_export/institutional_power_index.json?v=3');
          if (res.ok) insts = await res.json();
        } catch (e) {
          try {
            const res = await fetch('../data/web_export/institutional_power_index.json?v=3');
            if (res.ok) insts = await res.json();
          } catch (err) {}
        }
        if (insts && Array.isArray(insts.leaderboard)) insts = insts.leaderboard;
        state.institutions = insts || [];
      }

      let filtered = (state.institutions || []).slice();
      if (query) {
        filtered = filtered.filter((i) => {
          const name = (i.name || i.institution_name || '').toLowerCase();
          const code = (i.code || '').toLowerCase();
          return name.includes(query) || code.includes(query);
        });
      }

      // Cap displayed schools to Top 20 when not filtering, or all matching results when search query is active
      const displayed = query ? filtered : filtered.slice(0, 20);

      if (badge) {
        badge.textContent = query ? `${filtered.length} MATCHES` : `TOP 20 SCHOOLS`;
      }

      if (displayed.length === 0) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">No institutions match "${escapeHtml(query)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 44px; text-align: center;">#</th>
                <th style="width: 25%;">NAME OF SCHOOL</th>
                <th style="width: 9%; text-align: right;" title="Institutional Delta Formula: Diminishing-weight harmonic combination of school teams">DELTA</th>
                <th style="width: 10%; text-align: right;">A TEAM ATSS</th>
                <th style="width: 10%; text-align: right;">B TEAM ATSS</th>
                <th style="width: 10%; text-align: right;">NET DIFF</th>
                <th style="width: 11%; text-align: right;">TOURNAMENTS</th>
                <th style="width: 9%; text-align: right;">BREAK %</th>
                <th style="width: 13%; text-align: center;">HIGHEST BREAK</th>
              </tr>
            </thead>
            <tbody>
              ${displayed.map((i, idx) => {
                const rank = i.rank || idx + 1;
                const delta = i.delta !== undefined && i.delta !== null ? fmt(i.delta, 2) : (i.atiss ? fmt(i.atiss, 2) : '-');
                const aAtss = i.a_atss !== undefined && i.a_atss !== null ? fmt(i.a_atss, 2) : '-';
                const bAtss = i.b_atss !== undefined && i.b_atss !== null ? fmt(i.b_atss, 2) : '-';
                let netDiffHtml = '-';
                if (i.net_diff !== null && i.net_diff !== undefined) {
                  const nd = Number(i.net_diff);
                  const sign = nd > 0 ? '+' : '';
                  netDiffHtml = `<span style="font-family: var(--font-mono); font-weight: 700; color: ${nd >= 0 ? '#34d399' : '#f87171'};">${sign}${fmt(nd, 2)}</span>`;
                }
                const tours = i.tournaments_existed !== undefined ? i.tournaments_existed : (i.tournaments_debated || '-');
                const breakPct = i.break_percentage !== undefined ? fmt(i.break_percentage, 1) + '%' : '-';
                const highestPos = getBreakBadge(i.highest_break || i.highest_achievement);
                const instName = i.name || i.institution_name || '';

                return `
                <tr>
                  <td style="text-align: center;">${getRankBadge(rank)}</td>
                  <td style="font-weight: 700; color: #ffffff;" title="${escapeHtml(instName)}">
                    ${escapeHtml(instName)}
                    ${i.code ? `<span style="font-size: 11px; margin-left: 6px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.7); font-family: var(--font-mono);">${escapeHtml(i.code)}</span>` : ''}
                  </td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: 800; color: #38bdf8;">${delta}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${aAtss}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${bAtss}</td>
                  <td style="text-align: right;">${netDiffHtml}</td>
                  <td style="text-align: right; font-family: var(--font-mono); color: #38bdf8; font-weight: 700;">${tours}</td>
                  <td style="text-align: right; font-family: var(--font-mono); color: #34d399; font-weight: 700;">${breakPct}</td>
                  <td style="text-align: center;">${highestPos}</td>
                </tr>
              `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    } else if (activeLeaderboardTab === 'activity') {
      if (!state.activityDebaters || state.activityDebaters.length === 0) {
        try {
          const res = await fetch('data/web_export/activity_leaderboard.json');
          if (res.ok) state.activityDebaters = await res.json();
        } catch (e) {
          try {
            const res = await fetch('../data/web_export/activity_leaderboard.json');
            if (res.ok) state.activityDebaters = await res.json();
          } catch (err) {}
        }
      }

      let debaters = (state.activityDebaters || []).slice();
      if (query) {
        debaters = debaters.filter((s) => {
          const name = (s.debater_name || '').toLowerCase();
          const inst = (s.institution || '').toLowerCase();
          return name.includes(query) || inst.includes(query);
        });
      }

      if (debaters.length === 0) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">No active debaters match "${escapeHtml(query)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 44px; text-align: center;">#</th>
                <th style="width: 28%;">DEBATER</th>
                <th style="width: 28%;">INSTITUTION</th>
                <th style="width: 14%; text-align: right;">PRELIMS</th>
                <th style="width: 14%; text-align: right;">TOURNAMENTS</th>
                <th style="width: 16%; text-align: right;">ASS</th>
              </tr>
            </thead>
            <tbody>
              ${debaters.map((s, idx) => {
                const rank = s.rank || idx + 1;
                const spkName = s.debater_name || '';
                const instName = s.institution || 'Independent';
                const prelims = s.prelims_debated !== undefined ? s.prelims_debated : '-';
                const tours = s.tournaments_debated !== undefined ? s.tournaments_debated : '-';
                const ass = fmt(s.ass, 2);

                return `
                <tr class="clickable-row" onclick="window.location.href='bio.html?speaker=${encodeURIComponent(spkName)}'">
                  <td style="text-align: center;">${getRankBadge(rank)}</td>
                  <td style="font-weight: 700; color: #ffffff;" title="${escapeHtml(spkName)}">${escapeHtml(spkName)}</td>
                  <td style="color: rgba(255,255,255,0.75);" title="${escapeHtml(instName)}">${escapeHtml(instName)}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: 800; color: #38bdf8;">${prelims}</td>
                  <td style="text-align: right; font-family: var(--font-mono); color: #ffffff; font-weight: 600;">${tours}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: 700; color: #34d399;">${ass}</td>
                </tr>
              `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    } else if (activeLeaderboardTab === 'tournaments') {
      if (!state.tournamentRankings || state.tournamentRankings.length === 0) {
        try {
          const res = await fetch('data/web_export/tournament_rankings.json');
          if (res.ok) state.tournamentRankings = await res.json();
        } catch (e) {
          try {
            const res = await fetch('../data/web_export/tournament_rankings.json');
            if (res.ok) state.tournamentRankings = await res.json();
          } catch (err) {}
        }
      }

      let tours = (state.tournamentRankings || []).slice();
      if (query) {
        tours = tours.filter((t) => {
          const name = (t.tournament_name || '').toLowerCase();
          const dates = (t.dates || '').toLowerCase();
          const bs = (t.break_structure || '').toLowerCase();
          return name.includes(query) || dates.includes(query) || bs.includes(query);
        });
      }

      if (tours.length === 0) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">No tournaments match "${escapeHtml(query)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 44px; text-align: center; padding: 12px 4px;">#</th>
                <th style="width: 21%;">TOURNAMENT</th>
                <th style="width: 13%;">DATES</th>
                <th style="width: 9%; text-align: right; padding: 12px 4px;">APTTSS</th>
                <th style="width: 10%; text-align: right; padding: 12px 4px;">BRK APTTSS</th>
                <th style="width: 6%; text-align: right; padding: 12px 4px;">TEAMS</th>
                <th style="width: 6%; text-align: right; padding: 12px 4px;">RNDS</th>
                <th style="width: 17%; text-align: center;">BREAK STAGE</th>
                <th style="width: 8%; text-align: right; padding: 12px 4px;">SPEECHES</th>
                <th style="width: 8%; text-align: right; padding: 12px 6px;">DEBATES</th>
              </tr>
            </thead>
            <tbody>
              ${tours.map((t, idx) => {
                const rank = t.rank || idx + 1;
                const tName = t.tournament_name || '';
                const dates = t.dates || 'TBD';
                const apttss = fmt(t.apttss, 2);
                const apttssBreak = t.apttss_breaking ? fmt(t.apttss_breaking, 2) : '-';
                const teams = t.teams_participated !== undefined ? t.teams_participated : '-';
                const prelimRounds = t.prelim_rounds !== undefined ? t.prelim_rounds : '-';
                const breakStruct = t.break_structure || 'No Breaks';
                const speeches = t.speeches_count !== undefined ? t.speeches_count : '-';
                const debates = t.debates_count !== undefined ? t.debates_count : '-';

                return `
                <tr>
                  <td style="text-align: center; padding: 10px 2px;">${getRankBadge(rank)}</td>
                  <td style="font-weight: 700; color: #ffffff;" title="${escapeHtml(tName)}">${escapeHtml(tName)}</td>
                  <td style="color: rgba(255,255,255,0.75); font-family: var(--font-mono); font-size: 11.5px;">${escapeHtml(dates)}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: 800; color: #38bdf8;">${apttss}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: 700; color: #34d399;">${apttssBreak}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: 600;">${teams}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: 600;">${prelimRounds}</td>
                  <td style="text-align: center; padding: 10px 4px;">
                    <span class="break-tag break-semis" style="font-size: 10px; padding: 3px 6px; white-space: nowrap;">${escapeHtml(breakStruct)}</span>
                  </td>
                  <td style="text-align: right; font-family: var(--font-mono); color: rgba(255,255,255,0.75);">${speeches}</td>
                  <td style="text-align: right; font-family: var(--font-mono); color: #38bdf8; font-weight: 700;">${debates}</td>
                </tr>
              `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    }
  }

  // ==========================================================================
  // 3. BIO ENGINE PAGE (8 Core Circuit Metrics & Pure Debater Dossier)
  // ==========================================================================
  function renderBioEmptyState() {
    const container = document.getElementById('bioProfileContainer');
    const input = document.getElementById('bioSearchInput');
    const clearBtn = document.getElementById('bioClearBtn');
    if (input) input.value = '';
    if (clearBtn) clearBtn.classList.add('hidden');
    if (container) {
      container.innerHTML = `
        <div class="bio-empty-state" style="text-align: center; padding: 64px 20px; color: rgba(255,255,255,0.5); font-family: var(--font-mono);">
          <div style="font-size: 16px; color: #38bdf8; margin-bottom: 8px; font-weight: 600; letter-spacing: 0.06em;">ATOMOS BIO ENGINE // CAREER DOSSIER</div>
          <div style="font-size: 13px; max-width: 480px; margin: 0 auto; line-height: 1.6; color: rgba(255,255,255,0.65);">
            Type any debater's name or institution in the search box above to inspect their 8 core performance metrics, tournament trajectory, and circuit adjudication record.
          </div>
        </div>
      `;
    }
    if (window.history.replaceState) {
      window.history.replaceState(null, '', window.location.pathname);
    }
  }

  function initBioPage() {
    setupBioSearchInput();

    // Check URL parameters (e.g. bio.html?speaker=Vidath+Marasinghe)
    const urlParams = new URLSearchParams(window.location.search);
    const speakerParam = urlParams.get('speaker') || urlParams.get('name') || urlParams.get('id');

    // Never autoload Kulith or default debaters
    if (speakerParam && !speakerParam.toLowerCase().includes('kulith')) {
      loadDebaterDossier(speakerParam);
    } else {
      if (speakerParam && speakerParam.toLowerCase().includes('kulith') && window.history.replaceState) {
        window.history.replaceState(null, '', window.location.pathname);
      }
      renderBioEmptyState();
    }
  }

  function setupBioSearchInput() {
    const input = document.getElementById('bioSearchInput');
    const dropdown = document.getElementById('bioSuggestions');
    const clearBtn = document.getElementById('bioClearBtn');
    if (!input || !dropdown) return;

    function renderMatches(q) {
      const allDebaters = getAllDebatersList();
      const query = (q || '').trim().toLowerCase();
      let matches = allDebaters;
      if (query) {
        matches = allDebaters.filter(
          (d) => d.name.toLowerCase().includes(query) || (d.institution && d.institution.toLowerCase().includes(query))
        );
      }
      matches = matches.slice(0, 15);

      if (matches.length === 0) {
        dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255,255,255,0.5); font-size: 13px; text-align: center;">No matching debaters found in identity base.</div>`;
        dropdown.classList.remove('hidden');
        return;
      }

      dropdown.innerHTML = matches
        .map(
          (d, idx) => `
        <div class="bio-autocomplete-item${idx === 0 ? ' active' : ''}" data-name="${escapeHtml(d.name)}">
          <div>
            <div class="bio-auto-name">${escapeHtml(d.name)}</div>
            <div class="bio-auto-inst">${escapeHtml(d.institution || 'Independent')}</div>
          </div>
          <div class="bio-auto-meta">
            <span class="bio-auto-stat">${d.speaker_avg ? `Avg: ${Number(d.speaker_avg).toFixed(2)}` : ''}</span>
            <span style="font-size: 10px; color: rgba(255,255,255,0.4);">${d.prelims || 0} Prelims</span>
          </div>
        </div>
      `
        )
        .join('');

      dropdown.classList.remove('hidden');

      dropdown.querySelectorAll('.bio-autocomplete-item').forEach((el) => {
        el.addEventListener('mousedown', (e) => {
          e.preventDefault();
          e.stopPropagation();
          const name = el.getAttribute('data-name');
          selectDebater(name);
        });
      });
    }

    input.addEventListener('input', () => {
      if (clearBtn) {
        if (input.value) clearBtn.classList.remove('hidden');
        else clearBtn.classList.add('hidden');
      }
      renderMatches(input.value);
    });

    input.addEventListener('focus', () => {
      renderMatches(input.value);
    });

    input.addEventListener('blur', () => {
      setTimeout(() => {
        dropdown.classList.add('hidden');
        dropdown.innerHTML = '';
      }, 150);
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        dropdown.classList.add('hidden');
        dropdown.innerHTML = '';
        input.blur();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const activeItem = dropdown.querySelector('.bio-autocomplete-item.active') || dropdown.querySelector('.bio-autocomplete-item');
        if (activeItem) {
          const name = activeItem.getAttribute('data-name');
          selectDebater(name);
        } else {
          dropdown.classList.add('hidden');
          dropdown.innerHTML = '';
          input.blur();
        }
      } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const items = Array.from(dropdown.querySelectorAll('.bio-autocomplete-item'));
        if (items.length === 0) return;
        let activeIdx = items.findIndex((el) => el.classList.contains('active'));
        if (e.key === 'ArrowDown') {
          activeIdx = (activeIdx + 1) % items.length;
        } else {
          activeIdx = (activeIdx - 1 + items.length) % items.length;
        }
        items.forEach((el, idx) => {
          el.classList.toggle('active', idx === activeIdx);
          if (idx === activeIdx) el.scrollIntoView({ block: 'nearest' });
        });
      }
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        renderBioEmptyState();
        dropdown.classList.add('hidden');
        dropdown.innerHTML = '';
        input.focus();
        renderMatches('');
      });
    }

    // Dismiss on outside click
    document.addEventListener('pointerdown', (e) => {
      if (!e.target.closest('.bio-search-wrap')) {
        dropdown.classList.add('hidden');
        dropdown.innerHTML = '';
      }
    });
  }

  function getMasterRank(debaterName) {
    if (!debaterName) return null;
    const m = (state.masterSpeakers || []).find(
      (s) =>
        (s.speaker_name && s.speaker_name.toLowerCase() === debaterName.toLowerCase()) ||
        (s.canonical_name && s.canonical_name.toLowerCase() === debaterName.toLowerCase())
    );
    return m ? (m.rank || null) : null;
  }

  function derivePositionsFromTournaments(tournaments) {
    const pos = {
      '1st': { count: 0, avg: null, percentage: 0, total_score: 0 },
      '2nd': { count: 0, avg: null, percentage: 0, total_score: 0 },
      '3rd': { count: 0, avg: null, percentage: 0, total_score: 0 },
      'Reply': { count: 0, avg: null, percentage: 0, total_score: 0 },
      total_substantive: 0,
      total_speeches: 0,
    };
    (tournaments || []).forEach((t) => {
      const allRounds = [...(t.prelim_rounds || []), ...(t.elim_rounds || [])];
      allRounds.forEach((r) => {
        (r.speeches || []).forEach((sp) => {
          pos.total_speeches++;
          const p = sp.position;
          if (p && pos[p]) {
            pos[p].count++;
            if (sp.total_score) pos[p].total_score += Number(sp.total_score);
            if (sp.speech_type === 'SUBSTANTIVE' || p !== 'Reply') {
              pos.total_substantive++;
            }
          }
        });
      });
    });
    ['1st', '2nd', '3rd', 'Reply'].forEach((p) => {
      if (pos[p].count > 0 && pos[p].total_score > 0) {
        pos[p].avg = Math.round((pos[p].total_score / pos[p].count) * 100) / 100;
      }
      if (p !== 'Reply' && pos.total_substantive > 0) {
        pos[p].percentage = Math.round((pos[p].count / pos.total_substantive) * 1000) / 10;
      }
    });
    return pos;
  }

  async function loadDebaterDossier(speakerName) {
    const container = document.getElementById('bioProfileContainer');
    const dropdown = document.getElementById('bioSuggestions');
    const input = document.getElementById('bioSearchInput');
    const clearBtn = document.getElementById('bioClearBtn');

    if (dropdown) {
      dropdown.classList.add('hidden');
      dropdown.innerHTML = '';
    }
    if (input) {
      input.value = speakerName;
      input.blur();
    }
    if (clearBtn) clearBtn.classList.remove('hidden');
    if (!container) return;

    container.innerHTML = `
      <div style="text-align: center; padding: 40px; color: #38bdf8; font-family: var(--font-mono);">
        Loading career dossier for ${escapeHtml(speakerName)}...
      </div>
    `;

    let profile = null;

    // 1. Live API query
    if (state.isServerOnline) {
      try {
        const res = await fetch(`${state.apiUrl}/api/debaters/${encodeURIComponent(speakerName)}?compact=false`);
        if (res.ok) profile = await res.json();
      } catch (e) {}
    }

    // 2. Static precomputed fallback
    if (!profile) {
      const crit = (state.criticalSpeakers || []).find((s) => s.speaker_name && s.speaker_name.toLowerCase() === speakerName.toLowerCase());
      const master = (state.masterSpeakers || []).find((s) => s.speaker_name && s.speaker_name.toLowerCase() === speakerName.toLowerCase());

      if (crit || master) {
        profile = {
          canonical_name: (crit && crit.speaker_name) || (master && master.speaker_name),
          institution: (crit && crit.institution) || (master && master.institution_name) || 'Independent',
          national_level: (crit && crit.national_level) || (master && master.national_level),
          master_score: (master && master.master_score) || (crit && crit.avg),
          speech_avg: (crit && crit.speech_avg) || (master && master.speech_average),
          overall_substantive_avg: (master && master.speaker_avg) || (crit && crit.speaker_avg),
          master_tab_rank: master && master.rank,
          critical_stats_rank: crit && crit.rank,
          win_rate: (crit && crit.win_rate_debated) || (master && master.win_percentage) || 0,
          prelim_rounds_debated: (crit && crit.prelim_rounds_debated) || (master && master.prelims) || 0,
          break_rate: (crit && crit.break_percentage) || (master && master.break_percentage) || 0,
          eligible_tournaments_count: (crit && crit.eligible_tournaments) || (master && master.eligible_tournaments) || 0,
          total_tournaments_count: (master && master.tournaments) || (crit && crit.tournaments) || 1,
          tournaments: (master && master.tournament_breakdown) || [],
          regulation: (crit && crit.regulation) || 'new',
        };
      }
    }

    if (!profile) {
      container.innerHTML = `
        <div style="text-align: center; padding: 40px; color: #ef4444; font-family: var(--font-mono);">
          Debater record for "${escapeHtml(speakerName)}" not found in database.
        </div>
      `;
      return;
    }

    // Metric 1: Avg
    const speakerAvg = profile.overall_substantive_avg || profile.speech_avg || profile.speaker_avg || profile.master_score;

    // Metric 2: Critical tab rank (normal Tab if critical doesn't exist)
    const critRank = profile.critical_stats_rank || getCriticalRank(profile.canonical_name);
    const masterRank = profile.master_tab_rank || getMasterRank(profile.canonical_name);
    const hasCritRank = critRank !== null && critRank !== undefined;
    const rankValue = hasCritRank ? `#${critRank}` : (masterRank ? `#${masterRank}` : 'Unranked');
    const rankLabel = hasCritRank ? 'CRITICAL TAB' : 'MASTER TAB ONLY';
    const rankSub = hasCritRank ? 'Official Critical Standing' : 'Unranked in Critical (< 3 eligible)';
    const rankTagClass = hasCritRank ? 'break-semis' : 'break-octos';

    // Metric 3: Tournaments debated (eligible and participated both)
    const eligibleTours = profile.eligible_tournaments_count !== undefined ? profile.eligible_tournaments_count : (profile.eligible_tournaments || 0);
    const totalTours = profile.total_tournaments_count !== undefined ? profile.total_tournaments_count : (profile.tournaments_debated ? profile.tournaments_debated.length : (profile.tournaments ? profile.tournaments.length : 0));

    // Metric 4: Rounds debated (prelims, no eligibility issues)
    const prelimsDebated = profile.prelim_rounds_debated !== undefined ? profile.prelim_rounds_debated : (profile.prelims || 0);

    // Metric 5: Win rate
    const winRate = profile.win_rate !== undefined ? profile.win_rate : (profile.win_percentage || 0);

    // Metric 6: Break rate
    const breakRate = profile.break_rate !== undefined ? profile.break_rate : (profile.break_percentage || 0);

    // Metric 7: Speaker Positions Graph
    let positions = profile.positions_breakdown;
    if (!positions || (!positions['1st'] && !positions['2nd'])) {
      positions = derivePositionsFromTournaments(profile.tournaments);
    }
    const pos1 = (positions && positions['1st']) || { count: 0, percentage: 0, avg: null };
    const pos2 = (positions && positions['2nd']) || { count: 0, percentage: 0, avg: null };
    const pos3 = (positions && positions['3rd']) || { count: 0, percentage: 0, avg: null };
    const posReply = (positions && positions['Reply']) || { count: 0, percentage: 0, avg: null };
    const totalSubstantive = (positions && positions.total_substantive) || (pos1.count + pos2.count + pos3.count);

    // Calculate width percentages for horizontal bar
    const p1Width = totalSubstantive > 0 ? (pos1.count / totalSubstantive) * 100 : 0;
    const p2Width = totalSubstantive > 0 ? (pos2.count / totalSubstantive) * 100 : 0;
    const p3Width = totalSubstantive > 0 ? (pos3.count / totalSubstantive) * 100 : 0;

    // Metric 8: Adjudication Record ("Adjed or not")
    const adj = profile.adjudication_record;
    const hasAdjudicated = adj && adj.has_adjudicated && adj.tournaments_count > 0;

    // Tournament date ranking & ordering metadata (SLSDC Aug 2026 is latest, AISDC Jan 2026 is earliest)
    const TOURNAMENT_DATE_METADATA = {
      4: { rank: 8, date: "Aug 22–31, 2026" },       // SLSDC 2026 (Latest)
      18: { rank: 7, date: "July 31 – Aug 3, 2026" }, // Chap's '26
      3: { rank: 6, date: "July 17–20, 2026" },      // APIIT ISDC 2026
      16: { rank: 5, date: "July 3–6, 2026" },        // RIC ISDC 2026
      10: { rank: 4, date: "June 19–22, 2026" },      // Metho 2026
      1: { rank: 3, date: "June 5–8, 2026" },         // Vijis '26
      7: { rank: 2, date: "March 13–16, 2026" },      // VVIDC 2026
      2: { rank: 1, date: "Jan 2–5, 2026" },          // AISDC 2026 (Start of year)
    };

    function getTournamentDateInfo(t) {
      const id = Number(t.tournament_id || t.id);
      if (TOURNAMENT_DATE_METADATA[id]) return TOURNAMENT_DATE_METADATA[id];

      const name = (t.tournament_name || t.name || '').toLowerCase();
      if (name.includes('slsdc') || name.includes('sri lanka schools')) return { rank: 8, date: "Aug 22–31, 2026" };
      if (name.includes('chap') || name.includes('frances')) return { rank: 7, date: "July 31 – Aug 3, 2026" };
      if (name.includes('apiit')) return { rank: 6, date: "July 17–20, 2026" };
      if (name.includes('ric')) return { rank: 5, date: "July 3–6, 2026" };
      if (name.includes('metho') || name.includes('shanthi')) return { rank: 4, date: "June 19–22, 2026" };
      if (name.includes('viji') || name.includes('dr. vijitha')) return { rank: 3, date: "June 5–8, 2026" };
      if (name.includes('vvidc') || name.includes('visakha')) return { rank: 2, date: "March 13–16, 2026" };
      if (name.includes('aisdc') || name.includes('ais')) return { rank: 1, date: "Jan 2–5, 2026" };
      return { rank: 0, date: "" };
    }

    // Tournament cards sorted reverse chronologically (SLSDC at top, AISDC at bottom)
    const rawTournaments = (profile.tournaments || profile.tournament_breakdown || []).slice();
    rawTournaments.sort((a, b) => {
      const infoA = getTournamentDateInfo(a);
      const infoB = getTournamentDateInfo(b);
      return infoB.rank - infoA.rank;
    });

    const tournamentCards =
      rawTournaments.length > 0
        ? rawTournaments
            .map((t) => {
              const scores = (t.prelim_substantive_scores || t.scores || [])
                .map((sc) => `<span class="score-pill">${fmt(sc, 1)}</span>`)
                .join('');
              const tName = (t.tournament_name || '').split('|')[0].trim();
              const stage = t.highest_stage || (t.team_broke ? 'Knockouts' : 'Preliminaries');
              const tAvg = t.tournament_average !== undefined ? t.tournament_average : t.substantive_avg;
              const dateInfo = getTournamentDateInfo(t);
              const dateText = dateInfo.date ? `<span style="font-size: 11px; font-weight: normal; color: rgba(255,255,255,0.45); margin-left: 6px;">· ${dateInfo.date}</span>` : '';

              // Count prelims debated in this tournament
              const prelimsCount = (t.prelim_substantive_scores || t.scores || (t.prelim_rounds ? t.prelim_rounds.length : [])).length;
              const prelimsBadge = `<span class="break-tag break-semis" style="font-size: 9.5px; padding: 2px 7px;">${prelimsCount} Prelim${prelimsCount === 1 ? '' : 's'} Debated</span>`;

              return `
          <div class="trajectory-card">
            <div>
              <div class="t-info-title">${escapeHtml(tName)} ${prelimsBadge} ${dateText}</div>
              <div class="t-info-sub">Team: ${escapeHtml(t.team_name || 'Circuit Team')} · Stage: <strong style="color: #ffffff;">${escapeHtml(stage)}</strong> · Avg: <strong style="color: #38bdf8;">${fmt(tAvg, 2)}</strong></div>
            </div>
            <div class="score-pills">
              ${scores || '<span style="font-size: 11px; color: rgba(255,255,255,0.4);">No scores recorded</span>'}
            </div>
          </div>
        `;
            })
            .join('')
        : `<div style="color: rgba(255,255,255,0.5); font-size: 13px; font-style: italic; padding: 12px;">No tournament trajectories recorded.</div>`;

    container.innerHTML = `
      <!-- Header Profile Card -->
      <div class="bio-profile-header">
        <div class="bio-name-group">
          <h2 class="bio-name">${escapeHtml(profile.canonical_name || profile.speaker_name)}</h2>
          <div class="bio-institution">${escapeHtml(profile.institution || profile.institution_name || 'Independent Debater')}</div>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
          ${getNatStatusTag(profile.national_level)}
        </div>
      </div>

      <!-- 8 Core Metrics Grid (Top 6 Vitals) -->
      <div class="bio-stats-grid">
        <!-- 1. Speaker Avg -->
        <div class="bio-stat-tile">
          <div class="bio-stat-val" style="color: #38bdf8;">${fmt(speakerAvg, 2)}</div>
          <div class="bio-stat-lbl">1. SPEAKER AVG</div>
          <div style="font-size: 10px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Substantive Mean</div>
        </div>

        <!-- 2. Critical Tab Rank (or Master Tab if not in Critical) -->
        <div class="bio-stat-tile">
          <div class="bio-stat-val" style="color: ${hasCritRank ? '#38bdf8' : '#fbbf24'};">${rankValue}</div>
          <div class="bio-stat-lbl">2. CRITICAL TAB RANK</div>
          <div style="margin-top: 4px;">
            <span class="break-tag ${rankTagClass}" style="font-size: 9px; padding: 1px 6px;">${rankLabel}</span>
          </div>
          <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">${rankSub}</div>
        </div>

        <!-- 3. Tournaments Debated (Eligible vs Participated) -->
        <div class="bio-stat-tile">
          <div class="bio-stat-val" style="color: #34d399;">${eligibleTours} <span style="font-size: 16px; color: rgba(255,255,255,0.4);">/ ${totalTours}</span></div>
          <div class="bio-stat-lbl">3. TOURNAMENTS</div>
          <div style="font-size: 10px; color: rgba(255,255,255,0.6); font-family: var(--font-mono); margin-top: 2px;">${eligibleTours} Eligible · ${totalTours} Entered</div>
        </div>

        <!-- 4. Prelims Debated (no eligibility issues, any prelim) -->
        <div class="bio-stat-tile">
          <div class="bio-stat-val" style="color: #38bdf8;">${prelimsDebated}</div>
          <div class="bio-stat-lbl">4. PRELIMS DEBATED</div>
          <div style="font-size: 10px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Preliminary Rounds Debated</div>
        </div>

        <!-- 5. Win Rate -->
        <div class="bio-stat-tile">
          <div class="bio-stat-val" style="color: #34d399;">${fmt(winRate, 1)}%</div>
          <div class="bio-stat-lbl">5. WIN RATE</div>
          <div style="font-size: 10px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">In Debates Debated</div>
        </div>

        <!-- 6. Break Rate -->
        <div class="bio-stat-tile">
          <div class="bio-stat-val" style="color: #c084fc;">${fmt(breakRate, 1)}%</div>
          <div class="bio-stat-lbl">6. BREAK RATE</div>
          <div style="font-size: 10px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Elimination Progression</div>
        </div>
      </div>

      <!-- 7. Speaker Positions Graph -->
      <div class="bio-section-heading">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>
        7. SPEAKER POSITIONS BREAKDOWN & DISTRIBUTION GRAPH
      </div>
      <div class="positions-graph-card">
        <!-- Segmented Distribution Progress Bar -->
        <div style="display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 11px; margin-bottom: 6px; color: rgba(255,255,255,0.7);">
          <span>Substantive Distribution (${totalSubstantive} Speeches)</span>
          <span>1st: ${pos1.percentage}% · 2nd: ${pos2.percentage}% · 3rd: ${pos3.percentage}%</span>
        </div>
        <div class="positions-dist-bar-wrap">
          ${p1Width > 0 ? `<div class="positions-dist-segment pos-seg-1st" style="width: ${p1Width}%;" title="1st Speaker: ${pos1.count} speeches (${pos1.percentage}%)">${p1Width >= 8 ? `${Math.round(p1Width)}%` : ''}</div>` : ''}
          ${p2Width > 0 ? `<div class="positions-dist-segment pos-seg-2nd" style="width: ${p2Width}%;" title="2nd Speaker: ${pos2.count} speeches (${pos2.percentage}%)">${p2Width >= 8 ? `${Math.round(p2Width)}%` : ''}</div>` : ''}
          ${p3Width > 0 ? `<div class="positions-dist-segment pos-seg-3rd" style="width: ${p3Width}%;" title="3rd Speaker: ${pos3.count} speeches (${pos3.percentage}%)">${p3Width >= 8 ? `${Math.round(p3Width)}%` : ''}</div>` : ''}
          ${totalSubstantive === 0 ? `<div style="padding: 3px 10px; font-size: 11px; color: rgba(255,255,255,0.4);">No substantive speeches recorded</div>` : ''}
        </div>

        <!-- 4 Positions Grid -->
        <div class="positions-grid">
          <!-- 1st Speaker -->
          <div class="position-stat-box">
            <div class="position-box-header">
              <span class="position-box-tag pos-tag-1st">1ST SPEAKER</span>
              <span class="position-box-avg">${pos1.avg !== null ? `Avg: ${fmt(pos1.avg, 2)}` : 'No Speeches'}</span>
            </div>
            <div class="position-box-count">${pos1.count}</div>
            <div class="position-box-sub">
              <span>Speeches</span>
              <span style="color: #38bdf8;">${pos1.percentage}% of sub</span>
            </div>
          </div>

          <!-- 2nd Speaker -->
          <div class="position-stat-box">
            <div class="position-box-header">
              <span class="position-box-tag pos-tag-2nd">2ND SPEAKER</span>
              <span class="position-box-avg">${pos2.avg !== null ? `Avg: ${fmt(pos2.avg, 2)}` : 'No Speeches'}</span>
            </div>
            <div class="position-box-count">${pos2.count}</div>
            <div class="position-box-sub">
              <span>Speeches</span>
              <span style="color: #34d399;">${pos2.percentage}% of sub</span>
            </div>
          </div>

          <!-- 3rd Speaker -->
          <div class="position-stat-box">
            <div class="position-box-header">
              <span class="position-box-tag pos-tag-3rd">3RD SPEAKER</span>
              <span class="position-box-avg">${pos3.avg !== null ? `Avg: ${fmt(pos3.avg, 2)}` : 'No Speeches'}</span>
            </div>
            <div class="position-box-count">${pos3.count}</div>
            <div class="position-box-sub">
              <span>Speeches</span>
              <span style="color: #fbbf24;">${pos3.percentage}% of sub</span>
            </div>
          </div>

          <!-- Reply Speaker -->
          <div class="position-stat-box">
            <div class="position-box-header">
              <span class="position-box-tag pos-tag-reply">REPLY SPEAKER</span>
              <span class="position-box-avg" style="color: #c084fc;">${posReply.avg !== null ? `Avg: ${fmt(posReply.avg, 2)}` : 'No Replies'}</span>
            </div>
            <div class="position-box-count">${posReply.count}</div>
            <div class="position-box-sub">
              <span>Reply Speeches</span>
              <span style="color: #c084fc;">/ 40 pts</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 8. Adjudication History ("Adjed or not") -->
      <div class="bio-section-heading">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        8. CIRCUIT ADJUDICATION RECORD ("ADJED OR NOT")
      </div>
      <div class="adj-history-section">
        <div class="adj-status-banner">
          <div>
            <span class="adj-status-badge ${hasAdjudicated ? 'active' : 'inactive'}">
              ${hasAdjudicated ? 'OFFICIATED AS ADJUDICATOR' : 'NO ADJUDICATION RECORD'}
            </span>
          </div>
          <div style="font-family: var(--font-mono); font-size: 11.5px; color: rgba(255,255,255,0.6);">
            ${hasAdjudicated ? `${adj.tournaments_count} tournament(s) officiated on circuit record` : 'Debated exclusively · 0 recorded judging ballots'}
          </div>
        </div>

        ${hasAdjudicated ? `
          <div class="adj-tours-list">
            ${(adj.tournaments || []).map((at) => {
              const allRounds = Array.from(new Set([...(at.rounds_assigned || []), ...(at.rounds_balloted || [])]));
              const roundChips = allRounds.length > 0
                ? allRounds.map((rn) => `<span class="adj-round-chip">${escapeHtml(rn)}</span>`).join('')
                : '<span style="font-size: 11px; color: rgba(255,255,255,0.4);">Roster record on file</span>';
              const roleText = at.chair_count > 0 ? `${at.chair_count} Chair / ${at.panel_count} Panel` : (at.panel_count > 0 ? `${at.panel_count} Panel debates` : 'Tournament Adjudicator');
              return `
                <div class="adj-tour-row">
                  <div>
                    <div class="adj-tour-name">${escapeHtml(at.tournament_name)} ${at.year ? `<span style="font-size: 11px; color: rgba(255,255,255,0.4); font-weight: normal;">(${at.year})</span>` : ''}</div>
                    <div style="font-size: 11px; color: rgba(255,255,255,0.5); font-family: var(--font-mono); margin-top: 2px;">Role: <strong style="color: #34d399;">${escapeHtml(at.role || 'ADJUDICATOR')}</strong> · ${roleText}</div>
                  </div>
                  <div class="adj-rounds-chips">
                    ${roundChips}
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        ` : `
          <div style="font-size: 12.5px; color: rgba(255,255,255,0.5); font-family: var(--font-mono); line-height: 1.6;">
            This debater has competed exclusively as a speaker and has not officiated or submitted ballots as an adjudicator in recorded circuit tournaments.
          </div>
        `}
      </div>

      <!-- Tournament Performance & Trajectory -->
      <div class="bio-section-heading">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        TOURNAMENT PERFORMANCE TRAJECTORY
      </div>
      <div class="trajectory-list">
        ${tournamentCards}
      </div>
    `;

    // Update URL query parameter
    if (window.history.replaceState) {
      const newUrl = `${window.location.pathname}?speaker=${encodeURIComponent(profile.canonical_name || speakerName)}`;
      window.history.replaceState(null, '', newUrl);
    }
  }

  function selectDebater(speakerName) {
    loadDebaterDossier(speakerName);
  }

  // ==========================================================================
  // 4. HEAD TO HEAD ENGINE (6 Core Judging Categories)
  // ==========================================================================
  let selectedH2HA = null;
  let selectedH2HB = null;

  function getAllDebatersList() {
    const list = [];
    const seen = new Set();

    (state.criticalSpeakers || []).forEach((s) => {
      const name = s.speaker_name || s.canonical_name;
      if (name && !seen.has(name.toLowerCase())) {
        seen.add(name.toLowerCase());
        list.push({
          name: name,
          institution: s.institution || s.institution_name || 'Independent',
          speaker_avg: s.speaker_avg !== undefined ? s.speaker_avg : s.speech_avg,
          prelims: s.prelims !== undefined ? s.prelims : (s.prelim_rounds_debated || 0),
          win_percentage: s.win_percentage !== undefined ? s.win_percentage : s.win_rate_debated,
          break_percentage: s.break_percentage,
          tournaments: s.tournaments || s.eligible_tournaments || 0,
          tournament_breakdown: s.tournament_breakdown || [],
          raw: s,
        });
      }
    });

    (state.masterSpeakers || []).forEach((s) => {
      const name = s.speaker_name || s.canonical_name;
      if (name && !seen.has(name.toLowerCase())) {
        seen.add(name.toLowerCase());
        list.push({
          name: name,
          institution: s.institution || s.institution_name || 'Independent',
          speaker_avg: s.speaker_avg !== undefined ? s.speaker_avg : s.speech_avg,
          prelims: s.prelims !== undefined ? s.prelims : (s.prelim_rounds || 0),
          win_percentage: s.win_percentage !== undefined ? s.win_percentage : s.win_rate,
          break_percentage: s.break_percentage,
          tournaments: s.tournaments || s.eligible_tournaments || 0,
          tournament_breakdown: s.tournament_breakdown || [],
          raw: s,
        });
      }
    });

    return list;
  }

  function computeTourStdDev(debater) {
    if (!debater) return { sd: null, text: 'N/A' };
    const breakdown = debater.tournament_breakdown || debater.tournaments_breakdown || debater.tournaments || [];
    let avgs = [];
    if (Array.isArray(breakdown)) {
      avgs = breakdown
        .map((t) => (t.tournament_average !== undefined ? t.tournament_average : t.avg))
        .filter((a) => a !== undefined && a !== null && !isNaN(a) && Number(a) > 0);
    }
    if (avgs.length < 2) {
      return { sd: null, text: avgs.length === 1 ? 'N/A (1 Tour)' : 'N/A' };
    }
    const mean = avgs.reduce((a, b) => a + Number(b), 0) / avgs.length;
    const variance = avgs.reduce((sum, a) => sum + Math.pow(Number(a) - mean, 2), 0) / avgs.length;
    const sd = Math.sqrt(variance);
    return { sd: sd, text: `±${sd.toFixed(2)} pts` };
  }

  function getCriticalRank(debaterName) {
    if (!debaterName) return null;
    const crit = (state.criticalSpeakers || []).find(
      (s) =>
        (s.speaker_name && s.speaker_name.toLowerCase() === debaterName.toLowerCase()) ||
        (s.canonical_name && s.canonical_name.toLowerCase() === debaterName.toLowerCase())
    );
    return crit ? (crit.rank || null) : null;
  }

  function renderH2HEmptyState(message) {
    const container = document.getElementById('h2hResultContainer');
    if (!container) return;
    const msg =
      message ||
      "Select Contender 1 and Contender 2 in the search fields above to compute their 6-category head-to-head clash breakdown, prediction advantage, and historical tournament matchup records.";
    container.innerHTML = `
      <div class="h2h-empty-state" style="text-align: center; padding: 64px 20px; color: rgba(255,255,255,0.5); font-family: var(--font-mono);">
        <div style="font-size: 16px; color: #38bdf8; margin-bottom: 8px; font-weight: 600; letter-spacing: 0.06em;">ATOMOS HEAD TO HEAD // CLASH ENGINE</div>
        <div style="font-size: 13px; max-width: 520px; margin: 0 auto; line-height: 1.6; color: rgba(255,255,255,0.65);">
          ${msg}
        </div>
      </div>
    `;
  }

  function updateH2HUrl() {
    if (!window.history.replaceState) return;
    const nameA = selectedH2HA ? selectedH2HA.name : '';
    const nameB = selectedH2HB ? selectedH2HB.name : '';
    if (nameA && nameB) {
      const newUrl = `${window.location.pathname}?a=${encodeURIComponent(nameA)}&b=${encodeURIComponent(nameB)}`;
      window.history.replaceState(null, '', newUrl);
    } else if (nameA) {
      const newUrl = `${window.location.pathname}?a=${encodeURIComponent(nameA)}`;
      window.history.replaceState(null, '', newUrl);
    } else if (nameB) {
      const newUrl = `${window.location.pathname}?b=${encodeURIComponent(nameB)}`;
      window.history.replaceState(null, '', newUrl);
    } else {
      window.history.replaceState(null, '', window.location.pathname);
    }
  }

  function clearContender(side) {
    const input = document.getElementById(side === 'A' ? 'h2hInputA' : 'h2hInputB');
    const badge = document.getElementById(side === 'A' ? 'h2hSelectedBadgeA' : 'h2hSelectedBadgeB');
    const clearBtn = document.getElementById(side === 'A' ? 'h2hClearBtnA' : 'h2hClearBtnB');

    if (side === 'A') selectedH2HA = null;
    else selectedH2HB = null;

    if (input) input.value = '';
    if (badge) badge.classList.add('hidden');
    if (clearBtn) clearBtn.classList.add('hidden');

    closeAllH2HDropdowns();
    updateH2HUrl();
    runH2HComparison();
  }

  function initH2HPage() {
    const inputA = document.getElementById('h2hInputA');
    const inputB = document.getElementById('h2hInputB');
    if (!inputA || !inputB) return;

    selectedH2HA = null;
    selectedH2HB = null;
    inputA.value = '';
    inputB.value = '';

    const badgeA = document.getElementById('h2hSelectedBadgeA');
    const badgeB = document.getElementById('h2hSelectedBadgeB');
    const clearBtnA = document.getElementById('h2hClearBtnA');
    const clearBtnB = document.getElementById('h2hClearBtnB');
    if (badgeA) badgeA.classList.add('hidden');
    if (badgeB) badgeB.classList.add('hidden');
    if (clearBtnA) clearBtnA.classList.add('hidden');
    if (clearBtnB) clearBtnB.classList.add('hidden');

    setupAutocomplete('A', inputA, document.getElementById('h2hDropdownA'), clearBtnA, badgeA);
    setupAutocomplete('B', inputB, document.getElementById('h2hDropdownB'), clearBtnB, badgeB);

    const allDebaters = getAllDebatersList();

    // Check URL parameters ?a=...&b=... or ?contender1=...&contender2=...
    const urlParams = new URLSearchParams(window.location.search);
    const paramA = urlParams.get('a') || urlParams.get('contender1') || urlParams.get('debater');
    const paramB = urlParams.get('b') || urlParams.get('contender2');

    // Never autoload Vidath & Apoorva from old leftover URL state
    const isOldDefaultPair =
      paramA &&
      paramB &&
      paramA.toLowerCase().includes('vidath') &&
      paramB.toLowerCase().includes('apoorva');

    if (isOldDefaultPair && window.history.replaceState) {
      window.history.replaceState(null, '', window.location.pathname);
    }

    let initA = null;
    let initB = null;

    if (!isOldDefaultPair) {
      if (paramA) {
        initA = allDebaters.find((d) => d.name.toLowerCase() === paramA.toLowerCase());
      }
      if (paramB) {
        initB = allDebaters.find((d) => d.name.toLowerCase() === paramB.toLowerCase());
      }
    }

    if (initA) selectContender('A', initA);
    if (initB) selectContender('B', initB);

    if (initA && initB) {
      runH2HComparison();
    } else {
      renderH2HEmptyState(
        initA
          ? `Contender 1 (${escapeHtml(initA.name)}) selected. Select Contender 2 above to complete the clash comparison.`
          : initB
          ? `Contender 2 (${escapeHtml(initB.name)}) selected. Select Contender 1 above to complete the clash comparison.`
          : null
      );
    }
  }

  function closeAllH2HDropdowns() {
    ['h2hDropdownA', 'h2hDropdownB'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.classList.add('hidden');
        el.innerHTML = '';
      }
    });
  }

  // Global outside click handler for H2H autocomplete dropdowns
  document.addEventListener('pointerdown', (e) => {
    if (!e.target.closest('.h2h-search-wrap')) {
      closeAllH2HDropdowns();
    }
  });

  function setupAutocomplete(side, input, dropdown, clearBtn, badge) {
    if (!input || !dropdown) return;

    function renderMatches(q) {
      const allDebaters = getAllDebatersList();
      const query = (q || '').trim().toLowerCase();
      let matches = allDebaters;
      if (query) {
        matches = allDebaters.filter(
          (d) => d.name.toLowerCase().includes(query) || (d.institution && d.institution.toLowerCase().includes(query))
        );
      }
      matches = matches.slice(0, 15);

      if (matches.length === 0) {
        dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255,255,255,0.5); font-size: 12.5px; text-align: center;">No matching debaters in identity base.</div>`;
        dropdown.classList.remove('hidden');
        return;
      }

      dropdown.innerHTML = matches
        .map(
          (d, idx) => `
        <div class="h2h-autocomplete-item${idx === 0 ? ' active' : ''}" data-name="${escapeHtml(d.name)}">
          <div>
            <div class="h2h-auto-name">${escapeHtml(d.name)}</div>
            <div class="h2h-auto-inst">${escapeHtml(d.institution || 'Independent')}</div>
          </div>
          <div class="h2h-auto-meta">
            <span class="h2h-auto-stat">${d.speaker_avg ? `Avg: ${Number(d.speaker_avg).toFixed(2)}` : ''}</span>
            <span style="font-size: 10px; color: rgba(255,255,255,0.4);">${d.prelims || 0} Prelims</span>
          </div>
        </div>
      `
        )
        .join('');

      dropdown.classList.remove('hidden');

      dropdown.querySelectorAll('.h2h-autocomplete-item').forEach((el) => {
        el.addEventListener('mousedown', (e) => {
          e.preventDefault();
          e.stopPropagation();
          const name = el.getAttribute('data-name');
          const found = allDebaters.find((d) => d.name === name);
          if (found) {
            selectContender(side, found);
            runH2HComparison();
          }
        });
      });
    }

    input.addEventListener('input', () => {
      const val = input.value.trim();
      const currentSelected = side === 'A' ? selectedH2HA : selectedH2HB;

      if (clearBtn) {
        if (input.value) clearBtn.classList.remove('hidden');
        else clearBtn.classList.add('hidden');
      }

      // If user erased input or edited away from currently selected name
      if (!val) {
        if (side === 'A') selectedH2HA = null;
        else selectedH2HB = null;
        if (badge) badge.classList.add('hidden');
        updateH2HUrl();
        runH2HComparison();
      } else if (currentSelected && val.toLowerCase() !== currentSelected.name.toLowerCase()) {
        if (side === 'A') selectedH2HA = null;
        else selectedH2HB = null;
        if (badge) badge.classList.add('hidden');
        updateH2HUrl();
        runH2HComparison();
      }

      // Close opposing dropdown
      const otherSide = side === 'A' ? 'B' : 'A';
      const otherDropdown = document.getElementById(otherSide === 'A' ? 'h2hDropdownA' : 'h2hDropdownB');
      if (otherDropdown) {
        otherDropdown.classList.add('hidden');
        otherDropdown.innerHTML = '';
      }
      renderMatches(input.value);
    });

    input.addEventListener('focus', () => {
      // Close opposing dropdown
      const otherSide = side === 'A' ? 'B' : 'A';
      const otherDropdown = document.getElementById(otherSide === 'A' ? 'h2hDropdownA' : 'h2hDropdownB');
      if (otherDropdown) {
        otherDropdown.classList.add('hidden');
        otherDropdown.innerHTML = '';
      }
      renderMatches(input.value);
    });

    input.addEventListener('blur', () => {
      setTimeout(() => {
        dropdown.classList.add('hidden');
        dropdown.innerHTML = '';
        // If user typed exact debater name and blurred without clicking dropdown
        const currentSelected = side === 'A' ? selectedH2HA : selectedH2HB;
        if (!currentSelected && input.value.trim()) {
          const allDebaters = getAllDebatersList();
          const match = allDebaters.find((d) => d.name.toLowerCase() === input.value.trim().toLowerCase());
          if (match) {
            selectContender(side, match);
            runH2HComparison();
          }
        }
      }, 150);
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeAllH2HDropdowns();
        input.blur();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const activeItem = dropdown.querySelector('.h2h-autocomplete-item.active') || dropdown.querySelector('.h2h-autocomplete-item');
        if (activeItem) {
          const name = activeItem.getAttribute('data-name');
          const allDebaters = getAllDebatersList();
          const found = allDebaters.find((d) => d.name === name);
          if (found) {
            selectContender(side, found);
            runH2HComparison();
          }
        } else {
          closeAllH2HDropdowns();
          input.blur();
        }
      } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const items = Array.from(dropdown.querySelectorAll('.h2h-autocomplete-item'));
        if (items.length === 0) return;
        let activeIdx = items.findIndex((el) => el.classList.contains('active'));
        if (e.key === 'ArrowDown') {
          activeIdx = (activeIdx + 1) % items.length;
        } else {
          activeIdx = (activeIdx - 1 + items.length) % items.length;
        }
        items.forEach((el, idx) => {
          el.classList.toggle('active', idx === activeIdx);
          if (idx === activeIdx) el.scrollIntoView({ block: 'nearest' });
        });
      }
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        clearContender(side);
        input.focus();
        renderMatches('');
      });
    }
  }

  function selectContender(side, debater) {
    const input = document.getElementById(side === 'A' ? 'h2hInputA' : 'h2hInputB');
    const badge = document.getElementById(side === 'A' ? 'h2hSelectedBadgeA' : 'h2hSelectedBadgeB');
    const clearBtn = document.getElementById(side === 'A' ? 'h2hClearBtnA' : 'h2hClearBtnB');

    if (side === 'A') selectedH2HA = debater;
    else selectedH2HB = debater;

    if (input) {
      input.value = debater.name;
      input.blur(); // Release focus immediately so dropdown stays closed!
    }
    if (badge) {
      badge.textContent = debater.institution || 'Independent';
      badge.classList.remove('hidden');
    }
    if (clearBtn) clearBtn.classList.remove('hidden');

    // Close all dropdowns immediately and clear contents
    closeAllH2HDropdowns();

    // Update URL query parameters dynamically
    updateH2HUrl();
  }

  async function runH2HComparison() {
    const container = document.getElementById('h2hResultContainer');
    if (!container) return;

    const debaterA = selectedH2HA;
    const debaterB = selectedH2HB;

    if (!debaterA && !debaterB) {
      renderH2HEmptyState();
      return;
    }
    if (debaterA && !debaterB) {
      renderH2HEmptyState(`Contender 1 (${escapeHtml(debaterA.name)}) selected. Select Contender 2 above to complete the clash comparison.`);
      return;
    }
    if (!debaterA && debaterB) {
      renderH2HEmptyState(`Contender 2 (${escapeHtml(debaterB.name)}) selected. Select Contender 1 above to complete the clash comparison.`);
      return;
    }
    if (debaterA.name.toLowerCase() === debaterB.name.toLowerCase()) {
      renderH2HEmptyState(`Please select two different debaters to compute a Head to Head clash comparison.`);
      return;
    }

    container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);"><div class="spinner"></div> Computing 6-category clash comparison & matchup records...</div>`;

    // Fetch direct head-to-head records from live server if online
    let directDebates = [];
    let aDirectWins = 0;
    let bDirectWins = 0;

    try {
      const url = `${state.apiUrl}/api/h2h?a=${encodeURIComponent(debaterA.name)}&b=${encodeURIComponent(debaterB.name)}&mode=debater`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        directDebates = data.direct_debates || [];
        aDirectWins = data.a_direct_wins || 0;
        bDirectWins = data.b_direct_wins || 0;
      }
    } catch (e) {
      console.warn('Direct matchup fetch error:', e);
    }

    // Category 1: Average speak
    const avgA = debaterA.speaker_avg !== undefined && debaterA.speaker_avg !== null ? Number(debaterA.speaker_avg) : null;
    const avgB = debaterB.speaker_avg !== undefined && debaterB.speaker_avg !== null ? Number(debaterB.speaker_avg) : null;
    let winCat1 = 'TIE';
    if (avgA !== null && avgB !== null) {
      if (avgA > avgB) winCat1 = 'A';
      else if (avgB > avgA) winCat1 = 'B';
    } else if (avgA !== null) winCat1 = 'A';
    else if (avgB !== null) winCat1 = 'B';

    // Category 2: Win %
    const winRateA = debaterA.win_percentage !== undefined && debaterA.win_percentage !== null ? Number(debaterA.win_percentage) : null;
    const winRateB = debaterB.win_percentage !== undefined && debaterB.win_percentage !== null ? Number(debaterB.win_percentage) : null;
    let winCat2 = 'TIE';
    if (winRateA !== null && winRateB !== null) {
      if (winRateA > winRateB) winCat2 = 'A';
      else if (winRateB > winRateA) winCat2 = 'B';
    } else if (winRateA !== null) winCat2 = 'A';
    else if (winRateB !== null) winCat2 = 'B';

    // Category 3: Critical tab ranking
    const critRankA = getCriticalRank(debaterA.name);
    const critRankB = getCriticalRank(debaterB.name);
    let winCat3 = 'TIE';
    if (critRankA !== null && critRankB !== null) {
      if (critRankA < critRankB) winCat3 = 'A';
      else if (critRankB < critRankA) winCat3 = 'B';
    } else if (critRankA !== null) winCat3 = 'A';
    else if (critRankB !== null) winCat3 = 'B';

    // Category 4: Consistency (tour-to-tour speak deviation)
    const constA = computeTourStdDev(debaterA);
    const constB = computeTourStdDev(debaterB);
    let winCat4 = 'TIE';
    if (constA.sd !== null && constB.sd !== null) {
      // Lower SD is better
      if (constA.sd < constB.sd) winCat4 = 'A';
      else if (constB.sd < constA.sd) winCat4 = 'B';
    } else if (constA.sd !== null) winCat4 = 'A';
    else if (constB.sd !== null) winCat4 = 'B';

    // Category 5: Break %
    const brkA = debaterA.break_percentage !== undefined && debaterA.break_percentage !== null ? Number(debaterA.break_percentage) : null;
    const brkB = debaterB.break_percentage !== undefined && debaterB.break_percentage !== null ? Number(debaterB.break_percentage) : null;
    let winCat5 = 'TIE';
    if (brkA !== null && brkB !== null) {
      if (brkA > brkB) winCat5 = 'A';
      else if (brkB > brkA) winCat5 = 'B';
    } else if (brkA !== null) winCat5 = 'A';
    else if (brkB !== null) winCat5 = 'B';

    // Category 6: Head to Head in tournament if happened and both debated
    let winCat6 = 'NONE';
    if (directDebates.length > 0) {
      if (aDirectWins > bDirectWins) winCat6 = 'A';
      else if (bDirectWins > aDirectWins) winCat6 = 'B';
      else winCat6 = 'TIE';
    }

    // Tally score across the 6 categories
    const categories = [winCat1, winCat2, winCat3, winCat4, winCat5];
    let scoreA = categories.filter((w) => w === 'A').length;
    let scoreB = categories.filter((w) => w === 'B').length;
    if (winCat6 === 'A') scoreA++;
    if (winCat6 === 'B') scoreB++;

    let bannerTitle = '';
    let bannerColor = '#38bdf8';
    if (scoreA > scoreB) {
      bannerTitle = `${escapeHtml(debaterA.name)} LEADS ${scoreA} - ${scoreB}`;
      bannerColor = '#38bdf8';
    } else if (scoreB > scoreA) {
      bannerTitle = `${escapeHtml(debaterB.name)} LEADS ${scoreB} - ${scoreA}`;
      bannerColor = '#f43f5e';
    } else {
      bannerTitle = `EVEN CLASH TIED ${scoreA} - ${scoreB}`;
      bannerColor = '#fbbf24';
    }

    // Bar percentage helpers
    function getBarPcts(val1, val2, higherIsBetter = true) {
      if (val1 === null && val2 === null) return { a: 50, b: 50 };
      if (val1 === null) return { a: 20, b: 80 };
      if (val2 === null) return { a: 80, b: 20 };
      if (!higherIsBetter) {
        const inv1 = 1 / (val1 || 0.01);
        const inv2 = 1 / (val2 || 0.01);
        const total = inv1 + inv2;
        return { a: (inv1 / total) * 100, b: (inv2 / total) * 100 };
      }
      const total = val1 + val2;
      if (total === 0) return { a: 50, b: 50 };
      return { a: (val1 / total) * 100, b: (val2 / total) * 100 };
    }

    const bar1 = getBarPcts(avgA, avgB, true);
    const bar2 = getBarPcts(winRateA, winRateB, true);
    const bar3 = getBarPcts(critRankA, critRankB, false);
    const bar4 = getBarPcts(constA.sd, constB.sd, false);
    const bar5 = getBarPcts(brkA, brkB, true);
    const bar6 = directDebates.length > 0 ? getBarPcts(aDirectWins, bDirectWins, true) : { a: 50, b: 50 };

    function badgeHtml(w) {
      if (w === 'A') return `<span class="h2h-cat-badge badge-a">CONTENDER 1</span>`;
      if (w === 'B') return `<span class="h2h-cat-badge badge-b">CONTENDER 2</span>`;
      if (w === 'NONE') return `<span class="h2h-cat-badge badge-tie">NO CLASHES</span>`;
      return `<span class="h2h-cat-badge badge-tie">TIE</span>`;
    }

    container.innerHTML = `
      <!-- Overall Advantage Banner -->
      <div class="h2h-prediction-banner">
        <div style="font-family: var(--font-mono); font-size: 11.5px; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(255,255,255,0.7); margin-bottom: 6px;">
          HEAD TO HEAD ADVANTAGE
        </div>
        <div class="h2h-pred-prob" style="color: ${bannerColor};">${bannerTitle}</div>
        <div style="font-size: 13px; color: rgba(255,255,255,0.85); margin-top: 6px;">
          Judged across 6 circuit categories: Speaker Avg, Win %, Critical Tab Rank, Consistency, Break %, and Direct Tour Matchups.
        </div>
      </div>

      <!-- 6 Categories Comparison -->
      <div class="h2h-stat-compare">
        <!-- 1. Average Speak -->
        <div class="h2h-category-card">
          <div class="h2h-cat-val ${winCat1 === 'A' ? 'val-win' : ''}" style="color: #38bdf8;">
            ${avgA !== null ? avgA.toFixed(2) : 'N/A'}
          </div>
          <div class="h2h-cat-center">
            <div class="h2h-cat-title-row">
              <span class="h2h-cat-title">1. Average Speak</span>
              ${badgeHtml(winCat1)}
            </div>
            <div class="h2h-cat-bar">
              <div class="h2h-cat-bar-a" style="width: ${bar1.a}%;"></div>
              <div class="h2h-cat-bar-b" style="width: ${bar1.b}%;"></div>
            </div>
            <div class="h2h-cat-subtext">Preliminary substantive speech score average</div>
          </div>
          <div class="h2h-cat-val ${winCat1 === 'B' ? 'val-win' : ''}" style="color: #f43f5e;">
            ${avgB !== null ? avgB.toFixed(2) : 'N/A'}
          </div>
        </div>

        <!-- 2. Win % -->
        <div class="h2h-category-card">
          <div class="h2h-cat-val ${winCat2 === 'A' ? 'val-win' : ''}" style="color: #38bdf8;">
            ${winRateA !== null ? `${winRateA.toFixed(1)}%` : 'N/A'}
          </div>
          <div class="h2h-cat-center">
            <div class="h2h-cat-title-row">
              <span class="h2h-cat-title">2. Win %</span>
              ${badgeHtml(winCat2)}
            </div>
            <div class="h2h-cat-bar">
              <div class="h2h-cat-bar-a" style="width: ${bar2.a}%;"></div>
              <div class="h2h-cat-bar-b" style="width: ${bar2.b}%;"></div>
            </div>
            <div class="h2h-cat-subtext">Win rate in debates where the debater spoke</div>
          </div>
          <div class="h2h-cat-val ${winCat2 === 'B' ? 'val-win' : ''}" style="color: #f43f5e;">
            ${winRateB !== null ? `${winRateB.toFixed(1)}%` : 'N/A'}
          </div>
        </div>

        <!-- 3. Critical Tab Ranking -->
        <div class="h2h-category-card">
          <div class="h2h-cat-val ${winCat3 === 'A' ? 'val-win' : ''}" style="color: #38bdf8; font-size: 13px;">
            ${critRankA !== null ? `#${critRankA}` : 'Unranked'}
          </div>
          <div class="h2h-cat-center">
            <div class="h2h-cat-title-row">
              <span class="h2h-cat-title">3. Critical Tab Ranking</span>
              ${badgeHtml(winCat3)}
            </div>
            <div class="h2h-cat-bar">
              <div class="h2h-cat-bar-a" style="width: ${bar3.a}%;"></div>
              <div class="h2h-cat-bar-b" style="width: ${bar3.b}%;"></div>
            </div>
            <div class="h2h-cat-subtext">Official Critical Tab Standing (Minimum 3 eligible tournaments required)</div>
          </div>
          <div class="h2h-cat-val ${winCat3 === 'B' ? 'val-win' : ''}" style="color: #f43f5e; font-size: 13px;">
            ${critRankB !== null ? `#${critRankB}` : 'Unranked'}
          </div>
        </div>

        <!-- 4. Consistency -->
        <div class="h2h-category-card">
          <div class="h2h-cat-val ${winCat4 === 'A' ? 'val-win' : ''}" style="color: #38bdf8; font-size: 13px;">
            ${constA.text}
          </div>
          <div class="h2h-cat-center">
            <div class="h2h-cat-title-row">
              <span class="h2h-cat-title">4. Consistency (Speak Deviation)</span>
              ${badgeHtml(winCat4)}
            </div>
            <div class="h2h-cat-bar">
              <div class="h2h-cat-bar-a" style="width: ${bar4.a}%;"></div>
              <div class="h2h-cat-bar-b" style="width: ${bar4.b}%;"></div>
            </div>
            <div class="h2h-cat-subtext">Tournament-to-tournament score standard deviation (Lower = More Consistent)</div>
          </div>
          <div class="h2h-cat-val ${winCat4 === 'B' ? 'val-win' : ''}" style="color: #f43f5e; font-size: 13px;">
            ${constB.text}
          </div>
        </div>

        <!-- 5. Break % -->
        <div class="h2h-category-card">
          <div class="h2h-cat-val ${winCat5 === 'A' ? 'val-win' : ''}" style="color: #38bdf8;">
            ${brkA !== null ? `${Number(brkA).toFixed(1)}%` : 'N/A'}
          </div>
          <div class="h2h-cat-center">
            <div class="h2h-cat-title-row">
              <span class="h2h-cat-title">5. Break %</span>
              ${badgeHtml(winCat5)}
            </div>
            <div class="h2h-cat-bar">
              <div class="h2h-cat-bar-a" style="width: ${bar5.a}%;"></div>
              <div class="h2h-cat-bar-b" style="width: ${bar5.b}%;"></div>
            </div>
            <div class="h2h-cat-subtext">Tournament elimination round progression rate</div>
          </div>
          <div class="h2h-cat-val ${winCat5 === 'B' ? 'val-win' : ''}" style="color: #f43f5e;">
            ${brkB !== null ? `${Number(brkB).toFixed(1)}%` : 'N/A'}
          </div>
        </div>

        <!-- 6. Head to Head in Tournament -->
        <div class="h2h-category-card">
          <div class="h2h-cat-val ${winCat6 === 'A' ? 'val-win' : ''}" style="color: #38bdf8;">
            ${aDirectWins} <span style="font-size: 11px; font-weight: normal; color: rgba(255,255,255,0.6);">W</span>
          </div>
          <div class="h2h-cat-center">
            <div class="h2h-cat-title-row">
              <span class="h2h-cat-title">6. Head to Head in Tournament</span>
              ${badgeHtml(winCat6)}
            </div>
            <div class="h2h-cat-bar">
              <div class="h2h-cat-bar-a" style="width: ${bar6.a}%;"></div>
              <div class="h2h-cat-bar-b" style="width: ${bar6.b}%;"></div>
            </div>
            <div class="h2h-cat-subtext">
              ${directDebates.length > 0
                ? `${directDebates.length} debate${directDebates.length === 1 ? '' : 's'} where both debaters spoke on opposing sides`
                : 'No direct head-to-head tournament matchups on record'}
            </div>
          </div>
          <div class="h2h-cat-val ${winCat6 === 'B' ? 'val-win' : ''}" style="color: #f43f5e;">
            ${bDirectWins} <span style="font-size: 11px; font-weight: normal; color: rgba(255,255,255,0.6);">W</span>
          </div>
        </div>
      </div>

      <!-- Direct Matchups Section -->
      <div class="h2h-matchups-section">
        <div class="h2h-matchups-title">
          <span>DIRECT TOURNAMENT MATCHUPS (${directDebates.length})</span>
        </div>
        ${
          directDebates.length > 0
            ? directDebates
                .map((d) => {
                  const winnerIsA = d.a_won;
                  const winnerIsB = d.b_won;
                  const winnerColor = winnerIsA ? '#38bdf8' : (winnerIsB ? '#f43f5e' : '#fbbf24');
                  const outcomeText = d.winner_team_name ? `${escapeHtml(d.winner_team_name)} won` : 'Draw / Unrecorded';
                  const marginText = d.margin_a !== null && d.margin_a !== undefined ? ` · Net Margin: ${d.margin_a > 0 ? '+' : ''}${Number(d.margin_a).toFixed(1)} pts` : '';
                  const splitText = d.ballot_split ? ` · Ballot: ${d.ballot_split}` : '';

                  const cleanTour = (d.tournament_name || '').split('|')[0].trim();
                  let cleanRound = d.round_name || `Round ${d.round_number}`;
                  if (cleanRound.includes('Welcome to')) {
                    const match = cleanRound.match(/Round \d+|Octofinals|Quarterfinals|Semifinals|Grand Final/i);
                    cleanRound = match ? match[0] : `Round ${d.round_number}`;
                  }

                  return `
            <div class="h2h-matchup-card">
              <div class="h2h-matchup-header">
                <div class="h2h-matchup-tour">
                  ${escapeHtml(cleanTour)} <span style="font-size: 11px; color: rgba(255,255,255,0.5); font-weight: normal;">— ${escapeHtml(cleanRound)}</span>
                </div>
                <div class="h2h-matchup-outcome" style="color: ${winnerColor};">
                  ${outcomeText}${splitText}${marginText}
                </div>
              </div>

              <div class="h2h-matchup-body">
                <div class="h2h-matchup-team" style="color: #38bdf8; font-weight: 600;">
                  ${escapeHtml(d.team_a_name)} <span style="font-size: 11px; color: rgba(255,255,255,0.5);">(${d.side_a})</span>
                </div>
                <div style="font-family: var(--font-hero); font-size: 13px; color: rgba(255,255,255,0.4);">VS</div>
                <div class="h2h-matchup-team" style="color: #f43f5e; font-weight: 600; text-align: right;">
                  ${escapeHtml(d.team_b_name)} <span style="font-size: 11px; color: rgba(255,255,255,0.5);">(${d.side_b})</span>
                </div>
              </div>

              <div class="h2h-matchup-speeches">
                <div style="color: #38bdf8;">
                  ${escapeHtml(debaterA.name)}: ${d.pos_a || 'Speaker'} (${d.sub_score_a !== null && d.sub_score_a !== undefined ? Number(d.sub_score_a).toFixed(2) : '-'})
                </div>
                <div style="text-align: center; color: rgba(255,255,255,0.3); font-size: 10px;">SCORES</div>
                <div style="color: #f43f5e; text-align: right;">
                  ${escapeHtml(debaterB.name)}: ${d.pos_b || 'Speaker'} (${d.sub_score_b !== null && d.sub_score_b !== undefined ? Number(d.sub_score_b).toFixed(2) : '-'})
                </div>
              </div>
            </div>
          `;
                })
                .join('')
            : `
          <div class="h2h-no-matchups">
            <strong style="color: rgba(255,255,255,0.9); font-size: 13.5px; display: block; margin-bottom: 4px;">No Direct Head-to-Head Encounters on Record</strong>
            Neither debater has faced the other on opposing sides in an official circuit debate where both delivered speeches.
          </div>
        `
        }
      </div>
    `;
  }

  // ==========================================================================
  // 5. AI CHATBOT PAGE
  // ==========================================================================
  function initChatPage() {
    const input = document.getElementById('chatInput');
    const sendBtn = document.getElementById('chatSendBtn');

    if (sendBtn) {
      sendBtn.addEventListener('click', () => {
        const text = input ? input.value.trim() : '';
        if (text) sendChatPrompt(text);
      });
    }

    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          const text = input.value.trim();
          if (text) sendChatPrompt(text);
        }
      });
    }

    const urlParams = new URLSearchParams(window.location.search);
    const q = urlParams.get('q') || urlParams.get('query');
    if (q) {
      setTimeout(() => sendChatPrompt(q), 200);
    }
  }

  async function sendChatPrompt(promptText) {
    const messages = document.getElementById('chatMessages');
    const input = document.getElementById('chatInput');
    if (!messages) return;

    if (input) input.value = '';

    const userMsg = document.createElement('div');
    userMsg.className = 'chat-bubble user';
    userMsg.textContent = promptText;
    messages.appendChild(userMsg);

    const botMsg = document.createElement('div');
    botMsg.className = 'chat-bubble bot';
    botMsg.innerHTML = `<em>Thinking... querying Gemini 3.1 & atomos.db...</em>`;
    messages.appendChild(botMsg);
    messages.scrollTop = messages.scrollHeight;

    try {
      const res = await fetch(`${state.apiUrl}/api/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: promptText }),
      });

      if (res.ok) {
        const data = await res.json();
        const answer = data.answer || data.response || data.text;
        if (answer) {
          botMsg.innerHTML = formatMarkdownToHtml(answer);
          messages.scrollTop = messages.scrollHeight;
          return;
        } else if (data.error) {
          botMsg.innerHTML = `<div style="color: #f87171;">Engine Notice: ${escapeHtml(data.error)}</div>`;
          messages.scrollTop = messages.scrollHeight;
          return;
        }
      } else {
        const errData = await res.json().catch(() => ({}));
        const errMsg = errData.error || `Server responded with status ${res.status}`;
        botMsg.innerHTML = `<div style="color: #f87171;">Server Error: ${escapeHtml(errMsg)}</div>`;
        messages.scrollTop = messages.scrollHeight;
        return;
      }
    } catch (e) {
      console.warn('Direct AI query error:', e);
      botMsg.innerHTML = `<div style="color: #f87171;">Unable to communicate with the Atomos AI server at ${escapeHtml(state.apiUrl)}. Please ensure the backend server is running on port 5000.</div>`;
      messages.scrollTop = messages.scrollHeight;
      return;
    }
  }

  function formatInlineMarkdown(str) {
    if (!str) return '';
    let s = escapeHtml(str);
    s = s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*(.*?)\*/g, '<em>$1</em>');
    s = s.replace(/`(.*?)`/g, '<code>$1</code>');
    return s;
  }

  function formatMarkdownToHtml(text) {
    if (!text) return '';

    // Strip any residual emojis (strict website-wide ban)
    text = text.replace(/[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{2B50}-\u{2B55}]/gu, '');

    const lines = text.split('\n');
    const output = [];
    let inTable = false;
    let tableRows = [];

    function flushTable() {
      if (!inTable) return;
      if (tableRows.length > 0) {
        let html = '<div class="chat-table-wrap"><table class="chat-table">';
        tableRows.forEach((row, rIdx) => {
          const rawCells = row.split('|');
          const cells = rawCells.map(c => c.trim()).filter((c, i, arr) => i > 0 && i < arr.length - 1);
          if (rIdx === 0) {
            html += '<thead><tr>' + cells.map(c => `<th>${formatInlineMarkdown(c)}</th>`).join('') + '</tr></thead><tbody>';
          } else {
            html += '<tr>' + cells.map(c => `<td>${formatInlineMarkdown(c)}</td>`).join('') + '</tr>';
          }
        });
        html += '</tbody></table></div>';
        output.push(html);
      }
      inTable = false;
      tableRows = [];
    }

    for (let i = 0; i < lines.length; i++) {
      const rawLine = lines[i];
      const line = rawLine.trim();

      // Check if table row
      if (line.startsWith('|') && line.endsWith('|')) {
        // Delimiter line like | :--- | :--- |
        if (/^\|(\s*:?-+:?\s*\|)+$/.test(line)) {
          continue;
        }
        inTable = true;
        tableRows.push(line);
        continue;
      } else {
        flushTable();
      }

      if (!line) {
        output.push('<div style="height: 6px;"></div>');
        continue;
      }

      // Headers
      if (line.startsWith('### ')) {
        output.push(`<h3>${formatInlineMarkdown(line.slice(4))}</h3>`);
      } else if (line.startsWith('## ')) {
        output.push(`<h3>${formatInlineMarkdown(line.slice(3))}</h3>`);
      } else if (line.startsWith('# ')) {
        output.push(`<h3>${formatInlineMarkdown(line.slice(2))}</h3>`);
      } else if (line.startsWith('- ') || line.startsWith('* ')) {
        output.push(`<div style="margin: 3px 0 3px 14px;">• ${formatInlineMarkdown(line.slice(2))}</div>`);
      } else if (/^\d+\.\s+/.test(line)) {
        const match = line.match(/^(\d+\.)\s+(.*)$/);
        output.push(`<div style="margin: 3px 0 3px 14px;"><strong style="color: #38bdf8;">${match[1]}</strong> ${formatInlineMarkdown(match[2])}</div>`);
      } else {
        output.push(`<div>${formatInlineMarkdown(line)}</div>`);
      }
    }
    flushTable();

    return output.join('');
  }

  // Public API
  window.AtomosApp = {
    selectDebater,
    sendChatPrompt,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
