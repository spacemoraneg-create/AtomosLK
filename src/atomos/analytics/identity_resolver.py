"""
Atomos Identity Resolver & Merger Engine

Provides automated duplicate detection and transactional merging for:
1. Persons (Debaters & Adjudicators): Handles fuzzy typo matches, single-name expansions,
   and alias reconciliation with full foreign key cascading.
2. Teams: Identifies acronym vs full-name variations (e.g. TCK A vs Trinity A, EMS A vs Moir A)
   and unifies performance records.
"""

from difflib import SequenceMatcher
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


class IdentityResolver:
    """Automated duplicate detection and transactional merger for Atomos."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure required tables for alias and dismissal tracking exist."""
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dismissed_merges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                id_a INTEGER NOT NULL,
                id_b INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(entity_type, id_a, id_b)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS person_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                alias_name TEXT NOT NULL,
                source_tournament_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (person_id) REFERENCES persons(id)
            )
        """)
        self.conn.commit()

    def get_dismissed_pairs(self, entity_type: str) -> set:
        cur = self.conn.cursor()
        cur.execute("SELECT id_a, id_b FROM dismissed_merges WHERE entity_type = ?", (entity_type,))
        dismissed = set()
        for r in cur.fetchall():
            dismissed.add((r[0], r[1]))
            dismissed.add((r[1], r[0]))
        return dismissed

    def get_person_suggestions(self, min_similarity: float = 0.82) -> List[Dict[str, Any]]:
        """Find candidate duplicate persons with similarity scores and evidence."""
        dismissed = self.get_dismissed_pairs("person")
        cur = self.conn.cursor()

        # Fetch persons with speech counts and latest institution
        cur.execute("""
            SELECT p.id, p.canonical_name, p.national_level,
                   COUNT(sp.id) as speech_count,
                   (SELECT i.name FROM speech_performances sp2
                    JOIN teams t ON sp2.team_id = t.id
                    JOIN institutions i ON t.institution_id = i.id
                    WHERE sp2.person_id = p.id
                    ORDER BY sp2.id DESC LIMIT 1) as institution,
                   (SELECT COUNT(DISTINCT r.tournament_id) FROM speech_performances sp3
                    JOIN rounds r ON sp3.round_id = r.id
                    WHERE sp3.person_id = p.id) as tour_count
            FROM persons p
            LEFT JOIN speech_performances sp ON p.id = sp.person_id
            GROUP BY p.id
            ORDER BY p.canonical_name
        """)
        persons = [dict(r) for r in cur.fetchall()]

        suggestions = []

        for i, p1 in enumerate(persons):
            name1 = p1["canonical_name"].strip()
            w1 = name1.lower().split()
            if not w1:
                continue

            for p2 in persons[i + 1:]:
                id_a, id_b = p1["id"], p2["id"]
                if (id_a, id_b) in dismissed:
                    continue

                name2 = p2["canonical_name"].strip()
                w2 = name2.lower().split()
                if not w2:
                    continue

                # Don't match different first names sharing a common last name (e.g. Abeesha vs Aritha)
                if len(w1) > 1 and len(w2) > 1 and w1[0] != w2[0] and w1[-1] == w2[-1]:
                    continue

                sim = SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
                is_single1 = len(w1) == 1
                is_single2 = len(w2) == 1
                is_sub = (is_single1 and w1[0] in w2) or (is_single2 and w2[0] in w1)

                is_candidate = False
                match_type = ""
                confidence = round(sim * 100, 1)

                if is_sub:
                    is_candidate = True
                    match_type = "Single Name Expansion"
                    confidence = 90.0 if (p1["institution"] and p1["institution"] == p2["institution"]) else 75.0
                elif sim >= min_similarity:
                    is_candidate = True
                    match_type = "Typo / High Fuzzy Match"
                    confidence = round(sim * 100, 1)

                if is_candidate:
                    if len(w1) > len(w2):
                        primary, dup = p1, p2
                    elif len(w2) > len(w1):
                        primary, dup = p2, p1
                    elif p1["speech_count"] >= p2["speech_count"]:
                        primary, dup = p1, p2
                    else:
                        primary, dup = p2, p1

                    suggestions.append({
                        "type": "person",
                        "match_type": match_type,
                        "confidence": confidence,
                        "primary": primary,
                        "duplicate": dup,
                    })

        suggestions.sort(key=lambda s: -s["confidence"])
        return suggestions[:60]

    def get_team_suggestions(self) -> List[Dict[str, Any]]:
        """Find candidate duplicate teams (e.g. acronyms vs full names within same school)."""
        dismissed = self.get_dismissed_pairs("team")
        cur = self.conn.cursor()

        cur.execute("""
            SELECT t.id, t.name, t.canonical_name, t.tournament_id,
                   tour.name as tournament_name, i.name as institution_name,
                   (SELECT COUNT(*) FROM speech_performances sp WHERE sp.team_id = t.id) as speech_count
            FROM teams t
            JOIN tournaments tour ON t.tournament_id = tour.id
            LEFT JOIN institutions i ON t.institution_id = i.id
            ORDER BY t.name
        """)
        teams = [dict(r) for r in cur.fetchall()]

        known_acronyms = [
            ("tck", "trinity"),
            ("ems", "moir"),
            ("av", "anula"),
            ("nc", "nalanda"),
            ("mc", "metho"),
            ("sjcj", "sjoc"),
            ("sgck", "sgc"),
            ("eik", "ec"),
        ]

        suggestions = []
        for i, t1 in enumerate(teams):
            n1 = t1["name"].lower().strip()
            for t2 in teams[i + 1:]:
                id_a, id_b = t1["id"], t2["id"]
                if (id_a, id_b) in dismissed:
                    continue

                n2 = t2["name"].lower().strip()
                is_match = False
                for acr, full in known_acronyms:
                    if (acr in n1 and full in n2) or (acr in n2 and full in n1):
                        is_match = True
                        break

                if not is_match:
                    sim = SequenceMatcher(None, n1, n2).ratio()
                    if sim > 0.85 and n1 != n2:
                        is_match = True

                if is_match:
                    if t1["speech_count"] >= t2["speech_count"]:
                        primary, dup = t1, t2
                    else:
                        primary, dup = t2, t1

                    suggestions.append({
                        "type": "team",
                        "match_type": "Team Acronym / Variant",
                        "confidence": 92.0,
                        "primary": primary,
                        "duplicate": dup,
                    })

        suggestions.sort(key=lambda s: -s["confidence"])
        return suggestions[:40]

    def execute_person_merge(self, primary_id: int, duplicate_id: int) -> Dict[str, Any]:
        """Merge duplicate person into primary person, cascading all records."""
        if primary_id == duplicate_id:
            raise ValueError("Cannot merge a person into themselves.")

        cur = self.conn.cursor()
        cur.execute("SELECT id, canonical_name FROM persons WHERE id = ?", (primary_id,))
        p1 = cur.fetchone()
        cur.execute("SELECT id, canonical_name FROM persons WHERE id = ?", (duplicate_id,))
        p2 = cur.fetchone()

        if not p1 or not p2:
            raise ValueError(f"One or both person IDs ({primary_id}, {duplicate_id}) not found.")

        try:
            cur.execute("UPDATE speech_performances SET person_id = ? WHERE person_id = ?", (primary_id, duplicate_id))
            cur.execute("UPDATE team_members SET person_id = ? WHERE person_id = ?", (primary_id, duplicate_id))
            cur.execute("UPDATE adjudicator_ballots SET adjudicator_person_id = ? WHERE adjudicator_person_id = ?", (primary_id, duplicate_id))
            cur.execute("UPDATE adjudicator_assignments SET person_id = ? WHERE person_id = ?", (primary_id, duplicate_id))

            cur.execute("""
                INSERT INTO person_aliases (person_id, alias_name)
                VALUES (?, ?)
            """, (primary_id, p2["canonical_name"]))

            cur.execute("DELETE FROM persons WHERE id = ?", (duplicate_id,))
            self.conn.commit()

            return {
                "success": True,
                "message": f"Successfully merged '{p2['canonical_name']}' (ID {duplicate_id}) into '{p1['canonical_name']}' (ID {primary_id}).",
                "primary_name": p1["canonical_name"],
            }
        except Exception as e:
            self.conn.rollback()
            raise RuntimeError(f"Database error during person merge: {str(e)}")

    def execute_team_merge(self, primary_id: int, duplicate_id: int) -> Dict[str, Any]:
        """Merge duplicate team into primary team."""
        if primary_id == duplicate_id:
            raise ValueError("Cannot merge a team into itself.")

        cur = self.conn.cursor()
        cur.execute("SELECT id, name, canonical_name FROM teams WHERE id = ?", (primary_id,))
        t1 = cur.fetchone()
        cur.execute("SELECT id, name, canonical_name FROM teams WHERE id = ?", (duplicate_id,))
        t2 = cur.fetchone()

        if not t1 or not t2:
            raise ValueError(f"One or both team IDs ({primary_id}, {duplicate_id}) not found.")

        try:
            cur.execute("UPDATE speech_performances SET team_id = ? WHERE team_id = ?", (primary_id, duplicate_id))
            cur.execute("UPDATE team_members SET team_id = ? WHERE team_id = ?", (primary_id, duplicate_id))
            cur.execute("UPDATE debates SET prop_team_id = ? WHERE prop_team_id = ?", (primary_id, duplicate_id))
            cur.execute("UPDATE debates SET opp_team_id = ? WHERE opp_team_id = ?", (primary_id, duplicate_id))
            cur.execute("UPDATE debates SET walkover_winner_id = ? WHERE walkover_winner_id = ?", (primary_id, duplicate_id))

            cur.execute("DELETE FROM teams WHERE id = ?", (duplicate_id,))
            self.conn.commit()

            return {
                "success": True,
                "message": f"Successfully merged team '{t2['name']}' (ID {duplicate_id}) into '{t1['name']}' (ID {primary_id}).",
                "primary_name": t1["name"],
            }
        except Exception as e:
            self.conn.rollback()
            raise RuntimeError(f"Database error during team merge: {str(e)}")

    def dismiss_suggestion(self, entity_type: str, id_a: int, id_b: int):
        """Mark pair as dismissed so it will not appear in future scans."""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO dismissed_merges (entity_type, id_a, id_b)
            VALUES (?, ?, ?)
        """, (entity_type, id_a, id_b))
        self.conn.commit()
