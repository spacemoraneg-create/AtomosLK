# ATOMOS DECISION LEDGER

Record important architectural and domain decisions here.

---

### ADR-001 — Programming Language: Python

Date: 2026-09-09

Status: Accepted

Decision:

Atomos will be built in Python.

Reason:

Python is the strongest language for data processing, has the best AI/LLM ecosystem, and is the most readable for a non-programmer project owner.

Consequences:

All application code, tests, and scripts will be in Python. The project will use standard Python tooling (pip/uv, pytest, etc.).

Affected areas:

All folds (Extractor, Database, Analytics, LLM, UI)

---

### ADR-002 — Database: SQLite (for first version)

Date: 2026-09-09

Status: Accepted

Decision:

The first version of Atomos will use SQLite as its database.

Reason:

SQLite is simple, requires no installation, lives in a single file, and is easy to back up and share. It handles everything Atomos needs for the first several phases. Migration to PostgreSQL is possible later if needed.

Consequences:

The database is a single file on disk. No database server to manage. Some advanced features (concurrent writes, full-text search) may be limited compared to PostgreSQL, but these are not needed yet.

Affected areas:

Database / Normalizer (Fold 2)

---

### ADR-003 — Deployment: Local only (for first version)

Date: 2026-09-09

Status: Accepted

Decision:

Atomos will run locally on the project owner's computer. No web server or cloud deployment for now.

Reason:

Keeps things simple. Focus is on getting the data foundation right, not on infrastructure.

Consequences:

No need for authentication, hosting, or networking. The eventual UI (Fold 5) can be a web application later.

Affected areas:

UI (Fold 5), deployment

---

### ADR-004 — Scoring Scale: New scale only (60–80)

Date: 2026-09-09

Status: Accepted

Decision:

Atomos will initially support only the new WSDC scoring scale (60–80 for substantive, 30–40 for reply), effective from January 2026.

Reason:

The project owner wants to start with current tournaments only. A scale mapping exists in `docs/debating/Scoring Scale.txt` for future support of the old scale (69–81).

Consequences:

Tournaments before January 2026 cannot be imported until old-scale support is added. The system should be designed so adding old-scale support later does not require a redesign.

Affected areas:

Extractor, Normalizer, Analytics

---

### ADR-005 — Identity Resolution: Manual with system assistance

Date: 2026-09-09

Status: Accepted

Decision:

Atomos will not automatically merge people or teams based on name similarity. When potential matches are detected (same school abbreviation, similar names), the system will present them to the project owner for manual resolution.

Reason:

Constitution §7 requires identity to be explicit and uncertainty representable. Tabbycat provides no cross-tournament person ID — only names that may be spelled differently.

Consequences:

The system needs an identity resolution workflow. Initial imports may require significant manual review. Identity decisions must be recorded and traceable.

Affected areas:

Normalizer (Fold 2), all downstream analytics

---

### ADR-006 — Single-Command Autonomous Pipeline Architecture

Date: 2026-09-09

Status: Accepted

Decision:

Tournament ingestion from Tabbycat is consolidated into a single autonomous pipeline (`src/atomos/pipeline/ingestion.py`) triggered via CLI (`scripts/import_tournament.py`). The pipeline deterministically executes: Extractor → Normalizer → Reconciler → Integrity Validator.

Reason:

Allows the founder to import new tournaments from the VS Code terminal without manual code execution or prompt engineering. Ensures all verification, out-round decision extraction, and forfeit classification steps are enforced identically across all tournaments.

Consequences:

Any new stage added to data processing must be integrated into `IngestionPipeline` so that the CLI tool automatically inherits it.

Affected areas:

Pipeline, Extractor, Normalizer, Reconciler, CLI tooling

---

### ADR-007 — Critical Stats Engine: Parallel High-Rigor Analytics

Date: 2026-09-09

Status: Accepted

Decision:

Atomos maintains a parallel analytics engine called "Critical Stats" (`src/atomos/analytics/critical_stats.py`) alongside the standard Master Tabs. Critical Stats enforces a strict participation threshold of $\ge 3$ tournaments ($\ge 9$ prelim rounds for debaters) and computes specific metrics:
- Individual: Substantive Average, Average Within-Tournament Deviation ($\sigma_t$), Win % when debating, Prelims debated, Break %.
- Team: Break %, Win %, Prop/Opp split, Total rounds, Break rounds, ATSS, Avg Win Margin.

Reason:

Filters out small sample sizes, one-off tournaments, and noise to provide high-confidence rankings for established debaters and teams on the circuit.

Consequences:

Debaters or teams with $<3$ tournaments are excluded from Critical Stats leaderboards, even if their isolated averages are high.

Affected areas:

Analytics Engine, Critical Stats, CLI Viewers

---

### ADR-008 — Interactive Terminal UX for End-User Operations

Date: 2026-09-09

Status: Accepted

Decision:

All user-facing scripts (e.g. tournament importers, manual patchers, tab viewers) must be interactive by default via standard terminal input (`input()`). The user must never be required to modify code, edit config files, or supply complex command-line arguments to perform standard operations.

Reason:

The project owner operates Atomos directly from the VS Code terminal but does not modify application code. Scripts must present friendly prompts, accept pasted links/strings, strip accidental quotes or whitespace, provide sensible defaults, and guide the user through each step.

Consequences:

Every CLI entrypoint must implement fallback prompts when arguments are missing.

Affected areas:

CLI scripts (`scripts/`), Pipeline, Documentation

---

No major architectural decision should be silently changed by the coding agent. If a new implementation conflicts with an accepted decision, the agent should report the conflict.

