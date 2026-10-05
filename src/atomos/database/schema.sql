-- Atomos SQLite Database Schema (Fold 2)
-- Enforces foreign keys and strict relational integrity

PRAGMA foreign_keys = ON;

-- ============================================================================
-- 1. CREATOR PILLAR
-- ============================================================================

CREATE TABLE IF NOT EXISTS institutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,
    national_level TEXT CHECK(national_level IN ('Trials', 'Nat Pool, Trialed', 'Nat Pool, Direct', NULL)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS person_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    raw_name TEXT NOT NULL,
    source_tournament_id INTEGER REFERENCES tournaments(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(person_id, raw_name)
);

CREATE TABLE IF NOT EXISTS identity_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_name_a TEXT NOT NULL,
    raw_name_b TEXT NOT NULL,
    person_a_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    person_b_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING_REVIEW', 'CONFIRMED_MATCH', 'CONFIRMED_DIFFERENT')),
    confidence_score REAL DEFAULT 0.0,
    reason TEXT,
    reviewed_by_user INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP
);

-- ============================================================================
-- 2. CONTEXT PILLAR
-- ============================================================================

CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    version TEXT,
    year INTEGER,
    season TEXT CHECK(season IN ('1st Term', 'Mid Term', 'End Term', NULL)),
    scoring_scale TEXT DEFAULT '60-80',
    format TEXT DEFAULT 'PURE_OPEN' CHECK(format IN ('PURE_OPEN', 'PURE_NOVICE', 'NOVICE_AND_OPEN')),
    hosting_dates TEXT,
    extracted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tournament_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('DEBATER', 'ADJUDICATOR')),
    institution_id INTEGER REFERENCES institutions(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, person_id, role)
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    institution_id INTEGER REFERENCES institutions(id) ON DELETE SET NULL,
    category TEXT NOT NULL DEFAULT 'OPEN' CHECK(category IN ('OPEN', 'NOVICE')),
    source_team_id TEXT,
    raw_roster_text TEXT,
    canonical_name TEXT,
    tier TEXT CHECK(tier IN ('A', 'B', 'C', 'D', 'NOVICE', 'SWING', 'OTHER', NULL)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, name)
);

CREATE TABLE IF NOT EXISTS team_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    canonical_name TEXT NOT NULL,
    tier TEXT NOT NULL CHECK(tier IN ('A', 'B', 'C', 'D', 'NOVICE', 'SWING', 'OTHER')),
    institution_id INTEGER REFERENCES institutions(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'CONFIRMED' CHECK(status IN ('PENDING_REVIEW', 'CONFIRMED', 'REJECTED')),
    confidence REAL DEFAULT 1.0,
    reason TEXT,
    reviewed_by_user INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP,
    UNIQUE(team_id)
);

CREATE TABLE IF NOT EXISTS team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    member_order INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(team_id, person_id)
);

CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    round_type TEXT NOT NULL DEFAULT 'PRELIMINARY' CHECK(round_type IN ('PRELIMINARY', 'OCTOFINAL', 'QUARTERFINAL', 'SEMIFINAL', 'GRANDFINAL', 'ELIMINATION')),
    motion TEXT,
    info_slide TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, round_number)
);

CREATE TABLE IF NOT EXISTS debates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    debate_id TEXT NOT NULL,
    venue TEXT,
    prop_team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    opp_team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    is_walkover INTEGER DEFAULT 0,
    walkover_winner_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(round_id, debate_id)
);

CREATE TABLE IF NOT EXISTS adjudicator_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id INTEGER NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    is_chair INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(debate_id, person_id)
);

-- ============================================================================
-- 3. CREATION PILLAR (Atomic Performance & Scoresheets)
-- ============================================================================

CREATE TABLE IF NOT EXISTS adjudicator_ballots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id INTEGER NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    adjudicator_person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    adjudicator_raw_name TEXT,
    adjudicator_institution TEXT,
    prop_total_score REAL,
    opp_total_score REAL,
    win_margin REAL,
    winner_side TEXT CHECK(winner_side IN ('Proposition', 'Opposition', 'Tie', NULL)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS speech_performances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ballot_id INTEGER NOT NULL REFERENCES adjudicator_ballots(id) ON DELETE CASCADE,
    debate_id INTEGER NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    round_id INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    side TEXT NOT NULL CHECK(side IN ('Proposition', 'Opposition')),
    position TEXT NOT NULL CHECK(position IN ('1st', '2nd', '3rd', 'Reply')),
    speech_type TEXT NOT NULL CHECK(speech_type IN ('SUBSTANTIVE', 'REPLY')),
    total_score REAL NOT NULL,
    content REAL,
    style REAL,
    strategy REAL,
    is_valid_rubric INTEGER DEFAULT 1,
    is_iron_man INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 4. PROVENANCE & AUDIT PILLAR
-- ============================================================================

CREATE TABLE IF NOT EXISTS provenance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER REFERENCES tournaments(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    raw_json_path TEXT,
    extracted_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_persons_canonical ON persons(canonical_name);
CREATE INDEX IF NOT EXISTS idx_person_aliases_raw ON person_aliases(raw_name);
CREATE INDEX IF NOT EXISTS idx_teams_tournament ON teams(tournament_id);
CREATE INDEX IF NOT EXISTS idx_team_members_person ON team_members(person_id);
CREATE INDEX IF NOT EXISTS idx_debates_round ON debates(round_id);
CREATE INDEX IF NOT EXISTS idx_speech_person ON speech_performances(person_id);
CREATE INDEX IF NOT EXISTS idx_speech_debate ON speech_performances(debate_id);
CREATE INDEX IF NOT EXISTS idx_speech_round ON speech_performances(round_id);
CREATE INDEX IF NOT EXISTS idx_ballots_debate ON adjudicator_ballots(debate_id);
CREATE INDEX IF NOT EXISTS idx_debates_prop_team ON debates(prop_team_id);
CREATE INDEX IF NOT EXISTS idx_debates_opp_team ON debates(opp_team_id);
CREATE INDEX IF NOT EXISTS idx_speech_team ON speech_performances(team_id);
CREATE INDEX IF NOT EXISTS idx_rounds_tourn ON rounds(tournament_id);
CREATE INDEX IF NOT EXISTS idx_ballots_winner ON adjudicator_ballots(winner_side);
CREATE INDEX IF NOT EXISTS idx_institutions_name ON institutions(name);
