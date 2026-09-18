"""
Atomos Manual Ballot Override System

Enables the founder/adjudication core to manually supply missing or corrected ballots
from physical/offline records (e.g. paper scoresheets, WhatsApp records, Google Sheets).

Reads override files from:
- `data/overrides/<tournament_slug>_ballots.json`
- `data/overrides/manual_ballots.json`
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional


class ManualBallotPatcher:
    """Applies verified manual ballot overrides to the Atomos database."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def apply_overrides(self, overrides_dir: Path = Path("data/overrides")) -> int:
        cur = self.conn.cursor()
        if not overrides_dir.exists():
            return 0

        applied = 0
        for f in overrides_dir.glob("*.json"):
            try:
                records = json.loads(f.read_text(encoding="utf-8"))
                if not isinstance(records, list):
                    records = [records]

                for rec in records:
                    if self._apply_single_override(rec):
                        applied += 1
            except Exception as e:
                print(f"[!] Error processing override file {f.name}: {e}")

        self.conn.commit()
        return applied

    def _apply_single_override(self, rec: dict) -> bool:
        cur = self.conn.cursor()
        slug = rec.get("tournament_slug")
        r_num = rec.get("round_number")
        prop_name = rec.get("prop_team")
        opp_name = rec.get("opp_team")
        debate_id = rec.get("debate_id")

        if debate_id:
            cur.execute("""
                SELECT d.id, d.round_id, d.prop_team_id, d.opp_team_id
                FROM debates d
                WHERE d.debate_id = ?
            """, (str(debate_id),))
        elif slug and r_num and prop_name and opp_name:
            cur.execute("""
                SELECT d.id, d.round_id, d.prop_team_id, d.opp_team_id
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                JOIN tournaments tour ON r.tournament_id = tour.id
                JOIN teams p ON d.prop_team_id = p.id
                JOIN teams o ON d.opp_team_id = o.id
                WHERE tour.slug = ? AND r.round_number = ? AND p.name = ? AND o.name = ?
            """, (slug, r_num, prop_name, opp_name))
        else:
            return False

        row = cur.fetchone()
        if not row:
            return False

        db_debate_id = row[0]
        round_id = row[1]
        p_tid = row[2]
        o_tid = row[3]

        # Clean existing speeches for this debate if replacing
        cur.execute("DELETE FROM speech_performances WHERE debate_id = ?", (db_debate_id,))
        cur.execute("DELETE FROM adjudicator_ballots WHERE debate_id = ?", (db_debate_id,))

        adj_name = rec.get("adjudicator", "Founder Manual Record")
        p_speeches = rec.get("proposition", [])
        o_speeches = rec.get("opposition", [])

        p_total = sum(s.get("score", 0.0) for s in p_speeches)
        o_total = sum(s.get("score", 0.0) for s in o_speeches)
        margin = p_total - o_total
        winner = "Proposition" if margin > 0 else "Opposition" if margin < 0 else "Tie"

        cur.execute("""
            INSERT INTO adjudicator_ballots (
                debate_id, adjudicator_raw_name, adjudicator_institution,
                prop_total_score, opp_total_score, win_margin, winner_side
            ) VALUES (?, ?, 'Founder Verified', ?, ?, ?, ?)
        """, (db_debate_id, adj_name, p_total, o_total, margin, winner))
        ballot_id = cur.lastrowid

        def get_or_create_p(name: str) -> int:
            cur.execute("SELECT id FROM persons WHERE canonical_name = ?", (name,))
            pr = cur.fetchone()
            if pr:
                return pr[0]
            cur.execute("INSERT INTO persons (canonical_name) VALUES (?)", (name,))
            return cur.lastrowid

        for s in p_speeches:
            pid = get_or_create_p(s["speaker"])
            pos = s.get("position", "1st")
            stype = "REPLY" if pos == "Reply" else "SUBSTANTIVE"
            cur.execute("""
                INSERT INTO speech_performances (
                    ballot_id, debate_id, round_id, team_id, person_id,
                    side, position, speech_type, total_score,
                    content, style, strategy, is_valid_rubric, is_iron_man
                ) VALUES (?, ?, ?, ?, ?, 'Proposition', ?, ?, ?, ?, ?, ?, 1, 0)
            """, (ballot_id, db_debate_id, round_id, p_tid, pid, pos, stype, s["score"],
                  s.get("content"), s.get("style"), s.get("strategy")))

        for s in o_speeches:
            pid = get_or_create_p(s["speaker"])
            pos = s.get("position", "1st")
            stype = "REPLY" if pos == "Reply" else "SUBSTANTIVE"
            cur.execute("""
                INSERT INTO speech_performances (
                    ballot_id, debate_id, round_id, team_id, person_id,
                    side, position, speech_type, total_score,
                    content, style, strategy, is_valid_rubric, is_iron_man
                ) VALUES (?, ?, ?, ?, ?, 'Opposition', ?, ?, ?, ?, ?, ?, 1, 0)
            """, (ballot_id, db_debate_id, round_id, o_tid, pid, pos, stype, s["score"],
                  s.get("content"), s.get("style"), s.get("strategy")))

        cur.execute("UPDATE debates SET is_walkover = 0 WHERE id = ?", (db_debate_id,))
        return True
