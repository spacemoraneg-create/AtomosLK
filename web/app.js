/**
 * ATOMOS V3 - CLIENT ENGINE & APPLICATION CONTROLLER
 * Powering Home Page + Subpages with Complete Multi Purpose Analytics
 */

(function () {
  'use strict';

  const GITHUB_RAW_BASE = 'https://raw.githubusercontent.com/spacemoraneg-create/AtomosLK/main/data/web_export';

  // Global State
  const state = {
    // V2 Datasets
    v2SpeakersTab: [],
    v2SpeakersGeneral: [],
    v2SpeakersAll: [],
    v2TeamsTab: [],
    v2TeamsGeneral: [],
    v2TeamsAll: [],
    v2InstitutionsTab: [],
    v2InstitutionsGeneral: [],
    v2InstitutionsAll: [],
    v2Tournaments: [],
    v2Adjudicators: [],
    v2AdjudicatorsAll: [],
    v2NationalPool: null,
    v2H2HDebates: [],

    circuitSummary: null,
    searchIndex: [],

    // App & GitHub Sync State
    isServerOnline: false,
    useGitHubRaw: false,
    manifestVersion: null,
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
    if (!level || level === '-' || level === 'null') return '<span class="nat-tag nat-none">—</span>';
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

  // Helper: Rank Badge HTML (Zero-padded 2-digit editorial rank)
  function getRankBadge(rank) {
    let cls = 'rank-badge';
    if (rank === 1) cls += ' rank-1';
    else if (rank === 2) cls += ' rank-2';
    else if (rank === 3) cls += ' rank-3';
    const padded = String(rank).padStart(2, '0');
    return `<span class="${cls}">${padded}</span>`;
  }

  // Helper: Break Position Tag HTML
  function getBreakBadge(pos) {
    if (!pos || pos === '-' || pos === 'Preliminary Rounds') return '<span class="break-tag break-none">—</span>';
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

  // Analytics & Event Tracking (Google Analytics 4)
  function trackEvent(eventName, params = {}) {
    if (typeof window.gtag === 'function') {
      try {
        window.gtag('event', eventName, params);
      } catch (e) {}
    }
  }

  function createSearchTracker(searchType) {
    let timer = null;
    return function (term) {
      clearTimeout(timer);
      const query = (term || '').trim();
      if (query.length < 2) return;
      timer = setTimeout(() => {
        trackEvent('search', {
          search_term: query,
          search_type: searchType,
        });
      }, 700);
    };
  }

  // Fast In-Memory & Session Storage Cache Map
  const dataCache = new Map();
  let manifestCheckPromise = null;

  function clearClientDataCache() {
    dataCache.clear();
    try {
      const keysToRemove = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        if (k && k.startsWith('atomos_cache_')) {
          keysToRemove.push(k);
        }
      }
      keysToRemove.forEach((k) => sessionStorage.removeItem(k));
    } catch (e) {}
  }

  // Synchronize manifest version with local export & GitHub Raw to guarantee fresh data
  function syncWithGitHubManifest() {
    if (manifestCheckPromise) return manifestCheckPromise;
    manifestCheckPromise = (async () => {
      const fetchLocalManifest = async () => {
        try {
          let r = await fetch(`data/web_export/export_manifest.json`, { cache: 'no-cache' });
          if (!r.ok) r = await fetch(`../data/web_export/export_manifest.json`, { cache: 'no-cache' });
          if (r.ok) return await r.json();
        } catch (e) {}
        return null;
      };

      const fetchGitHubManifest = async () => {
        try {
          const r = await fetch(`${GITHUB_RAW_BASE}/export_manifest.json?t=${Math.floor(Date.now() / 30000)}`, {
            cache: 'no-cache',
            signal: AbortSignal.timeout(1800),
          });
          if (r.ok) return await r.json();
        } catch (e) {}
        return null;
      };

      const applyVersion = (ver, useGh) => {
        if (!ver) return;
        state.useGitHubRaw = Boolean(useGh);
        state.manifestVersion = ver;
        try {
          const cachedVer = Number(sessionStorage.getItem('atomos_manifest_version') || '0');
          if (cachedVer !== ver) {
            clearClientDataCache();
            sessionStorage.setItem('atomos_manifest_version', String(ver));
          }
        } catch (e) {}
      };

      const ghPromise = fetchGitHubManifest();
      const localManifest = await fetchLocalManifest();
      const localVer = localManifest && localManifest.version ? Number(localManifest.version) : 0;

      if (localVer > 0) {
        applyVersion(localVer, false);
        // Check GitHub Raw in background in case a newer commit was pushed remotely
        ghPromise.then((ghManifest) => {
          const ghVer = ghManifest && ghManifest.version ? Number(ghManifest.version) : 0;
          if (ghVer > localVer) {
            applyVersion(ghVer, true);
          }
        });
      } else {
        const ghManifest = await ghPromise;
        const ghVer = ghManifest && ghManifest.version ? Number(ghManifest.version) : 0;
        if (ghVer > 0) {
          applyVersion(ghVer, true);
        }
      }
    })();
    return manifestCheckPromise;
  }

  // Router / Initializer based on active page - Runs immediately on DOMContentLoaded
  function init() {
    checkServerStatus();
    syncWithGitHubManifest();

    const path = window.location.pathname.toLowerCase();

    if (document.getElementById('homeMultiTable') || path.endsWith('index.html') || path === '/' || path === '') {
      initHomePage();
    } else if (document.getElementById('lbTableContainer') || path.includes('leaderboards')) {
      initLeaderboardsPage();
    } else if (document.getElementById('bioProfileContainer') || (path.includes('bio') && !path.includes('team') && !path.includes('institution') && !path.includes('adjudicator'))) {
      initBioPage();
    } else if (document.getElementById('teamProfileContainer') || path.includes('team_bio') || path.includes('team-bio')) {
      initTeamBioPage();
    } else if (document.getElementById('instProfileContainer') || path.includes('institution_bio') || path.includes('institution-bio')) {
      initInstitutionBioPage();
    } else if (document.getElementById('judgeProfileContainer') || path.includes('adjudicator_bio') || path.includes('adjudicator-bio')) {
      initAdjudicatorBioPage();
    } else if (document.getElementById('h2hResultContainer') || path.includes('h2h')) {
      initH2HPage();
    } else if (document.getElementById('poolGridContainer') || path.includes('pool')) {
      initPoolPage();
    } else if (document.getElementById('chatMessages') || path.includes('chat')) {
      initChatPage();
    }

    prefetchBackgroundData();
  }

  // Check if Flask Backend is online (non-blocking)
  async function checkServerStatus() {
    try {
      const res = await fetch(`${state.apiUrl}/api/health`, { method: 'GET', signal: AbortSignal.timeout(1200) });
      if (res.ok) {
        state.isServerOnline = true;
      }
    } catch (e) {
      state.isServerOnline = false;
    }
  }

  async function tryFetchLocalExport(filename) {
    const qs = state.manifestVersion ? `?v=${state.manifestVersion}` : '';
    try {
      let res = await fetch(`data/web_export/${filename}${qs}`);
      if (!res.ok) {
        res = await fetch(`../data/web_export/${filename}${qs}`);
      }
      if (res.ok) return await res.json();
    } catch (e) {
      try {
        const res = await fetch(`../data/web_export/${filename}${qs}`);
        if (res.ok) return await res.json();
      } catch (err) {}
    }
    return null;
  }

  async function tryFetchGitHubRaw(filename) {
    const qs = state.manifestVersion ? `?v=${state.manifestVersion}` : '';
    try {
      const res = await fetch(`${GITHUB_RAW_BASE}/${filename}${qs}`, { signal: AbortSignal.timeout(5000) });
      if (res.ok) return await res.json();
    } catch (e) {}
    return null;
  }

  // Fetch JSON with manifest-verified caching, local + GitHub Raw synchronization, and live API fallback
  async function fetchJson(filename, fallbackApi) {
    await syncWithGitHubManifest();

    if (dataCache.has(filename)) {
      return dataCache.get(filename);
    }

    try {
      const cached = sessionStorage.getItem(`atomos_cache_${filename}`);
      if (cached) {
        const parsed = JSON.parse(cached);
        dataCache.set(filename, parsed);
        return parsed;
      }
    } catch (e) {}

    let data = null;

    if (state.useGitHubRaw) {
      // GitHub has a newer manifest version than local static files
      data = await tryFetchGitHubRaw(filename);
      if (!data) {
        data = await tryFetchLocalExport(filename);
      }
    } else {
      // Local static export is up-to-date
      data = await tryFetchLocalExport(filename);
    }

    // Fallback to Live Server API if static file unavailable
    if (!data && fallbackApi) {
      try {
        const res = await fetch(`${state.apiUrl}${fallbackApi}`);
        if (res.ok) {
          const j = await res.json();
          data = j.leaderboard || j;
          state.isServerOnline = true;
        }
      } catch (e) {}
    }

    // Final fallback to GitHub Raw if local & server both unavailable
    if (!data && !state.useGitHubRaw) {
      data = await tryFetchGitHubRaw(filename);
    }

    if (data) {
      dataCache.set(filename, data);
      try {
        const str = JSON.stringify(data);
        if (str.length < 2500000) {
          sessionStorage.setItem(`atomos_cache_${filename}`, str);
        }
      } catch (e) {}
    }

    return data;
  }

  // Background Prefetcher for remaining datasets after current page is active
  function prefetchBackgroundData() {
    const prefetchList = [
      ['circuit_summary.json', '/api/circuit'],
      ['v2_speakers_tab.json', '/api/v2/leaderboard/speakers?tier=tab'],
      ['v2_speakers_general.json', '/api/v2/leaderboard/speakers?tier=general'],
      ['v2_speakers_all.json', '/api/v2/leaderboard/speakers?tier=all'],
      ['v2_teams_tab.json', '/api/v2/leaderboard/teams?tier=tab'],
      ['v2_teams_general.json', '/api/v2/leaderboard/teams?tier=general'],
      ['v2_teams_all.json', '/api/v2/leaderboard/teams?tier=all'],
      ['v2_institutions_tab.json', '/api/v2/leaderboard/institutions?tier=tab'],
      ['v2_institutions_general.json', '/api/v2/leaderboard/institutions?tier=general'],
      ['v2_institutions_all.json', '/api/v2/leaderboard/institutions?tier=all'],
      ['v2_tournaments.json', '/api/v2/leaderboard/tournaments'],
      ['v2_adjudicators.json', '/api/v2/leaderboard/adjudicators'],
      ['v2_adjudicators_all.json', '/api/v2/leaderboard/adjudicators?min_prelims=1'],
      ['v2_national_pool.json', '/api/v2/pool'],
      ['v2_h2h_debates.json', null],
      ['search_index.json', '/api/search?q=a'],
    ];

    const runPrefetch = async () => {
      for (const [file, api] of prefetchList) {
        if (!dataCache.has(file)) {
          const res = await fetchJson(file, api);
          if (res) {
            if (file === 'circuit_summary.json' && !state.circuitSummary) state.circuitSummary = res;
            if (file === 'v2_speakers_tab.json' && !state.v2SpeakersTab.length) state.v2SpeakersTab = res;
            if (file === 'v2_speakers_general.json' && !state.v2SpeakersGeneral.length) state.v2SpeakersGeneral = res;
            if (file === 'v2_speakers_all.json' && !state.v2SpeakersAll.length) state.v2SpeakersAll = res;
            if (file === 'v2_teams_tab.json' && !state.v2TeamsTab.length) state.v2TeamsTab = res;
            if (file === 'v2_teams_general.json' && !state.v2TeamsGeneral.length) state.v2TeamsGeneral = res;
            if (file === 'v2_teams_all.json' && !state.v2TeamsAll.length) state.v2TeamsAll = res;
            if (file === 'v2_institutions_tab.json' && !state.v2InstitutionsTab.length) state.v2InstitutionsTab = res;
            if (file === 'v2_institutions_general.json' && !state.v2InstitutionsGeneral.length) state.v2InstitutionsGeneral = res;
            if (file === 'v2_institutions_all.json' && !state.v2InstitutionsAll.length) state.v2InstitutionsAll = res;
            if (file === 'v2_tournaments.json' && !state.v2Tournaments.length) state.v2Tournaments = res;
            if (file === 'v2_adjudicators.json' && !state.v2Adjudicators.length) state.v2Adjudicators = res;
            if (file === 'v2_adjudicators_all.json' && !state.v2AdjudicatorsAll.length) state.v2AdjudicatorsAll = res;
            if (file === 'v2_national_pool.json' && !state.v2NationalPool) state.v2NationalPool = res;
            if (file === 'v2_h2h_debates.json' && !state.v2H2HDebates.length) state.v2H2HDebates = res;
            if (file === 'search_index.json' && !state.searchIndex.length) state.searchIndex = res;
          }
        }
      }
    };

    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(() => runPrefetch(), { timeout: 2500 });
    } else {
      setTimeout(runPrefetch, 400);
    }
  }

  // ==========================================================================
  // 1. HOME PAGE LOGIC (Multi Purpose Leaderboard - Min 18 Rounds)
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
          trackEvent('select_metric', { metric: currentMetric, location: 'home' });
          renderTable();
        });
      });
    }

    const searchInput = document.getElementById('speakerSearchInput');
    const trackHomeSearch = createSearchTracker('home_tab_search');
    if (searchInput) {
      searchInput.addEventListener('input', () => {
        searchQuery = searchInput.value.trim().toLowerCase();
        renderTable();
        trackHomeSearch(searchInput.value);
      });
    }

    function renderTable() {
      const tbody = document.getElementById('homeMultiStatsBody');
      if (!tbody) return;

      let list = state.v2SpeakersTab.slice();

      // Sort based on currentMetric
      if (currentMetric === 'elo') {
        list.sort((a, b) => (b.elo || 1500) - (a.elo || 1500) || b.speaker_score - a.speaker_score);
      } else if (currentMetric === 'stdev') {
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
        tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 28px; color: rgba(255, 255, 255, 0.72);">No debaters found matching "${escapeHtml(searchQuery)}".</td></tr>`;
        return;
      }

      tbody.innerHTML = list.map((s) => {
        const debaterName = s.speaker_name || s.name || '';
        return `
          <tr>
            <td>${getRankBadge(s._trueRank)}</td>
            <td>
              <a class="table-link" href="bio.html?debater=${encodeURIComponent(debaterName)}">${escapeHtml(debaterName)}</a>
            </td>
            <td>
              <a class="table-link-inst" href="institution_bio.html?inst=${encodeURIComponent(s.institution)}">${escapeHtml(s.institution)}</a>
            </td>
            <td class="num-col">${fmt(s.speaker_score, 2)}</td>
            <td class="num-col">${fmt(s.elo || 1500, 1)}</td>
            <td class="num-col">${fmt(s.win_percentage, 1)}%</td>
            <td class="num-col">${fmt(s.stdev, 2)}</td>
            <td class="num-col">${s.prelims_debated}</td>
            <td>${getNatStatusTag(s.national_level)}</td>
          </tr>
        `;
      }).join('');
    }

    renderTable();

    // If datasets not yet in state, fetch immediately and render
    if (!state.v2SpeakersTab.length || !state.circuitSummary) {
      Promise.all([
        fetchJson('circuit_summary.json', '/api/circuit'),
        fetchJson('v2_speakers_tab.json', '/api/v2/leaderboard/speakers?tier=tab')
      ]).then(([sum, spk]) => {
        if (sum) {
          state.circuitSummary = sum;
          updateVitals(sum);
        }
        if (spk) {
          state.v2SpeakersTab = spk;
          renderTable();
        }
      });
    }
  }

  function updateVitals(data) {
    const t = document.getElementById('vitalTournaments');
    const d = document.getElementById('vitalDebaters');
    const s = document.getElementById('vitalSpeeches');
    const r = document.getElementById('vitalRounds');
    const p = document.getElementById('vitalPrelims');
    const k = document.getElementById('vitalKnockouts');

    if (t) t.textContent = data && data.total_tournaments ? String(data.total_tournaments) : '10';
    if (d) d.textContent = data && data.total_persons ? Number(data.total_persons).toLocaleString() : '831';
    if (s) {
      const speechCount = (data && data.total_speeches) ? data.total_speeches : (data && data.total_valid_speeches ? data.total_valid_speeches : 8034);
      s.textContent = Number(speechCount).toLocaleString();
    }
    if (r) r.textContent = data && data.total_debates_debated ? Number(data.total_debates_debated).toLocaleString() : '1,096';
    if (p) p.textContent = data && data.total_prelim_rounds ? Number(data.total_prelim_rounds).toLocaleString() : '973';
    if (k) k.textContent = data && data.total_knockout_rounds ? Number(data.total_knockout_rounds).toLocaleString() : '123';
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

          // Ensure dataset for chosen category is loaded
          if (activeCategory === 'teams' && !state.v2TeamsTab.length) {
            Promise.all([
              fetchJson('v2_teams_tab.json', '/api/v2/leaderboard/teams?tier=tab'),
              fetchJson('v2_teams_general.json', '/api/v2/leaderboard/teams?tier=general')
            ]).then(([tab, gen]) => {
              if (tab) state.v2TeamsTab = tab;
              if (gen) state.v2TeamsGeneral = gen;
              renderLeaderboard();
            });
          } else if (activeCategory === 'institutions' && !state.v2InstitutionsTab.length) {
            Promise.all([
              fetchJson('v2_institutions_tab.json', '/api/v2/leaderboard/institutions?tier=tab'),
              fetchJson('v2_institutions_general.json', '/api/v2/leaderboard/institutions?tier=general')
            ]).then(([tab, gen]) => {
              if (tab) state.v2InstitutionsTab = tab;
              if (gen) state.v2InstitutionsGeneral = gen;
              renderLeaderboard();
            });
          } else if (activeCategory === 'tournaments' && !state.v2Tournaments.length) {
            fetchJson('v2_tournaments.json', '/api/v2/leaderboard/tournaments').then((t) => {
              if (t) state.v2Tournaments = t;
              renderLeaderboard();
            });
          } else if (activeCategory === 'adjudicators' && !state.v2Adjudicators.length) {
            fetchJson('v2_adjudicators.json', '/api/v2/leaderboard/adjudicators').then((a) => {
              if (a) state.v2Adjudicators = a;
              renderLeaderboard();
            });
          }

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
          trackEvent('select_category', { category: activeCategory });
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
          trackEvent('select_tier', { tier: activeTier, category: activeCategory });
          renderLeaderboard();
        });
      });
    }

    const trackLbSearch = createSearchTracker('leaderboard_search');
    if (searchInput) {
      searchInput.addEventListener('input', () => {
        searchQuery = searchInput.value.trim().toLowerCase();
        renderLeaderboard();
        trackLbSearch(searchInput.value);
      });
    }

    function updateTierBadge() {
      if (!tierBadge) return;
      if (activeCategory === 'individual') {
        tierBadge.textContent = activeTier === 'tab' ? '01 // Tab Qualification (Min 18 Rounds)' : '01 // General Tab (Min 5 Rounds)';
      } else if (activeCategory === 'teams') {
        tierBadge.textContent = activeTier === 'tab' ? '01 // Tab Qualification (Min 3 Tournaments)' : '01 // General Tab (Min 2 Tournaments)';
      } else if (activeCategory === 'institutions') {
        tierBadge.textContent = activeTier === 'tab' ? '01 // Tab Qualification (Min 3 Tournaments)' : '01 // General Tab (Min 2 Tournaments)';
      } else if (activeCategory === 'tournaments') {
        tierBadge.textContent = '01 // Circuit Tournaments';
      } else if (activeCategory === 'adjudicators') {
        tierBadge.textContent = '01 // Circuit Adjudicators';
      }
    }

    function updateMetricPills() {
      if (!metricToolbar) return;
      let pills = [];

      if (activeCategory === 'individual') {
        pills = [
          { id: 'speaker_score', label: 'Speaker Score' },
          { id: 'elo', label: 'Elo' },
          { id: 'win_percentage', label: 'Win %' },
          { id: 'prelims_debated', label: 'Prelims' },
          { id: 'stdev', label: 'StDev' },
          { id: 'national_level', label: 'Nat Status' },
        ];
      } else if (activeCategory === 'teams') {
        pills = [
          { id: 'atss', label: 'ATSS' },
          { id: 'elo', label: 'Elo' },
          { id: 'win_percentage', label: 'Win %' },
          { id: 'awpt', label: 'AWPT (Wins / Tour)' },
          { id: 'achievement', label: 'Highest Break' },
        ];
      } else if (activeCategory === 'institutions') {
        pills = [
          { id: 'delta', label: 'Delta' },
          { id: 'elo', label: 'Elo' },
          { id: 'a_atss', label: 'A Team ATSS' },
          { id: 'b_atss', label: 'B Team ATSS' },
          { id: 'net_diff', label: 'Net Diff' },
          { id: 'win_percentage', label: 'Win %' },
          { id: 'pool_count', label: 'Debater Pool' },
        ];
      } else if (activeCategory === 'tournaments') {
        pills = [
          { id: 'atss', label: 'ATSS' },
          { id: 'brk_atss', label: 'Break ATSS' },
          { id: 'institutions', label: 'Institutions' },
          { id: 'teams', label: 'Teams' },
          { id: 'rounds', label: 'Prelims + Knockouts' },
          { id: 'speeches', label: 'Speeches' },
          { id: 'debates', label: 'Prelim Debates' },
        ];
      } else if (activeCategory === 'adjudicators') {
        pills = [
          { id: 'debates', label: 'Prelims Judged' },
          { id: 'aass', label: 'AASS (Speak Avg)' },
          { id: 'aatss', label: 'AATSS (Team Avg)' },
          { id: 'tournaments', label: 'Tournaments' },
        ];
      }

      metricToolbar.innerHTML = `
        <div class="metric-pills-bar">
          <span style="font-size: 11.5px; letter-spacing: 0.06em; text-transform: uppercase; color: rgba(255, 255, 255, 0.85); margin-right: 6px;">Sort by</span>
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

      if (activeMetric === 'elo') {
        list.sort((a, b) => (b.elo || 1500) - (a.elo || 1500) || b.speaker_score - a.speaker_score);
      } else if (activeMetric === 'stdev') {
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
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.88);">No debaters match "${escapeHtml(searchQuery)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 4%;">#</th>
                <th style="width: 15%;">Speaker</th>
                <th style="width: 14%;">Institution</th>
                <th class="num-col" style="width: 10%;">Avg Score</th>
                <th class="num-col" style="width: 9%;">Elo</th>
                <th class="num-col" style="width: 9%;">Win %</th>
                <th class="num-col" style="width: 8%;">StDev</th>
                <th class="num-col" style="width: 8%;">Prelims</th>
                <th class="num-col" style="width: 9%;">Tourneys</th>
                <th style="width: 14%;">Nat Status</th>
              </tr>
            </thead>
            <tbody>
              ${list.map((s) => {
                const debaterName = s.speaker_name || s.name || '';
                return `
                <tr>
                  <td>${getRankBadge(s._trueRank)}</td>
                  <td>
                    <a class="table-link" href="bio.html?debater=${encodeURIComponent(debaterName)}">${escapeHtml(debaterName)}</a>
                  </td>
                  <td>
                    <a class="table-link-inst" href="institution_bio.html?inst=${encodeURIComponent(s.institution)}">${escapeHtml(s.institution)}</a>
                  </td>
                  <td class="num-col">${fmt(s.speaker_score, 2)}</td>
                  <td class="num-col">${fmt(s.elo || 1500, 1)}</td>
                  <td class="num-col">${fmt(s.win_percentage, 1)}%</td>
                  <td class="num-col">${fmt(s.stdev, 2)}</td>
                  <td class="num-col">${s.prelims_debated}</td>
                  <td class="num-col">${s.tournaments_debated}</td>
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

      if (activeMetric === 'elo') {
        list.sort((a, b) => (b.elo || 1500) - (a.elo || 1500) || b.atss - a.atss);
      } else if (activeMetric === 'win_percentage') {
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
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.88);">No teams match "${escapeHtml(searchQuery)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 4%;">#</th>
                <th style="width: 16%;">Team</th>
                <th style="width: 15%;">Institution</th>
                <th class="num-col" style="width: 10%;">ATSS</th>
                <th class="num-col" style="width: 10%;">Elo</th>
                <th class="num-col" style="width: 10%;">Win %</th>
                <th class="num-col" style="width: 10%;">AWPT</th>
                <th class="num-col" style="width: 9%;">Tourneys</th>
                <th style="width: 16%;">Highest Break</th>
              </tr>
            </thead>
            <tbody>
              ${list.map((t) => `
                <tr>
                  <td>${getRankBadge(t._trueRank)}</td>
                  <td>
                    <a class="table-link" href="team_bio.html?team=${encodeURIComponent(t.team_name)}">${escapeHtml(t.team_name)}</a>
                  </td>
                  <td>
                    <a class="table-link-inst" href="institution_bio.html?inst=${encodeURIComponent(t.institution)}">${escapeHtml(t.institution)}</a>
                  </td>
                  <td class="num-col">${fmt(t.atss, 2)}</td>
                  <td class="num-col">${fmt(t.elo || 1500, 1)}</td>
                  <td class="num-col">${fmt(t.win_percentage, 1)}%</td>
                  <td class="num-col">${fmt(t.awpt, 2)}</td>
                  <td class="num-col">${t.tournaments_debated}</td>
                  <td>${getBreakBadge(t.highest_achievement)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    function renderInstitutionsTable(container) {
      let list = (activeTier === 'tab' ? state.v2InstitutionsTab : state.v2InstitutionsGeneral).slice();

      if (activeMetric === 'elo') {
        list.sort((a, b) => (b.elo || 1500) - (a.elo || 1500) || b.delta - a.delta);
      } else if (activeMetric === 'a_atss') {
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
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.88);">No institutions match "${escapeHtml(searchQuery)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 4%;">#</th>
                <th style="width: 22%;">Institution</th>
                <th class="num-col" style="width: 10%;">Delta</th>
                <th class="num-col" style="width: 10%;">Elo</th>
                <th class="num-col" style="width: 11%;">A Team ATSS</th>
                <th class="num-col" style="width: 11%;">B Team ATSS</th>
                <th class="num-col" style="width: 10%;">Net Diff</th>
                <th class="num-col" style="width: 10%;">Win %</th>
                <th class="num-col" style="width: 12%;">Debater Pool</th>
              </tr>
            </thead>
            <tbody>
              ${list.map((i) => {
                const aTeamLink = i.a_team_name ? `<a class="table-link" href="team_bio.html?team=${encodeURIComponent(i.a_team_name)}">${fmt(i.a_atss, 2)}</a>` : fmt(i.a_atss, 2);
                const bTeamLink = i.b_team_name && i.b_atss ? `<a class="table-link" href="team_bio.html?team=${encodeURIComponent(i.b_team_name)}">${fmt(i.b_atss, 2)}</a>` : (i.b_atss ? fmt(i.b_atss, 2) : '—');
                let netDiffHtml = '—';
                if (i.net_diff !== null && i.net_diff !== undefined) {
                  const nd = Number(i.net_diff);
                  const sign = nd > 0 ? '+' : '';
                  netDiffHtml = `<span>${sign}${fmt(nd, 2)}</span>`;
                }

                return `
                  <tr>
                    <td>${getRankBadge(i._trueRank)}</td>
                    <td style="white-space: normal;">
                      <a class="table-link" href="institution_bio.html?inst=${encodeURIComponent(i.institution_name)}">${escapeHtml(i.institution_name)}</a>
                      ${i.code ? `<span style="font-size: 10.5px; margin-left: 6px; padding: 1px 6px; border-radius: 3px; background: rgba(255, 255, 255, 0.12); border: 1px solid rgba(255, 255, 255, 0.28); color: #ffffff;">${escapeHtml(i.code)}</span>` : ''}
                    </td>
                    <td class="num-col">${fmt(i.delta, 2)}</td>
                    <td class="num-col">${fmt(i.elo || 1500, 1)}</td>
                    <td class="num-col">${aTeamLink}</td>
                    <td class="num-col">${bTeamLink}</td>
                    <td class="num-col">${netDiffHtml}</td>
                    <td class="num-col">${fmt(i.win_percentage, 1)}%</td>
                    <td class="num-col">${i.pool_count}</td>
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
                <th style="width: 4%;">#</th>
                <th style="width: 22%;">Tournament</th>
                <th style="width: 12%;">Dates</th>
                <th class="num-col" style="width: 9%;">ATSS</th>
                <th class="num-col" style="width: 10%;">Break ATSS</th>
                <th class="num-col" style="width: 10%;">Institutions</th>
                <th class="num-col" style="width: 8%;">Teams</th>
                <th class="num-col" style="width: 8%;">Rounds</th>
                <th class="num-col" style="width: 9%;">Speeches</th>
                <th class="num-col" style="width: 8%;">Debates</th>
              </tr>
            </thead>
            <tbody>
              ${list.map((t) => `
                <tr>
                  <td>${getRankBadge(t._trueRank)}</td>
                  <td style="font-weight: 400; color: #ffffff;">${escapeHtml(t.name)}</td>
                  <td style="font-size: 12.5px; color: rgba(255, 255, 255, 0.9);">${escapeHtml(t.hosting_dates)}</td>
                  <td class="num-col">${fmt(t.atss, 2)}</td>
                  <td class="num-col">${fmt(t.brk_atss, 2)}</td>
                  <td class="num-col">${t.participating_institutions}</td>
                  <td class="num-col">${t.participating_teams}</td>
                  <td class="num-col">${t.prelims_plus_knock}</td>
                  <td class="num-col">${Number(t.total_speeches).toLocaleString()}</td>
                  <td class="num-col">${t.prelim_debates}</td>
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
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.88);">No adjudicators match "${escapeHtml(searchQuery)}".</div>`;
        return;
      }

      container.innerHTML = `
        <div class="data-table-wrap">
          <table class="atomos-table">
            <thead>
              <tr>
                <th style="width: 4%;">#</th>
                <th style="width: 18%;">Adjudicator</th>
                <th style="width: 17%;">Institution</th>
                <th class="num-col" style="width: 13%;">AASS (Speak Avg)</th>
                <th class="num-col" style="width: 13%;">AATSS (Team Avg)</th>
                <th style="width: 15%;">Prop / Opp Balance</th>
                <th class="num-col" style="width: 11%;">Prelims Judged</th>
                <th class="num-col" style="width: 9%;">Tourneys</th>
              </tr>
            </thead>
            <tbody>
              ${list.map((j) => `
                <tr>
                  <td>${getRankBadge(j._trueRank)}</td>
                  <td>
                    <a class="table-link" href="adjudicator_bio.html?judge=${encodeURIComponent(j.adjudicator_name)}">${escapeHtml(j.adjudicator_name)}</a>
                  </td>
                  <td>${escapeHtml(j.institution)}</td>
                  <td class="num-col">${fmt(j.aass, 2)}</td>
                  <td class="num-col">${fmt(j.aatss, 2)}</td>
                  <td style="font-size: 12.5px; color: #ffffff;">
                    <span>${fmt(j.prop_bias_pct)}% P</span> · <span>${fmt(j.opp_bias_pct)}% O</span>
                  </td>
                  <td class="num-col">${j.prelims_adjudicated}</td>
                  <td class="num-col">${j.tournaments_adjudicated}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    }

    updateMetricPills();
    renderLeaderboard();

    // Ensure speakers tab and general are loaded if accessed directly
    if (!state.v2SpeakersTab.length) {
      Promise.all([
        fetchJson('v2_speakers_tab.json', '/api/v2/leaderboard/speakers?tier=tab'),
        fetchJson('v2_speakers_general.json', '/api/v2/leaderboard/speakers?tier=general')
      ]).then(([tab, gen]) => {
        if (tab) state.v2SpeakersTab = tab;
        if (gen) state.v2SpeakersGeneral = gen;
        renderLeaderboard();
      });
    }
  }

  // ==========================================================================
  // 3. DEBATER BIO PAGE (V2 SPEC)
  // ==========================================================================
  function initBioPage() {
    const input = document.getElementById('bioSearchInput');
    const dropdown = document.getElementById('bioSuggestions');
    const clearBtn = document.getElementById('bioClearBtn');
    const container = document.getElementById('bioProfileContainer');

    let isDataLoading = (!state.v2SpeakersAll.length && !state.v2SpeakersGeneral.length && !state.v2SpeakersTab.length);

    function getSpeakersPool() {
      if (state.v2SpeakersAll && state.v2SpeakersAll.length) return state.v2SpeakersAll;
      if (state.v2SpeakersGeneral && state.v2SpeakersGeneral.length) return state.v2SpeakersGeneral;
      return state.v2SpeakersTab || [];
    }

    function renderMatches(q) {
      const query = (q || '').trim().toLowerCase();
      let dataset = getSpeakersPool();

      if (isDataLoading && dataset.length === 0) {
        dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255, 255, 255, 0.88); font-size: 13px; text-align: center; font-family: var(--font-mono);"><span style="display:inline-block; margin-right:6px;">●</span> Loading debater records...</div>`;
        dropdown.classList.remove('hidden');
        return;
      }

      let matches = dataset;
      if (query) {
        const startsWithName = [];
        const containsName = [];
        const containsInst = [];

        for (let i = 0; i < dataset.length; i++) {
          const d = dataset[i];
          const dName = (d.name || d.speaker_name || '').toLowerCase();
          const dInst = (d.institution || '').toLowerCase();
          if (dName.startsWith(query)) {
            startsWithName.push(d);
          } else if (dName.includes(query)) {
            containsName.push(d);
          } else if (dInst.includes(query)) {
            containsInst.push(d);
          }
        }
        matches = [...startsWithName, ...containsName, ...containsInst];
      }
      matches = matches.slice(0, 15);

      if (matches.length === 0) {
        dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255, 255, 255, 0.76); font-size: 13px; text-align: center;">No matching debaters found.</div>`;
        dropdown.classList.remove('hidden');
        return;
      }

      dropdown.innerHTML = matches.map((d) => `
        <div class="h2h-autocomplete-item" data-name="${escapeHtml(d.name || d.speaker_name)}">
          <div>
            <div class="h2h-auto-name">${escapeHtml(d.name || d.speaker_name)}</div>
            <div class="h2h-auto-inst">${escapeHtml(d.institution || 'Independent')}</div>
          </div>
          <div class="h2h-auto-meta">
            <span class="h2h-auto-stat">Avg: ${fmt(d.speaker_score, 2)} · ELO: ${fmt(d.elo || 1500, 0)}</span>
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

    const trackBioSearch = createSearchTracker('debater_bio_search');
    if (input && dropdown) {
      input.addEventListener('input', () => {
        if (clearBtn) clearBtn.classList.toggle('hidden', !input.value);
        renderMatches(input.value);
        trackBioSearch(input.value);
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
            <div style="text-align: center; padding: 48px 20px; color: rgba(255, 255, 255, 0.76); font-family: var(--font-mono);">
              Type any debater's name above to view their career record.
            </div>
          `;
        }
        if (window.history.replaceState) window.history.replaceState(null, '', window.location.pathname);
      });
    }

    // Load speakers dataset immediately (including v2_speakers_all.json for 100% coverage)
    if (!state.v2SpeakersAll.length) {
      Promise.all([
        fetchJson('v2_speakers_all.json', '/api/v2/leaderboard/speakers?tier=all'),
        fetchJson('v2_speakers_general.json', '/api/v2/leaderboard/speakers?tier=general'),
        fetchJson('v2_speakers_tab.json', '/api/v2/leaderboard/speakers?tier=tab')
      ]).then(([spkAll, spkGen, spkTab]) => {
        if (spkAll) state.v2SpeakersAll = spkAll;
        if (spkGen) state.v2SpeakersGeneral = spkGen;
        if (spkTab) state.v2SpeakersTab = spkTab;
        isDataLoading = false;
        if (input && input.value && document.activeElement === input) {
          renderMatches(input.value);
        }
      });
    } else {
      isDataLoading = false;
    }

    const urlParams = new URLSearchParams(window.location.search);
    const debaterParam = urlParams.get('debater') || urlParams.get('speaker') || urlParams.get('name') || urlParams.get('id');

    if (debaterParam) {
      loadDebaterBio(debaterParam);
    }

    async function loadDebaterBio(name) {
      if (!container) return;
      trackEvent('view_debater', { debater_name: name });
      container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.76);"><div class="spinner"></div> Loading Debater Bio for "${escapeHtml(name)}"...</div>`;

      let profile = null;
      if (!state.useGitHubRaw) {
        try {
          const res = await fetch(`${state.apiUrl}/api/v2/debaters/${encodeURIComponent(name)}/bio`, { signal: AbortSignal.timeout(2500) });
          if (res.ok) {
            profile = await res.json();
            state.isServerOnline = true;
          }
        } catch (e) {}
      }

      // If server profile not loaded or GitHub Raw mode is active, use enriched precomputed JSON
      if (!profile) {
        if (!state.v2SpeakersAll.length && !state.v2SpeakersGeneral.length && !state.v2SpeakersTab.length) {
          const [spkAll, spkGen, spkTab] = await Promise.all([
            fetchJson('v2_speakers_all.json', '/api/v2/leaderboard/speakers?tier=all'),
            fetchJson('v2_speakers_general.json', '/api/v2/leaderboard/speakers?tier=general'),
            fetchJson('v2_speakers_tab.json', '/api/v2/leaderboard/speakers?tier=tab')
          ]);
          if (spkAll) state.v2SpeakersAll = spkAll;
          if (spkGen) state.v2SpeakersGeneral = spkGen;
          if (spkTab) state.v2SpeakersTab = spkTab;
        }

        const pool = getSpeakersPool();
        const qLower = name.toLowerCase();
        const found = pool.find((d) => (d.name || d.speaker_name || '').toLowerCase() === qLower) ||
                      pool.find((d) => (d.name || d.speaker_name || '').toLowerCase().includes(qLower));
        if (found) {
          const dName = found.canonical_name || found.name || found.speaker_name || '';
          profile = {
            ...found,
            canonical_name: dName,
            national_level: found.national_level,
            latest_institution: found.latest_institution || found.institution,
            most_debated_team: found.most_debated_team || 'Circuit Team',
            speaker_avg: found.speaker_avg !== undefined ? found.speaker_avg : found.speaker_score,
            elo: found.elo || 1500,
            peak_elo: found.peak_elo || found.elo || 1500,
            win_percentage: found.win_percentage,
            stdev: found.stdev,
            prelims_debated: found.prelims_debated,
            tournaments_debated: found.tournaments_debated,
            position_averages: found.position_averages || {},
            tournament_breakdown: found.tournament_breakdown || [],
          };
        }
      }

      if (!profile) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.76);">Debater "${escapeHtml(name)}" not found in circuit records.</div>`;
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
            <div style="display: flex; gap: 18px; margin-top: 6px; flex-wrap: wrap; font-size: 13.5px;">
              <div>
                <span style="color: rgba(255, 255, 255, 0.85); font-size: 11.5px; letter-spacing: 0.04em; text-transform: uppercase;">Most Debated Team: </span>
                <a class="table-link" href="team_bio.html?team=${encodeURIComponent(profile.most_debated_team)}">${escapeHtml(profile.most_debated_team)}</a>
              </div>
              <div>
                <span style="color: rgba(255, 255, 255, 0.85); font-size: 11.5px; letter-spacing: 0.04em; text-transform: uppercase;">Latest School: </span>
                <a class="table-link-inst" href="institution_bio.html?inst=${encodeURIComponent(profile.latest_institution)}">${escapeHtml(profile.latest_institution)}</a>
              </div>
            </div>
          </div>
          <div>${getNatStatusTag(profile.national_level)}</div>
        </div>

        <!-- 1. First Box Stats Seen (6 Core Metrics incl. International Standard Debater Elo) -->
        <div class="bio-stats-grid">
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(profile.speaker_avg, 2)}</div>
            <div class="bio-stat-lbl">Speaker Avg</div>
            <div class="bio-stat-sub">Universal Substantive Mean</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(profile.elo || 1500, 1)}</div>
            <div class="bio-stat-lbl">Debater Elo</div>
            <div class="bio-stat-sub">Peak: ${fmt(profile.peak_elo || profile.elo || 1500, 1)}</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(profile.win_percentage, 1)}%</div>
            <div class="bio-stat-lbl">Win %</div>
            <div class="bio-stat-sub">Debates Contested</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(profile.stdev, 2)}</div>
            <div class="bio-stat-lbl">StDev</div>
            <div class="bio-stat-sub">Speech Score Deviation</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${profile.prelims_debated}</div>
            <div class="bio-stat-lbl">Prelims Debated</div>
            <div class="bio-stat-sub">Preliminary Speeches</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${profile.tournaments_debated}</div>
            <div class="bio-stat-lbl">Tournaments</div>
            <div class="bio-stat-sub">Events Debated</div>
          </div>
        </div>

        <!-- 2. Speaker Position Debated Graph -->
        <div class="bio-section-heading">
          01 // Speaker Position Breakdown
        </div>
        <div class="bio-stats-grid bio-positions-grid">
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="font-size: 22px;">${pos1}</div>
            <div class="bio-stat-lbl">1st Speaker Avg</div>
            ${count1 ? `<div class="bio-stat-sub">${count1}</div>` : ''}
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="font-size: 22px;">${pos2}</div>
            <div class="bio-stat-lbl">2nd Speaker Avg</div>
            ${count2 ? `<div class="bio-stat-sub">${count2}</div>` : ''}
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="font-size: 22px;">${pos3}</div>
            <div class="bio-stat-lbl">3rd Speaker Avg</div>
            ${count3 ? `<div class="bio-stat-sub">${count3}</div>` : ''}
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="font-size: 22px;">${posReply}</div>
            <div class="bio-stat-lbl">Reply Speaker Avg</div>
            ${countReply ? `<div class="bio-stat-sub">${countReply}</div>` : ''}
          </div>
        </div>

        <!-- 4. Tournament Breakdown with Interactive Hover Details -->
        <div class="bio-section-heading" style="margin-top: 28px;">
          02 // Tournament Breakdown (Hover Round Score for Details)
        </div>
        <div class="trajectory-list">
          ${tourBreakdown.length > 0 ? tourBreakdown.map((t) => `
            <div class="trajectory-card" style="display: flex; flex-direction: column; align-items: flex-start; gap: 10px;">
              <div style="display: flex; justify-content: space-between; width: 100%; align-items: center; flex-wrap: wrap;">
                <div class="t-info-title">${escapeHtml(t.tournament_name)}</div>
                <div style="font-size: 13px; color: rgba(255, 255, 255, 0.92); font-weight: 400;">
                  Event Avg: ${fmt(t.tournament_average, 2)} pts (${t.speeches_count} prelim speeches)
                </div>
              </div>
              <div class="score-pills">
                ${(t.rounds || []).map((r) => {
                  const isReply = r.speech_type === 'REPLY';
                  return `
                  <div class="round-hover-trigger">
                    <span class="score-pill ${isReply ? 'pill-reply' : ''}">
                      ${isReply ? 'Reply: ' : ''}${fmt(r.score, 1)}
                    </span>
                    <div class="round-tooltip">
                      <div class="tooltip-title">${escapeHtml(r.round_name || 'Round ' + r.round_number)}</div>
                      <div class="tooltip-row">
                        <span class="tooltip-label">Opponent</span>
                        <span>${escapeHtml(r.opponent)}</span>
                      </div>
                      <div class="tooltip-row">
                        <span class="tooltip-label">Score</span>
                        <span>${fmt(r.score, 1)}</span>
                      </div>
                      <div class="tooltip-row">
                        <span class="tooltip-label">Judge</span>
                        <span>${escapeHtml(r.adjudicator)}</span>
                      </div>
                      <div class="tooltip-row">
                        <span class="tooltip-label">Position</span>
                        <span>${escapeHtml(r.position)}</span>
                      </div>
                    </div>
                  </div>
                `;}).join('')}
              </div>
            </div>
          `).join('') : `<div style="color: rgba(255, 255, 255, 0.85); padding: 12px;">No tournament breakdown recorded.</div>`}
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

    let isDataLoading = (!state.v2TeamsAll.length && !state.v2TeamsGeneral.length && !state.v2TeamsTab.length);

    function getTeamsPool() {
      if (state.v2TeamsAll && state.v2TeamsAll.length) return state.v2TeamsAll;
      if (state.v2TeamsGeneral && state.v2TeamsGeneral.length) return state.v2TeamsGeneral;
      return state.v2TeamsTab || [];
    }

    function renderMatches(q) {
      const query = (q || '').trim().toLowerCase();
      let dataset = getTeamsPool();

      if (isDataLoading && dataset.length === 0) {
        dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255, 255, 255, 0.88); font-size: 13px; text-align: center; font-family: var(--font-mono);"><span style="display:inline-block; margin-right:6px;">●</span> Loading team records...</div>`;
        dropdown.classList.remove('hidden');
        return;
      }

      let matches = dataset;
      if (query) {
        const startsWithName = [];
        const containsName = [];
        const containsInst = [];

        for (let i = 0; i < dataset.length; i++) {
          const t = dataset[i];
          const tName = (t.team_name || '').toLowerCase();
          const tInst = (t.institution || '').toLowerCase();
          if (tName.startsWith(query)) {
            startsWithName.push(t);
          } else if (tName.includes(query)) {
            containsName.push(t);
          } else if (tInst.includes(query)) {
            containsInst.push(t);
          }
        }
        matches = [...startsWithName, ...containsName, ...containsInst];
      }
      matches = matches.slice(0, 15);

      if (matches.length === 0) {
        dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255, 255, 255, 0.76); font-size: 13px; text-align: center;">No matching teams found.</div>`;
        dropdown.classList.remove('hidden');
        return;
      }

      dropdown.innerHTML = matches.map((t) => `
        <div class="h2h-autocomplete-item" data-name="${escapeHtml(t.team_name)}">
          <div>
            <div class="h2h-auto-name">${escapeHtml(t.team_name)}</div>
            <div class="h2h-auto-inst">${escapeHtml(t.institution || 'Independent')}</div>
          </div>
          <div class="h2h-auto-meta">
            <span class="h2h-auto-stat">ATSS: ${fmt(t.atss, 2)} · ELO: ${fmt(t.elo || 1500, 0)}</span>
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

    const trackTeamSearch = createSearchTracker('team_bio_search');
    if (input && dropdown) {
      input.addEventListener('input', () => {
        if (clearBtn) clearBtn.classList.toggle('hidden', !input.value);
        renderMatches(input.value);
        trackTeamSearch(input.value);
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
            <div style="text-align: center; padding: 48px 20px; color: rgba(255, 255, 255, 0.76); font-family: var(--font-mono);">
              Type any team name above to inspect ATSS, lineups, break achievements, and tournament progressions.
            </div>
          `;
        }
        if (window.history.replaceState) window.history.replaceState(null, '', window.location.pathname);
      });
    }

    // Load teams dataset immediately (including v2_teams_all.json for 100% coverage)
    if (!state.v2TeamsAll.length) {
      Promise.all([
        fetchJson('v2_teams_all.json', '/api/v2/leaderboard/teams?tier=all'),
        fetchJson('v2_teams_general.json', '/api/v2/leaderboard/teams?tier=general'),
        fetchJson('v2_teams_tab.json', '/api/v2/leaderboard/teams?tier=tab')
      ]).then(([teamsAll, teamsGen, teamsTab]) => {
        if (teamsAll) state.v2TeamsAll = teamsAll;
        if (teamsGen) state.v2TeamsGeneral = teamsGen;
        if (teamsTab) state.v2TeamsTab = teamsTab;
        isDataLoading = false;
        if (input && input.value && document.activeElement === input) {
          renderMatches(input.value);
        }
      });
    } else {
      isDataLoading = false;
    }

    const urlParams = new URLSearchParams(window.location.search);
    const teamParam = urlParams.get('team') || urlParams.get('name');

    if (teamParam) {
      loadTeamBio(teamParam);
    }

    async function loadTeamBio(teamName) {
      if (!container) return;
      trackEvent('view_team', { team_name: teamName });
      container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.76);"><div class="spinner"></div> Loading Team Bio for "${escapeHtml(teamName)}"...</div>`;

      let bio = null;
      if (!state.useGitHubRaw) {
        try {
          const res = await fetch(`${state.apiUrl}/api/v2/teams/${encodeURIComponent(teamName)}/bio`, { signal: AbortSignal.timeout(2500) });
          if (res.ok) {
            bio = await res.json();
            state.isServerOnline = true;
          }
        } catch (e) {}
      }

      if (!bio) {
        if (!state.v2TeamsAll.length && !state.v2TeamsGeneral.length && !state.v2TeamsTab.length) {
          const [tAll, tGen, tTab] = await Promise.all([
            fetchJson('v2_teams_all.json', '/api/v2/leaderboard/teams?tier=all'),
            fetchJson('v2_teams_general.json', '/api/v2/leaderboard/teams?tier=general'),
            fetchJson('v2_teams_tab.json', '/api/v2/leaderboard/teams?tier=tab')
          ]);
          if (tAll) state.v2TeamsAll = tAll;
          if (tGen) state.v2TeamsGeneral = tGen;
          if (tTab) state.v2TeamsTab = tTab;
        }

        const pool = getTeamsPool();
        const qLower = teamName.trim().toLowerCase();
        const aliasNormalized = qLower
          .replace(/^dss\s+/, 'ds ')
          .replace(/^d\.?\s*s\.?\s*senanayake\s+/, 'ds ')
          .replace(/^royal\s+/, 'rc ')
          .replace(/^ladies'?\s+/, 'lc ')
          .replace(/^trinity\s+/, 'tck ')
          .replace(/^ananda\s+/, 'ac ')
          .replace(/^visakha\s+/, 'vv ');
        const found = pool.find((t) => (t.team_name || '').toLowerCase() === qLower) ||
                      pool.find((t) => (t.team_name || '').toLowerCase() === aliasNormalized) ||
                      pool.find((t) => (t.team_name || '').toLowerCase().includes(qLower)) ||
                      pool.find((t) => (t.team_name || '').toLowerCase().includes(aliasNormalized));
        if (found) {
          bio = {
            ...found,
            team_name: found.team_name,
            institution: found.institution,
            atss: found.atss,
            elo: found.elo || 1500,
            peak_elo: found.peak_elo || found.elo || 1500,
            win_percentage: found.win_percentage,
            stdev: found.stdev || 0,
            prelims_debated: found.prelims_debated || found.total_debates,
            tournaments_debated: found.tournaments_debated,
            wins_per_tournament: found.wins_per_tournament !== undefined ? found.wins_per_tournament : found.awpt,
            top_break_achievements: found.top_break_achievements || [],
            top_win_lineups: found.top_win_lineups || [],
            top_atss_lineups: found.top_atss_lineups || [],
            tournament_breakdown: found.tournament_breakdown || [],
          };
        }
      }

      if (!bio) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.76);">Team "${escapeHtml(teamName)}" not found in circuit records.</div>`;
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
            <div style="font-size: 14px; margin-top: 6px; color: rgba(255, 255, 255, 0.78);">
              <span style="color: rgba(255, 255, 255, 0.65); font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; margin-right: 4px;">Representing</span>
              <a class="table-link-inst" href="institution_bio.html?inst=${encodeURIComponent(bio.institution)}">${escapeHtml(bio.institution)}</a>
            </div>
          </div>
          <div>
            <span class="badge-count">Team Tab Eligible</span>
          </div>
        </div>

        <!-- 1. First Box Seen (6 Metrics incl. International Standard Team Elo) -->
        <div class="bio-stats-grid">
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(bio.atss, 2)}</div>
            <div class="bio-stat-lbl">ATSS</div>
            <div class="bio-stat-sub">Avg Total Speaker Score</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(bio.elo || 1500, 1)}</div>
            <div class="bio-stat-lbl">Team Elo</div>
            <div class="bio-stat-sub">Peak: ${fmt(bio.peak_elo || bio.elo || 1500, 1)}</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(bio.win_percentage, 1)}%</div>
            <div class="bio-stat-lbl">Win %</div>
            <div class="bio-stat-sub">Total Debates Won</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(bio.stdev, 2)}</div>
            <div class="bio-stat-lbl">Stdev</div>
            <div class="bio-stat-sub">Match Score Deviation</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${bio.prelims_debated} <span style="font-size: 16px; color: rgba(255, 255, 255, 0.74);">/ ${bio.tournaments_debated}</span></div>
            <div class="bio-stat-lbl">Prelims & Tournaments</div>
            <div class="bio-stat-sub">Prelim Matches / Tourneys</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(bio.wins_per_tournament, 2)}</div>
            <div class="bio-stat-lbl">Wins Per Tournament</div>
            <div class="bio-stat-sub">Avg Wins / Tournament</div>
          </div>
        </div>

        <!-- 2. Top 5 Break Achievements -->
        <div class="bio-section-heading">
          Top 5 Break Achievements
        </div>
        <div class="achievement-list">
          ${achievements.length > 0 ? achievements.map((a) => `
            <div class="achievement-card">
              <div>
                <strong style="color: #ffffff; font-weight: 400;">${escapeHtml(a.tournament_name)}</strong>
                <div style="font-size: 11.5px; color: rgba(255, 255, 255, 0.72); margin-top: 2px;">
                  Tournament ATSS: ${fmt(a.tournament_atss !== undefined ? a.tournament_atss : a.atss, 2)}
                </div>
              </div>
              <div>${getBreakBadge(a.highest_break || a.highest_stage)}</div>
            </div>
          `).join('') : `<div style="color: rgba(255, 255, 255, 0.72); padding: 14px; font-weight: 300;">No elimination break stages recorded.</div>`}
        </div>

        <!-- 3. Lineup Analytics (Top 5 Win % & Top 5 ATSS 3-Debater Combinations) -->
        <div class="bio-section-heading" style="margin-top: 28px;">
          Lineup Analytics (Optimal 3-Speaker Combinations)
        </div>
        <div class="lineups-grid">
          <!-- Top 5 Win % Lineups -->
          <div class="roster-box">
            <div class="roster-box-header">
              <span>Top 5 Win % Lineups</span>
              <span>Win Rate</span>
            </div>
            <div class="roster-list">
              ${(bio.top_win_lineups || []).length > 0 ? (bio.top_win_lineups || []).map((l, idx) => `
                <div class="lineup-card">
                  <div class="lineup-names">
                    <span style="color: rgba(255, 255, 255, 0.68); margin-right: 6px;">${String(idx + 1).padStart(2, '0')}</span>
                    ${l.lineup.map(n => `<a class="table-link" href="bio.html?debater=${encodeURIComponent(n)}">${escapeHtml(n)}</a>`).join(' · ')}
                    <div style="font-size: 11px; color: rgba(255, 255, 255, 0.68); margin-top: 3px;">
                      ${l.debates_count} debates together
                    </div>
                  </div>
                  <div class="lineup-stat">${fmt(l.win_percentage, 1)}%</div>
                </div>
              `).join('') : `<div style="color: rgba(255, 255, 255, 0.72); padding: 14px; font-weight: 300;">No 3-person lineups on record.</div>`}
            </div>
          </div>

          <!-- Top 5 ATSS Lineups -->
          <div class="roster-box">
            <div class="roster-box-header">
              <span>Top 5 Highest ATSS Lineups</span>
              <span>Lineup ATSS</span>
            </div>
            <div class="roster-list">
              ${(bio.top_atss_lineups || []).length > 0 ? (bio.top_atss_lineups || []).map((l, idx) => `
                <div class="lineup-card">
                  <div class="lineup-names">
                    <span style="color: rgba(255, 255, 255, 0.68); margin-right: 6px;">${String(idx + 1).padStart(2, '0')}</span>
                    ${l.lineup.map(n => `<a class="table-link" href="bio.html?debater=${encodeURIComponent(n)}">${escapeHtml(n)}</a>`).join(' · ')}
                    <div style="font-size: 11px; color: rgba(255, 255, 255, 0.68); margin-top: 3px;">
                      ${l.debates_count} debates together
                    </div>
                  </div>
                  <div class="lineup-stat">${fmt(l.atss, 2)}</div>
                </div>
              `).join('') : `<div style="color: rgba(255, 255, 255, 0.72); padding: 14px; font-weight: 300;">No 3-person lineups on record.</div>`}
            </div>
          </div>
        </div>

        <!-- 4. Tournament Breakdown -->
        <div class="bio-section-heading" style="margin-top: 28px;">
          Tournament Breakdown & Progression
        </div>
        <div class="trajectory-list">
          ${tourBreakdown.length > 0 ? tourBreakdown.map((t) => `
            <div class="trajectory-card" style="display: flex; flex-direction: column; align-items: flex-start; gap: 10px;">
              <div style="display: flex; justify-content: space-between; width: 100%; align-items: center; flex-wrap: wrap;">
                <div>
                  <strong style="color: #ffffff; font-size: 14px; font-weight: 400;">${escapeHtml(t.tournament_name)}</strong>
                  <span style="margin-left: 8px;">${getBreakBadge(t.highest_break || t.highest_stage)}</span>
                </div>
                <div style="font-size: 12.5px; color: rgba(255, 255, 255, 0.85); font-weight: 400;">
                  Event ATSS: ${fmt(t.tournament_atss !== undefined ? t.tournament_atss : t.atss, 2)} pts (${t.debates_count || (t.debates || t.rounds || []).length} debates)
                </div>
              </div>
              <div class="score-pills">
                ${(t.debates || t.rounds || []).map((d) => {
                  const isWon = d.won !== undefined ? Boolean(d.won) : (d.result === 'Win' || d.result === 'WIN');
                  return `
                    <div class="round-hover-trigger">
                      <span class="score-pill ${isWon ? 'win-pill' : 'loss-pill'}">
                        ${isWon ? 'WIN' : 'LOSS'} · ${fmt(d.team_score, 1)}
                      </span>
                      <div class="round-tooltip">
                        <div class="tooltip-title">${escapeHtml(d.round_name)}</div>
                        <div class="tooltip-row">
                          <span class="tooltip-label">Opponent</span>
                          <span style="font-weight: 400; color: #ffffff;">${escapeHtml(d.opponent)}</span>
                        </div>
                        <div class="tooltip-row">
                          <span class="tooltip-label">Score</span>
                          <span style="font-weight: 400; color: #ffffff;">${fmt(d.team_score, 1)}</span>
                        </div>
                        <div class="tooltip-row">
                          <span class="tooltip-label">Side</span>
                          <span>${escapeHtml(d.side)}</span>
                        </div>
                      </div>
                    </div>
                  `;
                }).join('')}
              </div>
            </div>
          `).join('') : `<div style="color: rgba(255, 255, 255, 0.72); padding: 14px; font-weight: 300;">No tournament breakdown recorded.</div>`}
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

    let isDataLoading = (!state.v2InstitutionsAll.length && !state.v2InstitutionsGeneral.length && !state.v2InstitutionsTab.length);

    function getInstitutionsPool() {
      if (state.v2InstitutionsAll && state.v2InstitutionsAll.length) return state.v2InstitutionsAll;
      if (state.v2InstitutionsGeneral && state.v2InstitutionsGeneral.length) return state.v2InstitutionsGeneral;
      return state.v2InstitutionsTab || [];
    }

    function renderMatches(q) {
      const query = (q || '').trim().toLowerCase();
      let dataset = getInstitutionsPool();

      if (isDataLoading && dataset.length === 0) {
        dropdown.innerHTML = `<div style="padding: 14px; color: rgba(255, 255, 255, 0.85); font-size: 13px; text-align: center;">Loading institution records...</div>`;
        dropdown.classList.remove('hidden');
        return;
      }

      let matches = dataset;
      if (query) {
        const startsWithName = [];
        const containsName = [];
        const containsCode = [];

        for (let i = 0; i < dataset.length; i++) {
          const inst = dataset[i];
          const iName = (inst.institution_name || '').toLowerCase();
          const iCode = (inst.code || '').toLowerCase();
          if (iName.startsWith(query)) {
            startsWithName.push(inst);
          } else if (iName.includes(query)) {
            containsName.push(inst);
          } else if (iCode.includes(query)) {
            containsCode.push(inst);
          }
        }
        matches = [...startsWithName, ...containsName, ...containsCode];
      }
      matches = matches.slice(0, 15);

      if (matches.length === 0) {
        dropdown.innerHTML = `<div style="padding: 14px; color: rgba(255, 255, 255, 0.76); font-size: 13px; text-align: center;">No matching institutions found.</div>`;
        dropdown.classList.remove('hidden');
        return;
      }

      dropdown.innerHTML = matches.map((i) => `
        <div class="h2h-autocomplete-item" data-name="${escapeHtml(i.institution_name)}">
          <div>
            <div class="h2h-auto-name">${escapeHtml(i.institution_name)}</div>
            <div class="h2h-auto-inst">${i.code ? `${escapeHtml(i.code)} · ` : ''}Delta: ${fmt(i.delta, 2)}</div>
          </div>
          <div class="h2h-auto-meta">
            <span class="h2h-auto-stat">A: ${fmt(i.a_atss, 2)} · Elo: ${fmt(i.elo || 1500, 0)}</span>
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

    const trackInstSearch = createSearchTracker('institution_bio_search');
    if (input && dropdown) {
      input.addEventListener('input', () => {
        if (clearBtn) clearBtn.classList.toggle('hidden', !input.value);
        renderMatches(input.value);
        trackInstSearch(input.value);
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
            <div style="text-align: center; padding: 48px 20px; color: rgba(255, 255, 255, 0.78); font-weight: 300;">
              Type any institution name above to inspect Delta, A/B team ATSS, roster, and veteran vs new debater pool.
            </div>
          `;
        }
        if (window.history.replaceState) window.history.replaceState(null, '', window.location.pathname);
      });
    }

    // Load institutions dataset immediately (including v2_institutions_all.json for 100% coverage)
    if (!state.v2InstitutionsAll.length) {
      Promise.all([
        fetchJson('v2_institutions_all.json', '/api/v2/leaderboard/institutions?tier=all'),
        fetchJson('v2_institutions_general.json', '/api/v2/leaderboard/institutions?tier=general'),
        fetchJson('v2_institutions_tab.json', '/api/v2/leaderboard/institutions?tier=tab')
      ]).then(([instAll, instGen, instTab]) => {
        if (instAll) state.v2InstitutionsAll = instAll;
        if (instGen) state.v2InstitutionsGeneral = instGen;
        if (instTab) state.v2InstitutionsTab = instTab;
        isDataLoading = false;
        if (input && input.value && document.activeElement === input) {
          renderMatches(input.value);
        }
      });
    } else {
      isDataLoading = false;
    }

    const urlParams = new URLSearchParams(window.location.search);
    const instParam = urlParams.get('inst') || urlParams.get('name');

    if (instParam) {
      loadInstitutionBio(instParam);
    }

    async function loadInstitutionBio(instName) {
      if (!container) return;
      trackEvent('view_institution', { institution_name: instName });
      container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.78); font-weight: 300;"><div class="spinner"></div> Loading Institution Bio for "${escapeHtml(instName)}"...</div>`;

      let bio = null;
      if (!state.useGitHubRaw) {
        try {
          const res = await fetch(`${state.apiUrl}/api/v2/institutions/${encodeURIComponent(instName)}/bio`, { signal: AbortSignal.timeout(2500) });
          if (res.ok) {
            bio = await res.json();
            state.isServerOnline = true;
          }
        } catch (e) {}
      }

      if (!bio) {
        if (!state.v2InstitutionsAll.length && !state.v2InstitutionsGeneral.length && !state.v2InstitutionsTab.length) {
          const [iAll, iGen, iTab] = await Promise.all([
            fetchJson('v2_institutions_all.json', '/api/v2/leaderboard/institutions?tier=all'),
            fetchJson('v2_institutions_general.json', '/api/v2/leaderboard/institutions?tier=general'),
            fetchJson('v2_institutions_tab.json', '/api/v2/leaderboard/institutions?tier=tab')
          ]);
          if (iAll) state.v2InstitutionsAll = iAll;
          if (iGen) state.v2InstitutionsGeneral = iGen;
          if (iTab) state.v2InstitutionsTab = iTab;
        }

        const pool = getInstitutionsPool();
        const qLower = instName.toLowerCase();
        const found = pool.find((i) => (i.institution_name || '').toLowerCase() === qLower || (i.code || '').toLowerCase() === qLower) ||
                      pool.find((i) => (i.institution_name || '').toLowerCase().includes(qLower));
        if (found) {
          bio = {
            ...found,
            institution_name: found.institution_name,
            code: found.code,
            delta: found.delta,
            a_team_name: found.a_team_name,
            a_atss: found.a_atss,
            b_team_name: found.b_team_name,
            b_atss: found.b_atss,
            win_percentage: found.win_percentage,
            elo: found.elo || 1500.0,
            peak_elo: found.peak_elo || found.elo || 1500.0,
            teams_list: found.teams_list || [],
            pool_count: found.pool_count || 0,
            veterans: found.veterans || [],
            new_debaters: found.new_debaters || [],
          };
        }
      }

      if (!bio) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.78); font-weight: 300;">Institution "${escapeHtml(instName)}" not found in circuit records.</div>`;
        return;
      }

      if (window.history.replaceState) {
        window.history.replaceState(null, '', `${window.location.pathname}?inst=${encodeURIComponent(bio.institution_name)}`);
      }
      if (input) input.value = bio.institution_name;
      if (clearBtn) clearBtn.classList.remove('hidden');

      const teamsFielded = bio.teams_list || [];

      container.innerHTML = `
        <!-- Institution Header Card -->
        <div class="bio-profile-header">
          <div class="bio-name-group">
            <h2 class="bio-name">${escapeHtml(bio.institution_name)}</h2>
            <div style="font-size: 13px; color: rgba(255, 255, 255, 0.75); margin-top: 6px; letter-spacing: 0.04em;">
              ${bio.code ? `Code: ${escapeHtml(bio.code)} · ` : ''}Total Debaters Fielded: ${bio.pool_count}
            </div>
          </div>
          <div>
            <span class="badge-count">Institution Tab</span>
          </div>
        </div>

        <!-- 1. First Box Seen (6 Metrics) -->
        <div class="bio-stats-grid">
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(bio.delta, 2)}</div>
            <div class="bio-stat-lbl">Delta</div>
            <div class="bio-stat-sub">(0.8×A + 1.2×B) / 2</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(bio.elo || 1500, 1)}</div>
            <div class="bio-stat-lbl">Institution Elo</div>
            <div class="bio-stat-sub">Peak: ${fmt(bio.peak_elo || bio.elo || 1500, 1)}</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${teamsFielded.length}</div>
            <div class="bio-stat-lbl">Teams Fielded</div>
            <div class="bio-stat-sub">Active Circuit Rosters</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="font-size: 20px;">
              A: ${fmt(bio.a_atss, 1)}<br />
              <span style="color: rgba(255, 255, 255, 0.76);">B: ${bio.b_atss ? fmt(bio.b_atss, 1) : '—'}</span>
            </div>
            <div class="bio-stat-lbl">A & B Team ATSS</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${fmt(bio.win_percentage, 1)}%</div>
            <div class="bio-stat-lbl">Win Rate</div>
            <div class="bio-stat-sub">All Debates Contested</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${bio.pool_count}</div>
            <div class="bio-stat-lbl">Debater Pool</div>
            <div class="bio-stat-sub">Eligible Debaters Fielded</div>
          </div>
        </div>

        <!-- Representing Teams List -->
        <div class="bio-section-heading">
          Teams Representing ${escapeHtml(bio.institution_name)}
        </div>
        <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px;">
          ${teamsFielded.length > 0 ? teamsFielded.map(t => `
            <a class="opt-btn" href="team_bio.html?team=${encodeURIComponent(t)}">
              ${escapeHtml(t)}
            </a>
          `).join('') : '<div style="color: rgba(255, 255, 255, 0.72); font-weight: 300;">No teams recorded.</div>'}
        </div>

        <!-- 2. Debater Pool Graph: Veterans (>= 2 tourneys) vs New Debaters (1 tourney) -->
        <div class="bio-section-heading">
          Debater Pool: Veterans (≥ 2 Tournaments) vs New Debaters (1 Tournament)
        </div>
        <div class="roster-split-grid">
          <!-- Veterans Column -->
          <div class="roster-box">
            <div class="roster-box-header">
              <span>Veteran Debaters (${bio.veterans ? bio.veterans.length : 0})</span>
              <span>Tournaments</span>
            </div>
            <div class="roster-list">
              ${(bio.veterans || []).length > 0 ? (bio.veterans || []).map((v) => `
                <div class="pool-debater-card">
                  <div>
                    <a class="pool-debater-name" href="bio.html?debater=${encodeURIComponent(v.name)}">${escapeHtml(v.name)}</a>
                    <div style="font-size: 11px; color: rgba(255, 255, 255, 0.68); margin-top: 2px;">
                      ${v.prelims} prelims debated
                    </div>
                  </div>
                  <div style="font-size: 12.5px; font-weight: 400; color: rgba(255, 255, 255, 0.88);">
                    ${v.tournaments} Tourneys
                  </div>
                </div>
              `).join('') : `<div style="color: rgba(255, 255, 255, 0.72); padding: 14px; font-weight: 300;">No veteran debaters recorded.</div>`}
            </div>
          </div>

          <!-- New Debaters Column -->
          <div class="roster-box">
            <div class="roster-box-header">
              <span>New Debaters (${bio.new_debaters ? bio.new_debaters.length : 0})</span>
              <span>Prelims</span>
            </div>
            <div class="roster-list">
              ${(bio.new_debaters || []).length > 0 ? (bio.new_debaters || []).map((n) => `
                <div class="pool-debater-card">
                  <div>
                    <a class="pool-debater-name" href="bio.html?debater=${encodeURIComponent(n.name)}">${escapeHtml(n.name)}</a>
                    <div style="font-size: 11px; color: rgba(255, 255, 255, 0.68); margin-top: 2px;">
                      1 tournament debated
                    </div>
                  </div>
                  <div style="font-size: 12.5px; font-weight: 400; color: rgba(255, 255, 255, 0.88);">
                    ${n.prelims} Prelims
                  </div>
                </div>
              `).join('') : `<div style="color: rgba(255, 255, 255, 0.72); padding: 14px; font-weight: 300;">No new debaters recorded.</div>`}
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

    let isDataLoading = (!state.v2AdjudicatorsAll.length && (!state.v2Adjudicators || !state.v2Adjudicators.length));

    function getAdjudicatorsPool() {
      if (state.v2AdjudicatorsAll && state.v2AdjudicatorsAll.length) return state.v2AdjudicatorsAll;
      return state.v2Adjudicators || [];
    }

    function renderMatches(q) {
      const query = (q || '').trim().toLowerCase();
      let dataset = getAdjudicatorsPool();

      if (isDataLoading && dataset.length === 0) {
        dropdown.innerHTML = `<div style="padding: 14px; color: rgba(255, 255, 255, 0.85); font-size: 13px; text-align: center;">Loading adjudicator records...</div>`;
        dropdown.classList.remove('hidden');
        return;
      }

      let matches = dataset;
      if (query) {
        const startsWithName = [];
        const containsName = [];
        const containsInst = [];

        for (let i = 0; i < dataset.length; i++) {
          const j = dataset[i];
          const jName = (j.adjudicator_name || '').toLowerCase();
          const jInst = (j.institution || '').toLowerCase();
          if (jName.startsWith(query)) {
            startsWithName.push(j);
          } else if (jName.includes(query)) {
            containsName.push(j);
          } else if (jInst.includes(query)) {
            containsInst.push(j);
          }
        }
        matches = [...startsWithName, ...containsName, ...containsInst];
      }
      matches = matches.slice(0, 15);

      if (matches.length === 0) {
        dropdown.innerHTML = `<div style="padding: 14px; color: rgba(255, 255, 255, 0.76); font-size: 13px; text-align: center;">No matching adjudicators found.</div>`;
        dropdown.classList.remove('hidden');
        return;
      }

      dropdown.innerHTML = matches.map((j) => `
        <div class="h2h-autocomplete-item" data-name="${escapeHtml(j.adjudicator_name)}">
          <div>
            <div class="h2h-auto-name">${escapeHtml(j.adjudicator_name)}</div>
            <div class="h2h-auto-inst">${escapeHtml(j.institution || 'Independent')}</div>
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

    const trackAdjSearch = createSearchTracker('adjudicator_bio_search');
    if (input && dropdown) {
      input.addEventListener('input', () => {
        if (clearBtn) clearBtn.classList.toggle('hidden', !input.value);
        renderMatches(input.value);
        trackAdjSearch(input.value);
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
            <div style="text-align: center; padding: 48px 20px; color: rgba(255, 255, 255, 0.78); font-weight: 300;">
              Type any adjudicator's name above to inspect AASS, AATSS, Prop/Opp bias, and judging history.
            </div>
          `;
        }
        if (window.history.replaceState) window.history.replaceState(null, '', window.location.pathname);
      });
    }

    // Load adjudicators dataset immediately (including v2_adjudicators_all.json for 100% coverage)
    if (!state.v2AdjudicatorsAll.length) {
      Promise.all([
        fetchJson('v2_adjudicators_all.json', '/api/v2/leaderboard/adjudicators?min_prelims=1'),
        fetchJson('v2_adjudicators.json', '/api/v2/leaderboard/adjudicators')
      ]).then(([judgesAll, judges]) => {
        if (judgesAll) state.v2AdjudicatorsAll = judgesAll;
        if (judges) state.v2Adjudicators = judges;
        isDataLoading = false;
        if (input && input.value && document.activeElement === input) {
          renderMatches(input.value);
        }
      });
    } else {
      isDataLoading = false;
    }

    const urlParams = new URLSearchParams(window.location.search);
    const judgeParam = urlParams.get('judge') || urlParams.get('name');

    if (judgeParam) {
      loadAdjudicatorBio(judgeParam);
    }

    async function loadAdjudicatorBio(judgeName) {
      if (!container) return;
      trackEvent('view_adjudicator', { adjudicator_name: judgeName });
      container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.78); font-weight: 300;"><div class="spinner"></div> Loading Adjudicator Bio for "${escapeHtml(judgeName)}"...</div>`;

      let bio = null;
      if (!state.useGitHubRaw) {
        try {
          const res = await fetch(`${state.apiUrl}/api/v2/adjudicators/${encodeURIComponent(judgeName)}/bio`, { signal: AbortSignal.timeout(2500) });
          if (res.ok) {
            bio = await res.json();
            state.isServerOnline = true;
          }
        } catch (e) {}
      }

      if (!bio) {
        if (!state.v2AdjudicatorsAll.length && !state.v2Adjudicators.length) {
          const [judgesAll, judges] = await Promise.all([
            fetchJson('v2_adjudicators_all.json', '/api/v2/leaderboard/adjudicators?min_prelims=1'),
            fetchJson('v2_adjudicators.json', '/api/v2/leaderboard/adjudicators')
          ]);
          if (judgesAll) state.v2AdjudicatorsAll = judgesAll;
          if (judges) state.v2Adjudicators = judges;
        }
        const pool = getAdjudicatorsPool();
        const qLower = judgeName.toLowerCase();
        const found = pool.find((j) => (j.adjudicator_name || '').toLowerCase() === qLower) ||
                      pool.find((j) => (j.adjudicator_name || '').toLowerCase().includes(qLower));
        if (found) bio = found;
      }

      if (!bio) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.78); font-weight: 300;">Adjudicator "${escapeHtml(judgeName)}" not found in circuit records.</div>`;
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
            <div style="font-size: 14px; color: rgba(255, 255, 255, 0.78); margin-top: 6px;">
              ${escapeHtml(bio.institution || 'Independent Adjudicator')}
            </div>
          </div>
          <div>
            <span class="badge-count">Adjudicator</span>
          </div>
        </div>

        <!-- 1. Key Metrics Grid (6 Metrics) -->
        <div class="bio-stats-grid">
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${bio.aass ? fmt(bio.aass, 2) : '—'}</div>
            <div class="bio-stat-lbl">AASS (Substantive Mean)</div>
            <div class="bio-stat-sub">Awarded Speaker Avg</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${bio.aatss ? fmt(bio.aatss, 2) : '—'}</div>
            <div class="bio-stat-lbl">AATSS (Team Avg)</div>
            <div class="bio-stat-sub">Awarded Team Avg</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val" style="font-size: 20px;">${propPctStr}% P / ${oppPctStr}% O</div>
            <div class="bio-stat-lbl">Prop / Opp Win Bias</div>
            <div class="bio-stat-sub">Decision Split</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${bio.prelims_adjudicated || 0}</div>
            <div class="bio-stat-lbl">Prelims Adjudicated</div>
            <div class="bio-stat-sub">Preliminary Rounds</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${bio.outrounds_adjudicated || 0}</div>
            <div class="bio-stat-lbl">Knockouts Adjudicated</div>
            <div class="bio-stat-sub">Elimination Panels</div>
          </div>
          <div class="bio-stat-tile">
            <div class="bio-stat-val">${bio.tournaments_adjudicated || 0}</div>
            <div class="bio-stat-lbl">Tournaments Adjudicated</div>
            <div class="bio-stat-sub">Tournaments</div>
          </div>
        </div>

        <!-- Prop vs Opp Decision Bias Visual Bar -->
        <div class="bio-section-heading">
          Ballot Decision Split
        </div>
        <div class="roster-box" style="margin-bottom: 24px;">
          <div class="bias-container">
            <div class="bias-labels">
              <span style="color: #ffffff; font-weight: 400;">Proposition: ${propPctStr}% (${bio.prop_wins || 0} wins)</span>
              <span style="color: rgba(255, 255, 255, 0.82); font-weight: 400;">Opposition: ${oppPctStr}% (${bio.opp_wins || 0} wins)</span>
            </div>
            <div class="bias-bar-wrap">
              <div class="bias-bar-prop" style="width: ${propPct}%;"></div>
              <div class="bias-bar-opp" style="width: ${oppPct}%;"></div>
            </div>
          </div>
        </div>

        <!-- 2. Detailed Judging History Table -->
        <div class="bio-section-heading">
          Judging History (${(bio.judging_history && bio.judging_history.length) || (bio.prelims_adjudicated + (bio.outrounds_adjudicated || 0))} Debates)
        </div>
        ${bio.judging_history && bio.judging_history.length > 0 ? `
          <div class="data-table-wrap" style="margin-bottom: 32px;">
            <table class="atomos-table">
              <thead>
                <tr>
                  <th style="width: 24%;">Tournament</th>
                  <th style="width: 14%;">Round</th>
                  <th style="width: 32%;">Contested Matchup</th>
                  <th style="width: 14%;">Decision</th>
                  <th style="width: 16%;">Panel / Role</th>
                </tr>
              </thead>
              <tbody>
                ${bio.judging_history.map((h) => {
                  const isKnockout = h.round_type === 'ELIMINATION';
                  const roundBadge = isKnockout
                    ? `<span class="break-pill break-champion">${escapeHtml(h.round_name)}</span>`
                    : `<span class="break-pill break-prelim">${escapeHtml(h.round_name)}</span>`;

                  const marginText = h.win_margin ? ` (${fmt(h.win_margin, 1)} pts)` : '';

                  const panelText = h.is_panel && h.panel_members && h.panel_members.length > 0
                    ? `<div style="font-size: 12px; color: rgba(255, 255, 255, 0.88);"><span style="color: rgba(255, 255, 255, 0.65); font-size: 10.5px; letter-spacing: 0.06em; text-transform: uppercase;">Panel:</span> ${h.panel_members.map(m => escapeHtml(m)).join(', ')}</div>`
                    : `<span style="font-size: 12px; color: rgba(255, 255, 255, 0.74);">Solo Chair</span>`;

                  return `
                    <tr>
                      <td style="color: #ffffff;">
                        <div>${escapeHtml(h.tournament_name)}</div>
                        <div style="font-size: 11px; color: rgba(255, 255, 255, 0.65);">${escapeHtml(h.tournament_dates || '')}</div>
                      </td>
                      <td>${roundBadge}</td>
                      <td>
                        <div style="display: flex; align-items: center; gap: 6px; font-size: 13px; flex-wrap: wrap;">
                          <a class="table-link" href="team_bio.html?team=${encodeURIComponent(h.prop_team)}">${escapeHtml(h.prop_team)}</a>
                          <span style="font-size: 11px; color: rgba(255, 255, 255, 0.65);">(Prop)</span>
                          <span style="color: rgba(255, 255, 255, 0.65);">vs</span>
                          <a class="table-link" href="team_bio.html?team=${encodeURIComponent(h.opp_team)}">${escapeHtml(h.opp_team)}</a>
                          <span style="font-size: 11px; color: rgba(255, 255, 255, 0.65);">(Opp)</span>
                        </div>
                      </td>
                      <td style="font-size: 12.5px; color: #ffffff;">
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
          <div class="roster-box" style="text-align: center; padding: 24px; color: rgba(255, 255, 255, 0.75); font-size: 13px; font-weight: 300; margin-bottom: 24px;">
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

    let isDataLoading = (!state.v2SpeakersAll.length && !state.v2SpeakersGeneral.length && !state.v2SpeakersTab.length);

    function getSpeakersPool() {
      if (state.v2SpeakersAll && state.v2SpeakersAll.length) return state.v2SpeakersAll;
      if (state.v2SpeakersGeneral && state.v2SpeakersGeneral.length) return state.v2SpeakersGeneral;
      return state.v2SpeakersTab || [];
    }

    function setupH2HSearch(side, input, dropdown, clearBtn, badge) {
      if (!input || !dropdown) return;

      function renderMatches(q) {
        const query = (q || '').trim().toLowerCase();
        let dataset = getSpeakersPool();

        if (isDataLoading && dataset.length === 0) {
          dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255, 255, 255, 0.88); font-size: 13px; text-align: center; font-family: var(--font-mono);"><span style="display:inline-block; margin-right:6px;">●</span> Loading debater records...</div>`;
          dropdown.classList.remove('hidden');
          return;
        }

        let matches = dataset;
        if (query) {
          const startsWithName = [];
          const containsName = [];
          const containsInst = [];

          for (let i = 0; i < dataset.length; i++) {
            const d = dataset[i];
            const dName = (d.name || d.speaker_name || '').toLowerCase();
            const dInst = (d.institution || '').toLowerCase();
            if (dName.startsWith(query)) {
              startsWithName.push(d);
            } else if (dName.includes(query)) {
              containsName.push(d);
            } else if (dInst.includes(query)) {
              containsInst.push(d);
            }
          }
          matches = [...startsWithName, ...containsName, ...containsInst];
        }
        matches = matches.slice(0, 15);

        if (matches.length === 0) {
          dropdown.innerHTML = `<div style="padding: 12px; color: rgba(255, 255, 255, 0.76); font-size: 13px; text-align: center;">No matching debaters found.</div>`;
          dropdown.classList.remove('hidden');
          return;
        }

        dropdown.innerHTML = matches.map((d) => `
          <div class="h2h-autocomplete-item" data-name="${escapeHtml(d.name || d.speaker_name)}">
            <div>
              <div class="h2h-auto-name">${escapeHtml(d.name || d.speaker_name)}</div>
              <div class="h2h-auto-inst">${escapeHtml(d.institution || 'Independent')}</div>
            </div>
            <div class="h2h-auto-meta">
              <span class="h2h-auto-stat">Avg: ${fmt(d.speaker_score, 2)} · ELO: ${fmt(d.elo || 1500, 0)}</span>
            </div>
          </div>
        `).join('');

        dropdown.classList.remove('hidden');

        dropdown.querySelectorAll('.h2h-autocomplete-item').forEach((el) => {
          el.addEventListener('mousedown', (e) => {
            e.preventDefault();
            const name = el.getAttribute('data-name');
            const match = matches.find((m) => (m.name || m.speaker_name) === name);
            if (side === 'A') selectedA = match;
            else selectedB = match;

            input.value = match.name || match.speaker_name;
            dropdown.classList.add('hidden');
            if (badge) {
              badge.textContent = match.institution || 'Independent';
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

    function applyUrlParams() {
      const urlParams = new URLSearchParams(window.location.search);
      const paramA = urlParams.get('a') || urlParams.get('contender1');
      const paramB = urlParams.get('b') || urlParams.get('contender2');
      const dataset = getSpeakersPool();

      if (paramA) {
        const matchA = dataset.find((s) => (s.name || s.speaker_name || '').toLowerCase() === paramA.toLowerCase()) ||
                       dataset.find((s) => (s.name || s.speaker_name || '').toLowerCase().includes(paramA.toLowerCase()));
        if (matchA) {
          selectedA = matchA;
          if (inputA) inputA.value = matchA.name || matchA.speaker_name;
          if (badgeA) { badgeA.textContent = matchA.institution || 'Independent'; badgeA.classList.remove('hidden'); }
          if (clearA) clearA.classList.remove('hidden');
        }
      }

      if (paramB) {
        const matchB = dataset.find((s) => (s.name || s.speaker_name || '').toLowerCase() === paramB.toLowerCase()) ||
                       dataset.find((s) => (s.name || s.speaker_name || '').toLowerCase().includes(paramB.toLowerCase()));
        if (matchB) {
          selectedB = matchB;
          if (inputB) inputB.value = matchB.name || matchB.speaker_name;
          if (badgeB) { badgeB.textContent = matchB.institution || 'Independent'; badgeB.classList.remove('hidden'); }
          if (clearB) clearB.classList.remove('hidden');
        }
      }

      if (selectedA || selectedB) {
        updateH2H();
      }
    }

    applyUrlParams();

    // Load speakers and H2H debate datasets immediately
    if (!state.v2SpeakersAll.length || !state.v2H2HDebates.length) {
      Promise.all([
        fetchJson('v2_speakers_all.json', '/api/v2/leaderboard/speakers?tier=all'),
        fetchJson('v2_speakers_general.json', '/api/v2/leaderboard/speakers?tier=general'),
        fetchJson('v2_speakers_tab.json', '/api/v2/leaderboard/speakers?tier=tab'),
        fetchJson('v2_h2h_debates.json', null)
      ]).then(([spkAll, spkGen, spkTab, h2hDebates]) => {
        if (spkAll) state.v2SpeakersAll = spkAll;
        if (spkGen) state.v2SpeakersGeneral = spkGen;
        if (spkTab) state.v2SpeakersTab = spkTab;
        if (h2hDebates) state.v2H2HDebates = h2hDebates;
        isDataLoading = false;
        applyUrlParams();
      });
    } else {
      isDataLoading = false;
    }

    async function updateH2H() {
      if (!container) return;

      if (!selectedA && !selectedB) {
        container.innerHTML = `
          <div class="h2h-empty-state" style="text-align: center; padding: 64px 20px; color: rgba(255, 255, 255, 0.78); font-family: var(--font-display);">
            <div style="font-family: var(--font-mono); font-size: 12px; color: rgba(255, 255, 255, 0.72); margin-bottom: 10px; font-weight: 400; letter-spacing: 0.1em; text-transform: uppercase;">07 // Direct Matchup Comparison</div>
            <div style="font-size: 14px; font-weight: 300; max-width: 560px; margin: 0 auto; line-height: 1.6; color: rgba(255, 255, 255, 0.85);">
              Select Contender 01 and Contender 02 above to compare Speaker Score, Elo Rating, Win %, Break Rank Avg (BRA), Prelims, Highest Achievement, and Direct Tournament Clashes.
            </div>
          </div>
        `;
        return;
      }

      const nameA = selectedA ? (selectedA.name || selectedA.speaker_name) : '';
      const nameB = selectedB ? (selectedB.name || selectedB.speaker_name) : '';

      if (selectedA && !selectedB) {
        container.innerHTML = `<div style="text-align: center; padding: 48px; color: rgba(255, 255, 255, 0.78); font-weight: 300;">Contender 01 (${escapeHtml(nameA)}) selected. Select Contender 02 above.</div>`;
        return;
      }

      if (!selectedA && selectedB) {
        container.innerHTML = `<div style="text-align: center; padding: 48px; color: rgba(255, 255, 255, 0.78); font-weight: 300;">Contender 02 (${escapeHtml(nameB)}) selected. Select Contender 01 above.</div>`;
        return;
      }

      if (nameA.toLowerCase() === nameB.toLowerCase()) {
        container.innerHTML = `<div style="text-align: center; padding: 48px; color: rgba(255, 255, 255, 0.78); font-weight: 300;">Please select two different debaters to compare.</div>`;
        return;
      }

      if (window.history.replaceState) {
        window.history.replaceState(null, '', `${window.location.pathname}?a=${encodeURIComponent(nameA)}&b=${encodeURIComponent(nameB)}`);
      }

      container.innerHTML = `<div style="text-align: center; padding: 40px; color: rgba(255, 255, 255, 0.78); font-weight: 300;"><div class="spinner"></div> Computing head-to-head clash...</div>`;
      trackEvent('view_h2h_matchup', {
        contender_a: nameA,
        contender_b: nameB,
      });

      // Fetch live direct clashes and BRA from server if available, or resolve from v2_h2h_debates.json
      let directDebates = [];
      let aDirectWins = 0;
      let bDirectWins = 0;
      let braA = selectedA.bra !== undefined ? selectedA.bra : null;
      let braB = selectedB.bra !== undefined ? selectedB.bra : null;
      let loadedFromServer = false;

      if (!state.useGitHubRaw) {
        try {
          const res = await fetch(`${state.apiUrl}/api/h2h?a=${encodeURIComponent(nameA)}&b=${encodeURIComponent(nameB)}&mode=debater`, { signal: AbortSignal.timeout(2500) });
          if (res.ok) {
            const j = await res.json();
            directDebates = j.direct_debates || [];
            aDirectWins = j.a_direct_wins || 0;
            bDirectWins = j.b_direct_wins || 0;
            if (j.a_bra !== undefined) braA = j.a_bra;
            if (j.b_bra !== undefined) braB = j.b_bra;
            state.isServerOnline = true;
            loadedFromServer = true;
          }
        } catch (e) {}
      }

      // Resolve direct clashes from precomputed/GitHub v2_h2h_debates.json when server isn't used
      if (!loadedFromServer) {
        if (!state.v2H2HDebates || !state.v2H2HDebates.length) {
          const h2hData = await fetchJson('v2_h2h_debates.json', null);
          if (h2hData) state.v2H2HDebates = h2hData;
        }
        const aLower = nameA.toLowerCase();
        const bLower = nameB.toLowerCase();
        for (const d of (state.v2H2HDebates || [])) {
          const propSpk = (d.prop_speakers || []).map((s) => ((typeof s === 'string' ? s : s.name) || '').toLowerCase());
          const oppSpk = (d.opp_speakers || []).map((s) => ((typeof s === 'string' ? s : s.name) || '').toLowerCase());
          const aInProp = propSpk.includes(aLower);
          const aInOpp = oppSpk.includes(aLower);
          const bInProp = propSpk.includes(bLower);
          const bInOpp = oppSpk.includes(bLower);

          if ((aInProp && bInOpp) || (aInOpp && bInProp)) {
            const sideA = aInProp ? 'PROPOSITION' : 'OPPOSITION';
            const sideB = bInProp ? 'PROPOSITION' : 'OPPOSITION';
            const teamA = aInProp ? d.prop_team : d.opp_team;
            const teamB = bInProp ? d.prop_team : d.opp_team;
            const winSideNorm = (d.winner_side || '').toUpperCase();
            const aWon = winSideNorm === sideA || (aInProp && winSideNorm.startsWith('PROP')) || (aInOpp && winSideNorm.startsWith('OPP'));
            if (aWon) aDirectWins++;
            else if (winSideNorm === sideB || (bInProp && winSideNorm.startsWith('PROP')) || (bInOpp && winSideNorm.startsWith('OPP'))) bDirectWins++;
            directDebates.push({
              debate_id: d.debate_id,
              tournament_name: d.tournament_name,
              round_name: d.round_name,
              round_type: d.round_type,
              side_a: aInProp ? 'Proposition' : 'Opposition',
              side_b: bInProp ? 'Proposition' : 'Opposition',
              team_a: teamA,
              team_b: teamB,
              a_won: aWon,
            });
          }
        }
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

      const eloA = selectedA.elo !== undefined ? selectedA.elo : 1500.0;
      const eloB = selectedB.elo !== undefined ? selectedB.elo : 1500.0;
      const expectedProbA = (1.0 / (1.0 + Math.pow(10.0, (eloB - eloA) / 400.0))) * 100.0;
      const expectedProbB = 100.0 - expectedProbA;

      // Categories Comparison:
      // 1. Speaker Score (higher better)
      let w1 = 'TIE';
      if (selectedA.speaker_score > selectedB.speaker_score) w1 = 'A';
      else if (selectedB.speaker_score > selectedA.speaker_score) w1 = 'B';

      // 2. Debater Elo Rating (higher better)
      let wElo = 'TIE';
      if (eloA > eloB) wElo = 'A';
      else if (eloB > eloA) wElo = 'B';

      // 3. Win % (higher better)
      let w2 = 'TIE';
      if (selectedA.win_percentage > selectedB.win_percentage) w2 = 'A';
      else if (selectedB.win_percentage > selectedA.win_percentage) w2 = 'B';

      // 4. Break Rank Avg (BRA) - lower seed rank is better! (e.g. 1st seed > 4th seed)
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

      // 5. Prelims Debated (higher better)
      let w4 = 'TIE';
      if (selectedA.prelims_debated > selectedB.prelims_debated) w4 = 'A';
      else if (selectedB.prelims_debated > selectedA.prelims_debated) w4 = 'B';

      // 6. Highest Achievement (lower rank order is better)
      let w5 = 'TIE';
      if (rankAchA < rankAchB) w5 = 'A';
      else if (rankAchB < rankAchA) w5 = 'B';

      // 7. Head to Head in Tournaments
      let w6 = 'NONE';
      if (directDebates.length > 0) {
        if (aDirectWins > bDirectWins) w6 = 'A';
        else if (bDirectWins > aDirectWins) w6 = 'B';
        else w6 = 'TIE';
      }

      const allCat = [w1, wElo, w2, w3, w4, w5];
      let scoreA = allCat.filter(w => w === 'A').length;
      let scoreB = allCat.filter(w => w === 'B').length;
      if (w6 === 'A') scoreA++;
      if (w6 === 'B') scoreB++;

      let bannerTitle = '';
      if (scoreA > scoreB) {
        bannerTitle = `${escapeHtml(nameA)} Leads ${scoreA} – ${scoreB}`;
      } else if (scoreB > scoreA) {
        bannerTitle = `${escapeHtml(nameB)} Leads ${scoreB} – ${scoreA}`;
      } else {
        bannerTitle = `Even Clash Tied ${scoreA} – ${scoreB}`;
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

      function badge(w, noneText = 'No Breaks') {
        if (w === 'A') return `<span class="h2h-cat-badge badge-a">Contender 01</span>`;
        if (w === 'B') return `<span class="h2h-cat-badge badge-b">Contender 02</span>`;
        if (w === 'NONE') return `<span class="h2h-cat-badge badge-tie">${escapeHtml(noneText)}</span>`;
        return `<span class="h2h-cat-badge badge-tie">Tie</span>`;
      }

      const b1 = getBar(selectedA.speaker_score, selectedB.speaker_score, true);
      const bElo = { a: expectedProbA, b: expectedProbB };
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
          <div style="font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(255, 255, 255, 0.76); margin-bottom: 6px;">
            Head to Head Result · Elo Win Expectancy: ${fmt(expectedProbA, 1)}% vs ${fmt(expectedProbB, 1)}%
          </div>
          <div class="h2h-pred-prob">${bannerTitle}</div>
          <div style="font-size: 13px; font-weight: 300; color: rgba(255, 255, 255, 0.82); margin-top: 6px;">
            Judged across Speaker Score, Elo, Win %, Break Rank Avg (BRA), Prelims, Highest Achievement, and Direct Tournament Clashes.
          </div>
        </div>

        <div class="h2h-stat-compare">
          <!-- 1. Speaker Score -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val">${fmt(selectedA.speaker_score, 2)}</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">01 // Speaker Score</span>
                ${badge(w1)}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b1.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b1.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">Speaker average across substantive speeches</div>
            </div>
            <div class="h2h-cat-val">${fmt(selectedB.speaker_score, 2)}</div>
          </div>

          <!-- 2. Debater Elo Rating -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val">${fmt(eloA, 1)}</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">02 // Elo Rating</span>
                ${badge(wElo)}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${bElo.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${bElo.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">Expected Win Share: ${fmt(expectedProbA, 1)}% vs ${fmt(expectedProbB, 1)}%</div>
            </div>
            <div class="h2h-cat-val">${fmt(eloB, 1)}</div>
          </div>

          <!-- 3. Win % -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val">${fmt(selectedA.win_percentage, 1)}%</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">03 // Win %</span>
                ${badge(w2)}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b2.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b2.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">Match win rate across contested debates</div>
            </div>
            <div class="h2h-cat-val">${fmt(selectedB.win_percentage, 1)}%</div>
          </div>

          <!-- 4. Break Rank Avg (BRA) -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val">${braA !== null ? fmt(braA, 2) : '—'}</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">04 // Break Rank Avg (BRA)</span>
                ${badge(w3, 'No Breaks')}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b3.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b3.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">Average preliminary break seed (Lower is better)</div>
            </div>
            <div class="h2h-cat-val">${braB !== null ? fmt(braB, 2) : '—'}</div>
          </div>


          <!-- 5. Prelims Debated -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val">${selectedA.prelims_debated}</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">05 // Prelims Debated</span>
                ${badge(w4)}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b4.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b4.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">Preliminary speeches completed</div>
            </div>
            <div class="h2h-cat-val">${selectedB.prelims_debated}</div>
          </div>

          <!-- 6. Highest Achievement -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val" style="font-size: 13px;">${achA}</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">06 // Highest Achievement</span>
                ${badge(w5)}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b5.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b5.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">Peak elimination progression</div>
            </div>
            <div class="h2h-cat-val" style="font-size: 13px;">${achB}</div>
          </div>

          <!-- 7. Head to Head in Tournaments -->
          <div class="h2h-category-card">
            <div class="h2h-cat-val">${aDirectWins}</div>
            <div class="h2h-cat-center">
              <div class="h2h-cat-title-row">
                <span class="h2h-cat-title">07 // Direct Tournament Clashes</span>
                ${badge(w6, 'No Clashes')}
              </div>
              <div class="h2h-cat-bar">
                <div class="h2h-cat-bar-a" style="width: ${b6.a}%;"></div>
                <div class="h2h-cat-bar-b" style="width: ${b6.b}%;"></div>
              </div>
              <div class="h2h-cat-subtext">${directDebates.length} direct debate matchup${directDebates.length === 1 ? '' : 's'} contested</div>
            </div>
            <div class="h2h-cat-val">${bDirectWins}</div>
          </div>
        </div>

        <!-- Direct Matchups Breakdown if any -->
        ${directDebates.length > 0 ? `
          <div class="h2h-matchups-section">
            <div class="h2h-matchups-title">
              Direct Tournament Encounters (${directDebates.length})
            </div>
            ${directDebates.map(m => `
              <div class="h2h-matchup-card">
                <div class="h2h-matchup-header">
                  <span class="h2h-matchup-tour">${escapeHtml(m.tournament_name)} · ${escapeHtml(m.round_name)}</span>
                  <span class="h2h-matchup-outcome">
                    ${m.a_won ? escapeHtml(nameA) + ' Won' : escapeHtml(nameB) + ' Won'}
                  </span>
                </div>
                <div class="h2h-matchup-body">
                  <div class="h2h-matchup-team">${escapeHtml(m.team_a || m.team_a_name)} (${m.side_a})</div>
                  <div style="font-family: var(--font-mono); font-size: 11px; color: rgba(255, 255, 255, 0.72);">vs</div>
                  <div class="h2h-matchup-team" style="text-align: right;">${escapeHtml(m.team_b || m.team_b_name)} (${m.side_b})</div>
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
      if (cd) cd.textContent = `${direct.length} Debaters`;
      if (ctr) ctr.textContent = `${trialed.length} Debaters`;
      if (ct) ct.textContent = `${trials.length} Debaters`;

      function renderItems(arr, tagClass) {
        if (arr.length === 0) {
          return `<div style="text-align: center; padding: 24px; color: rgba(255, 255, 255, 0.72); font-size: 13px; font-weight: 300;">No debaters match.</div>`;
        }
        return arr.map((d, idx) => `
          <div class="pool-debater-card">
            <div style="display: flex; align-items: baseline; gap: 14px; min-width: 0;">
              <span class="pool-rank-badge">${String(d.rank_in_tier || idx + 1).padStart(2, '0')}</span>
              <div style="min-width: 0;">
                <a class="pool-debater-name" href="bio.html?debater=${encodeURIComponent(d.name)}">${escapeHtml(d.name)}</a>
                <div>
                  <a class="pool-debater-inst" href="institution_bio.html?inst=${encodeURIComponent(d.institution || '')}">${escapeHtml(d.institution || 'Independent')}</a>
                </div>
              </div>
            </div>
            <div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 3px; flex-shrink: 0;">
              <span class="nat-tag ${tagClass}">${escapeHtml(d.national_level || '')}</span>
              ${d.speaker_score ? `<span style="font-size: 11px; font-family: var(--font-mono); color: rgba(255, 255, 255, 0.82); font-weight: 400; white-space: nowrap;">Avg ${fmt(d.speaker_score, 2)} · Elo ${fmt(d.elo || 1500, 0)}</span>` : ''}
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

    if (!poolData) {
      fetchJson('v2_national_pool.json', '/api/v2/pool').then((p) => {
        if (p) {
          poolData = p;
          state.v2NationalPool = p;
          renderPoolLists(searchInput ? searchInput.value : '');
        }
      });
    }
  }

  // ==========================================================================
  // 9. AI CHATBOT INTEGRATION
  // ==========================================================================
  function getChatSessionId() {
    let sid = sessionStorage.getItem('atomos_chat_session_id') || localStorage.getItem('atomos_chat_session_id');
    if (!sid) {
      sid = 'session_' + Math.random().toString(36).substring(2, 11) + '_' + Date.now();
    }
    sessionStorage.setItem('atomos_chat_session_id', sid);
    try { localStorage.setItem('atomos_chat_session_id', sid); } catch (e) {}
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
        try { localStorage.removeItem('atomos_chat_session_id'); } catch (e) {}
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

  async function answerChatFromGitHubData(promptText) {
    const q = (promptText || '').trim().toLowerCase();

    // Client-side circuit boundary lock
    const offTopicKeywords = ['recipe', 'toast', 'bake', 'cook', 'cinnamon', 'ingredient', 'cake', 'bread', 'soup', 'sandwich', 'pizza', 'pasta', 'cocktail', 'poem', 'poetry', 'write a song', 'story about', 'joke about', 'weather in', 'translate to', 'movie', 'celebrity'];
    const debateKeywords = ['debate', 'debater', 'debating', 'wsdc', 'tabbycat', 'ballot', 'speaker', 'speeches', 'elo', 'rating', 'motion', 'round', 'prelim', 'elim', 'break', 'bra', 'atss', 'awpt', 'atomos', 'school', 'college', 'royal', 'ananda', 'ds', 'chaps', 'slsdc', 'vvidc', 'metho', 'vijis'];
    if (offTopicKeywords.some(w => q.includes(w)) && !debateKeywords.some(w => q.includes(w))) {
      return "I am Atomos, an exclusive intelligence analyst calibrated solely for the Sri Lankan Schools Debating Circuit and Atomos debate analytics. I do not provide recipes, general programming, or off-topic assistance. Ask me about debaters, teams, tournaments, ballots, Elo ratings, or speaker rankings instead.";
    }

    const [sum, spkAll, spkTab, teamsAll, instAll, tourneys, adjAll, pool] = await Promise.all([
      state.circuitSummary || fetchJson('circuit_summary.json', '/api/circuit'),
      state.v2SpeakersAll.length ? state.v2SpeakersAll : fetchJson('v2_speakers_all.json', '/api/v2/leaderboard/speakers?tier=all'),
      state.v2SpeakersTab.length ? state.v2SpeakersTab : fetchJson('v2_speakers_tab.json', '/api/v2/leaderboard/speakers?tier=tab'),
      state.v2TeamsAll.length ? state.v2TeamsAll : fetchJson('v2_teams_all.json', '/api/v2/leaderboard/teams?tier=all'),
      state.v2InstitutionsAll.length ? state.v2InstitutionsAll : fetchJson('v2_institutions_all.json', '/api/v2/leaderboard/institutions?tier=all'),
      state.v2Tournaments.length ? state.v2Tournaments : fetchJson('v2_tournaments.json', '/api/v2/leaderboard/tournaments'),
      state.v2AdjudicatorsAll.length ? state.v2AdjudicatorsAll : fetchJson('v2_adjudicators_all.json', '/api/v2/leaderboard/adjudicators?min_prelims=1'),
      state.v2NationalPool || fetchJson('v2_national_pool.json', '/api/v2/pool'),
    ]);

    if (sum) state.circuitSummary = sum;
    if (spkAll) state.v2SpeakersAll = spkAll;
    if (spkTab) state.v2SpeakersTab = spkTab;
    if (teamsAll) state.v2TeamsAll = teamsAll;
    if (instAll) state.v2InstitutionsAll = instAll;
    if (tourneys) state.v2Tournaments = tourneys;
    if (adjAll) state.v2AdjudicatorsAll = adjAll;
    if (pool) state.v2NationalPool = pool;

    // 1. Check if query mentions one or more specific debaters (full name or distinctive token >= 4 chars)
    const stopWords = new Set(['what', 'when', 'where', 'which', 'show', 'tell', 'compare', 'comparison', 'between', 'from', 'with', 'history', 'record', 'debater', 'debaters', 'speaker', 'speakers', 'team', 'teams', 'school', 'college', 'metho', 'chaps', 'slsdc', 'vvidc', 'vijis', 'round', 'prelim', 'prelims', 'break', 'average', 'score', 'scores', 'rank', 'ranking', 'national', 'pool', 'direct', 'trialed', 'trials']);
    const qWords = q.replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter(w => w.length >= 4 && !stopWords.has(w));
    const matchedSpeakers = [];
    const seenIds = new Set();

    // First pass: exact full name match
    for (const s of (spkAll || [])) {
      const sName = (s.name || s.speaker_name || '').toLowerCase();
      if (sName && q.includes(sName)) {
        seenIds.add(sName);
        matchedSpeakers.push(s);
      }
    }
    // Second pass: token match (first name / surname) ordered by prelims_debated DESC
    if (qWords.length > 0) {
      const sortedByActivity = [...(spkAll || [])].sort((a, b) => (b.prelims_debated || 0) - (a.prelims_debated || 0));
      for (const w of qWords) {
        const wStem = w.endsWith('s') && w.length > 4 ? w.slice(0, -1) : w;
        if (matchedSpeakers.some(ms => {
          const tokens = (ms.name || '').toLowerCase().split(/\s+/);
          return tokens.includes(w) || tokens.includes(wStem);
        })) continue;
        const found = sortedByActivity.find(s => {
          const sName = (s.name || s.speaker_name || '').toLowerCase();
          if (seenIds.has(sName)) return false;
          const parts = sName.replace(/[^a-z0-9\s]/g, ' ').split(/\s+/);
          return parts.includes(w) || parts.includes(wStem);
        });
        if (found) {
          seenIds.add((found.name || found.speaker_name || '').toLowerCase());
          matchedSpeakers.push(found);
        }
      }
    }

    if (matchedSpeakers.length >= 2) {
      const rows = matchedSpeakers.slice(0, 5);
      return [
        `### Debater Comparison (${rows.map(r => r.name).join(' vs ')})`,
        `| Debater | Institution | Speaker Avg | Avg Speaker Tab Rank | Elo (Peak) | Win % | Prelims | Highest Achievement |`,
        `| --- | --- | --- | --- | --- | --- | --- | --- |`,
        ...rows.map(s => `| ${s.name} | ${s.institution} | ${fmt(s.speaker_score, 3)} | ${s.avg_speaker_tab_rank != null ? fmt(s.avg_speaker_tab_rank, 3) : '—'} | ${fmt(s.elo || 1500, 3)} (${fmt(s.peak_elo || s.elo || 1500, 3)}) | ${fmt(s.win_percentage, 3)}% | ${s.prelims_debated} | ${s.highest_achievement || 'Preliminary Rounds'} |`),
      ].join('\n');
    }

    if (matchedSpeakers.length === 1) {
      const matchedSpeaker = matchedSpeakers[0];
      const pos = matchedSpeaker.position_averages || {};
      const p1 = pos['1st'] && pos['1st'].average ? fmt(pos['1st'].average, 3) : '—';
      const p2 = pos['2nd'] && pos['2nd'].average ? fmt(pos['2nd'].average, 3) : '—';
      const p3 = pos['3rd'] && pos['3rd'].average ? fmt(pos['3rd'].average, 3) : '—';
      const tb = matchedSpeaker.tournament_breakdown || [];
      const eligRanks = tb.filter(t => t.speaker_tab_rank_avg != null).map(t => t.speaker_tab_rank_avg);
      const eligDeriv = eligRanks.length > 0
        ? `((${eligRanks.join(' + ')}) / ${eligRanks.length} = ${eligRanks.reduce((a, b) => a + b, 0)} / ${eligRanks.length} = ${fmt(matchedSpeaker.avg_speaker_tab_rank, 3)})`
        : '';
      const lines = [
        `### ${matchedSpeaker.name} (${matchedSpeaker.institution})`,
        `- **Speaker Average:** ${fmt(matchedSpeaker.speaker_score, 3)} pts (${matchedSpeaker.prelims_debated} prelims across ${matchedSpeaker.tournaments_debated} tournaments)`,
        `- **Career Avg Speaker Tab Rank (WSDC Qualifying >=3 Prelims):** **${matchedSpeaker.avg_speaker_tab_rank != null ? fmt(matchedSpeaker.avg_speaker_tab_rank, 3) : '—'}** ${eligDeriv}`,
        `- **Career Avg Speaker Tab Rank (Tabbycat Full Prelims by Total Pts):** **${matchedSpeaker.avg_speaker_tab_rank_full_prelims != null ? fmt(matchedSpeaker.avg_speaker_tab_rank_full_prelims, 3) : '—'}** · **Best Tab Rank:** ${matchedSpeaker.best_speaker_tab_rank_avg ? '#' + matchedSpeaker.best_speaker_tab_rank_avg : '—'}`,
        `- **Debater Elo:** ${fmt(matchedSpeaker.elo || 1500, 3)} (Peak: ${fmt(matchedSpeaker.peak_elo || matchedSpeaker.elo || 1500, 3)})`,
        `- **Win Rate:** ${fmt(matchedSpeaker.win_percentage, 3)}% · **StDev:** ${fmt(matchedSpeaker.stdev, 3)}`,
        `- **Highest Achievement:** ${matchedSpeaker.highest_achievement || 'Preliminary Rounds'} · **National Status:** ${matchedSpeaker.national_level || '—'}`,
        `- **Position Averages:** 1st: ${p1} · 2nd: ${p2} · 3rd: ${p3}`,
      ];
      if (tb.length > 0) {
        lines.push('', `| Tournament | Team | Prelims | Avg Score | Total Pts | Speaker Tab Rank (Avg) | Speaker Tab Rank (Total) | Stage Reached |`, `| --- | --- | --- | --- | --- | --- | --- | --- |`);
        tb.forEach(t => {
          const rAvg = t.speaker_tab_rank_avg != null ? `#${t.speaker_tab_rank_avg} / ${t.eligible_speakers || '—'}` : 'Ineligible (<3)';
          const rTot = t.speaker_tab_rank_total != null ? `#${t.speaker_tab_rank_total} / ${t.total_speakers || '—'}` : '—';
          const prelimStr = t.max_prelims ? `${t.prelims_debated}/${t.max_prelims}` : `${t.prelims_debated || '—'}`;
          lines.push(`| ${t.tournament_name} | ${t.team_name || '—'} | ${prelimStr} | **${fmt(t.average_score || t.tournament_average, 3)}** | ${t.total_points != null ? fmt(t.total_points, 3) : '—'} | **${rAvg}** | ${rTot} | ${t.highest_break || t.highest_stage || 'Preliminary Rounds'} |`);
        });
      }
      return lines.join('\n');
    }

    // 2. Check if query mentions a specific team
    const matchedTeam = (teamsAll || []).find((t) => q.includes((t.team_name || '').toLowerCase()));
    if (matchedTeam) {
      return [
        `### ${matchedTeam.team_name} (${matchedTeam.institution})`,
        `- **ATSS:** ${fmt(matchedTeam.atss, 2)} pts · **Team Elo:** ${fmt(matchedTeam.elo || 1500, 1)} (Peak: ${fmt(matchedTeam.peak_elo || matchedTeam.elo || 1500, 1)})`,
        `- **Win Rate:** ${fmt(matchedTeam.win_percentage, 1)}% (${matchedTeam.prelims_debated} prelims across ${matchedTeam.tournaments_debated} tournaments)`,
        `- **Highest Break:** ${matchedTeam.highest_achievement || 'Preliminary Rounds'} · **AWPT:** ${fmt(matchedTeam.awpt, 2)}`,
      ].join('\n');
    }

    // 3. Check if query mentions a specific institution
    const matchedInst = (instAll || []).find((i) => q.includes((i.institution_name || '').toLowerCase()));
    if (matchedInst) {
      return [
        `### ${matchedInst.institution_name}`,
        `- **Delta:** ${fmt(matchedInst.delta, 2)} · **Institution Elo:** ${fmt(matchedInst.elo || 1500, 1)}`,
        `- **A Team (${matchedInst.a_team_name || '—'}):** ${fmt(matchedInst.a_atss, 2)} ATSS · **B Team (${matchedInst.b_team_name || '—'}):** ${matchedInst.b_atss ? fmt(matchedInst.b_atss, 2) + ' ATSS' : '—'}`,
        `- **Win Rate:** ${fmt(matchedInst.win_percentage, 1)}% · **Debater Pool:** ${matchedInst.pool_count} debaters (${(matchedInst.veterans || []).length} veterans, ${(matchedInst.new_debaters || []).length} new)`,
      ].join('\n');
    }

    // 4. Top speakers / teams / institutions queries
    if (q.includes('team')) {
      const topTeams = (teamsAll || []).filter((t) => t.tournaments_debated >= 3).slice(0, 5);
      return [
        `### Top 5 Circuit Teams (Tab Qualified)`,
        `| Rank | Team | Institution | ATSS | Elo | Win % |`,
        `| --- | --- | --- | --- | --- | --- |`,
        ...topTeams.map((t, idx) => `| ${idx + 1} | ${t.team_name} | ${t.institution} | ${fmt(t.atss, 2)} | ${fmt(t.elo || 1500, 1)} | ${fmt(t.win_percentage, 1)}% |`),
      ].join('\n');
    }

    if (q.includes('school') || q.includes('institution') || q.includes('delta')) {
      const topInst = (instAll || []).filter((i) => i.tournaments_debated >= 3).slice(0, 5);
      return [
        `### Top 5 Circuit Institutions (by Delta)`,
        `| Rank | Institution | Delta | Elo | A ATSS | B ATSS |`,
        `| --- | --- | --- | --- | --- | --- |`,
        ...topInst.map((i, idx) => `| ${idx + 1} | ${i.institution_name} | ${fmt(i.delta, 2)} | ${fmt(i.elo || 1500, 1)} | ${fmt(i.a_atss, 2)} | ${i.b_atss ? fmt(i.b_atss, 2) : '—'} |`),
      ].join('\n');
    }

    if (q.includes('judge') || q.includes('adjudicator')) {
      const topAdj = (adjAll || []).filter((j) => j.prelims_adjudicated >= 4).slice(0, 5);
      return [
        `### Top 5 Circuit Adjudicators`,
        `| Rank | Adjudicator | Prelims | AASS | AATSS | Prop / Opp Split |`,
        `| --- | --- | --- | --- | --- | --- |`,
        ...topAdj.map((j, idx) => `| ${idx + 1} | ${j.adjudicator_name} | ${j.prelims_adjudicated} | ${fmt(j.aass, 2)} | ${fmt(j.aatss, 2)} | ${fmt(j.prop_bias_pct, 1)}% P / ${fmt(j.opp_bias_pct, 1)}% O |`),
      ].join('\n');
    }

    const topSpk = (spkTab || []).slice(0, 5);
    return [
      `### Sri Lankan Debate Circuit Overview (${sum ? sum.total_tournaments : 10} Tournaments · ${sum ? sum.total_debates_debated : 1096} Debates)`,
      `| Rank | Debater | Institution | Avg Score | Elo | Win % |`,
      `| --- | --- | --- | --- | --- | --- |`,
      ...topSpk.map((s, idx) => `| ${idx + 1} | ${s.name} | ${s.institution} | ${fmt(s.speaker_score, 2)} | ${fmt(s.elo || 1500, 1)} | ${fmt(s.win_percentage, 1)}% |`),
    ].join('\n');
  }

  async function sendChatPrompt(promptText) {
    const messages = document.getElementById('chatMessages');
    const input = document.getElementById('chatInput');
    if (!messages) return;

    if (input) input.value = '';
    trackEvent('ai_chat_prompt', { prompt_snippet: promptText.substring(0, 80) });

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
        signal: AbortSignal.timeout(45000),

      });

      if (res.ok) {
        const data = await res.json();
        const answer = data.answer || data.response || data.text;
        if (answer) {
          botMsg.innerHTML = formatMarkdownToHtml(answer);
          messages.scrollTop = messages.scrollHeight;
          return;
        }
      }
    } catch (e) {}

    botMsg.innerHTML = `<div>AI assistance is unavailable currently.</div>`;
    messages.scrollTop = messages.scrollHeight;
  }


  function formatInlineMarkdown(str) {
    if (!str) return '';
    // Clean up math/LaTeX syntax for clean human readability: $\ge 3$ -> ≥ 3
    str = str.replace(/\\ge\b/g, '≥');
    str = str.replace(/\\le\b/g, '≤');
    str = str.replace(/\\times\b/g, '×');
    str = str.replace(/\$([^\$]+)\$/g, '$1');
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
        output.push(`<div style="margin: 3px 0 3px 14px;"><strong style="color: rgba(255, 255, 255, 0.88);">${match[1]}</strong> ${formatInlineMarkdown(match[2])}</div>`);
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
