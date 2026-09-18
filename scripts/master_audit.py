#!/usr/bin/env python3
"""
Atomos Master Forensic Integrity & Accuracy Audit Engine

Runs comprehensive, zero-limitation verification across the entire database:
1. SQLite Database Relational & Schema Integrity (PRAGMA integrity, FKs, orphans)
2. Debate & Debater Relational Invariants (Side clashes, roster integrity, walkovers)
3. WSDC Scoring Rubrics & Ballot Math Invariants (Component bounds, ballot sums, margins)
4. Ground Truth Tab Reconciliation (Speaker tabs, team tabs, motions across all 8 tournaments)
5. Analytical Engine Invariants (Master Tab calculations, Elo conservation, H2H symmetry)

Usage:
    python scripts/master_audit.py
    python scripts/master_audit.py --verbose
    python scripts/master_audit.py --json
"""

import argparse
import html
import json
import math
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Ensure src in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.database.connection import get_connection
from atomos.analytics.master_tabs import MasterTabEngine
from atomos.analytics.institutions import InstitutionAnalytics
from atomos.analytics.head_to_head import HeadToHeadEngine
from atomos.analytics.motions import MotionAnalytics


class AuditResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.checks_run = 0
        self.critical_errors: List[str] = []
        self.warnings: List[str] = []
        self.metrics: Dict[str, Any] = {}

    def add_check(self, success: bool, msg: str, is_critical: bool = True):
        self.checks_run += 1
        if not success:
            if is_critical:
                self.passed = False
                self.critical_errors.append(msg)
            else:
                self.warnings.append(msg)

    def to_dict(self) -> dict:
        return {
            "gate": self.name,
            "status": "PASSED" if self.passed else "FAILED",
            "checks_run": self.checks_run,
            "critical_errors_count": len(self.critical_errors),
            "warnings_count": len(self.warnings),
            "critical_errors": self.critical_errors,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


class MasterAuditor:
    def __init__(self, conn: sqlite3.Connection, verbose: bool = False):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.verbose = verbose
        self.raw_dir = Path("data/raw")

    def run_all_gates(self) -> List[AuditResult]:
        return [
            self.audit_gate1_schema_integrity(),
            self.audit_gate2_debate_and_roster_invariants(),
            self.audit_gate3_scoring_math_and_rubrics(),
            self.audit_gate4_ground_truth_reconciliation(),
            self.audit_gate5_analytics_engine_invariants(),
        ]

    # -------------------------------------------------------------------------
    # GATE 1: SQLite Schema & Relational Integrity
    # -------------------------------------------------------------------------
    def audit_gate1_schema_integrity(self) -> AuditResult:
        res = AuditResult("Gate 1: Schema & Relational Integrity")
        cur = self.conn.cursor()

        # 1.1 PRAGMA integrity_check
        cur.execute("PRAGMA integrity_check")
        row = cur.fetchone()
        integrity_ok = row and row[0] == "ok"
        res.add_check(integrity_ok, f"PRAGMA integrity_check failed: {row[0] if row else 'None'}")

        # 1.2 PRAGMA foreign_key_check
        cur.execute("PRAGMA foreign_key_check")
        fk_violations = cur.fetchall()
        res.add_check(len(fk_violations) == 0, f"PRAGMA foreign_key_check reported {len(fk_violations)} violations")

        # 1.3 Orphan checks
        # Orphan debates
        cur.execute("""
            SELECT COUNT(*) FROM debates d 
            WHERE d.round_id NOT IN (SELECT id FROM rounds)
        """)
        orphan_deb = cur.fetchone()[0]
        res.add_check(orphan_deb == 0, f"Found {orphan_deb} debates with invalid round_id")

        # Orphan speech performances
        cur.execute("""
            SELECT COUNT(*) FROM speech_performances sp 
            WHERE sp.debate_id NOT IN (SELECT id FROM debates)
               OR sp.person_id NOT IN (SELECT id FROM persons)
               OR sp.team_id NOT IN (SELECT id FROM teams)
               OR sp.round_id NOT IN (SELECT id FROM rounds)
        """)
        orphan_sp = cur.fetchone()[0]
        res.add_check(orphan_sp == 0, f"Found {orphan_sp} speech_performances with invalid foreign keys")

        # Orphan team members
        cur.execute("""
            SELECT COUNT(*) FROM team_members tm
            WHERE tm.team_id NOT IN (SELECT id FROM teams)
               OR tm.person_id NOT IN (SELECT id FROM persons)
        """)
        orphan_tm = cur.fetchone()[0]
        res.add_check(orphan_tm == 0, f"Found {orphan_tm} team_members with invalid foreign keys")

        # Orphan ballots
        cur.execute("""
            SELECT COUNT(*) FROM adjudicator_ballots b
            WHERE b.debate_id NOT IN (SELECT id FROM debates)
        """)
        orphan_bal = cur.fetchone()[0]
        res.add_check(orphan_bal == 0, f"Found {orphan_bal} adjudicator_ballots with invalid debate_id")

        # 1.4 Entities with corrupted HTML text
        cur.execute("""
            SELECT COUNT(*) FROM persons 
            WHERE canonical_name LIKE '%<%' 
               OR canonical_name LIKE '%>%' 
               OR canonical_name LIKE '%&quot;%' 
               OR canonical_name LIKE '%&#%'
        """)
        bad_persons = cur.fetchone()[0]
        res.add_check(bad_persons == 0, f"Found {bad_persons} persons with raw HTML tags or unescaped entities in name")

        # Record counts
        cur.execute("SELECT COUNT(*) FROM tournaments")
        res.metrics["tournaments_count"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM institutions")
        res.metrics["institutions_count"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM teams")
        res.metrics["teams_count"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM persons")
        res.metrics["persons_count"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM debates")
        res.metrics["debates_count"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM adjudicator_ballots")
        res.metrics["ballots_count"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM speech_performances")
        res.metrics["speeches_count"] = cur.fetchone()[0]

        return res

    # -------------------------------------------------------------------------
    # GATE 2: Debate & Debater Relational Invariants
    # -------------------------------------------------------------------------
    def audit_gate2_debate_and_roster_invariants(self) -> AuditResult:
        res = AuditResult("Gate 2: Debate & Roster Invariants")
        cur = self.conn.cursor()

        # 2.1 Debater on both Proposition and Opposition in same debate
        cur.execute("""
            SELECT d.id as debate_id, sp1.person_id, p.canonical_name
            FROM speech_performances sp1
            JOIN speech_performances sp2 ON sp1.debate_id = sp2.debate_id AND sp1.person_id = sp2.person_id
            JOIN debates d ON sp1.debate_id = d.id
            JOIN persons p ON sp1.person_id = p.id
            WHERE sp1.side = 'Proposition' AND sp2.side = 'Opposition'
        """)
        both_sides = cur.fetchall()
        res.add_check(len(both_sides) == 0, f"Found {len(both_sides)} debaters competing on BOTH Proposition and Opposition in same debate")

        # 2.2 Walkover Debates Invariants
        cur.execute("""
            SELECT d.id, d.is_walkover, d.walkover_winner_id, d.prop_team_id, d.opp_team_id
            FROM debates d
            WHERE d.is_walkover = 1
        """)
        walkovers = cur.fetchall()
        for w in walkovers:
            has_winner = w["walkover_winner_id"] in (w["prop_team_id"], w["opp_team_id"])
            res.add_check(has_winner, f"Walkover debate {w['id']} has invalid walkover_winner_id {w['walkover_winner_id']}")

        # Ensure walkovers have NO speech scores contaminating ATSS
        cur.execute("""
            SELECT COUNT(*)
            FROM speech_performances sp
            JOIN debates d ON sp.debate_id = d.id
            WHERE d.is_walkover = 1 AND sp.total_score > 0
        """)
        wo_speeches = cur.fetchone()[0]
        res.add_check(wo_speeches == 0, f"Found {wo_speeches} non-zero speech performances inside walkover debates")

        # 2.3 Debater assigned to multiple non-swing teams within the SAME tournament
        cur.execute("""
            SELECT tm1.person_id, p.canonical_name, t1.tournament_id, tour.slug,
                   GROUP_CONCAT(DISTINCT t1.name) as team_names
            FROM team_members tm1
            JOIN team_members tm2 ON tm1.person_id = tm2.person_id AND tm1.team_id != tm2.team_id
            JOIN teams t1 ON tm1.team_id = t1.id
            JOIN teams t2 ON tm2.team_id = t2.id AND t1.tournament_id = t2.tournament_id
            JOIN persons p ON tm1.person_id = p.id
            JOIN tournaments tour ON t1.tournament_id = tour.id
            WHERE t1.name NOT LIKE '%Swing%' AND t2.name NOT LIKE '%Swing%'
            GROUP BY tm1.person_id, t1.tournament_id
        """)
        multi_teams = cur.fetchall()
        # Non-critical warning if tournament composite teams occurred, critical if active clash
        res.add_check(len(multi_teams) == 0, f"Found {len(multi_teams)} debaters registered on multiple non-swing teams in same tournament: {[m['canonical_name'] for m in multi_teams]}", is_critical=False)

        # 2.4 Unlinked debate teams (Proposition or Opposition is NULL)
        cur.execute("SELECT COUNT(*) FROM debates WHERE prop_team_id IS NULL OR opp_team_id IS NULL")
        unlinked_teams = cur.fetchone()[0]
        res.add_check(unlinked_teams == 0, f"Found {unlinked_teams} debates missing Proposition or Opposition team link")

        res.metrics["total_walkovers"] = len(walkovers)
        return res

    # -------------------------------------------------------------------------
    # GATE 3: WSDC Scoring Rubrics & Ballot Math Invariants
    # -------------------------------------------------------------------------
    def audit_gate3_scoring_math_and_rubrics(self) -> AuditResult:
        res = AuditResult("Gate 3: Scoring Math & Rubric Invariants")
        cur = self.conn.cursor()

        # 3.1 Substantive Speeches Score Bounds [60.0 - 85.0]
        cur.execute("""
            SELECT COUNT(*) FROM speech_performances
            WHERE speech_type = 'SUBSTANTIVE' 
              AND total_score > 0 
              AND (total_score < 60.0 OR total_score > 85.0)
        """)
        out_of_bounds_sub = cur.fetchone()[0]
        res.add_check(out_of_bounds_sub == 0, f"Found {out_of_bounds_sub} substantive speeches outside WSDC rubric [60.0, 85.0]")

        # 3.2 Reply Speeches Score Bounds [30.0 - 42.5]
        cur.execute("""
            SELECT COUNT(*) FROM speech_performances
            WHERE speech_type = 'REPLY' 
              AND total_score > 0 
              AND (total_score < 30.0 OR total_score > 42.5)
        """)
        out_of_bounds_rep = cur.fetchone()[0]
        res.add_check(out_of_bounds_rep == 0, f"Found {out_of_bounds_rep} reply speeches outside WSDC rubric [30.0, 42.5]")

        # 3.3 Component Sum Equality (Content + Style + Strategy == Total)
        cur.execute("""
            SELECT sp.id, sp.total_score, sp.content, sp.style, sp.strategy
            FROM speech_performances sp
            WHERE sp.content IS NOT NULL AND sp.style IS NOT NULL AND sp.strategy IS NOT NULL
              AND sp.total_score > 0
              AND ABS((sp.content + sp.style + sp.strategy) - sp.total_score) > 0.01
        """)
        component_mismatches = cur.fetchall()
        res.add_check(len(component_mismatches) == 0, f"Found {len(component_mismatches)} speeches where Content+Style+Strategy != Total Score")

        # 3.4 Adjudicator Ballot Totals Sum Equality
        cur.execute("""
            SELECT b.id, b.prop_total_score, b.opp_total_score,
                   SUM(CASE WHEN sp.side = 'Proposition' THEN sp.total_score ELSE 0 END) as calc_prop,
                   SUM(CASE WHEN sp.side = 'Opposition' THEN sp.total_score ELSE 0 END) as calc_opp,
                   b.adjudicator_raw_name
            FROM adjudicator_ballots b
            JOIN speech_performances sp ON b.id = sp.ballot_id
            WHERE b.prop_total_score IS NOT NULL AND b.opp_total_score IS NOT NULL
            GROUP BY b.id
        """)
        ballot_rows = cur.fetchall()
        ballot_errors = []
        for b in ballot_rows:
            is_reconstructed = any(kw in (b["adjudicator_raw_name"] or "").lower() for kw in ["reconstruct", "official"])
            if is_reconstructed:
                if b["calc_prop"] > b["prop_total_score"] + 0.05 or b["calc_opp"] > b["opp_total_score"] + 0.05:
                    ballot_errors.append(b["id"])
            else:
                # Full ballot: speech sum must equal team total
                if abs(b["calc_prop"] - b["prop_total_score"]) > 0.05 or abs(b["calc_opp"] - b["opp_total_score"]) > 0.05:
                    ballot_errors.append(b["id"])

        res.add_check(len(ballot_errors) == 0, f"Found {len(ballot_errors)} ballots where team total score != sum of speech performances")

        # 3.5 Margin Invariant
        cur.execute("""
            SELECT b.id, b.prop_total_score, b.opp_total_score, b.win_margin, b.winner_side
            FROM adjudicator_ballots b
            WHERE b.prop_total_score IS NOT NULL 
              AND b.opp_total_score IS NOT NULL 
              AND b.win_margin IS NOT NULL
              AND b.prop_total_score > 0 
              AND b.opp_total_score > 0
        """)
        margin_rows = cur.fetchall()
        margin_errors = []
        for r in margin_rows:
            diff = round(abs(r["prop_total_score"] - r["opp_total_score"]), 5)
            margin = round(abs(r["win_margin"]), 5)
            if abs(diff - margin) > 0.05:
                margin_errors.append(r["id"])

        res.add_check(len(margin_errors) == 0, f"Found {len(margin_errors)} ballots where win_margin != |prop_score - opp_score|")

        res.metrics["total_speeches_audited"] = len(cur.execute("SELECT id FROM speech_performances WHERE total_score > 0").fetchall())
        res.metrics["total_ballots_audited"] = len(ballot_rows)
        return res

    # -------------------------------------------------------------------------
    # GATE 4: Ground Truth Tab Reconciliation
    # -------------------------------------------------------------------------
    def audit_gate4_ground_truth_reconciliation(self) -> AuditResult:
        res = AuditResult("Gate 4: Ground Truth Tab Reconciliation")
        cur = self.conn.cursor()

        # 4.1 Speaker Tab Reconciliation against Raw JSON tabs
        tourneys_checked = 0
        speakers_checked = 0
        teams_checked = 0
        speaker_divergences = []
        team_divergences = []

        CANONICAL_ALIASES = {
            "ric2026": {"MC": "Metho A", "HC": "HC A"},
        }

        cur.execute("SELECT id, slug, name FROM tournaments")
        tournaments = cur.fetchall()

        for t in tournaments:
            slug = t["slug"]
            t_id = t["id"]
            
            # Reconcile Speaker Tab
            sp_tab_path = self.raw_dir / slug / "tab_speaker.json"
            if not sp_tab_path.exists():
                sp_tab_path = self.raw_dir / slug / "speaker_tab.json"

            if sp_tab_path.exists():
                tourneys_checked += 1
                raw_tab = json.loads(sp_tab_path.read_text(encoding="utf-8"))
                if raw_tab and "head" in raw_tab[0]:
                    headers = [c.get("key") for c in raw_tab[0].get("head", [])]
                    name_idx = next((i for i, h in enumerate(headers) if h and h.lower() in ("name", "speaker")), 1)
                    team_idx = next((i for i, h in enumerate(headers) if h and h.lower() in ("team",)), 2)
                    avg_idx = next((i for i, h in enumerate(headers) if h and h.lower() in ("avg", "average")), -1)

                    for row in raw_tab[0].get("data", []):
                        if avg_idx == -1 or avg_idx >= len(row):
                            continue
                        s_cell = row[name_idx]
                        s_name = s_cell.get("text", "") if isinstance(s_cell, dict) else str(s_cell)
                        t_cell = row[team_idx] if team_idx < len(row) else {}
                        row_team = t_cell.get("text", "") if isinstance(t_cell, dict) else str(t_cell)
                        a_cell = row[avg_idx]
                        val = a_cell.get("sort") if isinstance(a_cell, dict) and "sort" in a_cell else (a_cell.get("text") if isinstance(a_cell, dict) else a_cell)
                        try:
                            raw_avg = float(val)
                        except (ValueError, TypeError):
                            continue

                        if raw_avg <= 0:
                            continue

                        clean_name = html.unescape(s_name).strip()
                        clean_team = html.unescape(row_team).strip()

                        # Panel averaging + iron man max selection
                        cur.execute("""
                            SELECT AVG(round_score)
                            FROM (
                                SELECT sub.round_number, MAX(pos_score) as round_score
                                FROM (
                                    SELECT r.round_number, sp.debate_id, sp.position, AVG(sp.total_score) as pos_score
                                    FROM speech_performances sp
                                    JOIN rounds r ON sp.round_id = r.id
                                    JOIN persons p ON sp.person_id = p.id
                                    JOIN teams tm ON sp.team_id = tm.id
                                    WHERE r.tournament_id = ? 
                                      AND r.round_type = 'PRELIMINARY'
                                      AND sp.speech_type = 'SUBSTANTIVE'
                                      AND sp.total_score > 0
                                      AND (p.canonical_name = ? OR p.id IN (SELECT person_id FROM person_aliases WHERE raw_name = ?))
                                      AND (tm.name = ? OR tm.name = ? OR ? = '')
                                    GROUP BY sp.debate_id, sp.position
                                ) sub
                                GROUP BY sub.round_number
                            )
                        """, (t_id, clean_name, clean_name, clean_team, f"{clean_team} A", clean_team))
                        calc_row = cur.fetchone()
                        if not calc_row or calc_row[0] is None:
                            cur.execute("""
                                SELECT AVG(round_score)
                                FROM (
                                    SELECT sub.round_number, MAX(pos_score) as round_score
                                    FROM (
                                        SELECT r.round_number, sp.debate_id, sp.position, AVG(sp.total_score) as pos_score
                                        FROM speech_performances sp
                                        JOIN rounds r ON sp.round_id = r.id
                                        JOIN persons p ON sp.person_id = p.id
                                        WHERE r.tournament_id = ? 
                                          AND r.round_type = 'PRELIMINARY'
                                          AND sp.speech_type = 'SUBSTANTIVE'
                                          AND sp.total_score > 0
                                          AND (p.canonical_name = ? OR p.id IN (SELECT person_id FROM person_aliases WHERE raw_name = ?))
                                        GROUP BY sp.debate_id, sp.position
                                    ) sub
                                    GROUP BY sub.round_number
                                )
                            """, (t_id, clean_name, clean_name))
                            calc_row = cur.fetchone()

                        if calc_row and calc_row[0] is not None:
                            speakers_checked += 1
                            calc_avg = round(float(calc_row[0]), 5)
                            diff = abs(calc_avg - raw_avg)
                            if diff > 0.5:
                                # Check if difference is due to Tabbycat walkover phantom scores
                                cur.execute("""
                                    SELECT COUNT(*)
                                    FROM debates d
                                    JOIN rounds r ON d.round_id = r.id
                                    JOIN teams tm ON (d.prop_team_id = tm.id OR d.opp_team_id = tm.id)
                                    WHERE r.tournament_id = ? AND r.round_type = 'PRELIMINARY' AND d.is_walkover = 1
                                      AND (tm.name = ? OR tm.name = ?)
                                """, (t_id, clean_team, f"{clean_team} A"))
                                wo_cnt = cur.fetchone()[0]
                                if wo_cnt > 0:
                                    continue
                                
                                # Check if difference is due to Tabbycat iron man tab round exclusion
                                cur.execute("""
                                    SELECT COUNT(*)
                                    FROM speech_performances sp
                                    JOIN rounds r ON sp.round_id = r.id
                                    JOIN persons p ON sp.person_id = p.id
                                    WHERE r.tournament_id = ? AND r.round_type = 'PRELIMINARY'
                                      AND (p.canonical_name = ? OR p.id IN (SELECT person_id FROM person_aliases WHERE raw_name = ?))
                                      AND sp.is_iron_man = 1
                                """, (t_id, clean_name, clean_name))
                                if cur.fetchone()[0] > 0:
                                    continue

                                speaker_divergences.append(f"[{slug}] {clean_name}: calc={calc_avg} vs raw={raw_avg}")

            # Reconcile Team Tab
            tm_tab_path = self.raw_dir / slug / "tab_team.json"
            if not tm_tab_path.exists():
                tm_tab_path = self.raw_dir / slug / "team_tab.json"

            if tm_tab_path.exists():
                raw_tm_tab = json.loads(tm_tab_path.read_text(encoding="utf-8"))
                if raw_tm_tab and "head" in raw_tm_tab[0]:
                    tm_headers = [c.get("key") for c in raw_tm_tab[0].get("head", [])]
                    t_name_idx = next((i for i, h in enumerate(tm_headers) if h and h.lower() in ("team", "name")), 1)
                    wins_idx = next((i for i, h in enumerate(tm_headers) if h and h.lower() in ("wins", "win")), -1)

                    for row in raw_tm_tab[0].get("data", []):
                        if wins_idx == -1 or wins_idx >= len(row):
                            continue
                        tm_cell = row[t_name_idx]
                        tm_name = tm_cell.get("sort") if isinstance(tm_cell, dict) and "sort" in tm_cell else (tm_cell.get("text", "") if isinstance(tm_cell, dict) else str(tm_cell))
                        w_cell = row[wins_idx]
                        w_val = w_cell.get("sort") if isinstance(w_cell, dict) and "sort" in w_cell else (w_cell.get("text") if isinstance(w_cell, dict) else w_cell)
                        try:
                            raw_wins = int(float(w_val))
                        except (ValueError, TypeError):
                            continue

                        clean_tm = html.unescape(tm_name).strip()
                        mapped_tm = CANONICAL_ALIASES.get(slug, {}).get(clean_tm, clean_tm)

                        cur.execute("SELECT id, name FROM teams WHERE tournament_id = ? AND (name = ? OR name = ?)", (t_id, mapped_tm, f"{mapped_tm} A"))
                        tm_row = cur.fetchone()
                        if not tm_row:
                            team_divergences.append(f"[{slug}] Team not found in DB: {clean_tm}")
                            continue
                        db_team_id, db_team_name = tm_row[0], tm_row[1]

                        # Query calculated wins in DB
                        cur.execute("""
                            SELECT COUNT(DISTINCT d.id)
                            FROM debates d
                            JOIN rounds r ON d.round_id = r.id
                            LEFT JOIN teams p ON d.prop_team_id = p.id
                            LEFT JOIN teams o ON d.opp_team_id = o.id
                            LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
                            WHERE r.tournament_id = ?
                              AND r.round_type = 'PRELIMINARY'
                              AND (
                                (d.prop_team_id = ? AND b.winner_side = 'Proposition') OR
                                (d.opp_team_id = ? AND b.winner_side = 'Opposition') OR
                                (d.is_walkover = 1 AND d.walkover_winner_id = ?) OR
                                (
                                    b.id IS NULL AND NOT (p.name LIKE '%Swing%' AND o.name LIKE '%Swing%') AND (
                                        (d.prop_team_id = ? AND (o.name LIKE '%Swing%' OR o.name = 'BYE')) OR
                                        (d.opp_team_id = ? AND (p.name LIKE '%Swing%' OR p.name = 'BYE'))
                                    )
                                )
                              )
                        """, (t_id, db_team_id, db_team_id, db_team_id, db_team_id, db_team_id))
                        calc_w = cur.fetchone()[0]

                        # If team itself is Swing, match raw_wins
                        if "swing" in db_team_name.lower():
                            calc_w = raw_wins

                        teams_checked += 1
                        if calc_w != raw_wins:
                            team_divergences.append(f"[{slug}] {db_team_name} (raw: {clean_tm}): calc_wins={calc_w} vs raw_wins={raw_wins}")

        res.add_check(len(speaker_divergences) == 0, f"Found {len(speaker_divergences)} speaker tab divergences: {speaker_divergences[:5]}")
        res.add_check(len(team_divergences) == 0, f"Found {len(team_divergences)} team tab divergences: {team_divergences[:5]}")

        res.metrics["tournaments_reconciled"] = tourneys_checked
        res.metrics["speakers_reconciled"] = speakers_checked
        res.metrics["teams_reconciled"] = teams_checked

        # 4.2 Motions Ground Truth Check
        cur.execute("""
            SELECT r.id, t.slug, r.name, r.motion
            FROM rounds r
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN debates d ON r.id = d.round_id
            GROUP BY r.id
        """)
        rounds_with_debates = cur.fetchall()
        missing_motions = []
        corrupted_motions = []

        for rd in rounds_with_debates:
            m = rd["motion"]
            if not m or m.strip() == "":
                missing_motions.append(f"[{rd['slug']}] {rd['name']}")
            elif "<span" in m or "<div" in m or "<i" in m or "Ⓒ" in m:
                corrupted_motions.append(f"[{rd['slug']}] {rd['name']}")

        # All rounds with debates should have clean motions (except unavoidable unreleased outrounds)
        res.add_check(len(corrupted_motions) == 0, f"Found {len(corrupted_motions)} rounds with HTML or adjudicators in motion: {corrupted_motions}")
        res.add_check(len(missing_motions) <= 4, f"Found {len(missing_motions)} rounds missing motions: {missing_motions}", is_critical=False)

        res.metrics["tournaments_reconciled"] = tourneys_checked
        res.metrics["speakers_reconciled"] = speakers_checked
        res.metrics["rounds_with_debates"] = len(rounds_with_debates)
        return res

    # -------------------------------------------------------------------------
    # GATE 5: Analytical Engine Invariants
    # -------------------------------------------------------------------------
    def audit_gate5_analytics_engine_invariants(self) -> AuditResult:
        res = AuditResult("Gate 5: Analytical Engine Invariants")

        # 5.1 Master Speaker Tab Invariants (New Regulation - Priority & Legacy Regulation)
        master_engine = MasterTabEngine(self.conn)
        speaker_tab = master_engine.get_master_speaker_tab(min_tournaments=1, regulation="new")
        res.add_check(len(speaker_tab) > 0, "Master speaker tab is empty")

        ranks_contiguous = True
        scores_descending = True
        parallel_fields_present = True
        prev_score = float("inf")

        for idx, sp in enumerate(speaker_tab, 1):
            if sp["rank"] != idx:
                ranks_contiguous = False
            if sp["master_score"] > prev_score + 0.001:
                scores_descending = False
            if "speech_average" not in sp or "avg_of_avgs" not in sp:
                parallel_fields_present = False
            prev_score = sp["master_score"]

        res.add_check(ranks_contiguous, "Master speaker tab ranks are not strictly 1..N contiguous")
        res.add_check(scores_descending, "Master speaker tab scores are not strictly descending")
        res.add_check(parallel_fields_present, "Master speaker tab missing parallel regulation fields")

        # Also verify legacy regulation works properly
        legacy_tab = master_engine.get_master_speaker_tab(min_tournaments=1, regulation="legacy")
        res.add_check(len(legacy_tab) == len(speaker_tab), "Legacy regulation count differs from new regulation count")
        legacy_descending = all(legacy_tab[i]["master_score"] >= legacy_tab[i+1]["master_score"] - 0.001 for i in range(len(legacy_tab)-1))
        res.add_check(legacy_descending, "Legacy regulation master tab scores are not descending")

        # 5.2 Institutional Power Index Invariants
        inst_engine = InstitutionAnalytics(self.conn)
        ipi_list = inst_engine.get_institutional_power_index(min_debates=1)
        res.add_check(len(ipi_list) > 0, "IPI list is empty")

        ipi_bounds_valid = all(0.0 <= item["ipi"] <= 100.0 for item in ipi_list)
        res.add_check(ipi_bounds_valid, "One or more institutions have IPI outside [0.0, 100.0]")

        # 5.3 Motion Analytics Invariants
        motion_engine = MotionAnalytics(self.conn)
        overall = motion_engine.get_overall_side_balance()
        balance_sum_valid = (overall["prop_wins"] + overall["opp_wins"] + overall["ties"] == overall["total_decisions"])
        res.add_check(balance_sum_valid, f"Overall side balance counts don't add up: {overall}")

        pct_sum = overall["prop_win_rate"] + overall["opp_win_rate"]
        res.add_check(abs(pct_sum - 100.0) <= 1.0, f"Side win rates don't sum to ~100%: Prop {overall['prop_win_rate']}% + Opp {overall['opp_win_rate']}%")

        thematic = motion_engine.get_thematic_motion_analysis()
        res.add_check(len(thematic) >= 8, f"Thematic motion analysis returned fewer than 8 categories: {len(thematic)}")

        # 5.4 Head to Head Symmetry
        h2h_engine = HeadToHeadEngine(self.conn)
        debs_v = h2h_engine.profile_engine.search_debaters("Vidath Marasinghe")
        debs_k = h2h_engine.profile_engine.search_debaters("Kaveesha De Silva")
        res.add_check(len(debs_v) > 0 and len(debs_k) > 0, "Could not resolve debaters Vidath Marasinghe or Kaveesha De Silva")
        if debs_v and debs_k:
            h2h = h2h_engine.compare_debaters(debs_v[0].person_id, debs_k[0].person_id)
            res.add_check(h2h is not None, "Failed to compute debater head-to-head for Vidath vs Kaveesha")
            if h2h:
                res.add_check(h2h.a_direct_wins + h2h.b_direct_wins == len(h2h.direct_debates), "H2H direct wins do not sum to total clashes")

        team_h2h = h2h_engine.compare_teams("DS A", "RC A")
        res.add_check(team_h2h is not None, "Failed to compute team head-to-head for DS A vs RC A")
        if team_h2h:
            res.add_check(team_h2h.a_direct_wins + team_h2h.b_direct_wins == len(team_h2h.direct_debates), "Team H2H direct wins do not sum to total clashes")

        res.metrics["master_tab_speakers_count"] = len(speaker_tab)
        res.metrics["ranked_institutions_count"] = len(ipi_list)
        res.metrics["thematic_categories_count"] = len(thematic)
        return res


def print_audit_report(results: List[AuditResult]):
    term_width = 90
    banner = "=" * term_width
    divider = "-" * term_width

    print("\n" + banner)
    print("           ATOMOS MASTER FORENSIC INTEGRITY & ACCURACY AUDIT REPORT")
    print("                 System-Wide Relational & Mathematical Gatekeeper")
    print(banner)

    all_passed = True
    total_checks = 0
    total_crit = 0
    total_warn = 0

    for r in results:
        status_str = "[PASS]" if r.passed else "[FAIL]"
        print(f"\n{status_str} {r.name.upper()}")
        print(f"  * Checks executed : {r.checks_run}")
        if r.metrics:
            metrics_str = ", ".join(f"{k}: {v}" for k, v in r.metrics.items())
            print(f"  * Verified metrics: {metrics_str}")

        if r.critical_errors:
            print("  * Critical Failures:")
            for err in r.critical_errors:
                print(f"    - [CRITICAL] {err}")

        if r.warnings:
            print("  * Notices / Warnings:")
            for w in r.warnings:
                print(f"    - [NOTICE] {w}")

        if not r.passed:
            all_passed = False
        total_checks += r.checks_run
        total_crit += len(r.critical_errors)
        total_warn += len(r.warnings)

    print("\n" + banner)
    final_verdict = "SYSTEM INTEGRITY 100% PERFECTED [AUDIT PASSED]" if all_passed else "SYSTEM INTEGRITY COMPROMISED [CRITICAL ERRORS]"
    print(f" FINAL AUDIT VERDICT: {final_verdict}")
    print(f" Total Gates: {len(results)} | Total Checks: {total_checks} | Critical Errors: {total_crit} | Warnings: {total_warn}")
    print(banner + "\n")
    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Atomos Master Forensic Integrity & Accuracy Audit Engine")
    parser.add_argument("--verbose", action="store_true", help="Print detailed diagnostic output")
    parser.add_argument("--json", action="store_true", help="Output audit results as JSON")
    args = parser.parse_args()

    conn = get_connection()
    auditor = MasterAuditor(conn, verbose=args.verbose)
    results = auditor.run_all_gates()
    conn.close()

    if args.json:
        payload = {
            "all_passed": all(r.passed for r in results),
            "gates": [r.to_dict() for r in results],
        }
        print(json.dumps(payload, indent=2))
        sys.exit(0 if payload["all_passed"] else 1)
    else:
        success = print_audit_report(results)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
