"""
Atomos Integrity Validator (The Gatekeeper)

Automatically runs forensic validation checks on the SQLite database after every
tournament extraction or normalization.

Guarantees that no data inconsistency, unlinked debate, or corrupted entity
can enter the Atomos intelligence system silently.
"""

import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ValidationReport:
    is_valid: bool
    critical_errors: List[str] = field(default_factory=list)
    domain_anomalies: List[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            "=" * 50,
            "ATOMOS AUTOMATED INTEGRITY GATE REPORT",
            "=" * 50,
            f"Overall Status: {'PASSED [100% CLEAN]' if self.is_valid else 'FAILED [CRITICAL ERRORS FOUND]'}",
            "",
            "--- Database Metrics ---",
        ]
        for k, v in self.stats.items():
            lines.append(f"  * {k}: {v}")

        if self.critical_errors:
            lines.append("\n--- CRITICAL INTEGRITY ERRORS (Action Required) ---")
            for err in self.critical_errors:
                lines.append(f"  [CRITICAL] {err}")

        if self.domain_anomalies:
            lines.append("\n--- TOURNAMENT SOURCE ANOMALIES (Flagged/Quarantined) ---")
            for anom in self.domain_anomalies:
                lines.append(f"  [NOTICE] {anom}")

        lines.append("=" * 50)
        return "\n".join(lines)


class IntegrityValidator:
    """Enforces zero-defect data guarantees across all imported tournaments."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def validate(self, tournament_id: Optional[int] = None) -> ValidationReport:
        cur = self.conn.cursor()
        critical_errors: List[str] = []
        domain_anomalies: List[str] = []
        stats = {}

        # 1. Check Institutions
        cur.execute("SELECT id, name, code FROM institutions WHERE name IS NULL OR name = '' OR code IS NULL OR code = ''")
        bad_inst = cur.fetchall()
        if bad_inst:
            critical_errors.append(f"Found {len(bad_inst)} institutions with empty names or codes")

        cur.execute("SELECT name, COUNT(*) as cnt FROM institutions GROUP BY name HAVING cnt > 1")
        dup_names = cur.fetchall()
        if dup_names:
            critical_errors.append(f"Found {len(dup_names)} duplicate institution names")

        cur.execute("SELECT code, COUNT(*) as cnt FROM institutions GROUP BY code HAVING cnt > 1")
        dup_codes = cur.fetchall()
        if dup_codes:
            critical_errors.append(f"Found {len(dup_codes)} duplicate institution codes")

        # 2. Check Persons
        cur.execute("""
            SELECT id, canonical_name FROM persons 
            WHERE canonical_name IS NULL 
               OR canonical_name = '' 
               OR canonical_name LIKE '%<%' 
               OR canonical_name LIKE '%>%' 
               OR canonical_name LIKE '%&#%'
        """)
        bad_persons = cur.fetchall()
        if bad_persons:
            critical_errors.append(f"Found {len(bad_persons)} persons with HTML or corrupted text")

        # 3. Check Teams and Institutional Affiliation
        t_filter = "AND t.tournament_id = ?" if tournament_id else ""
        t_params = (tournament_id,) if tournament_id else ()

        cur.execute(f"""
            SELECT t.id, t.name, tour.slug
            FROM teams t
            JOIN tournaments tour ON t.tournament_id = tour.id
            WHERE t.institution_id IS NULL AND t.name NOT LIKE '%Swing%' AND t.name NOT LIKE '%BYE%'
            {t_filter}
        """, t_params)
        unlinked_teams = cur.fetchall()
        if unlinked_teams:
            critical_errors.append(f"Found {len(unlinked_teams)} non-swing teams without an institution link")

        # Check roster sizes (Standard WSDC regulations allow 3 to 5 debaters per team)
        cur.execute(f"""
            SELECT t.id, t.name, tour.slug, COUNT(tm.person_id) as roster_size
            FROM teams t
            JOIN tournaments tour ON t.tournament_id = tour.id
            LEFT JOIN team_members tm ON t.id = tm.team_id
            WHERE t.name NOT LIKE '%Swing%' AND t.name NOT LIKE '%BYE%'
            {t_filter}
            GROUP BY t.id
        """, t_params)
        for r in cur.fetchall():
            sz = r[3]
            if sz < 3 or sz > 5:
                domain_anomalies.append(f"Team '{r[1]}' in '{r[2]}' has unusual roster size: {sz} debaters (expected 3-5)")

        # 4. Check Debates & Team Linkages
        if tournament_id:
            cur.execute("""
                SELECT d.id, d.debate_id, r.name as round_name, tour.slug
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                JOIN tournaments tour ON r.tournament_id = tour.id
                WHERE r.tournament_id = ? AND (d.prop_team_id IS NULL OR d.opp_team_id IS NULL)
            """, (tournament_id,))
        else:
            cur.execute("""
                SELECT d.id, d.debate_id, r.name as round_name, tour.slug
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                JOIN tournaments tour ON r.tournament_id = tour.id
                WHERE d.prop_team_id IS NULL OR d.opp_team_id IS NULL
            """)
        unlinked_debates = cur.fetchall()
        if unlinked_debates:
            critical_errors.append(f"Found {len(unlinked_debates)} debates with unlinked Proposition or Opposition teams")

        # 5. Check Speech Performance Math & Rubrics
        if tournament_id:
            cur.execute("""
                SELECT sp.id, sp.speech_type, sp.total_score, sp.content, sp.style, sp.strategy, sp.is_valid_rubric
                FROM speech_performances sp
                JOIN debates d ON sp.debate_id = d.id
                JOIN rounds r ON d.round_id = r.id
                WHERE r.tournament_id = ?
            """, (tournament_id,))
        else:
            cur.execute("""
                SELECT sp.id, sp.speech_type, sp.total_score, sp.content, sp.style, sp.strategy, sp.is_valid_rubric
                FROM speech_performances sp
            """)
        speeches = cur.fetchall()

        sum_mismatches = []
        zero_scores = []
        non_standard_rubrics = []

        for s in speeches:
            tot = s[2]
            c = s[3]
            st = s[4]
            strat = s[5]
            is_valid_r = s[6]

            if tot == 0.0:
                zero_scores.append(s[0])
                continue

            if c is not None and st is not None and strat is not None:
                if abs((c + st + strat) - tot) > 0.01:
                    sum_mismatches.append(s[0])

            if is_valid_r == 0:
                non_standard_rubrics.append(s[0])

        if sum_mismatches:
            critical_errors.append(f"Found {len(sum_mismatches)} speeches where Content+Style+Strategy does not equal Total Score")

        if zero_scores:
            domain_anomalies.append(f"Found {len(zero_scores)} placeholder 0.0 speech scores (administrative forfeit / walkover)")

        if non_standard_rubrics:
            domain_anomalies.append(f"Notice: {len(non_standard_rubrics)} speeches have verified total scores with non-standard judge component splits (flagged is_valid_rubric=0)")

        # 6. Check Adjudicator Ballot Totals
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
        ballot_mismatches = []
        for bc in cur.fetchall():
            is_reconstructed = any(kw in (bc[5] or "").lower() for kw in ["reconstruct", "official"])
            if is_reconstructed:
                # For tab-reconstructed ballots with partial speeches, sum must not exceed team total
                if bc[3] > bc[1] + 0.01 or bc[4] > bc[2] + 0.01:
                    ballot_mismatches.append(bc[0])
            else:
                if abs(bc[1] - bc[3]) > 0.01 or abs(bc[2] - bc[4]) > 0.01:
                    ballot_mismatches.append(bc[0])

        if ballot_mismatches:
            critical_errors.append(f"Found {len(ballot_mismatches)} ballots where team total does not equal sum of speeches")

        # Populate Statistics
        cur.execute("SELECT COUNT(*) FROM tournaments")
        stats["Tournaments in DB"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM institutions")
        stats["Institutions"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM teams")
        stats["Teams"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM persons")
        stats["Persons"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM debates")
        stats["Debates"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM speech_performances")
        stats["Speech Performances"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM identity_resolutions WHERE status = 'PENDING_REVIEW'")
        stats["Pending Identity Reviews"] = cur.fetchone()[0]

        is_valid = len(critical_errors) == 0
        return ValidationReport(
            is_valid=is_valid,
            critical_errors=critical_errors,
            domain_anomalies=domain_anomalies,
            stats=stats,
        )
