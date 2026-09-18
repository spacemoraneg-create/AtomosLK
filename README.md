# Atomos: Sri Lankan WSDC Debating Intelligence Engine

**Atomos** is a high-precision, production-grade intelligence, analytics, and historical archive platform for the Sri Lankan World Schools Debating Championship (WSDC) circuit. It ingests, standardizes, models, and serves comprehensive data across competitive tournaments, speaker performances, team dynamics, motion balances, adjudicator behavior, and elimination brackets.

---

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [Installation & Quick Start](#installation--quick-start)
- [CLI Tools & Commands](#cli-tools--commands)
- [Headless REST API](#headless-rest-api)
- [Analytical Engines](#analytical-engines)
- [Precomputed Caching & Web Data Exports](#precomputed-caching--web-data-exports)
- [Automated Ingestion Pipeline](#automated-ingestion-pipeline)
- [Verification & Forensic Auditing](#verification--forensic-auditing)
- [Test Suite](#test-suite)

---

## Architecture Overview

Atomos operates on a 6-layer architecture designed for mathematical accuracy, relational integrity, and zero data hallucination:

```
[ Layer 1: Ingestion & Extraction ]
  Tabbycat Scraper -> JSON Normalizer -> Schema Validator
                 |
[ Layer 2: Entity Reconciliation & Normalization ]
  Debater Identity Merger -> Team Resolver -> School Canonicalization
                 |
[ Layer 3: Relational Database (SQLite) ]
  atomos.db: Tournaments | Institutions | Teams | Persons | Debates | Ballots | Speeches
                 |
[ Layer 4: Analytics & Modeling Engines ]
  Elo Ratings | Master Tabs | Critical Stats | Adjudicator Dossiers | Bracket Engine | Match Predictor
                 |
[ Layer 5: Access Layers & Headless REST API ]
  Flask Headless REST API (CORS Enabled) | Static Web Compiler (data/web_export/)
                 |
[ Layer 6: Autonomous LLM Agent & Tooling ]
  Gemini 2.5 Multi-Turn Reasoning Agent (18 Grounded Tool Functions)
```

---

## Installation & Quick Start

### Prerequisites
- Python **3.12** or higher
- SQLite 3.35+

### Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/debating-atomos/atomos.git
cd atomos
pip install -r requirements.txt
```

To configure Google Gemini AI features (optional for LLM agent):
Create a `.env` file in the project root:
```env
GEMINI_API_KEY="your-gemini-api-key-here"
GEMINI_MODEL="gemini-2.5-flash"
```

---

## CLI Tools & Commands

Atomos provides a suite of CLI tools for rapid analysis:

### 1. Debater Dossier & Trajectory
Inspect a debater's career record, institutional affiliation, tournament-by-tournament breakdown, national status, and chronological performance trajectory:
```bash
python scripts/view_identity.py "Balishta Wijesinghe"
python scripts/view_identity.py 42 --full
```

### 2. Adjudicator Intelligence Dossier
Examine an adjudicator's side bias (Prop vs Opp win %), scoring strictness relative to national benchmark (71.20 pts), average win margin, and outround panel history:
```bash
# View judge dossier
python scripts/view_judge.py "Minithi Hewage"

# View national adjudicator leaderboard
python scripts/view_judge.py --top 20 --sort debates
python scripts/view_judge.py --top 10 --sort margin
```

### 3. Match Simulation & Predictive Clash
Simulate a competitive debate clash between two teams using Elo ratings, team ATSS, and national talent density:
```bash
python scripts/ask_atomos.py "Simulate a debate between DS A and RC A"
```

### 4. Head-to-Head Clash Analysis
Compare two institutions, teams, or debaters across direct matchups and mutual rivals:
```bash
# School vs School
python scripts/compare_schools.py "RC" "AC"

# Team vs Team or School vs School with detailed breakdown
python scripts/head_to_head.py "Royal" "Ananda" --school
```

### 5. Multi-Metric Critical Stats & Leaderboards
Display high-rigor statistical rankings across debaters and institutions:
```bash
# Speaker rankings with National Status
python scripts/view_critical_stats.py --limit 25

# Institutional Power Index (IPI)
python scripts/institutional_leaderboard.py --top 20

# Full National Circuit Report
python scripts/circuit_report.py --top 10
```

### 6. Interactive AI Debating Console
Chat with the Atomos Gemini Agent grounded directly in `atomos.db`:
```bash
python scripts/ask_atomos.py --chat
```

---

## Headless REST API

Atomos includes a CORS-enabled REST API ready for web frontends (Next.js, React, Vue, Svelte):

```bash
# Launch the local REST API server (default: port 5000)
python src/atomos/server.py --port 5000
```

### Core API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Service status, active database state, record count |
| `POST` | `/api/ask` | Natural language conversational query interface |
| `GET` | `/api/search?q=...` | Unified search across debaters, institutions, and teams |
| `GET` | `/api/debaters/<id>/profile` | Comprehensive debater profile with chronological trajectory |
| `GET` | `/api/leaderboard/speakers` | Multi-metric speaker tab (`metric=master_tab`, `prelims`, `debates`) |
| `GET` | `/api/tournaments/<slug>/bracket`| Tournament elimination knockout tree (Octos -> Grand Final) |
| `GET` | `/api/judges/<identifier>` | Adjudicator intelligence dossier |
| `GET` | `/api/judges?limit=...` | National judge leaderboard |
| `GET` | `/api/predict?team_a=...&team_b=...`| Match predictive simulation with win probabilities |
| `GET` | `/api/national-pool` | Complete 27-debater national squad registry |
| `GET` | `/api/debates/<debate_id>` | Detailed debate scoresheet and adjudicator ballots |
| `GET` | `/api/institutions` | Institutional Power Index leaderboard |
| `GET` | `/api/motions/summary` | Circuit-wide motion analytics and side balance |

---

## Analytical Engines

1. **Master Speaker & Reply Tabs (`MasterTabEngine`)**:
   - Computes weighted speaker averages, prelim qualifying thresholds (minimum 3 substantive rounds), and reply tab standings.
2. **Critical Statistics Engine (`CriticalStatsEngine`)**:
   - Measures multi-tournament standard deviation, debate conversion efficiency, floor/ceiling metrics, and outround break rates.
3. **Squad & Debater Ratings (`EloRatingEngine`)**:
   - Zero-sum Elo rating calculation with dynamic K-factor adjustments based on win margins and tournament importance.
4. **Adjudicator Intelligence (`JudgeAnalyticsEngine`)**:
   - Objective calculation of judge scoring tendencies, side favoritism, and blowout propensities.
5. **Tournament Knockout Engine (`BracketEngine`)**:
   - Reconstructs hierarchical elimination brackets, individual matchup lineups, split decisions, and closeouts.
6. **Predictive Clash Simulator (`MatchPredictor`)**:
   - Multi-factor model combining Elo ratings (50%), team ATSS (35%), and national talent density (15%).

---

## Precomputed Caching & Web Data Exports

Atomos features a precomputed SQLite cache (`precomputed_cache`) and a static web exporter that generates production-ready JSON files in `data/web_export/`:

```bash
# Recompile and export all static datasets and tournament brackets
python scripts/export_web_data.py
```

Generated static web assets include:
- `data/web_export/master_speaker_tab.json`
- `data/web_export/master_reply_tab.json`
- `data/web_export/critical_speaker_stats.json`
- `data/web_export/institutional_power_index.json`
- `data/web_export/judge_leaderboard.json`
- `data/web_export/national_pool.json`
- `data/web_export/circuit_summary.json`
- Individual bracket trees: `chaps2026_bracket.json`, `slsdc26_bracket.json`, `vvidc2026_bracket.json`, etc.

---

## Automated Ingestion Pipeline

To import a new tournament spreadsheet or live Tabbycat URL with 1 click:
```bash
python scripts/ingest_circuit_tournament.py "https://site.calicotab.com/slug/" --refresh-cache
```
This automatically extracts raw tab data, maps institutional identities, enforces WSDC rubric constraints, executes the 5-gate audit, updates precomputed caches, and re-exports the static web datasets.

---

## Verification & Forensic Auditing

Atomos enforces a 5-Gate Master Forensic Integrity Audit with 48 automated checks across relational constraints, scoring math, ground truth reconciliation, and analytical models:

```bash
python scripts/master_audit.py
```

**Quality Gates Audited:**
- Gate 1: Schema & Relational Integrity (zero orphaned foreign keys).
- Gate 2: Debate & Roster Invariants (unique registrations, walkover consistency).
- Gate 3: Scoring Math & Rubric Invariants (substantive scores 60-80, replies 30-40, correct ballot summing).
- Gate 4: Ground Truth Tab Reconciliation (exact match against official Tabbycat tabs).
- Gate 5: Analytical Engine Invariants (all leaderboards monotonic and mathematically sound).

---

## Test Suite

Run the full automated test suite covering all modules, analytics, and endpoints:
```bash
pytest tests/
```
Current test suite status: **181 / 181 passing (100%)**.
