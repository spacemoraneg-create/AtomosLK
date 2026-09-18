# ATOMOS: The Sovereign Intelligence, Analytics & Archival System
### Comprehensive Architecture, Data Engineering & Analytical Specification
**Sri Lankan World Schools Debating Championship (WSDC) Circuit**

---

## 1. Executive Overview & Mission

**Atomos** is an enterprise-grade debate intelligence platform, forensic data archive, and predictive analytics engine built specifically for the Sri Lankan World Schools Debating Championship (WSDC) circuit. 

For decades, competitive debating records across Sri Lankan schools were fragmented across transient Tabbycat instances, paper scorecards, and local tournament archives. Discrepancies in speaker naming, inconsistent institutional spelling, unstandardized scoring metrics, and the lack of historical cross-tournament tracking made circuit-wide longitudinal analysis impossible.

Atomos solves this fundamentally. It unifies, reconciles, and mathematically standardizes multi-year tournament data into a single, sovereign relational SQLite database (`data/atomos.db`). Operating on top of this foundation is a suite of statistical engines that benchmark debater performance, evaluate adjudicator bias and strictness, reconstruct elimination knockout brackets, simulate competitive team clashes, and power an autonomous AI debate agent grounded in verified data.

Atomos is designed for three distinct user groups:
1. **Debaters & Coaches**: Deep tactical debater dossiers, head-to-head clash histories, team performance trends, and longitudinal skill trajectories.
2. **Tournament Adjudication Cores (Ad-Cores)**: Objective adjudicator intelligence dossiers, panel strictness calibration, and side balance analysis across motions.
3. **Software Engineers & Web Developers**: A headless, CORS-enabled REST API and precomputed static web datasets (`data/web_export/`) ready for instant integration with React, Next.js, Vue, or mobile applications.

---

## 2. The Competitive Domain Context (WSDC Debating in Sri Lanka)

To understand Atomos, one must understand the rules, nuances, and conventions of the Sri Lankan competitive debating circuit:

* **Format**: World Schools Debating Championship (WSDC) format.
* **Matchup Structure**: Two opposing teams—**Proposition (Prop)** and **Opposition (Opp)**—comprising 3 speakers per team.
* **Speeches**:
  * 3 Substantive Speeches per side (1st, 2nd, and 3rd speakers), each traditionally scored on a scale of **60.0 to 80.0 points** (with 70.0 as the expected circuit average).
  * 1 Reply Speech per side (given by either the 1st or 2nd speaker), scored on a half-scale of **30.0 to 40.0 points** (with 35.0 as average).
  * Team Total in a single debate: Sum of 3 substantives + 1 reply, ranging between **210.0 and 280.0 points** per judge ballot.
* **Panels & Adjudication**:
  * Debates may be judged by a single adjudicator or a multi-member panel (3, 5, or 7 judges).
  * Panel decisions are awarded by majority vote ($2\text{--}1, 3\text{--}0, 4\text{--}1, 5\text{--}0$).
  * Total scores from each panelist must be averaged to derive the authoritative match score and speaker score.
* **Speaker Tab Qualification Rule (The 3-Round Rule)**:
  * In official WSDC rules, a debater is only eligible for individual speaker awards if they spoke in at least $3$ preliminary rounds. Debaters speaking in only 1 or 2 rounds are ineligible for official speaker tab rankings. Atomos strictly enforces this distinction.
* **Institutional Multi-Team Fielding**:
  * Major debating schools field multiple squads (e.g., *Royal College A*, *Royal College B*, *D. S. Senanayake College A*, *Ladies' College Gold*, *Bishop's College Purple*).
  * In knockout rounds, teams from the same institution occasionally face each other or execute an institutional "closeout" (where the school decides which squad advances without debating).

---

## 3. System Architecture: The 6-Tier Architecture

Atomos is structured into 6 decoupled architectural layers:

```
+-----------------------------------------------------------------------------------+
|                        LAYER 6: AUTONOMOUS AI AGENT                              |
|   Google Gemini 2.5 Multi-Turn Reasoning Agent | 18 Specialized Grounded Tools     |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
|                        LAYER 5: HEADLESS ACCESS & EXPORTS                         |
|   CORS-Enabled REST API (Flask) | Precomputed Cache | Static JSON Compiler        |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
|                        LAYER 4: ANALYTICAL & MODELING ENGINES                     |
|  Master Tabs | Elo Ratings | Critical Stats | Judges | Brackets | Match Predictor  |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
|                        LAYER 3: RELATIONAL DATABASE & STORAGE                     |
|  SQLite (data/atomos.db): 10 Tables | Foreign Key Constraints | Covering Indices  |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
|                        LAYER 2: NORMALIZATION & ENTITY RESOLUTION                 |
|  Identity Merger | Team Resolver | Institutional Normalizer | WSDC Rubric Guards |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
|                        LAYER 1: EXTRACTION & DATA INGESTION                       |
|  Tabbycat Scraper | Motion Categorizer | Spreadsheet Importer | Ingestion Script  |
+-----------------------------------------------------------------------------------+
```

---

## 4. The Data Layer & Relational Schema (`atomos.db`)

The physical database resides at `data/atomos.db`. It enforces foreign key constraints and covering indices across 10 core relational tables:

1. **`tournaments`**: Metadata for each tournament (name, slug, year, season, start/end dates).
2. **`institutions`**: Canonical schools and universities (name, code, region, type).
3. **`teams`**: Debating teams fielded by institutions (name, canonical name, institution ID, tier).
4. **`persons`**: Unique debater and adjudicator profiles (canonical name, gender, school ID, national level).
5. **`debater_aliases`**: Alias map linking misspellings, nicknames, and alternative transcriptions back to canonical person records.
6. **`team_members`**: Mapping of persons to specific team rosters per tournament.
7. **`rounds`**: Rounds within tournaments (round number, stage name, type: `PRELIMINARY` vs `ELIMINATION`, motion, info slide, motion theme).
8. **`debates`**: Match records between Proposition and Opposition teams (venue, round ID, bracket position, is_walkover flag).
9. **`adjudicator_ballots`**: Individual scoresheets from each panelist (adjudicator name, institution, Prop score, Opp score, margin, winner side).
10. **`speech_performances`**: Granular speech records (person ID, side, position: 1st/2nd/3rd/Reply, speech type, total score).
11. **`precomputed_cache`**: High-speed materialized key-value cache storing heavy precomputed analytical results.

### Database Scale in Active Circuit
* **Tournaments**: 9 major championships (Chaps 2026, SLSDC 2026, VVIDC 2026, Metho 2026, Vijis 2026, AISDC 2026, APIIT ISDC 2026, RIC 2026, IDC).
* **Canonical Institutions**: 69 registered schools.
* **Registered Teams**: 318 teams.
* **Unique Persons Indexed**: 772 debaters and judges.
* **Contested Debates**: 920 matches (including 12 documented walkovers).
* **Ballots Audited**: 928 adjudicator panel ballots.
* **Speeches Evaluated**: 6,442 individual substantive and reply speeches.

---

## 5. Identity Reconciliation & Entity Resolution

In high school debating tournaments, student names are frequently registered with discrepancies:
* Variations: *"Balishta Wijesinghe"* vs *"Balishta W."* vs *"Balishta"*.
* School prefixes: *"DS Balishta"* vs *"Balishta (DSSC)"*.
* Inversions: *"Wijesinghe Balishta"*.
* Institution ambiguity: Ensuring *Muslim Ladies' College (MLC)* and *Ladies' College (LC)* are strictly segregated as distinct institutions.

### The Identity Merger Engine (`src/atomos/normalizer/identity_merger.py`)
Atomos detects and reconciles duplicates across 5 safe heuristic passes:
1. **EXACT_CASE**: Identical names with differing capitalizations.
2. **SPACING_PUNCTUATION**: Differences in whitespace, dots, or hyphens.
3. **NAME_INVERSION**: `FirstName LastName` vs `LastName FirstName`.
4. **SUBSTRING_SAME_SCHOOL**: Shortened names from the exact same institution.
5. **SAME_TEAM_COLLISION**: A mathematical guard ensuring two debaters are never merged if they spoke in the exact same debate on the same team.

### Team ID Resolver (`src/atomos/normalizer/team_resolver.py`)
Enables manual and automated grouping of multi-tournament team aliases (e.g. mapping *"DS A"*, *"D. S. Senanayake A"*, and *"DSSC A"* into a single canonical competitive entity).

### National Team Status Registry
Atomos tracks the Sri Lankan National Debating Contingent directly in debater profiles and displays it across all leaderboards:
* **`Nat Trials`**: Debaters who competed in the National Selection Trials.
* **`Nat Pool, Trialed`**: Debaters who qualified for the National Pool via trials.
* **`Nat Pool, Direct`**: Debaters who received direct admission into the National Pool.

---

## 6. The Core Analytical & Modeling Engines

Atomos implements 7 sophisticated analytical engines located in `src/atomos/analytics/`:

### 6.1 Master Tab Engine (`master_tabs.py`)
Computes official speaker averages conforming to international WSDC tab rules:
* Filters out non-qualifying speakers (fewer than 3 preliminary rounds) when generating official speaker leaderboards.
* Reconciles multiple adjudicator ballots per debate into a single unweighted average per speech.
* Produces the official **National Master Speaker Tab** and **National Master Reply Tab**.

### 6.2 Critical Statistics Engine (`critical_stats.py`)
Debating performance cannot be measured by raw scoring average alone due to tournament inflation, panel variability, and schedule strength. The Critical Stats Engine measures:
* **ATSS (Average Total Speaker Score)**: Team preliminary scoring baseline.
* **Scoring Consistency ($\sigma$)**: Standard deviation of substantive scores across tournaments.
* **Ceiling & Floor Analysis**: Highest and lowest single-speech score recorded.
* **Debate Conversion Rate**: Win percentage in matches where the specific debater spoke.
* **Outround Break Rate**: Percentage of entered tournaments where the debater/team advanced to elimination rounds.

### 6.3 Dynamic Elo Rating System (`ratings.py`)
An implementation of zero-sum Elo rating tailored to competitive debating:
* **Baseline Rating**: 1,500.0 points.
* **Dynamic K-Factor**: Adjusted based on match significance (Preliminary vs Elimination) and score margin (a 0.5-point razor split adjusts ratings less than a 5.0-point blowout).
* **Institutional Power Index (IPI)**: Ranks schools by combining team Elo ratings, squad depth, and total elimination victories.
* **Debater Performance Index (DPI)**: Individual debater impact metrics derived from speaker point deviations against tournament room averages.

### 6.4 Adjudicator Intelligence Engine (`judges.py`)
Provides analytical oversight and dossiers for debate adjudicators:
* **Side Bias Profile**: Proposition vs Opposition win percentage, detecting statistically significant deviations from a 50/50 balance.
* **Scoring Strictness Index**: Compares a judge's substantive score distribution against the national circuit benchmark ($71.20$ pts). Classifies adjudicators into:
  * `Strict / Low-Scoring` ($\ge 0.40$ pts below circuit average)
  * `Circuit Standard (Moderate)` (within $\pm 0.40$ pts)
  * `High-Scoring / Generous` ($\ge 0.40$ pts above circuit average)
* **Margin Tendencies**: Frequency of awarding close splits ($\le 1.5$ pts) versus blowouts ($\ge 4.0$ pts).
* **Outround Experience**: Detailed record of elimination panels officiated (Octos through Grand Finals).

### 6.5 Tournament Knockout Bracket Engine (`brackets.py`)
Reconstructs elimination trees for any tournament:
* Hierarchical structure: Octofinals $\rightarrow$ Quarterfinals $\rightarrow$ Semifinals $\rightarrow$ Grand Final.
* Detailed matchup nodes: Team lineups, individual speaker scores, panel vote counts, and win margins.
* Closeout Detection: Identifies single-institution closeouts where squads from the same school reached the final stage (e.g., Ananda College closeouts at Chap's 2026 and SLSDC 2026).

### 6.6 Predictive Clash Simulator (`predictor.py`)
Simulates upcoming or hypothetical debates between any two teams using a 3-factor composite model:
* **$50\%$ Squad Elo Rating differential**: Evaluated via standard logistic win probability curve:
  $$P(A) = \frac{1}{1 + 10^{(Elo_B - Elo_A) / 400}}$$
* **$35\%$ Preliminary ATSS Baseline**: Win equity shift adjusted by scoring power.
* **$15\%$ National Contingent Density**: Roster strength weighted by debaters holding `Nat Trials`, `Nat Pool, Trialed`, or `Nat Pool, Direct` status.
* **Output**: Exact win probabilities, predicted point margin, competitiveness classification (`Razor-Thin Split`, `Competitive Contest`, `Decisive Advantage`), and tactical keys to victory.

### 6.7 Chronological Debater Trajectory (`debater_profile.py`)
Tracks a debater's form and evolution over time in strict chronological tournament sequence:
* Measures tournament-by-tournament substantive average, personal ceiling, floor, reply average, and running career cumulative average.
* Rendered in CLI and API profiles for visual progression graphing.

---

## 7. Headless REST API & Precomputed Web Infrastructure

Atomos is decoupled from any specific frontend presentation layer. It provides both a live REST API and precomputed static JSON payloads.

### Headless REST API (`src/atomos/server.py`)
* Built with Flask, featuring global CORS headers (`Access-Control-Allow-Origin: *`).
* Supports `GET, POST, PUT, DELETE, OPTIONS`.
* Command to run: `python src/atomos/server.py --port 5000`.

#### Key Endpoints
* `GET /api/health` — System status, database health, total persons indexed.
* `POST /api/ask` — Natural language question answering via the agent.
* `GET /api/search?q=...` — Unified multi-entity search (debaters, teams, schools).
* `GET /api/debaters/<id>/profile` — Full debater dossier with career trajectory.
* `GET /api/leaderboard/speakers` — Multi-metric speaker tab with national status filtering.
* `GET /api/tournaments/<slug>/bracket` — Hierarchical elimination knockout tree.
* `GET /api/judges/<identifier>` & `GET /api/judges` — Adjudicator dossiers & leaderboards.
* `GET /api/predict?team_a=...&team_b=...` — Matchup simulation and win probability.
* `GET /api/national-pool` — Complete national team pool debaters registry.
* `GET /api/debates/<debate_id>` — Detailed scoresheet, ballots, and speeches.
* `GET /api/institutions` — Institutional Power Index leaderboard.
* `GET /api/motions/summary` — Motion balance, themes, and side bias statistics.

### Precomputed Web Exporter (`scripts/export_web_data.py`)
For modern Jamstack web applications (Next.js, Astro, Nuxt), dynamic database queries can introduce latency. Atomos includes an automated exporter that pre-generates static JSON files into `data/web_export/`:
* `master_speaker_tab.json`
* `master_reply_tab.json`
* `critical_speaker_stats.json`
* `critical_team_stats.json`
* `institutional_power_index.json`
* `judge_leaderboard.json`
* `national_pool.json`
* `circuit_summary.json`
* Knockout trees for all 8 tournaments (`chaps2026_bracket.json`, `slsdc26_bracket.json`, etc.)

---

## 8. Autonomous AI Agent & 18 Grounded Tools

Atomos incorporates an autonomous conversational AI agent powered by Google Gemini (`src/atomos/agent/gemini_agent.py` and `orchestrator.py`).

### Anti-Hallucination Philosophy
The agent does not guess, speculate, or fabricate debate statistics. Every factual response must be derived from one of **18 registered tool schemas**:

1. `search_entities`: Search across debaters, schools, and teams.
2. `get_debater_profile`: Career stats, tournament breakdown, and trajectory.
3. `get_head_to_head`: Direct clash records between debaters, teams, or schools.
4. `compare_institutions`: In-depth comparison of two debating schools.
5. `get_institutional_leaderboard`: National school rankings by IPI and break rate.
6. `get_speaker_leaderboard`: Speaker rankings by master tab, volume, or replies.
7. `get_circuit_summary`: High-level circuit health indicators.
8. `get_tournament_finals`: Elimination finals and champions.
9. `get_motion_analytics`: Motion balance, thematic breakdowns, and side bias.
10. `get_debate_ballot`: Granular scoresheet and lineup for a specific debate.
11. `get_team_record`: Tournament-by-tournament team scores and highest quality debates.
12. `get_tier_matchup_stats`: Win ratios between school tiers (e.g. A teams vs B teams).
13. `get_national_pool`: Debaters holding National Team designations.
14. `get_tournament_bracket`: Complete elimination trees and split decisions.
15. `get_judge_profile`: Adjudicator dossier, strictness, and side bias.
16. `get_judge_leaderboard`: National ranking of debate adjudicators.
17. `predict_matchup`: Match predictive simulation with projected score margins.
18. `execute_sql`: Safe, read-only SELECT execution for ad-hoc forensic queries.

---

## 9. Quality Assurance: The 5-Gate Master Forensic Audit

To guarantee mathematical and relational consistency, Atomos features a continuous integrity gatekeeper (`scripts/master_audit.py`). Every database change must pass 48 automated checks across 5 quality gates:

* **Gate 1: Schema & Relational Integrity** (7 checks)
  * Validates table existence, index coverage, primary keys, and zero orphaned foreign keys.
* **Gate 2: Debate & Roster Invariants** (16 checks)
  * Ensures exactly one Proposition and one Opposition team per debate, validates walkover consistency, and verifies debater team registrations.
* **Gate 3: Scoring Math & Rubric Invariants** (5 checks)
  * Verifies substantive scores fall strictly within $60.0 \text{--} 80.0$, replies fall within $30.0 \text{--} 40.0$, and ballot team scores equal the exact sum of speaker scores.
* **Gate 4: Ground Truth Tab Reconciliation** (4 checks)
  * Verifies that Atomos speaker tabs, win counts, and team totals match official published tournament tabs to 4 decimal places.
* **Gate 5: Analytical Engine Invariants** (16 checks)
  * Ensures monotonic rankings, verified Elo calculations, valid strictness indices, and non-empty bracket structures.

**Current Audit Status**: **5 / 5 Gates Passed | 48 / 48 Checks Passed | 0 Critical Errors**.

---

## 10. CLI Ecosystem & Operations Manual

Atomos provides a suite of CLI tools for power users:

| Task | Command |
| :--- | :--- |
| **View Debater Profile & Trajectory** | `python scripts/view_identity.py "Balishta Wijesinghe"` |
| **View Judge Dossier** | `python scripts/view_judge.py "Minithi Hewage"` |
| **View National Judge Leaderboard** | `python scripts/view_judge.py --top 20 --sort debates` |
| **Compare Two Debating Schools** | `python scripts/compare_schools.py "Royal College" "Ananda College"` |
| **Detailed Head-to-Head Clash** | `python scripts/head_to_head.py "DS A" "RC A" --team` |
| **View Critical Debater Stats** | `python scripts/view_critical_stats.py --limit 25` |
| **View Institutional Leaderboard** | `python scripts/institutional_leaderboard.py --top 20` |
| **Analyze Motion Side Balance** | `python scripts/motion_analysis.py --side-bias` |
| **Run Master Forensic Audit** | `python scripts/master_audit.py` |
| **Compile & Export Web JSONs** | `python scripts/export_web_data.py` |
| **Ingest New Tournament Tab** | `python scripts/ingest_circuit_tournament.py "https://site.calicotab.com/slug/" --refresh-cache` |
| **Interactive AI Debating Chat** | `python scripts/ask_atomos.py --chat` |
| **Start Headless REST API Server** | `python src/atomos/server.py --port 5000` |
| **Run Complete Test Suite** | `pytest tests/` |

---

## 11. Current Circuit Scope & Benchmark Figures

Across the active database (`atomos.db`):
* **Circuit Benchmark Substantive Average**: **$71.20$ points**.
* **Circuit Benchmark Reply Average**: **$35.60$ points**.
* **Total Contested Matches**: **920 debates**.
* **National Debater Registry**: **27 debaters** holding official National Squad status (9 Nat Trials, 9 Nat Pool Trialed, 9 Nat Pool Direct).
* **Tournaments Reconciled**: 9 (Chap's 26, SLSDC 26, VVIDC 26, Metho 26, Vijis 26, AISDC 26, APIIT ISDC 26, RIC 26, IDC).

---

## 12. Production Readiness & Developer Hand-Off Guide

Atomos is packaged, audited, and ready for immediate deployment or handover:

1. **Self-Contained Storage**: The entire system, database, and web export package is approximately **44 MB** and requires no external database server (SQLite 3.35+ is built into Python).
2. **Environment Portability**: Zero hardcoded drive letters or absolute operating system paths. Compatible with Windows, macOS, and Linux out of the box.
3. **Easy Setup**: New developers can run:
   ```bash
   git clone <repo-url>
   cd Atomos
   pip install -r requirements.txt
   pytest tests/
   ```
4. **Web Frontend Development**: Frontend developers can immediately consume:
   * Real-time endpoints via `python src/atomos/server.py`.
   * Static precomputed JSON payloads from `data/web_export/`.

---
*Report certified and compiled by Antigravity on September 13, 2026.*
