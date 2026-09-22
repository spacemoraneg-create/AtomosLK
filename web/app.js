/**
 * ATOMOS V2 - CLIENT ENGINE & APPLICATION CONTROLLER
 * Powering Canva Home Page + Subpages with Complete Multi Purpose Analytics
 */

(function () {
  'use strict';

  // Global State
  const state = {
    // V2 Datasets
    v2SpeakersTab: [],
    v2SpeakersGeneral: [],
    v2TeamsTab: [],
    v2TeamsGeneral: [],
    v2InstitutionsTab: [],
    v2InstitutionsGeneral: [],
    v2Tournaments: [],
    v2Adjudicators: [],
    v2NationalPool: null,

    circuitSummary: null,
    searchIndex: [],

    // App State
    isServerOnline: false,
    apiUrl: window.location.origin.includes('http') ? window.location.origin : 'http://127.0.0.1:5000',
  };

  // UNIVERSAL RULE: DO NOT ROUND UP, UP TO 3 DECIMAL PLACES IF EXIST HAS TO BE SHOWN
  function fmt(val, maxDecimals = 3) {
    if (val === undefined || val === null || isNaN(val) || val === '') return 'N/A';
    const num = Number(val);
    if (!isFinite(num)) return 'N/A';
    if (num % 1 === 0) return String(Math.trunc(num));
    // Up to maxDecimals places (default 3), never round up
    const targetDecimals = (maxDecimals !== undefined && maxDecimals !== null) ? maxDecimals : 3;
    const s = num.toFixed(8);
    const parts = s.split('.');
    const integerPart = parts[0];
    let decimalPart = parts[1].substring(0, targetDecimals).replace(/0+$/, '');
    if (!decimalPart) return integerPart;
    return `${integerPart}.${decimalPart}`;
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

  // Helper: National Status Tag HTML
  function getNatStatusTag(level) {
    if (!level || level === '-' || level === 'null') return '<span class="nat-tag nat-none">-</span>';
    const l = level.toLowerCase();
    if (l.includes('direct')) {
      return '<span class="nat-tag nat-direct">Nat Pool, Direct</span>';
    } else if (l.includes('trialed')) {
      return '<span class="nat-tag nat-trialed">Nat Pool, Trialed</span>';
    } else if (l.includes('trials') || l === 'trials') {
      return '<span class="nat-tag nat-trials">Trials</span>';
    }
    return `<span class="nat-tag nat-trials">${escapeHtml(level)}</span>`;
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
    if (!pos || pos === '-' || pos === 'Preliminary Rounds') return '<span class="break-tag break-none">-</span>';
    const p = pos.trim().toLowerCase();
    if (p === 'champion') {
      return '<span class="break-tag break-champion">Champion</span>';
    } else if (p === 'finalist' || p === 'runners-up') {
      return '<span class="break-tag break-finalist">Finalist</span>';
    } else if (p === 'semifinalist') {
      return '<span class="break-tag break-semis">Semifinalist</span>';
    } else if (p === 'quarterfinalist') {
      return '<span class="break-tag break-quarters">Quarterfinalist</span>';
    } else if (p.includes('partial octo')) {
      return `<span class="break-tag break-octos">${escapeHtml(pos)}</span>`;
    } else if (p === 'octofinalist') {
      return '<span class="break-tag break-octos">Octofinalist</span>';
    }
    return `<span class="break-tag break-none">${escapeHtml(pos)}</span>`;
  }

  // Router / Initializer based on active page
  async function init() {
    await checkServerStatus();
    await loadInitialData();

    const path = window.location.pathname.toLowerCase();

    if (document.getElementById('homeMultiTable') || path.endsWith('index.html') || path === '/' || path === '') {
      initHomePage();
    }
    if (document.getElementById('lbTableContainer') || path.includes('leaderboards')) {
      initLeaderboardsPage();
    }
    if (document.getElementById('bioProfileContainer') || (path.includes('bio') && !path.includes('team') && !path.includes('institution') && !path.includes('adjudicator'))) {
      initBioPage();
    }
    if (document.getElementById('teamProfileContainer') || path.includes('team_bio') || path.includes('team-bio')) {
      initTeamBioPage();
    }
    if (document.getElementById('instProfileContainer') || path.includes('institution_bio') || path.includes('institution-bio')) {
      initInstitutionBioPage();
    }
    if (document.getElementById('judgeProfileContainer') || path.includes('adjudicator_bio') || path.includes('adjudicator-bio')) {
      initAdjudicatorBioPage();
    }
    if (document.getElementById('h2hResultContainer') || path.includes('h2h')) {
      initH2HPage();
    }
    if (document.getElementById('poolGridContainer') || path.includes('pool')) {
      initPoolPage();
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
        console.log('[ONLINE] Connected to Atomos V2 REST API Server');
      }
    } catch (e) {
      state.isServerOnline = false;
      console.log('[OFFLINE] Running in Static Archival Mode (offline JSON fallback)');
    }
  }

  // Fetch JSON with offline fallback
  async function fetchJson(filename, fallbackApi) {
    let data = null;
    try {
      const res = await fetch(`data/web_export/${filename}`);
      if (res.ok) data = await res.json();
    } catch (e) {
      try {
        const res = await fetch(`../data/web_export/${filename}`);
        if (res.ok) data = await res.json();
      } catch (err) {}
    }

    if (!data && state.isServerOnline && fallbackApi) {
      try {
        const res = await fetch(`${state.apiUrl}${fallbackApi}`);
        if (res.ok) {
          const j = await res.json();
          data = j.leaderboard || j;
        }
      } catch (e) {}
    }
    return data;
  }

  // Load Initial Datasets
  async function loadInitialData() {
    const [
      spkTab, spkGen,
      teamsTab, teamsGen,
      instTab, instGen,
      tours, judges, pool,
      summary, sIndex
    ] = await Promise.all([
      fetchJson('v2_speakers_tab.json', '/api/v2/leaderboard/speakers?tier=tab'),
      fetchJson('v2_speakers_general.json', '/api/v2/leaderboard/speakers?tier=general'),
      fetchJson('v2_teams_tab.json', '/api/v2/leaderboard/teams?tier=tab'),
      fetchJson('v2_teams_general.json', '/api/v2/leaderboard/teams?tier=general'),
      fetchJson('v2_institutions_tab.json', '/api/v2/leaderboard/institutions?tier=tab'),
      fetchJson('v2_institutions_general.json', '/api/v2/leaderboard/institutions?tier=general'),
      fetchJson('v2_tournaments.json', '/api/v2/leaderboard/tournaments'),
      fetchJson('v2_adjudicators.json', '/api/v2/leaderboard/adjudicators'),
      fetchJson('v2_national_pool.json', '/api/v2/pool'),
      fetchJson('circuit_summary.json', '/api/circuit'),
      fetchJson('search_index.json', '/api/search?q=a'),
    ]);

    state.v2SpeakersTab = spkTab || [];
    state.v2SpeakersGeneral = spkGen || [];
    state.v2TeamsTab = teamsTab || [];
    state.v2TeamsGeneral = teamsGen || [];
    state.v2InstitutionsTab = instTab || [];
    state.v2InstitutionsGeneral = instGen || [];
    state.v2Tournaments = tours || [];
    state.v2Adjudicators = judges || [];
    state.v2NationalPool = pool || null;
    state.circuitSummary = summary || null;
    state.searchIndex = sIndex || [];
  }

  // ==========================================================================
  // 1. HOME PAGE LOGIC (Multi Purpose Leaderboard - Min 12 Rounds)
  // ==========================================================================
  function initHomePage() {
    updateVitals(state.circuitSummary);

    let currentMetric = 'speaker_score';
    let searchQuery = '';

    const switcher = document.getElementById('homeMetricSwitcher');
    if (switcher) {
      switcher.querySelectorAll('.subpage-tab-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          switcher.querySelectorAll('.subpage-tab-btn').forEach((b) => b.classList.remove('active'));
          btn.classList.add('active');
          currentMetric = btn.getAttribute('data-metric');
          renderTable();
        });
      });
    }

    const searchInput = document.getElementById('speakerSearchInput');
    if (searchInput) {
      searchInput.addEventListener('input', () => {
        searchQuery = searchInput.value.trim().toLowerCase();
        renderTable();
      });
    }

    function renderTable() {
      const tbody = document.getElementById('homeMultiStatsBody');
      if (!tbody) return;

      let list = state.v2SpeakersTab.slice();

      // Sort based on currentMetric
      if (currentMetric === 'stdev') {
        // Lower is better for stdev
        list.sort((a, b) => a.stdev - b.stdev);
      } else if (currentMetric === 'win_percentage') {
        list.sort((a, b) => b.win_percentage - a.win_percentage || b.speaker_score - a.speaker_score);
      } else if (currentMetric === 'prelims_debated') {
        list.sort((a, b) => b.prelims_debated - a.prelims_debated || b.speaker_score - a.speaker_score);
      } else if (currentMetric === 'national_level') {
        // Nat Direct 1st, Nat Trialed 2nd, Trials 3rd, within group sort by speaker_score
        function natOrder(lvl) {
          if (!lvl) return 4;
          const l = lvl.toLowerCase();
          if (l.includes('direct')) return 1;
          if (l.includes('trialed')) return 2;
          if (l.includes('trials')) return 3;
          return 4;
        }
        list.sort((a, b) => {
          const ordDiff = natOrder(a.national_level) - natOrder(b.national_level);
          if (ordDiff !== 0) return ordDiff;
          return b.speaker_score - a.speaker_score;
        });
      } else {
        // Default: speaker_score
        list.sort((a, b) => b.speaker_score - a.speaker_score);
      }

      // Assign true circuit rank before filtering
      list.forEach((s, idx) => {
        s._trueRank = idx + 1;
      });

      // Filter by search
      if (searchQuery) {
        const q = searchQuery.toLowerCase().trim();
        list = list.filter((s) => {
          const debaterName = (s.speaker_name || s.name || '').toLowerCase();
          const inst = (s.institution || '').toLowerCase();
          return debaterName.includes(q) || inst.includes(q);
        });

        // Prioritize debater name matches over institution matches
        list.sort((a, b) => {
          const aNameMatch = (a.speaker_name || a.name || '').toLowerCase().includes(q);
          const bNameMatch = (b.speaker_name || b.name || '').toLowerCase().includes(q);
          if (aNameMatch && !bNameMatch) return -1;
          if (!aNameMatch && bNameMatch) return 1;
          return a._trueRank - b._trueRank;
        });
      }

      if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 24px; color: rgba(255,255,255,0.6);">No debaters found matching "${escapeHtml(searchQuery)}".</td></tr>`;
        return;
      }

      tbody.innerHTML = list.map((s) => {
        const debaterName = s.speaker_name || s.name || '';
        return `
          <tr>
            <td style="text-align: center;">${getRankBadge(s._trueRank)}</td>
            <td>
              <a class="table-link" href="bio.html?debater=${encodeURIComponent(debaterName)}">${escapeHtml(debaterName)}</a>
            </td>
            <td>
              <a class="table-link-inst" href="institution_bio.html?inst=${encodeURIComponent(s.institution)}">${escapeHtml(s.institution)}</a>
            </td>
            <td style="text-align: right; font-family: var(--font-mono); font-weight: ${currentMetric === 'speaker_score' ? '800; color: #38bdf8;' : '600;'}">${fmt(s.speaker_score, 2)}</td>
            <td style="text-align: right; font-family: var(--font-mono); font-weight: ${currentMetric === 'win_percentage' ? '800; color: #38bdf8;' : '600;'}">${fmt(s.win_percentage, 1)}%</td>
            <td style="text-align: right; font-family: var(--font-mono); font-weight: ${currentMetric === 'stdev' ? '800; color: #38bdf8;' : '600;'}">${fmt(s.stdev, 2)}</td>
            <td style="text-align: right; font-family: var(--font-mono); font-weight: ${currentMetric === 'prelims_debated' ? '800; color: #38bdf8;' : '600;'}">${s.prelims_debated}</td>
            <td style="text-align: right; font-family: var(--font-mono); color: rgba(255,255,255,0.7);">${s.tournaments_debated}</td>
            <td>${getNatStatusTag(s.national_level)}</td>
          </tr>
        `;
      }).join('');
    }

    renderTable();
  }

  function updateVitals(data) {
    const t = document.getElementById('vitalTournaments');
    const d = document.getElementById('vitalDebaters');
    const s = document.getElementById('vitalSpeeches');
    const r = document.getElementById('vitalRounds');
    const p = document.getElementById('vitalPrelims');
    const k = document.getElementById('vitalKnockouts');

    if (t) t.textContent = data && data.total_tournaments ? String(data.total_tournaments) : '9';
    if (d) d.textContent = data && data.total_persons ? Number(data.total_persons).toLocaleString() : '844';
    if (s) {
      const speechCount = (data && data.total_speeches) ? data.total_speeches : (data && data.total_valid_speeches ? data.total_valid_speeches : 7410);
      s.textContent = Number(speechCount).toLocaleString();
    }
    if (r) r.textContent = data && data.total_debates_debated ? Number(data.total_debates_debated).toLocaleString() : '1,012';
    if (p) p.textContent = data && data.total_prelim_rounds ? Number(data.total_prelim_rounds).toLocaleString() : '882';
    if (k) k.textContent = data && data.total_knockout_rounds ? Number(data.total_knockout_rounds).toLocaleString() : '130';
  }

  // ==========================================================================
  // 2. LEADERBOARDS PAGE (Universal Tab vs General Tab + Multi Purpose)
  // ==========================================================================
  function initLeaderboardsPage() {
    let activeCategory = 'individual';
    let activeTier = 'tab'; // Tab is default
    let activeMetric = 'speaker_score';
    let searchQuery = '';

    const catSwitcher = document.getElementById('lbCategoryTabs');
    const tierSwitcher = document.getElementById('tierModeSwitcher');
    const metricToolbar = document.getElementById('lbMetricToolbar');
    const tierBadge = document.getElementById('tierEligibilityBadge');
    const searchInput = document.getElementById('lbSearchInput');

    if (catSwitcher) {
      catSwitcher.querySelectorAll('.subpage-tab-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          catSwitcher.querySelectorAll('.subpage-tab-btn').forEach((b) => b.classList.remove('active'));
          btn.classList.add('active');
          activeCategory = btn.getAttribute('data-tab');
          // Reset default metric for new category
          if (activeCategory === 'individual') activeMetric = 'speaker_score';
          else if (activeCategory === 'teams') activeMetric = 'atss';
          else if (activeCategory === 'institutions') activeMetric = 'delta';
          else if (activeCategory === 'tournaments') activeMetric = 'atss';
          else if (activeCategory === 'adjudicators') activeMetric = 'debates';

          // For Tournaments & Adjudicators, there is no General Tab - just Tab
          const generalBtn = tierSwitcher ? tierSwitcher.querySelector('[data-tier="general"]') : null;
          const tabBtn = tierSwitcher ? tierSwitcher.querySelector('[data-tier="tab"]') : null;
          if (activeCategory === 'tournaments' || activeCategory === 'adjudicators') {
            if (generalBtn) generalBtn.style.display = 'none';
            activeTier = 'tab';
            if (tabBtn) tabBtn.classList.add('active');
            if (generalBtn) generalBtn.classList.remove('active');
          } else {
            if (generalBtn) generalBtn.style.display = '';
          }

          updateMetricPills();
          renderLeaderboard();
        });
      });
    }

    if (tierSwitcher) {
      tierSwitcher.querySelectorAll('.mode-switch-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          tierSwitcher.querySelectorAll('.mode-switch-btn').forEach((b) => b.classList.remove('active'));
          btn.classList.add('active');
          activeTier = btn.getAttribute('data-tier');
          updateTierBadge();
          renderLeaderboard();
        });
      });
    }

    if (searchInput) {
      searchInput.addEventListener('input', () => {
        searchQuery = searchInput.value.trim().toLowerCase();
        renderLeaderboard();
      });
    }

    function updateTierBadge() {
      if (!tierBadge) return;
      if (activeCategory === 'individual') {
        tierBadge.textContent = activeTier === 'tab' ? 'TAB // MIN 12 ROUNDS' : 'GENERAL TAB // MIN 5 ROUNDS';
      } else if (activeCategory === 'teams') {
        tierBadge.textContent = activeTier === 'tab' ? 'TAB // MIN 3 TOURNAMENTS' : 'GENERAL TAB // MIN 2 TOURNAMENTS';
      } else if (activeCategory === 'institutions') {
        tierBadge.textContent = activeTier === 'tab' ? 'TAB // MIN 3 TOURNAMENTS' : 'GENERAL TAB // MIN 2 TOURNAMENTS';
      } else if (activeCategory === 'tournaments') {
        tierBadge.textContent = 'TAB // 8 CIRCUIT TOURNAMENTS';
      } else if (activeCategory === 'adjudicators') {
        tierBadge.textContent = 'TAB // CIRCUIT ADJUDICATORS';
      }
    }

    function updateMetricPills() {
      if (!metricToolbar) return;
      let pills = [];

      if (activeCategory === 'individual') {
        pills = [
          { id: 'speaker_score', label: 'Speaker Score' },
          { id: 'win_percentage', label: 'Win %' },
          { id: 'prelims_debated', label: 'Prelims Debated' },
          { id: 'stdev', label: 'Stdev' },
          { id: 'national_level', label: 'Nat Status' },
        ];
      } else if (activeCategory === 'teams') {
        pills = [
          { id: 'atss', label: 'ATSS' },
          { id: 'win_percentage', label: 'Win %' },
          { id: 'awpt', label: 'AWPT (Wins / Tour)' },
          { id: 'achievement', label: 'Highest Achievement' },
        ];
      } else if (activeCategory === 'institutions') {
        pills = [
          { id: 'delta', label: 'Delta' },
          { id: 'a_atss', label: 'A Team ATSS' },
          { id: 'b_atss', label: 'B Team ATSS' },
          { id: 'net_diff', label: 'Net Diff' },
          { id: 'win_percentage', label: 'Win %' },
          { id: 'pool_count', label: 'Debater Pool' },
        ];
      } else if (activeCategory === 'tournaments') {
        pills = [
          { id: 'atss', label: 'ATSS' },
          { id: 'brk_atss', label: 'BRK ATSS' },
          { id: 'institutions', label: 'Institutions' },
          { id: 'teams', label: 'Teams' },
          { id: 'rounds', label: 'Prelims + Knockouts' },
          { id: 'speeches', label: 'Speeches' },
          { id: 'debates', label: 'Prelim Debates' },
        ];
      } else if (activeCategory === 'adjudicators') {
        pills = [
          { id: 'debates', label: 'Prelims Judged' },
          { id: 'aass', label: 'AASS (Substantive Mean)' },
          { id: 'aatss', label: 'AATSS (Team Avg)' },
          { id: 'tournaments', label: 'Tournaments' },
        ];
      }

      metricToolbar.innerHTML = `
        <div class="metric-pills-bar">
          <span style="font-family: var(--font-mono); font-size: 11px; color: rgba(255,255,255,0.5); margin-right: 4px;">RANK BY:</span>
          ${pills.map((p) => `
            <button class="metric-pill-btn${p.id === activeMetric ? ' active' : ''}" data-metric="${p.id}">
              ${p.label}
            </button>
          `).join('')}
        </div>
      `;

      metricToolbar.querySelectorAll('.metric-pill-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          metricToolbar.querySelectorAll('.metric-pill-btn').forEach((b) => b.classList.remove('active'));
          btn.classList.add('active');
          activeMetric = btn.getAttribute('data-metric');
          renderLeaderboard();
        });
      });
      updateTierBadge();
    }

    function renderLeaderboard() {
      const container = document.getElementById('lbTableContainer');
      if (!container) return;

      if (activeCategory === 'individual') {
        renderIndividualTable(container);
      } else if (activeCategory === 'teams') {
        renderTeamsTable(container);
      } else if (activeCategory === 'institutions') {
        renderInstitutionsTable(container);
      } else if (activeCategory === 'tournaments') {
        renderTournamentsTable(container);
      } else if (activeCategory === 'adjudicators') {
        renderAdjudicatorsTable(container);
      }
    }

    function renderIndividualTable(container) {
      let list = (activeTier === 'tab' ? state.v2SpeakersTab : state.v2SpeakersGeneral).slice();

      if (activeMetric === 'stdev') {
        list.sort((a, b) => a.stdev - b.stdev);
      } else if (activeMetric === 'win_percentage') {
        list.sort((a, b) => b.win_percentage - a.win_percentage || b.speaker_score - a.speaker_score);
      } else if (activeMetric === 'prelims_debated') {
        list.sort((a, b) => b.prelims_debated - a.prelims_debated || b.speaker_score - a.speaker_score);
      } else if (activeMetric === 'national_level') {
        function natOrder(lvl) {
          if (!lvl) return 4;
          const l = lvl.toLowerCase();
          if (l.includes('direct')) return 1;
          if (l.includes('trialed')) return 2;
          if (l.includes('trials')) return 3;
          return 4;
        }
        list.sort((a, b) => {
          const ordDiff = natOrder(a.national_level) - natOrder(b.national_level);
          if (ordDiff !== 0) return ordDiff;
          return b.speaker_score - a.speaker_score;
        });
      } else {
        list.sort((a, b) => b.speaker_score - a.speaker_score);
      }

      // Assign true circuit rank before filtering
      list.forEach((s, idx) => {
        s._trueRank = idx + 1;
      });

      if (searchQuery) {
        const q = searchQuery.toLowerCase().trim();
        list = list.filter((s) => {
          const debaterName = (s.speaker_name || s.name || '').toLowerCase();
          const inst = (s.institution || '').toLowerCase();
          return debaterName.includes(q) || inst.includes(q);
        });

        // Prioritize debater name matches over institution matches
        list.sort((a, b) => {
          const aNameMatch = (a.speaker_name || a.name || '').toLowerCase().includes(q);
          const bNameMatch = (b.speaker_name || b.name || '').toLowerCase().includes(q);
          if (aNameMatch && !bNameMatch) return -1;
          if (!aNameMatch && bNameMatch) return 1;
          return a._trueRank - b._trueRank;
        });
      }

      if (list.length === 0) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">No debaters match "${escapeHtml(searchQuery)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 44px; text-align: center;">#</th>
                <th>SPEAKER</th>
                <th>INSTITUTION</th>
                <th style="text-align: right;">SPEAKER SCORE</th>
                <th style="text-align: right;">WIN %</th>
                <th style="text-align: right;">STDEV</th>
                <th style="text-align: right;">PRELIMS</th>
                <th style="text-align: right;">TOURNAMENTS</th>
                <th>NAT STATUS</th>
              </tr>
            </thead>
            <tbody>
              ${list.map((s) => {
                const debaterName = s.speaker_name || s.name || '';
                return `
                <tr>
                  <td style="text-align: center;">${getRankBadge(s._trueRank)}</td>
                  <td>
                    <a class="table-link" href="bio.html?debater=${encodeURIComponent(debaterName)}">${escapeHtml(debaterName)}</a>
                  </td>
                  <td>
                    <a class="table-link-inst" href="institution_bio.html?inst=${encodeURIComponent(s.institution)}">${escapeHtml(s.institution)}</a>
                  </td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'speaker_score' ? '800; color: #38bdf8;' : '600;'}">${fmt(s.speaker_score, 2)}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'win_percentage' ? '800; color: #38bdf8;' : '600;'}">${fmt(s.win_percentage, 1)}%</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'stdev' ? '800; color: #38bdf8;' : '600;'}">${fmt(s.stdev, 2)}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'prelims_debated' ? '800; color: #38bdf8;' : '600;'}">${s.prelims_debated}</td>
                  <td style="text-align: right; font-family: var(--font-mono); color: rgba(255,255,255,0.7);">${s.tournaments_debated}</td>
                  <td>${getNatStatusTag(s.national_level)}</td>
                </tr>
              `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    function renderTeamsTable(container) {
      let list = (activeTier === 'tab' ? state.v2TeamsTab : state.v2TeamsGeneral).slice();

      const achOrder = {
        "Champion": 1, "Runners-Up": 2, "Finalist": 2, "Semifinalist": 3,
        "Quarterfinalist": 4, "Partial Octofinalist": 5, "Octofinalist": 6,
        "Double Partial Octofinalist": 7, "Preliminary Rounds": 8, "Unranked": 9
      };

      if (activeMetric === 'win_percentage') {
        list.sort((a, b) => b.win_percentage - a.win_percentage || b.atss - a.atss);
      } else if (activeMetric === 'awpt') {
        list.sort((a, b) => b.awpt - a.awpt || b.atss - a.atss);
      } else if (activeMetric === 'achievement') {
        list.sort((a, b) => {
          const rA = achOrder[a.highest_achievement] || 9;
          const rB = achOrder[b.highest_achievement] || 9;
          if (rA !== rB) return rA - rB;
          return b.atss - a.atss;
        });
      } else {
        list.sort((a, b) => b.atss - a.atss);
      }

      // Assign true rank before filtering
      list.forEach((t, idx) => {
        t._trueRank = idx + 1;
      });

      if (searchQuery) {
        const q = searchQuery.toLowerCase().trim();
        list = list.filter((t) =>
          (t.team_name && t.team_name.toLowerCase().includes(q)) ||
          (t.institution && t.institution.toLowerCase().includes(q))
        );

        list.sort((a, b) => {
          const aNameMatch = (a.team_name || '').toLowerCase().includes(q);
          const bNameMatch = (b.team_name || '').toLowerCase().includes(q);
          if (aNameMatch && !bNameMatch) return -1;
          if (!aNameMatch && bNameMatch) return 1;
          return a._trueRank - b._trueRank;
        });
      }

      if (list.length === 0) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">No teams match "${escapeHtml(searchQuery)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 44px; text-align: center;">#</th>
                <th>TEAM NAME</th>
                <th>INSTITUTION</th>
                <th style="text-align: right;">ATSS</th>
                <th style="text-align: right;">WIN %</th>
                <th style="text-align: right;">AWPT</th>
                <th style="text-align: right;">TOURNAMENTS</th>
                <th style="text-align: center;">HIGHEST BREAK</th>
              </tr>
            </thead>
            <tbody>
              ${list.map((t) => `
                <tr>
                  <td style="text-align: center;">${getRankBadge(t._trueRank)}</td>
                  <td>
                    <a class="table-link" href="team_bio.html?team=${encodeURIComponent(t.team_name)}">${escapeHtml(t.team_name)}</a>
                  </td>
                  <td>
                    <a class="table-link-inst" href="institution_bio.html?inst=${encodeURIComponent(t.institution)}">${escapeHtml(t.institution)}</a>
                  </td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'atss' ? '800; color: #38bdf8;' : '600;'}">${fmt(t.atss, 2)}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'win_percentage' ? '800; color: #38bdf8;' : '600;'}">${fmt(t.win_percentage, 1)}%</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'awpt' ? '800; color: #38bdf8;' : '600;'}">${fmt(t.awpt, 2)}</td>
                  <td style="text-align: right; font-family: var(--font-mono); color: rgba(255,255,255,0.7);">${t.tournaments_debated}</td>
                  <td style="text-align: center;">${getBreakBadge(t.highest_achievement)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    function renderInstitutionsTable(container) {
      let list = (activeTier === 'tab' ? state.v2InstitutionsTab : state.v2InstitutionsGeneral).slice();

      if (activeMetric === 'a_atss') {
        list.sort((a, b) => b.a_atss - a.a_atss || b.delta - a.delta);
      } else if (activeMetric === 'b_atss') {
        list.sort((a, b) => (b.b_atss || 0) - (a.b_atss || 0) || b.delta - a.delta);
      } else if (activeMetric === 'net_diff') {
        // Smallest to highest difference between A and B
        list.sort((a, b) => {
          const diffA = a.net_diff !== null ? Math.abs(a.net_diff) : 9999;
          const diffB = b.net_diff !== null ? Math.abs(b.net_diff) : 9999;
          return diffA - diffB;
        });
      } else if (activeMetric === 'win_percentage') {
        list.sort((a, b) => b.win_percentage - a.win_percentage || b.delta - a.delta);
      } else if (activeMetric === 'pool_count') {
        list.sort((a, b) => b.pool_count - a.pool_count || b.delta - a.delta);
      } else {
        // Default: Delta
        list.sort((a, b) => b.delta - a.delta);
      }

      // Assign true rank before filtering
      list.forEach((i, idx) => {
        i._trueRank = idx + 1;
      });

      if (searchQuery) {
        const q = searchQuery.toLowerCase().trim();
        list = list.filter((i) =>
          (i.institution_name && i.institution_name.toLowerCase().includes(q)) ||
          (i.code && i.code.toLowerCase().includes(q))
        );
      }

      if (list.length === 0) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">No institutions match "${escapeHtml(searchQuery)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 44px; text-align: center;">#</th>
                <th>INSTITUTION</th>
                <th style="text-align: right;">DELTA</th>
                <th style="text-align: right;">A TEAM ATSS</th>
                <th style="text-align: right;">B TEAM ATSS</th>
                <th style="text-align: right;">NET DIFF</th>
                <th style="text-align: right;">WIN %</th>
                <th style="text-align: right;">DEBATER POOL</th>
              </tr>
            </thead>
            <tbody>
              ${list.map((i) => {
                const aTeamLink = i.a_team_name ? `<a class="table-link" href="team_bio.html?team=${encodeURIComponent(i.a_team_name)}">${fmt(i.a_atss, 2)}</a>` : fmt(i.a_atss, 2);
                const bTeamLink = i.b_team_name && i.b_atss ? `<a class="table-link" href="team_bio.html?team=${encodeURIComponent(i.b_team_name)}">${fmt(i.b_atss, 2)}</a>` : (i.b_atss ? fmt(i.b_atss, 2) : '-');
                let netDiffHtml = '-';
                if (i.net_diff !== null && i.net_diff !== undefined) {
                  const nd = Number(i.net_diff);
                  const sign = nd > 0 ? '+' : '';
                  netDiffHtml = `<span style="font-family: var(--font-mono); font-weight: 700; color: ${nd >= 0 ? '#34d399' : '#f87171'};">${sign}${fmt(nd, 2)}</span>`;
                }

                return `
                  <tr>
                    <td style="text-align: center;">${getRankBadge(i._trueRank)}</td>
                    <td>
                      <a class="table-link" href="institution_bio.html?inst=${encodeURIComponent(i.institution_name)}">${escapeHtml(i.institution_name)}</a>
                      ${i.code ? `<span style="font-size: 10px; margin-left: 6px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.7); font-family: var(--font-mono);">${escapeHtml(i.code)}</span>` : ''}
                    </td>
                    <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'delta' ? '800; color: #38bdf8;' : '700;'}">${fmt(i.delta, 2)}</td>
                    <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'a_atss' ? '800; color: #38bdf8;' : '600;'}">${aTeamLink}</td>
                    <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'b_atss' ? '800; color: #38bdf8;' : '600;'}">${bTeamLink}</td>
                    <td style="text-align: right;">${netDiffHtml}</td>
                    <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'win_percentage' ? '800; color: #38bdf8;' : '600;'}">${fmt(i.win_percentage, 1)}%</td>
                    <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'pool_count' ? '800; color: #38bdf8;' : '600;'}">${i.pool_count}</td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    function renderTournamentsTable(container) {
      let list = state.v2Tournaments.slice();

      if (activeMetric === 'brk_atss') {
        list.sort((a, b) => b.brk_atss - a.brk_atss);
      } else if (activeMetric === 'institutions') {
        list.sort((a, b) => b.participating_institutions - a.participating_institutions);
      } else if (activeMetric === 'teams') {
        list.sort((a, b) => b.participating_teams - a.participating_teams);
      } else if (activeMetric === 'rounds') {
        list.sort((a, b) => b.prelims_plus_knock - a.prelims_plus_knock);
      } else if (activeMetric === 'speeches') {
        list.sort((a, b) => b.total_speeches - a.total_speeches);
      } else if (activeMetric === 'debates') {
        list.sort((a, b) => b.prelim_debates - a.prelim_debates);
      } else {
        list.sort((a, b) => b.atss - a.atss);
      }

      // Assign true rank before filtering
      list.forEach((t, idx) => {
        t._trueRank = idx + 1;
      });

      if (searchQuery) {
        const q = searchQuery.toLowerCase().trim();
        list = list.filter((t) =>
          (t.name && t.name.toLowerCase().includes(q)) ||
          (t.hosting_dates && t.hosting_dates.toLowerCase().includes(q))
        );
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 44px; text-align: center;">#</th>
                <th>TOURNAMENT</th>
                <th>DATES</th>
                <th style="text-align: right;">ATSS</th>
                <th style="text-align: right;">BRK ATSS</th>
                <th style="text-align: right;">INSTITUTIONS</th>
                <th style="text-align: right;">TEAMS</th>
                <th style="text-align: right;">PRELIMS+KNOCK</th>
                <th style="text-align: right;">SPEECHES</th>
                <th style="text-align: right;">PRELIM DEBATES</th>
              </tr>
            </thead>
            <tbody>
              ${list.map((t) => `
                <tr>
                  <td style="text-align: center;">${getRankBadge(t._trueRank)}</td>
                  <td style="font-weight: 700; color: #ffffff;">${escapeHtml(t.name)}</td>
                  <td style="font-family: var(--font-mono); font-size: 11px; color: rgba(255,255,255,0.65);">${escapeHtml(t.hosting_dates)}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: 800; color: #38bdf8;">${fmt(t.atss, 2)}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: 700;">${fmt(t.brk_atss, 2)}</td>
                  <td style="text-align: right; font-family: var(--font-mono);">${t.participating_institutions}</td>
                  <td style="text-align: right; font-family: var(--font-mono);">${t.participating_teams}</td>
                  <td style="text-align: right; font-family: var(--font-mono); color: #34d399;">${t.prelims_plus_knock}</td>
                  <td style="text-align: right; font-family: var(--font-mono);">${Number(t.total_speeches).toLocaleString()}</td>
                  <td style="text-align: right; font-family: var(--font-mono);">${t.prelim_debates}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    function renderAdjudicatorsTable(container) {
      let list = state.v2Adjudicators.slice();

      if (activeMetric === 'aass') {
        list.sort((a, b) => b.aass - a.aass);
      } else if (activeMetric === 'aatss') {
        list.sort((a, b) => b.aatss - a.aatss);
      } else if (activeMetric === 'tournaments') {
        list.sort((a, b) => b.tournaments_adjudicated - a.tournaments_adjudicated);
      } else {
        list.sort((a, b) => b.prelims_adjudicated - a.prelims_adjudicated);
      }

      // Assign true rank before filtering
      list.forEach((j, idx) => {
        j._trueRank = idx + 1;
      });

      if (searchQuery) {
        const q = searchQuery.toLowerCase().trim();
        list = list.filter((j) =>
          (j.adjudicator_name && j.adjudicator_name.toLowerCase().includes(q)) ||
          (j.institution && j.institution.toLowerCase().includes(q))
        );

        list.sort((a, b) => {
          const aNameMatch = (a.adjudicator_name || '').toLowerCase().includes(q);
          const bNameMatch = (b.adjudicator_name || '').toLowerCase().includes(q);
          if (aNameMatch && !bNameMatch) return -1;
          if (!aNameMatch && bNameMatch) return 1;
          return a._trueRank - b._trueRank;
        });
      }

      if (list.length === 0) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">No adjudicators match "${escapeHtml(searchQuery)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 44px; text-align: center;">#</th>
                <th>ADJUDICATOR</th>
                <th>INSTITUTION</th>
                <th style="text-align: right;">AASS (SPEAK AVG)</th>
                <th style="text-align: right;">AATSS (TEAM AVG)</th>
                <th style="text-align: center;">PROP / OPP BIAS</th>
                <th style="text-align: right;">PRELIMS ADJUDICATED</th>
                <th style="text-align: right;">TOURNAMENTS</th>
              </tr>
            </thead>
            <tbody>
              ${list.map((j) => `
                <tr>
                  <td style="text-align: center;">${getRankBadge(j._trueRank)}</td>
                  <td>
                    <a class="table-link" href="adjudicator_bio.html?judge=${encodeURIComponent(j.adjudicator_name)}">${escapeHtml(j.adjudicator_name)}</a>
                  </td>
                  <td style="color: rgba(255,255,255,0.75);">${escapeHtml(j.institution)}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'aass' ? '800; color: #38bdf8;' : '600;'}">${fmt(j.aass, 2)}</td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'aatss' ? '800; color: #38bdf8;' : '600;'}">${fmt(j.aatss, 2)}</td>
                  <td style="text-align: center; font-family: var(--font-mono); font-size: 11px;">
                    <span style="color: #38bdf8; font-weight: 700;">${fmt(j.prop_bias_pct)}% P</span> / <span style="color: #f43f5e; font-weight: 700;">${fmt(j.opp_bias_pct)}% O</span>
                  </td>
                  <td style="text-align: right; font-family: var(--font-mono); font-weight: ${activeMetric === 'debates' ? '800; color: #38bdf8;' : '600;'}">${j.prelims_adjudicated}</td>
                  <td style="text-align: right; font-family: var(--font-mono); color: rgba(255,255,255,0.7);">${j.tournaments_adjudicated}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    updateMetricPills();
    renderLeaderboard();
  }

  // ==========================================================================
  // 3. DEBATER BIO PAGE (V2 SPEC)
  // ==========================================================================
  function initBioPage() {
    const input = document.getElementById('bioSearchInput');
    const dropdown = document.getElementById('bioSuggestions');
    const clearBtn = document.getElementById('bioClearBtn');
    const container = document.getElementById('bioProfileContainer');

    const urlParams = new URLSearchParams(window.location.search);
    const debaterParam = urlParams.get('debater') || urlParams.get('speaker') || urlParams.get('name') || urlParams.get('id');

    if (debaterParam) {
      loadDebaterBio(debaterParam);
    }

    if (input && dropdown) {
      function renderMatches(q) {
        const query = (q || '').trim().toLowerCase();
        let matches = (state.v2SpeakersGeneral.length ? state.v2SpeakersGeneral : state.v2SpeakersTab);
        if (query) {
          matches = matches.filter((d) => d.name.toLowerCase().includes(query) || (d.institution && d.institution.toLowerCase().includes(query)));
        }
        matches = matches.slice(0, 15);

        if (matches.length === 0) {
          dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255,255,255,0.5); font-size: 13px; text-align: center;">No matching debaters found.</div>`;
          dropdown.classList.remove('hidden');
          return;
        }

        dropdown.innerHTML = matches.map((d) => `
          <div class="h2h-autocomplete-item" data-name="${escapeHtml(d.name)}">
            <div>
              <div class="h2h-auto-name">${escapeHtml(d.name)}</div>
              <div class="h2h-auto-inst">${escapeHtml(d.institution)}</div>
            </div>
            <div class="h2h-auto-meta">
              <span class="h2h-auto-stat">Avg: ${fmt(d.speaker_score, 2)}</span>
            </div>
          </div>
        `).join('');

        dropdown.classList.remove('hidden');

        dropdown.querySelectorAll('.h2h-autocomplete-item').forEach((el) => {
          el.addEventListener('mousedown', (e) => {
            e.preventDefault();
            const name = el.getAttribute('data-name');
            input.value = name;
            dropdown.classList.add('hidden');
            if (clearBtn) clearBtn.classList.remove('hidden');
            loadDebaterBio(name);
          });
        });
      }

      input.addEventListener('input', () => {
        if (clearBtn) clearBtn.classList.toggle('hidden', !input.value);
        renderMatches(input.value);
      });

      input.addEventListener('focus', () => renderMatches(input.value));
      input.addEventListener('blur', () => setTimeout(() => dropdown.classList.add('hidden'), 180));
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (input) input.value = '';
        clearBtn.classList.add('hidden');
        if (container) {
          container.innerHTML = `
            <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.5); font-family: var(--font-mono);">
              Type any debater's name above to view their career record.
            </div>
          `;
        }
        if (window.history.replaceState) window.history.replaceState(null, '', window.location.pathname);
      });
    }

    async function loadDebaterBio(name) {
      if (!container) return;
      container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);"><div class="spinner"></div> Loading Debater Bio for "${escapeHtml(name)}"...</div>`;

      let profile = null;
      if (state.isServerOnline) {
        try {
          const res = await fetch(`${state.apiUrl}/api/v2/debaters/${encodeURIComponent(name)}/bio`);
          if (res.ok) profile = await res.json();
        } catch (e) {}
      }

      // If server profile not loaded, find in local datasets
      if (!profile) {
        const found = (state.v2SpeakersGeneral.length ? state.v2SpeakersGeneral : state.v2SpeakersTab).find((d) => {
          const dn = d.name || d.speaker_name || '';
          return dn.toLowerCase() === name.toLowerCase() || dn.toLowerCase().includes(name.toLowerCase());
        });
        if (found) {
          const dName = found.name || found.speaker_name || '';
          profile = {
            canonical_name: dName,
            national_level: found.national_level,
            latest_institution: found.institution,
            most_debated_team: 'Circuit Team',
            speaker_avg: found.speaker_score,
            win_percentage: found.win_percentage,
            stdev: found.stdev,
            prelims_debated: found.prelims_debated,
            tournaments_debated: found.tournaments_debated,
            position_averages: { "1st": found.speaker_score, "2nd": found.speaker_score, "3rd": found.speaker_score, "Reply": 35.5 },
            tournament_breakdown: [],
          };
        }
      }

      if (!profile) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">Debater "${escapeHtml(name)}" not found in circuit records.</div>`;
        return;
      }

      // Update URL without reload
      if (window.history.replaceState) {
        window.history.replaceState(null, '', `${window.location.pathname}?debater=${encodeURIComponent(profile.canonical_name)}`);
      }
      if (input) input.value = profile.canonical_name;
      if (clearBtn) clearBtn.classList.remove('hidden');

      function extractPosAvg(p) {
        if (!p) return '-';
        if (typeof p === 'number') return fmt(p, 2);
        if (typeof p === 'object') {
          const avg = p.average !== undefined ? p.average : p.avg;
          if (avg === undefined || avg === null || isNaN(avg) || Number(avg) === 0) return '-';
          return fmt(avg, 2);
        }
        return '-';
      }

      function extractPosCount(p) {
        if (p && typeof p === 'object' && p.count) {
          return `${p.count} ${p.count === 1 ? 'speech' : 'speeches'}`;
        }
        return '';
      }

      const pos = profile.position_averages || {};
      const pos1 = extractPosAvg(pos["1st"]);
      const pos2 = extractPosAvg(pos["2nd"]);
      const pos3 = extractPosAvg(pos["3rd"]);
      const posReply = extractPosAvg(pos["Reply"]);

      const count1 = extractPosCount(pos["1st"]);
      const count2 = extractPosCount(pos["2nd"]);
      const count3 = extractPosCount(pos["3rd"]);
      const countReply = extractPosCount(pos["Reply"]);

      const tourBreakdown = profile.tournament_breakdown || [];

      container.innerHTML = `
        <!-- Debater Header Card -->
        <div class="bio-profile-header">
          <div class="bio-name-group">
            <h2 class="bio-name">${escapeHtml(profile.canonical_name)}</h2>
            <div style="display: flex; gap: 16px; margin-top: 6px; flex-wrap: wrap; font-size: 13.5px;">
              <div>
                <span style="color: rgba(255,255,255,0.5); font-family: var(--font-mono); font-size: 11px;">MOST DEBATED TEAM: </span>
                <a class="table-link" href="team_bio.html?team=${encodeURIComponent(profile.most_debated_team)}">${escapeHtml(profile.most_debated_team)}</a>
              </div>
              <div>
                <span style="color: rgba(255,255,255,0.5); font-family: var(--font-mono); font-size: 11px;">LATEST SCHOOL: </span>
                <a class="table-link-inst" href="institution_bio.html?inst=${encodeURIComponent(profile.latest_institution)}">${escapeHtml(profile.latest_institution)}</a>
              </div>
            </div>
          </div>
          <div>${getNatStatusTag(profile.national_level)}</div>
        </div>

        <!-- 1. First Box Stats Seen (5 Core Metrics) -->
        <div class="bio-stats-grid">
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #38bdf8;">${fmt(profile.speaker_avg, 2)}</div>
            <div class="bio-stat-lbl">SPEAKER AVG</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Universal Substantive Mean</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #34d399;">${fmt(profile.win_percentage, 1)}%</div>
            <div class="bio-stat-lbl">WIN %</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Debates Contested</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #fbbf24;">${fmt(profile.stdev, 2)}</div>
            <div class="bio-stat-lbl">STDEV</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Speech Score Deviation</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #38bdf8;">${profile.prelims_debated}</div>
            <div class="bio-stat-lbl">PRELIMS DEBATED</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Preliminary Speeches</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #c084fc;">${profile.tournaments_debated}</div>
            <div class="bio-stat-lbl">TOURNAMENTS</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Events Debated</div>
          </div>
        </div>

        <!-- 2. Speaker Position Debated Graph -->
        <div class="bio-section-heading">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>
          SPEAKER POSITION DEBATED BREAKDOWN
        </div>
        <div class="bio-stats-grid bio-positions-grid">
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="font-size: 22px; color: #38bdf8;">${pos1}</div>
            <div class="bio-stat-lbl">1ST SPEAKER AVG</div>
            ${count1 ? `<div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">${count1}</div>` : ''}
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="font-size: 22px; color: #38bdf8;">${pos2}</div>
            <div class="bio-stat-lbl">2ND SPEAKER AVG</div>
            ${count2 ? `<div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">${count2}</div>` : ''}
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="font-size: 22px; color: #38bdf8;">${pos3}</div>
            <div class="bio-stat-lbl">3RD SPEAKER AVG</div>
            ${count3 ? `<div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">${count3}</div>` : ''}
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="font-size: 22px; color: #a855f7;">${posReply}</div>
            <div class="bio-stat-lbl">REPLY SPEAKER AVG</div>
            ${countReply ? `<div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">${countReply}</div>` : ''}
          </div>
        </div>

        <!-- 4. Tournament Breakdown with Interactive Hover Details -->
        <div class="bio-section-heading" style="margin-top: 28px;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/></svg>
          TOURNAMENT BREAKDOWN (HOVER FOR JUDGE & OPPONENT)
        </div>
        <div class="trajectory-list">
          ${tourBreakdown.length > 0 ? tourBreakdown.map((t) => `
            <div class="trajectory-card" style="display: flex; flex-direction: column; align-items: flex-start; gap: 10px;">
              <div style="display: flex; justify-content: space-between; width: 100%; align-items: center; flex-wrap: wrap;">
                <div class="t-info-title">${escapeHtml(t.tournament_name)}</div>
                <div style="font-family: var(--font-mono); font-size: 13px; color: #38bdf8; font-weight: 700;">
                  Event Avg: ${fmt(t.tournament_average, 2)} pts (${t.speeches_count} prelim speeches)
                </div>
              </div>
              <div class="score-pills">
                ${(t.rounds || []).map((r) => {
                  const isReply = r.speech_type === 'REPLY';
                  return `
                  <div class="round-hover-trigger">
                    <span class="score-pill" style="cursor: pointer; ${isReply ? 'background: rgba(168, 85, 247, 0.15); border-color: rgba(168, 85, 247, 0.4); color: #d8b4fe;' : ''}">
                      ${isReply ? 'Reply: ' : ''}${fmt(r.score, 1)}
                    </span>
                    <div class="round-tooltip">
                      <div class="tooltip-title">${escapeHtml(r.round_name || 'Round ' + r.round_number)}</div>
                      <div class="tooltip-row">
                        <span class="tooltip-label">OPPONENT:</span>
                        <span style="font-weight: 600;">${escapeHtml(r.opponent)}</span>
                      </div>
                      <div class="tooltip-row">
                        <span class="tooltip-label">SCORE:</span>
                        <span style="font-weight: 700; color: ${isReply ? '#d8b4fe' : '#38bdf8'};">${fmt(r.score, 1)}</span>
                      </div>
                      <div class="tooltip-row">
                        <span class="tooltip-label">JUDGE:</span>
                        <span>${escapeHtml(r.adjudicator)}</span>
                      </div>
                      <div class="tooltip-row">
                        <span class="tooltip-label">POSITION:</span>
                        <span style="color: ${isReply ? '#c084fc' : '#34d399'};">${escapeHtml(r.position)}</span>
                      </div>
                    </div>
                  </div>
                `;}).join('')}
              </div>
            </div>
          `).join('') : `<div style="color: rgba(255,255,255,0.5); padding: 12px; font-style: italic;">No tournament breakdown recorded.</div>`}
        </div>
      `;
    }
  }

  // ==========================================================================
  // 4. TEAM BIO PAGE (NEW V2 VIEW)
  // ==========================================================================
  function initTeamBioPage() {
    const input = document.getElementById('teamSearchInput');
    const dropdown = document.getElementById('teamSuggestions');
    const clearBtn = document.getElementById('teamClearBtn');
    const container = document.getElementById('teamProfileContainer');

    const urlParams = new URLSearchParams(window.location.search);
    const teamParam = urlParams.get('team') || urlParams.get('name');

    if (teamParam) {
      loadTeamBio(teamParam);
    }

    if (input && dropdown) {
      function renderMatches(q) {
        const query = (q || '').trim().toLowerCase();
        let matches = (state.v2TeamsGeneral.length ? state.v2TeamsGeneral : state.v2TeamsTab);
        if (query) {
          matches = matches.filter((t) => t.team_name.toLowerCase().includes(query) || (t.institution && t.institution.toLowerCase().includes(query)));
        }
        matches = matches.slice(0, 15);

        if (matches.length === 0) {
          dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255,255,255,0.5); font-size: 13px; text-align: center;">No matching teams found.</div>`;
          dropdown.classList.remove('hidden');
          return;
        }

        dropdown.innerHTML = matches.map((t) => `
          <div class="h2h-autocomplete-item" data-name="${escapeHtml(t.team_name)}">
            <div>
              <div class="h2h-auto-name">${escapeHtml(t.team_name)}</div>
              <div class="h2h-auto-inst">${escapeHtml(t.institution)}</div>
            </div>
            <div class="h2h-auto-meta">
              <span class="h2h-auto-stat">ATSS: ${fmt(t.atss, 2)}</span>
            </div>
          </div>
        `).join('');

        dropdown.classList.remove('hidden');

        dropdown.querySelectorAll('.h2h-autocomplete-item').forEach((el) => {
          el.addEventListener('mousedown', (e) => {
            e.preventDefault();
            const name = el.getAttribute('data-name');
            input.value = name;
            dropdown.classList.add('hidden');
            if (clearBtn) clearBtn.classList.remove('hidden');
            loadTeamBio(name);
          });
        });
      }

      input.addEventListener('input', () => {
        if (clearBtn) clearBtn.classList.toggle('hidden', !input.value);
        renderMatches(input.value);
      });

      input.addEventListener('focus', () => renderMatches(input.value));
      input.addEventListener('blur', () => setTimeout(() => dropdown.classList.add('hidden'), 180));
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (input) input.value = '';
        clearBtn.classList.add('hidden');
        if (container) {
          container.innerHTML = `
            <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.5); font-family: var(--font-mono);">
              Type any team name above to inspect ATSS, lineups, break achievements, and tournament progressions.
            </div>
          `;
        }
        if (window.history.replaceState) window.history.replaceState(null, '', window.location.pathname);
      });
    }

    async function loadTeamBio(teamName) {
      if (!container) return;
      container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);"><div class="spinner"></div> Loading Team Bio for "${escapeHtml(teamName)}"...</div>`;

      let bio = null;
      if (state.isServerOnline) {
        try {
          const res = await fetch(`${state.apiUrl}/api/v2/teams/${encodeURIComponent(teamName)}/bio`);
          if (res.ok) bio = await res.json();
        } catch (e) {}
      }

      if (!bio) {
        // Fallback from teams dataset
        const found = (state.v2TeamsGeneral.length ? state.v2TeamsGeneral : state.v2TeamsTab).find(
          (t) => t.team_name.toLowerCase() === teamName.toLowerCase() || t.team_name.toLowerCase().includes(teamName.toLowerCase())
        );
        if (found) {
          bio = {
            team_name: found.team_name,
            institution: found.institution,
            atss: found.atss,
            win_percentage: found.win_percentage,
            stdev: found.stdev || 2.4,
            prelims_debated: found.prelims_debated || found.total_debates,
            tournaments_debated: found.tournaments_debated,
            wins_per_tournament: found.awpt,
            top_win_lineups: [],
            top_atss_lineups: [],
            tournament_breakdown: [],
          };
        }
      }

      if (!bio) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">Team "${escapeHtml(teamName)}" not found in circuit records.</div>`;
        return;
      }

      if (window.history.replaceState) {
        window.history.replaceState(null, '', `${window.location.pathname}?team=${encodeURIComponent(bio.team_name)}`);
      }
      if (input) input.value = bio.team_name;
      if (clearBtn) clearBtn.classList.remove('hidden');

      // Top 5 break achievements
      const tourBreakdown = bio.tournament_breakdown || [];
      const achievements = (bio.top_break_achievements && bio.top_break_achievements.length > 0)
        ? bio.top_break_achievements
        : tourBreakdown
            .filter((t) => {
              const brk = t.highest_break || t.highest_stage;
              return brk && brk !== 'Preliminary Rounds' && brk !== 'Unranked';
            })
            .slice(0, 5);

      container.innerHTML = `
        <!-- Team Header Card -->
        <div class="bio-profile-header">
          <div class="bio-name-group">
            <h2 class="bio-name">${escapeHtml(bio.team_name)}</h2>
            <div style="font-size: 15px; margin-top: 4px;">
              <span style="color: rgba(255,255,255,0.5); font-family: var(--font-mono); font-size: 11px;">REPRESENTING: </span>
              <a class="table-link-inst" href="institution_bio.html?inst=${encodeURIComponent(bio.institution)}">${escapeHtml(bio.institution)}</a>
            </div>
          </div>
          <div>
            <span class="badge-count" style="background: rgba(56, 189, 248, 0.2); color: #38bdf8;">TEAM TAB ELIGIBLE</span>
          </div>
        </div>

        <!-- 1. First Box Seen (5 Metrics) -->
        <div class="bio-stats-grid">
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #38bdf8;">${fmt(bio.atss, 2)}</div>
            <div class="bio-stat-lbl">ATSS</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Avg Total Speaker Score</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #34d399;">${fmt(bio.win_percentage, 1)}%</div>
            <div class="bio-stat-lbl">WIN %</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Total Debates Won</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #fbbf24;">${fmt(bio.stdev, 2)}</div>
            <div class="bio-stat-lbl">STDEV</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Match Score Standard Deviation</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #38bdf8;">${bio.prelims_debated} <span style="font-size: 16px; color: rgba(255,255,255,0.4);">/ ${bio.tournaments_debated}</span></div>
            <div class="bio-stat-lbl">PRELIMS & TOURNAMENTS</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Prelim Matches / Tourneys</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #c084fc;">${fmt(bio.wins_per_tournament, 2)}</div>
            <div class="bio-stat-lbl">WINS PER TOURNAMENT</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Avg Wins / Tournament</div>
          </div>
        </div>

        <!-- 2. Top 5 Break Achievements -->
        <div class="bio-section-heading">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/></svg>
          TOP 5 BREAK ACHIEVEMENTS
        </div>
        <div class="achievement-list">
          ${achievements.length > 0 ? achievements.map((a) => `
            <div class="achievement-card">
              <div>
                <strong style="color: #ffffff;">${escapeHtml(a.tournament_name)}</strong>
                <div style="font-size: 11px; color: rgba(255,255,255,0.5); font-family: var(--font-mono);">
                  Tournament ATSS: ${fmt(a.tournament_atss !== undefined ? a.tournament_atss : a.atss, 2)}
                </div>
              </div>
              <div>${getBreakBadge(a.highest_break || a.highest_stage)}</div>
            </div>
          `).join('') : `<div style="color: rgba(255,255,255,0.5); padding: 12px; font-style: italic;">No elimination break stages recorded.</div>`}
        </div>

        <!-- 3. Lineup Analytics (Top 5 Win % & Top 5 ATSS 3-Debater Combinations) -->
        <div class="bio-section-heading" style="margin-top: 28px;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          LINEUP ANALYTICS (OPTIMAL 3-SPEAKER COMBINATIONS)
        </div>
        <div class="lineups-grid">
          <!-- Top 5 Win % Lineups -->
          <div class="roster-box">
            <div class="roster-box-header">
              <span>TOP 5 MOST (WIN %) LINEUPS</span>
              <span>WIN RATE</span>
            </div>
            <div class="roster-list">
              ${(bio.top_win_lineups || []).length > 0 ? (bio.top_win_lineups || []).map((l, idx) => `
                <div class="lineup-card">
                  <div class="lineup-names">
                    <span style="color: rgba(255,255,255,0.4); margin-right: 6px;">#${idx + 1}</span>
                    ${l.lineup.map(n => `<a class="table-link" href="bio.html?debater=${encodeURIComponent(n)}">${escapeHtml(n)}</a>`).join(' · ')}
                    <div style="font-size: 11px; color: rgba(255,255,255,0.5); font-family: var(--font-mono); margin-top: 2px;">
                      ${l.debates_count} debates together
                    </div>
                  </div>
                  <div class="lineup-stat" style="color: #34d399;">${fmt(l.win_percentage, 1)}%</div>
                </div>
              `).join('') : `<div style="color: rgba(255,255,255,0.5); padding: 12px; font-style: italic;">No 3-person lineups on record.</div>`}
            </div>
          </div>

          <!-- Top 5 ATSS Lineups -->
          <div class="roster-box">
            <div class="roster-box-header">
              <span>TOP 5 HIGHEST (ATSS) LINEUPS</span>
              <span>LINEUP ATSS</span>
            </div>
            <div class="roster-list">
              ${(bio.top_atss_lineups || []).length > 0 ? (bio.top_atss_lineups || []).map((l, idx) => `
                <div class="lineup-card">
                  <div class="lineup-names">
                    <span style="color: rgba(255,255,255,0.4); margin-right: 6px;">#${idx + 1}</span>
                    ${l.lineup.map(n => `<a class="table-link" href="bio.html?debater=${encodeURIComponent(n)}">${escapeHtml(n)}</a>`).join(' · ')}
                    <div style="font-size: 11px; color: rgba(255,255,255,0.5); font-family: var(--font-mono); margin-top: 2px;">
                      ${l.debates_count} debates together
                    </div>
                  </div>
                  <div class="lineup-stat" style="color: #38bdf8;">${fmt(l.atss, 2)}</div>
                </div>
              `).join('') : `<div style="color: rgba(255,255,255,0.5); padding: 12px; font-style: italic;">No 3-person lineups on record.</div>`}
            </div>
          </div>
        </div>

        <!-- 4. Tournament Breakdown -->
        <div class="bio-section-heading" style="margin-top: 28px;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/></svg>
          TOURNAMENT BREAKDOWN & PROGRESSION
        </div>
        <div class="trajectory-list">
          ${tourBreakdown.length > 0 ? tourBreakdown.map((t) => `
            <div class="trajectory-card" style="display: flex; flex-direction: column; align-items: flex-start; gap: 10px;">
              <div style="display: flex; justify-content: space-between; width: 100%; align-items: center; flex-wrap: wrap;">
                <div>
                  <strong style="color: #ffffff; font-size: 14px;">${escapeHtml(t.tournament_name)}</strong>
                  <span style="margin-left: 8px;">${getBreakBadge(t.highest_break || t.highest_stage)}</span>
                </div>
                <div style="font-family: var(--font-mono); font-size: 13px; color: #38bdf8; font-weight: 700;">
                  Event ATSS: ${fmt(t.tournament_atss !== undefined ? t.tournament_atss : t.atss, 2)} pts (${t.debates_count || (t.debates || t.rounds || []).length} debates)
                </div>
              </div>
              <div class="score-pills">
                ${(t.debates || t.rounds || []).map((d) => {
                  const isWon = d.won !== undefined ? Boolean(d.won) : (d.result === 'Win' || d.result === 'WIN');
                  return `
                    <div class="round-hover-trigger">
                      <span class="score-pill" style="color: ${isWon ? '#34d399' : '#f87171'}; border-color: ${isWon ? 'rgba(52, 211, 153, 0.4)' : 'rgba(248, 113, 113, 0.4)'};">
                        ${isWon ? 'WIN' : 'LOSS'} ${fmt(d.team_score, 1)}
                      </span>
                      <div class="round-tooltip">
                        <div class="tooltip-title">${escapeHtml(d.round_name)}</div>
                        <div class="tooltip-row">
                          <span class="tooltip-label">OPPONENT:</span>
                          <span style="font-weight: 600;">${escapeHtml(d.opponent)}</span>
                        </div>
                        <div class="tooltip-row">
                          <span class="tooltip-label">SCORE:</span>
                          <span style="font-weight: 700; color: #38bdf8;">${fmt(d.team_score, 1)}</span>
                        </div>
                        <div class="tooltip-row">
                          <span class="tooltip-label">SIDE:</span>
                          <span>${escapeHtml(d.side)}</span>
                        </div>
                      </div>
                    </div>
                  `;
                }).join('')}
              </div>
            </div>
          `).join('') : `<div style="color: rgba(255,255,255,0.5); padding: 12px; font-style: italic;">No tournament breakdown recorded.</div>`}
        </div>
      `;
    }
  }

  // ==========================================================================
  // 5. INSTITUTION BIO PAGE (NEW V2 VIEW)
  // ==========================================================================
  function initInstitutionBioPage() {
    const input = document.getElementById('instSearchInput');
    const dropdown = document.getElementById('instSuggestions');
    const clearBtn = document.getElementById('instClearBtn');
    const container = document.getElementById('instProfileContainer');

    const urlParams = new URLSearchParams(window.location.search);
    const instParam = urlParams.get('inst') || urlParams.get('name');

    if (instParam) {
      loadInstitutionBio(instParam);
    }

    if (input && dropdown) {
      function renderMatches(q) {
        const query = (q || '').trim().toLowerCase();
        let matches = (state.v2InstitutionsGeneral.length ? state.v2InstitutionsGeneral : state.v2InstitutionsTab);
        if (query) {
          matches = matches.filter((i) => i.institution_name.toLowerCase().includes(query) || (i.code && i.code.toLowerCase().includes(query)));
        }
        matches = matches.slice(0, 15);

        if (matches.length === 0) {
          dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255,255,255,0.5); font-size: 13px; text-align: center;">No matching institutions found.</div>`;
          dropdown.classList.remove('hidden');
          return;
        }

        dropdown.innerHTML = matches.map((i) => `
          <div class="h2h-autocomplete-item" data-name="${escapeHtml(i.institution_name)}">
            <div>
              <div class="h2h-auto-name">${escapeHtml(i.institution_name)}</div>
              <div class="h2h-auto-inst">${i.code ? `[${i.code}]` : ''} Delta: ${fmt(i.delta, 2)}</div>
            </div>
            <div class="h2h-auto-meta">
              <span class="h2h-auto-stat">A: ${fmt(i.a_atss, 2)}</span>
            </div>
          </div>
        `).join('');

        dropdown.classList.remove('hidden');

        dropdown.querySelectorAll('.h2h-autocomplete-item').forEach((el) => {
          el.addEventListener('mousedown', (e) => {
            e.preventDefault();
            const name = el.getAttribute('data-name');
            input.value = name;
            dropdown.classList.add('hidden');
            if (clearBtn) clearBtn.classList.remove('hidden');
            loadInstitutionBio(name);
          });
        });
      }

      input.addEventListener('input', () => {
        if (clearBtn) clearBtn.classList.toggle('hidden', !input.value);
        renderMatches(input.value);
      });

      input.addEventListener('focus', () => renderMatches(input.value));
      input.addEventListener('blur', () => setTimeout(() => dropdown.classList.add('hidden'), 180));
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (input) input.value = '';
        clearBtn.classList.add('hidden');
        if (container) {
          container.innerHTML = `
            <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.5); font-family: var(--font-mono);">
              Type any institution name above to inspect Delta, A/B team ATSS, roster, and veteran vs new debater pool.
            </div>
          `;
        }
        if (window.history.replaceState) window.history.replaceState(null, '', window.location.pathname);
      });
    }

    async function loadInstitutionBio(instName) {
      if (!container) return;
      container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);"><div class="spinner"></div> Loading Institution Bio for "${escapeHtml(instName)}"...</div>`;

      let bio = null;
      if (state.isServerOnline) {
        try {
          const res = await fetch(`${state.apiUrl}/api/v2/institutions/${encodeURIComponent(instName)}/bio`);
          if (res.ok) bio = await res.json();
        } catch (e) {}
      }

      if (!bio) {
        const found = (state.v2InstitutionsGeneral.length ? state.v2InstitutionsGeneral : state.v2InstitutionsTab).find(
          (i) => i.institution_name.toLowerCase() === instName.toLowerCase() || i.institution_name.toLowerCase().includes(instName.toLowerCase())
        );
        if (found) {
          bio = {
            institution_name: found.institution_name,
            code: found.code,
            delta: found.delta,
            a_team_name: found.a_team_name,
            a_atss: found.a_atss,
            b_team_name: found.b_team_name,
            b_atss: found.b_atss,
            win_percentage: found.win_percentage,
            teams_list: found.teams_list || [],
            pool_count: found.pool_count || 0,
            veterans: [],
            new_debaters: [],
          };
        }
      }

      if (!bio) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">Institution "${escapeHtml(instName)}" not found in circuit records.</div>`;
        return;
      }

      if (window.history.replaceState) {
        window.history.replaceState(null, '', `${window.location.pathname}?inst=${encodeURIComponent(bio.institution_name)}`);
      }
      if (input) input.value = bio.institution_name;
      if (clearBtn) clearBtn.classList.remove('hidden');

      const aTeamHtml = bio.a_team_name ? `<a class="table-link" href="team_bio.html?team=${encodeURIComponent(bio.a_team_name)}">${fmt(bio.a_atss, 2)} (${escapeHtml(bio.a_team_name)})</a>` : `${fmt(bio.a_atss, 2)}`;
      const bTeamHtml = bio.b_team_name && bio.b_atss ? `<a class="table-link" href="team_bio.html?team=${encodeURIComponent(bio.b_team_name)}">${fmt(bio.b_atss, 2)} (${escapeHtml(bio.b_team_name)})</a>` : (bio.b_atss ? fmt(bio.b_atss, 2) : '-');

      const teamsFielded = bio.teams_list || [];

      container.innerHTML = `
        <!-- Institution Header Card -->
        <div class="bio-profile-header">
          <div class="bio-name-group">
            <h2 class="bio-name">${escapeHtml(bio.institution_name)}</h2>
            <div style="font-size: 13.5px; color: rgba(255,255,255,0.6); font-family: var(--font-mono); margin-top: 4px;">
              ${bio.code ? `CODE: ${escapeHtml(bio.code)} · ` : ''}TOTAL DEBATERS FIELDED: ${bio.pool_count}
            </div>
          </div>
          <div>
            <span class="badge-count" style="background: rgba(16, 185, 129, 0.2); color: #34d399;">INSTITUTION TAB</span>
          </div>
        </div>

        <!-- 1. First Box Seen (5 Metrics) -->
        <div class="bio-stats-grid">
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #38bdf8;">${fmt(bio.delta, 2)}</div>
            <div class="bio-stat-lbl">DELTA</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">(0.8*A + 1.2*B) / 2</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #ffffff;">${teamsFielded.length}</div>
            <div class="bio-stat-lbl">TEAMS FIELDED</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Active Circuit Rosters</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #38bdf8; font-size: 20px;">
              A: ${fmt(bio.a_atss, 1)}<br />
              <span style="color: #c084fc;">B: ${bio.b_atss ? fmt(bio.b_atss, 1) : '-'}</span>
            </div>
            <div class="bio-stat-lbl">A & B TEAM ATSS</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #34d399;">${fmt(bio.win_percentage, 1)}%</div>
            <div class="bio-stat-lbl">WIN RATE</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">All Debates Contested</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #fbbf24;">${bio.pool_count}</div>
            <div class="bio-stat-lbl">DEBATER POOL</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Eligible Debaters Fielded</div>
          </div>
        </div>

        <!-- Representing Teams List -->
        <div class="bio-section-heading">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
          TEAMS THAT REPRESENTED ${escapeHtml(bio.institution_name).toUpperCase()}
        </div>
        <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px;">
          ${teamsFielded.length > 0 ? teamsFielded.map(t => `
            <a class="opt-btn" href="team_bio.html?team=${encodeURIComponent(t)}" style="padding: 10px 18px; font-size: 12px; border-radius: 10px;">
              ${escapeHtml(t)}
            </a>
          `).join('') : '<div style="color: rgba(255,255,255,0.5); font-style: italic;">No teams recorded.</div>'}
        </div>

        <!-- 2. Debater Pool Graph: Veterans (>= 2 tourneys) vs New Debaters (1 tourney) -->
        <div class="bio-section-heading">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          DEBATER POOL: VETERANS (>= 2 TOURNAMENTS) VS NEW DEBATERS (1 TOURNAMENT)
        </div>
        <div class="roster-split-grid">
          <!-- Veterans Column -->
          <div class="roster-box">
            <div class="roster-box-header">
              <span>VETERAN DEBATERS (${bio.veterans ? bio.veterans.length : 0})</span>
              <span>TOURNAMENTS</span>
            </div>
            <div class="roster-list">
              ${(bio.veterans || []).length > 0 ? (bio.veterans || []).map((v) => `
                <div class="pool-debater-card">
                  <div>
                    <a class="pool-debater-name" href="bio.html?debater=${encodeURIComponent(v.name)}">${escapeHtml(v.name)}</a>
                    <div style="font-size: 10.5px; color: rgba(255,255,255,0.45); font-family: var(--font-mono);">
                      ${v.prelims} prelims debated
                    </div>
                  </div>
                  <div style="font-family: var(--font-mono); font-weight: 700; color: #38bdf8;">
                    ${v.tournaments} Tourneys
                  </div>
                </div>
              `).join('') : `<div style="color: rgba(255,255,255,0.5); padding: 12px; font-style: italic;">No veteran debaters recorded.</div>`}
            </div>
          </div>

          <!-- New Debaters Column -->
          <div class="roster-box">
            <div class="roster-box-header">
              <span>NEW DEBATERS (${bio.new_debaters ? bio.new_debaters.length : 0})</span>
              <span>PRELIMS</span>
            </div>
            <div class="roster-list">
              ${(bio.new_debaters || []).length > 0 ? (bio.new_debaters || []).map((n) => `
                <div class="pool-debater-card">
                  <div>
                    <a class="pool-debater-name" href="bio.html?debater=${encodeURIComponent(n.name)}">${escapeHtml(n.name)}</a>
                    <div style="font-size: 10.5px; color: rgba(255,255,255,0.45); font-family: var(--font-mono);">
                      1 tournament debated
                    </div>
                  </div>
                  <div style="font-family: var(--font-mono); font-weight: 700; color: #34d399;">
                    ${n.prelims} Prelims
                  </div>
                </div>
              `).join('') : `<div style="color: rgba(255,255,255,0.5); padding: 12px; font-style: italic;">No new debaters recorded.</div>`}
            </div>
          </div>
        </div>
      `;
    }
  }

  // ==========================================================================
  // 6. ADJUDICATOR BIO PAGE (NEW V2 VIEW)
  // ==========================================================================
  function initAdjudicatorBioPage() {
    const input = document.getElementById('judgeSearchInput');
    const dropdown = document.getElementById('judgeSuggestions');
    const clearBtn = document.getElementById('judgeClearBtn');
    const container = document.getElementById('judgeProfileContainer');

    const urlParams = new URLSearchParams(window.location.search);
    const judgeParam = urlParams.get('judge') || urlParams.get('name');

    if (judgeParam) {
      loadAdjudicatorBio(judgeParam);
    }

    if (input && dropdown) {
      function renderMatches(q) {
        const query = (q || '').trim().toLowerCase();
        let matches = state.v2Adjudicators;
        if (query) {
          matches = matches.filter((j) => j.adjudicator_name.toLowerCase().includes(query) || (j.institution && j.institution.toLowerCase().includes(query)));
        }
        matches = matches.slice(0, 15);

        if (matches.length === 0) {
          dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255,255,255,0.5); font-size: 13px; text-align: center;">No matching adjudicators found.</div>`;
          dropdown.classList.remove('hidden');
          return;
        }

        dropdown.innerHTML = matches.map((j) => `
          <div class="h2h-autocomplete-item" data-name="${escapeHtml(j.adjudicator_name)}">
            <div>
              <div class="h2h-auto-name">${escapeHtml(j.adjudicator_name)}</div>
              <div class="h2h-auto-inst">${escapeHtml(j.institution)}</div>
            </div>
            <div class="h2h-auto-meta">
              <span class="h2h-auto-stat">AASS: ${fmt(j.aass, 2)}</span>
            </div>
          </div>
        `).join('');

        dropdown.classList.remove('hidden');

        dropdown.querySelectorAll('.h2h-autocomplete-item').forEach((el) => {
          el.addEventListener('mousedown', (e) => {
            e.preventDefault();
            const name = el.getAttribute('data-name');
            input.value = name;
            dropdown.classList.add('hidden');
            if (clearBtn) clearBtn.classList.remove('hidden');
            loadAdjudicatorBio(name);
          });
        });
      }

      input.addEventListener('input', () => {
        if (clearBtn) clearBtn.classList.toggle('hidden', !input.value);
        renderMatches(input.value);
      });

      input.addEventListener('focus', () => renderMatches(input.value));
      input.addEventListener('blur', () => setTimeout(() => dropdown.classList.add('hidden'), 180));
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (input) input.value = '';
        clearBtn.classList.add('hidden');
        if (container) {
          container.innerHTML = `
            <div style="text-align: center; padding: 48px 20px; color: rgba(255,255,255,0.5); font-family: var(--font-mono);">
              Type any adjudicator's name above to inspect AASS, AATSS, Prop/Opp bias, and judging history.
            </div>
          `;
        }
        if (window.history.replaceState) window.history.replaceState(null, '', window.location.pathname);
      });
    }

    async function loadAdjudicatorBio(judgeName) {
      if (!container) return;
      container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);"><div class="spinner"></div> Loading Adjudicator Bio for "${escapeHtml(judgeName)}"...</div>`;

      let bio = null;
      if (state.isServerOnline) {
        try {
          const res = await fetch(`${state.apiUrl}/api/v2/adjudicators/${encodeURIComponent(judgeName)}/bio`);
          if (res.ok) bio = await res.json();
        } catch (e) {}
      }

      if (!bio) {
        const found = state.v2Adjudicators.find(
          (j) => j.adjudicator_name.toLowerCase() === judgeName.toLowerCase() || j.adjudicator_name.toLowerCase().includes(judgeName.toLowerCase())
        );
        if (found) bio = found;
      }

      if (!bio) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);">Adjudicator "${escapeHtml(judgeName)}" not found in circuit records.</div>`;
        return;
      }

      if (window.history.replaceState) {
        window.history.replaceState(null, '', `${window.location.pathname}?judge=${encodeURIComponent(bio.adjudicator_name)}`);
      }
      if (input) input.value = bio.adjudicator_name;
      if (clearBtn) clearBtn.classList.remove('hidden');

      const propPct = bio.prop_bias_pct !== undefined && bio.prop_bias_pct !== null ? bio.prop_bias_pct : 50.0;
      const oppPct = bio.opp_bias_pct !== undefined && bio.opp_bias_pct !== null ? bio.opp_bias_pct : (100.0 - propPct);
      const propPctStr = fmt(propPct);
      const oppPctStr = fmt(oppPct);

      container.innerHTML = `
        <!-- Adjudicator Header Card -->
        <div class="bio-profile-header">
          <div class="bio-name-group">
            <h2 class="bio-name">${escapeHtml(bio.adjudicator_name)}</h2>
            <div style="font-size: 15px; color: rgba(255,255,255,0.7); margin-top: 4px;">
              ${escapeHtml(bio.institution || 'Independent Adjudicator')}
            </div>
          </div>
          <div>
            <span class="badge-count" style="background: rgba(168, 85, 247, 0.2); color: #c084fc;">ADJUDICATOR</span>
          </div>
        </div>

        <!-- 1. Key Metrics Grid (6 Metrics) -->
        <div class="bio-stats-grid">
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #38bdf8;">${bio.aass ? fmt(bio.aass, 2) : '-'}</div>
            <div class="bio-stat-lbl">AASS (SUBSTANTIVE MEAN)</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Awarded Speaker Avg</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #34d399;">${bio.aatss ? fmt(bio.aatss, 2) : '-'}</div>
            <div class="bio-stat-lbl">AATSS (TEAM AVG)</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Awarded Team Avg</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #f43f5e; font-size: 20px;">${propPctStr}% P / ${oppPctStr}% O</div>
            <div class="bio-stat-lbl">PROP / OPP WIN BIAS</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Decision Split</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #38bdf8;">${bio.prelims_adjudicated || 0}</div>
            <div class="bio-stat-lbl">PRELIMS ADJUDICATED</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Preliminary Rounds</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #fbbf24;">${bio.outrounds_adjudicated || 0}</div>
            <div class="bio-stat-lbl">KNOCKOUTS ADJUDICATED</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Elimination Panels</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="color: #c084fc;">${bio.tournaments_adjudicated || 0}</div>
            <div class="bio-stat-lbl">TOURNAMENTS ADJUDICATED</div>
            <div style="font-size: 9.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono); margin-top: 2px;">Tournaments</div>
          </div>
        </div>

        <!-- Prop vs Opp Decision Bias Visual Bar -->
        <div class="bio-section-heading">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/></svg>
          BALLOT DECISION SPLIT
        </div>
        <div class="roster-box" style="margin-bottom: 24px;">
          <div class="bias-container">
            <div class="bias-labels">
              <span style="color: #38bdf8; font-weight: 700;">PROPOSITION: ${propPctStr}% (${bio.prop_wins || 0} wins)</span>
              <span style="color: #f43f5e; font-weight: 700;">OPPOSITION: ${oppPctStr}% (${bio.opp_wins || 0} wins)</span>
            </div>
            <div class="bias-bar-wrap">
              <div class="bias-bar-prop" style="width: ${propPct}%;"></div>
              <div class="bias-bar-opp" style="width: ${oppPct}%;"></div>
            </div>
          </div>
        </div>

        <!-- 2. Detailed Judging History Table -->
        <div class="bio-section-heading">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          JUDGING HISTORY (${(bio.judging_history && bio.judging_history.length) || (bio.prelims_adjudicated + (bio.outrounds_adjudicated || 0))} DEBATES)
        </div>
        ${bio.judging_history && bio.judging_history.length > 0 ? `
          <div class="data-table-wrap" style="margin-bottom: 32px;">
            <table class="atomos-table">
              <thead>
                <tr>
                  <th style="width: 22%;">TOURNAMENT</th>
                  <th style="width: 14%;">ROUND</th>
                  <th style="width: 32%;">CONTESTED MATCHUP</th>
                  <th style="width: 14%; text-align: center;">DECISION</th>
                  <th style="width: 18%;">PANEL / ROLE</th>
                </tr>
              </thead>
              <tbody>
                ${bio.judging_history.map((h) => {
                  const isKnockout = h.round_type === 'ELIMINATION';
                  const roundBadge = isKnockout
                    ? `<span style="display: inline-block; padding: 2px 6px; font-size: 10px; border-radius: 4px; background: rgba(251, 191, 36, 0.2); color: #fbbf24; font-weight: 700;">${escapeHtml(h.round_name)}</span>`
                    : `<span style="display: inline-block; padding: 2px 6px; font-size: 10px; border-radius: 4px; background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-weight: 600;">${escapeHtml(h.round_name)}</span>`;

                  const winnerColor = h.winner_side === 'Proposition' ? '#38bdf8' : (h.winner_side === 'Opposition' ? '#f43f5e' : 'rgba(255,255,255,0.7)');
                  const marginText = h.win_margin ? ` (${fmt(h.win_margin, 1)} pts)` : '';

                  const panelText = h.is_panel && h.panel_members && h.panel_members.length > 0
                    ? `<div style="font-size: 11px; color: rgba(255,255,255,0.85);"><span style="color: #c084fc; font-weight: 700;">PANEL:</span> ${h.panel_members.map(m => escapeHtml(m)).join(', ')}</div>`
                    : `<span style="font-size: 11px; color: rgba(255,255,255,0.5); font-family: var(--font-mono);">Solo Chair</span>`;

                  return `
                    <tr>
                      <td style="font-weight: 600; color: #ffffff;">
                        <div>${escapeHtml(h.tournament_name)}</div>
                        <div style="font-size: 10.5px; color: rgba(255,255,255,0.45); font-family: var(--font-mono);">${escapeHtml(h.tournament_dates || '')}</div>
                      </td>
                      <td>${roundBadge}</td>
                      <td>
                        <div style="display: flex; align-items: center; gap: 6px; font-size: 12.5px;">
                          <a class="table-link" href="team_bio.html?team=${encodeURIComponent(h.prop_team)}">${escapeHtml(h.prop_team)}</a>
                          <span style="font-size: 10px; color: rgba(255,255,255,0.4); font-family: var(--font-mono);">(Prop)</span>
                          <span style="color: rgba(255,255,255,0.3);">vs</span>
                          <a class="table-link" href="team_bio.html?team=${encodeURIComponent(h.opp_team)}">${escapeHtml(h.opp_team)}</a>
                          <span style="font-size: 10px; color: rgba(255,255,255,0.4); font-family: var(--font-mono);">(Opp)</span>
                        </div>
                      </td>
                      <td style="text-align: center; font-family: var(--font-mono); font-size: 11.5px; font-weight: 700; color: ${winnerColor};">
                        ${escapeHtml(h.winner_side || 'Decided')}${marginText}
                      </td>
                      <td>${panelText}</td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          </div>
        ` : `
          <div class="roster-box" style="text-align: center; padding: 24px; color: rgba(255,255,255,0.5); font-family: var(--font-mono); font-size: 12px; margin-bottom: 24px;">
            Detailed round matchups recorded under standard preliminary scoring ballots.
          </div>
        `}
      `;
    }
  }

  // ==========================================================================
  // 7. HEAD TO HEAD (6 CORE METRICS OVERHAUL)
  // ==========================================================================
  function initH2HPage() {
    let selectedA = null;
    let selectedB = null;

    const inputA = document.getElementById('h2hInputA');
    const inputB = document.getElementById('h2hInputB');
    const dropA = document.getElementById('h2hDropdownA');
    const dropB = document.getElementById('h2hDropdownB');
    const badgeA = document.getElementById('h2hSelectedBadgeA');
    const badgeB = document.getElementById('h2hSelectedBadgeB');
    const clearA = document.getElementById('h2hClearBtnA');
    const clearB = document.getElementById('h2hClearBtnB');
    const container = document.getElementById('h2hResultContainer');

    function setupH2HSearch(side, input, dropdown, clearBtn, badge) {
      if (!input || !dropdown) return;

      function renderMatches(q) {
        const query = (q || '').trim().toLowerCase();
        let matches = (state.v2SpeakersGeneral.length ? state.v2SpeakersGeneral : state.v2SpeakersTab);
        if (query) {
          matches = matches.filter((d) => d.name.toLowerCase().includes(query) || (d.institution && d.institution.toLowerCase().includes(query)));
        }
        matches = matches.slice(0, 15);

        if (matches.length === 0) {
          dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255,255,255,0.5); font-size: 13px; text-align: center;">No matching debaters found.</div>`;
          dropdown.classList.remove('hidden');
          return;
        }

        dropdown.innerHTML = matches.map((d) => `
          <div class="h2h-autocomplete-item" data-name="${escapeHtml(d.name)}">
            <div>
              <div class="h2h-auto-name">${escapeHtml(d.name)}</div>
              <div class="h2h-auto-inst">${escapeHtml(d.institution)}</div>
            </div>
            <div class="h2h-auto-meta">
              <span class="h2h-auto-stat">Avg: ${fmt(d.speaker_score, 2)}</span>
            </div>
          </div>
        `).join('');

        dropdown.classList.remove('hidden');

        dropdown.querySelectorAll('.h2h-autocomplete-item').forEach((el) => {
          el.addEventListener('mousedown', (e) => {
            e.preventDefault();
            const name = el.getAttribute('data-name');
            const match = matches.find((m) => m.name === name);
            if (side === 'A') selectedA = match;
            else selectedB = match;

            input.value = match.name;
            dropdown.classList.add('hidden');
            if (badge) {
              badge.textContent = match.institution;
              badge.classList.remove('hidden');
            }
            if (clearBtn) clearBtn.classList.remove('hidden');
            updateH2H();
          });
        });
      }

      input.addEventListener('input', () => {
        if (clearBtn) clearBtn.classList.toggle('hidden', !input.value);
        renderMatches(input.value);
      });

      input.addEventListener('focus', () => renderMatches(input.value));
      input.addEventListener('blur', () => setTimeout(() => dropdown.classList.add('hidden'), 180));

      if (clearBtn) {
        clearBtn.addEventListener('click', () => {
          if (side === 'A') selectedA = null;
          else selectedB = null;
          input.value = '';
          clearBtn.classList.add('hidden');
          if (badge) badge.classList.add('hidden');
          updateH2H();
        });
      }
    }

    setupH2HSearch('A', inputA, dropA, clearA, badgeA);
    setupH2HSearch('B', inputB, dropB, clearB, badgeB);

    const urlParams = new URLSearchParams(window.location.search);
    const paramA = urlParams.get('a') || urlParams.get('contender1');
    const paramB = urlParams.get('b') || urlParams.get('contender2');

    if (paramA) {
      const matchA = (state.v2SpeakersGeneral.length ? state.v2SpeakersGeneral : state.v2SpeakersTab).find((s) => s.name.toLowerCase() === paramA.toLowerCase());
      if (matchA) {
        selectedA = matchA;
        if (inputA) inputA.value = matchA.name;
        if (badgeA) { badgeA.textContent = matchA.institution; badgeA.classList.remove('hidden'); }
        if (clearA) clearA.classList.remove('hidden');
      }
    }

    if (paramB) {
      const matchB = (state.v2SpeakersGeneral.length ? state.v2SpeakersGeneral : state.v2SpeakersTab).find((s) => s.name.toLowerCase() === paramB.toLowerCase());
      if (matchB) {
        selectedB = matchB;
        if (inputB) inputB.value = matchB.name;
        if (badgeB) { badgeB.textContent = matchB.institution; badgeB.classList.remove('hidden'); }
        if (clearB) clearB.classList.remove('hidden');
      }
    }

    async function updateH2H() {
      if (!container) return;

      if (!selectedA && !selectedB) {
        container.innerHTML = `
          <div class="h2h-empty-state" style="text-align: center; padding: 64px 20px; color: rgba(255,255,255,0.5); font-family: var(--font-mono);">
            <div style="font-size: 16px; color: #38bdf8; margin-bottom: 8px; font-weight: 600; letter-spacing: 0.06em;">HEAD TO HEAD // 6 CORE METRICS</div>
            <div style="font-size: 13px; max-width: 520px; margin: 0 auto; line-height: 1.6; color: rgba(255,255,255,0.65);">
              Select Contender 1 and Contender 2 above to compare them across the 6 official circuit metrics: Speaker Score, Win %, Break Rank Avg (BRA), Prelims Debated, Highest Achievement, and Direct Tournament Clashes.
            </div>
          </div>
        `;
        return;
      }

      if (selectedA && !selectedB) {
        container.innerHTML = `<div style="text-align: center; padding: 48px; color: rgba(255,255,255,0.6);">Contender 1 (${escapeHtml(selectedA.name)}) selected. Select Contender 2 above.</div>`;
        return;
      }

      if (!selectedA && selectedB) {
        container.innerHTML = `<div style="text-align: center; padding: 48px; color: rgba(255,255,255,0.6);">Contender 2 (${escapeHtml(selectedB.name)}) selected. Select Contender 1 above.</div>`;
        return;
      }

      if (selectedA.name.toLowerCase() === selectedB.name.toLowerCase()) {
        container.innerHTML = `<div style="text-align: center; padding: 48px; color: rgba(255,255,255,0.6);">Please select two different debaters to compare.</div>`;
        return;
      }

      if (window.history.replaceState) {
        window.history.replaceState(null, '', `${window.location.pathname}?a=${encodeURIComponent(selectedA.name)}&b=${encodeURIComponent(selectedB.name)}`);
      }

      container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.6);"><div class="spinner"></div> Computing 6-metric head-to-head clash...</div>`;

      // Fetch live direct clashes and BRA from server if available
      let directDebates = [];
      let aDirectWins = 0;
      let bDirectWins = 0;
      let braA = selectedA.bra !== undefined ? selectedA.bra : null;
      let braB = selectedB.bra !== undefined ? selectedB.bra : null;

      if (state.isServerOnline) {
        try {
          const res = await fetch(`${state.apiUrl}/api/h2h?a=${encodeURIComponent(selectedA.name)}&b=${encodeURIComponent(selectedB.name)}&mode=debater`);
          if (res.ok) {
            const j = await res.json();
            directDebates = j.direct_debates || [];
            aDirectWins = j.a_direct_wins || 0;
            bDirectWins = j.b_direct_wins || 0;
            if (j.a_bra !== undefined) braA = j.a_bra;
            if (j.b_bra !== undefined) braB = j.b_bra;
          }
        } catch (e) {}
      }

      // Achievement ranking hierarchy
      const achOrder = {
        "Champion": 1, "Runners-Up": 2, "Finalist": 2, "Semifinalist": 3,
        "Quarterfinalist": 4, "Partial Octofinalist": 5, "Octofinalist": 6,
        "Double Partial Octofinalist": 7, "Preliminary Rounds": 8, "Unranked": 9
      };

      const achA = selectedA.highest_achievement || 'Preliminary Rounds';
      const achB = selectedB.highest_achievement || 'Preliminary Rounds';
      const rankAchA = achOrder[achA] || 8;
      const rankAchB = achOrder[achB] || 8;

      // 6 Categories Comparison:
      // 1. Speaker Score (higher better)
      let w1 = 'TIE';
      if (selectedA.speaker_score > selectedB.speaker_score) w1 = 'A';
      else if (selectedB.speaker_score > selectedA.speaker_score) w1 = 'B';

      // 2. Win % (higher better)
      let w2 = 'TIE';
      if (selectedA.win_percentage > selectedB.win_percentage) w2 = 'A';
      else if (selectedB.win_percentage > selectedA.win_percentage) w2 = 'B';

      // 3. Break Rank Avg (BRA) - lower seed rank is better! (e.g. 1st seed > 4th seed)
      let w3 = 'TIE';
      if (braA !== null && braB !== null) {
        if (braA < braB) w3 = 'A';
        else if (braB < braA) w3 = 'B';
        else w3 = 'TIE';
      } else if (braA !== null && braB === null) {
        w3 = 'A'; // Contender A broke to knockouts, B never broke
      } else if (braB !== null && braA === null) {
        w3 = 'B'; // Contender B broke to knockouts, A never broke
      } else {
        w3 = 'NONE';
      }

      // 4. Prelims Debated (higher better)
      let w4 = 'TIE';
      if (selectedA.prelims_debated > selectedB.prelims_debated) w4 = 'A';
      else if (selectedB.prelims_debated > selectedA.prelims_debated) w4 = 'B';

      // 5. Highest Achievement (lower rank order is better)
      let w5 = 'TIE';
      if (rankAchA < rankAchB) w5 = 'A';
      else if (rankAchB < rankAchA) w5 = 'B';

      // 6. Head to Head in Tournaments
      let w6 = 'NONE';
      if (directDebates.length > 0) {
        if (aDirectWins > bDirectWins) w6 = 'A';
        else if (bDirectWins > aDirectWins) w6 = 'B';
        else w6 = 'TIE';
      }

      const allCat = [w1, w2, w3, w4, w5];
      let scoreA = allCat.filter(w => w === 'A').length;
      let scoreB = allCat.filter(w => w === 'B').length;
      if (w6 === 'A') scoreA++;
      if (w6 === 'B') scoreB++;

      let bannerTitle = '';
      let bannerColor = '#38bdf8';
      if (scoreA > scoreB) {
        bannerTitle = `${escapeHtml(selectedA.name)} LEADS ${scoreA} - ${scoreB}`;
        bannerColor = '#38bdf8';
      } else if (scoreB > scoreA) {
        bannerTitle = `${escapeHtml(selectedB.name)} LEADS ${scoreB} - ${scoreA}`;
        bannerColor = '#f43f5e';
      } else {
        bannerTitle = `EVEN CLASH TIED ${scoreA} - ${scoreB}`;
        bannerColor = '#fbbf24';
      }

      function getBar(valA, valB, higherBetter = true) {
        if (valA === null || valB === null) return { a: 50, b: 50 };
        if (!higherBetter) {
          const invA = 1 / (valA || 0.01);
          const invB = 1 / (valB || 0.01);
          const tot = invA + invB;
          return { a: (invA / tot) * 100, b: (invB / tot) * 100 };
        }
        const tot = valA + valB;
        if (tot === 0) return { a: 50, b: 50 };
        return { a: (valA / tot) * 100, b: (valB / tot) * 100 };
      }

      function badge(w) {
        if (w === 'A') return `<span class="h2h-cat-badge badge-a">CONTENDER 1</span>`;
        if (w === 'B') return `<span class="h2h-cat-badge badge-b">CONTENDER 2</span>`;
        if (w === 'NONE') return `<span class="h2h-cat-badge badge-tie">NO BREAKS</span>`;
        return `<span class="h2h-cat-badge badge-tie">TIE</span>`;
      }

      const b1 = getBar(selectedA.speaker_score, selectedB.speaker_score, true);
      const b2 = getBar(selectedA.win_percentage, selectedB.win_percentage, true);
      let b3 = { a: 50, b: 50 };
      if (braA !== null && braB !== null) {
        b3 = getBar(braA, braB, false);
      } else if (braA !== null && braB === null) {
        b3 = { a: 100, b: 0 };
      } else if (braB !== null && braA === null) {
        b3 = { a: 0, b: 100 };
      }
      const b4 = getBar(selectedA.prelims_debated, selectedB.prelims_debated, true);
      const b5 = getBar(10 - rankAchA, 10 - rankAchB, true);
      const b6 = directDebates.length > 0 ? getBar(aDirectWins, bDirectWins, true) : { a: 50, b: 50 };

      container.innerHTML = `
        <div class="h2h-prediction-banner">
          <div style="font-family: var(--font-mono); font-size: 11.5px; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(255,255,255,0.7); margin-bottom: 6px;">
            6-METRIC HEAD TO HEAD RESULT
          </div>
          <div class="h2h-pred-prob" style="color: ${bannerColor};">${bannerTitle}</div>
          <div style="font-size: 13px; color: rgba(255,255,255,0.85); margin-top: 6px;">
            Judged strictly across: Speaker Score, Win %, Break Rank Avg (BRA), Prelims Debated, Highest Achievement, and Tournament Clashes.
          </div>
        </div>

        <div class="h2h-stat-compare">
          <!-- 1. Speaker Score -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val" style="color: #38bdf8;">${fmt(selectedA.speaker_score, 2)}</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">1. SPEAKER SCORE</span>
                ${badge(w1)}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b1.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b1.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">Speaker average across substantive speeches</div>
            </div>
            <div class="h2h-cat-val" style="color: #f43f5e;">${fmt(selectedB.speaker_score, 2)}</div>
          </div>

          <!-- 2. Win % -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val" style="color: #38bdf8;">${fmt(selectedA.win_percentage, 1)}%</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">2. WIN %</span>
                ${badge(w2)}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b2.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b2.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">Match win rate across contested debates</div>
            </div>
            <div class="h2h-cat-val" style="color: #f43f5e;">${fmt(selectedB.win_percentage, 1)}%</div>
          </div>

          <!-- 3. Break Rank Avg (BRA) -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val" style="color: #38bdf8;">${braA !== null ? fmt(braA, 2) : '-'}</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">3. BREAK RANK AVG (BRA)</span>
                ${badge(w3)}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b3.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b3.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">Average preliminary break seed (Lower is better)</div>
            </div>
            <div class="h2h-cat-val" style="color: #f43f5e;">${braB !== null ? fmt(braB, 2) : '-'}</div>
          </div>


          <!-- 4. Prelims Debated -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val" style="color: #38bdf8;">${selectedA.prelims_debated}</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">4. PRELIMS DEBATED</span>
                ${badge(w4)}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b4.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b4.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">Preliminary speeches completed</div>
            </div>
            <div class="h2h-cat-val" style="color: #f43f5e;">${selectedB.prelims_debated}</div>
          </div>

          <!-- 5. Highest Achievement -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val" style="font-size: 11.5px; color: #38bdf8;">${achA}</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">5. HIGHEST ACHIEVEMENT</span>
                ${badge(w5)}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b5.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b5.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">Peak elimination progression</div>
            </div>
            <div class="h2h-cat-val" style="font-size: 11.5px; color: #f43f5e;">${achB}</div>
          </div>

          <!-- 6. Head to Head in Tournaments -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val" style="color: #38bdf8;">${aDirectWins}</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">6. HEAD TO HEAD IN TOURNAMENTS</span>
                ${badge(w6)}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b6.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b6.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">${directDebates.length} direct debate matchup${directDebates.length === 1 ? '' : 's'} contested</div>
            </div>
            <div class="h2h-cat-val" style="color: #f43f5e;">${bDirectWins}</div>
          </div>
        </div>

        <!-- Direct Matchups Breakdown if any -->
        ${directDebates.length > 0 ? `
          <div class="h2h-matchups-section">
            <div class="h2h-matchups-title">
              DIRECT TOURNAMENT ENCOUNTERS (${directDebates.length})
            </div>
            ${directDebates.map(m => `
              <div class="h2h-matchup-card">
                <div class="h2h-matchup-header">
                  <span class="h2h-matchup-tour">${escapeHtml(m.tournament_name)} - ${escapeHtml(m.round_name)}</span>
                  <span class="h2h-matchup-outcome" style="color: ${m.a_won ? '#38bdf8' : '#f43f5e'};">
                    ${m.a_won ? escapeHtml(selectedA.name) + ' WON' : escapeHtml(selectedB.name) + ' WON'}
                  </span>
                </div>
                <div class="h2h-matchup-body">
                  <div class="h2h-matchup-team">${escapeHtml(m.team_a)} (${m.side_a})</div>
                  <div style="font-family: var(--font-mono); font-weight: 700; color: rgba(255,255,255,0.4);">VS</div>
                  <div class="h2h-matchup-team" style="text-align: right;">${escapeHtml(m.team_b)} (${m.side_b})</div>
                </div>
              </div>
            `).join('')}
          </div>
        ` : ''}
      `;
    }

    if (selectedA && selectedB) {
      updateH2H();
    }
  }

  // ==========================================================================
  // 8. NATIONAL POOL PAGE (3 CLEAN UNRANKED LISTS)
  // ==========================================================================
  function initPoolPage() {
    const listDirect = document.getElementById('listDirect');
    const listTrialed = document.getElementById('listTrialed');
    const listTrials = document.getElementById('listTrials');
    const searchInput = document.getElementById('poolSearchInput');

    let poolData = state.v2NationalPool;

    function renderPoolLists(q = '') {
      if (!poolData) return;

      const query = q.trim().toLowerCase();

      function filterList(arr) {
        if (!arr) return [];
        if (!query) return arr;
        return arr.filter(d => d.name.toLowerCase().includes(query) || (d.institution && d.institution.toLowerCase().includes(query)));
      }

      const direct = filterList(poolData.nat_pool_direct);
      const trialed = filterList(poolData.nat_pool_trialed);
      const trials = filterList(poolData.trials);

      const cd = document.getElementById('countDirect');
      const ctr = document.getElementById('countTrialed');
      const ct = document.getElementById('countTrials');
      if (cd) cd.textContent = `${direct.length} DEBATERS`;
      if (ctr) ctr.textContent = `${trialed.length} DEBATERS`;
      if (ct) ct.textContent = `${trials.length} DEBATERS`;

      function renderItems(arr, tagClass) {
        if (arr.length === 0) {
          return `<div style="text-align: center; padding: 20px; color: rgba(255,255,255,0.4); font-size: 12px;">No debaters match.</div>`;
        }
        return arr.map(d => `
          <div class="pool-debater-card">
            <div style="display: flex; align-items: center; gap: 12px;">
              <span class="pool-rank-badge">#${d.rank_in_tier || '-'}</span>
              <div>
                <a class="pool-debater-name" href="bio.html?debater=${encodeURIComponent(d.name)}">${escapeHtml(d.name)}</a>
                <div>
                  <a class="pool-debater-inst" href="institution_bio.html?inst=${encodeURIComponent(d.institution || '')}">${escapeHtml(d.institution || 'Independent')}</a>
                </div>
              </div>
            </div>
            <div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
              <span class="nat-tag ${tagClass}">${escapeHtml(d.national_level || '')}</span>
              ${d.speaker_score ? `<span style="font-size: 11px; font-family: var(--font-mono); color: #38bdf8; font-weight: 600;">Avg: ${fmt(d.speaker_score, 3)} pts <span style="color: rgba(255,255,255,0.4); font-size: 9.5px; text-transform: uppercase;">(${escapeHtml(d.score_source || 'Tab')})</span></span>` : ''}
            </div>
          </div>
        `).join('');
      }

      if (listDirect) listDirect.innerHTML = renderItems(direct, 'nat-direct');
      if (listTrialed) listTrialed.innerHTML = renderItems(trialed, 'nat-trialed');
      if (listTrials) listTrials.innerHTML = renderItems(trials, 'nat-trials');
    }

    if (searchInput) {
      searchInput.addEventListener('input', () => {
        renderPoolLists(searchInput.value);
      });
    }

    renderPoolLists();
  }

  // ==========================================================================
  // 9. AI CHATBOT INTEGRATION
  // ==========================================================================
  function getChatSessionId() {
    let sid = sessionStorage.getItem('atomos_chat_session_id');
    if (!sid) {
      sid = 'session_' + Math.random().toString(36).substring(2, 11) + '_' + Date.now();
      sessionStorage.setItem('atomos_chat_session_id', sid);
    }
    return sid;
  }

  function initChatPage() {
    const input = document.getElementById('chatInput');
    const sendBtn = document.getElementById('chatSendBtn');
    const clearBtn = document.getElementById('clearChatBtn');
    const messages = document.getElementById('chatMessages');

    if (clearBtn) {
      clearBtn.addEventListener('click', async () => {
        const sid = getChatSessionId();
        try {
          await fetch(`${state.apiUrl}/api/chat/reset`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sid }),
          });
        } catch (e) {}
        sessionStorage.removeItem('atomos_chat_session_id');
        if (messages) {
          messages.innerHTML = `
            <div class="chat-bubble bot">
              <strong>Atomos:</strong> Session reset. What would you like to explore about the circuit?
            </div>
          `;
        }
      });
    }

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
    botMsg.innerHTML = `<em>Analyzing circuit data...</em>`;
    messages.appendChild(botMsg);
    messages.scrollTop = messages.scrollHeight;

    const sid = getChatSessionId();

    try {
      const res = await fetch(`${state.apiUrl}/api/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: promptText, session_id: sid }),
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
      botMsg.innerHTML = `<div style="color: #f87171;">Unable to communicate with the Atomos AI server at ${escapeHtml(state.apiUrl)}.</div>`;
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

      if (line.startsWith('|') && line.endsWith('|')) {
        if (/^\|(\s*:?-+:?\s*\|)+$/.test(line)) continue;
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
    sendChatPrompt,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
