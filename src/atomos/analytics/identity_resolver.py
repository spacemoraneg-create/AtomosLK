"""
Atomos Identity Resolver & Merger Engine

Provides automated duplicate detection and transactional merging for:
1. Persons (Debaters & Adjudicators): Strictly implementing the user's 3 deterministic rules:
   - Rule 1: Ignore capitalization (case-insensitive exact match). Different capitalization does not equal different names.
   - Rule 2: Change of space characters (spacing variations between words, initials, tokens).
   - Rule 3: 2 character changes away (Levenshtein distance <= 2).
2. Teams: Identifies duplicates within the same institution and tournament (suffix-preserving, case/space/edit).
"""

import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


def levenshtein_distance_le_2(s1: str, s2: str) -> Optional[int]:
    """
    Returns the Levenshtein edit distance between s1 and s2 if <= 2, otherwise None.
    Handles insertions, deletions, substitutions, and implicit adjacent transpositions.
    """
    len1, len2 = len(s1), len(s2)
    if abs(len1 - len2) > 2:
        return None
    if s1 == s2:
        return 0

    prev = list(range(len2 + 1))
    for i in range(len1):
        curr = [i + 1] + [0] * len2
        for j in range(len2):
            cost = 0 if s1[i] == s2[j] else 1
            curr[j + 1] = min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost)
        if min(curr) > 2:
            return None
        prev = curr

    res = prev[len2]
    return res if res <= 2 else None


def is_placeholder_name(name: str) -> bool:
    """Filter out synthetic test placeholders and generic slot names."""
    low = (name or "").strip().lower()
    return bool(re.match(r"^(speaker\s*\d*|adjudicator\s*\d*|tab|official.*)$", low))


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
                person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                raw_name TEXT NOT NULL,
                source_tournament_id INTEGER REFERENCES tournaments(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(person_id, raw_name)
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

    def get_person_suggestions(self) -> List[Dict[str, Any]]:
        """
        Find candidate duplicate persons strictly using the 3 deterministic rules:
        1. Ignore Capitalization: Different capitalization does not equal different names (0 edit distance case-insensitive).
        2. Spacing / Whitespace Variation: Change of space characters between tokens or initials.
        3. Edit Distance <= 2: Name is 1 or 2 character changes away from another name (Levenshtein distance <= 2).
        """
        dismissed = self.get_dismissed_pairs("person")
        cur = self.conn.cursor()

        # Fetch persons with speech counts, institution, and tournament activity
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
            ORDER BY p.id
        """)
        persons = [dict(r) for r in cur.fetchall()]

        suggestions = []

        for i, p1 in enumerate(persons):
            n1 = p1["canonical_name"].strip()
            if is_placeholder_name(n1):
                continue
            n1_lower = n1.lower()
            n1_nospace = "".join(n1_lower.split())
            w1 = n1_lower.split()

            for p2 in persons[i + 1:]:
                id_a, id_b = p1["id"], p2["id"]
                if (id_a, id_b) in dismissed:
                    continue

                n2 = p2["canonical_name"].strip()
                if is_placeholder_name(n2):
                    continue
                n2_lower = n2.lower()
                n2_nospace = "".join(n2_lower.split())
                w2 = n2_lower.split()

                is_match = False
                match_type = ""
                reason = ""
                confidence = 0.0

                # Rule 1: Ignore capitalization (case-insensitive exact match)
                if n1_lower == n2_lower and n1 != n2:
                    is_match = True
                    match_type = "Exact Match (Capitalization Difference)"
                    reason = f"Identical name with different capitalization: '{n1}' vs '{n2}'"
                    confidence = 100.0

                # Rule 2: Change of space characters (spaces added/removed or different spacing)
                elif n1_nospace == n2_nospace and n1_lower != n2_lower:
                    is_match = True
                    match_type = "Spacing / Whitespace Variation"
                    reason = f"Identical characters with different spacing: '{n1}' vs '{n2}'"
                    confidence = 98.0

                # Rule 3: 2 character changes away (Levenshtein distance <= 2)
                else:
                    d = levenshtein_distance_le_2(n1_lower, n2_lower)
                    if d is not None:
                        # Guardrail: Don't match different first names sharing a common surname (e.g. Binupa Bandara vs Vinuja Bandara)
                        if len(w1) >= 2 and len(w2) >= 2 and w1[-1] == w2[-1]:
                            fn_d = levenshtein_distance_le_2(w1[0], w2[0])
                            if fn_d is None or fn_d > 1:
                                continue

                        min_len = min(len(n1_lower), len(n2_lower))
                        if d == 1 and min_len >= 4:
                            is_match = True
                            match_type = "1 Character Change Away (Typo / Missing Letter)"
                            reason = f"Names differ by exactly 1 character change: '{n1}' vs '{n2}'"
                            confidence = 95.0
                        elif d == 2 and min_len >= 5:
                            is_match = True
                            match_type = "2 Character Changes Away (Transposition / Minor Typo)"
                            reason = f"Names differ by 2 character changes: '{n1}' vs '{n2}'"
                            confidence = 90.0

                if is_match:
                    same_inst = bool(p1["institution"] and p2["institution"] and p1["institution"].lower() == p2["institution"].lower())
                    if same_inst and confidence < 100.0:
                        confidence = min(99.0, confidence + 2.0)
                        reason += f" (Both from {p1['institution']})"

                    # Primary target is the record with more recorded debate activity
                    if p1["speech_count"] > p2["speech_count"]:
                        primary, dup = p1, p2
                    elif p2["speech_count"] > p1["speech_count"]:
                        primary, dup = p2, p1
                    elif (p1.get("tour_count") or 0) > (p2.get("tour_count") or 0):
                        primary, dup = p1, p2
                    elif (p2.get("tour_count") or 0) > (p1.get("tour_count") or 0):
                        primary, dup = p2, p1
                    elif p1["id"] < p2["id"]:
                        primary, dup = p1, p2
                    else:
                        primary, dup = p2, p1

                    suggestions.append({
                        "type": "person",
                        "match_type": match_type,
                        "reason": reason,
                        "confidence": confidence,
                        "primary": primary,
                        "duplicate": dup,
                    })

        suggestions.sort(key=lambda s: (-s["confidence"], s["primary"]["canonical_name"]))
        return suggestions

    def get_team_suggestions(self) -> List[Dict[str, Any]]:
        """Find candidate duplicate teams strictly within the same tournament and institution."""
        dismissed = self.get_dismissed_pairs("team")
        cur = self.conn.cursor()

        cur.execute("""
            SELECT t.id, t.name, t.canonical_name, t.tournament_id, t.institution_id,
                   tour.name as tournament_name, i.name as institution_name,
                   (SELECT COUNT(*) FROM speech_performances sp WHERE sp.team_id = t.id) as speech_count
            FROM teams t
            JOIN tournaments tour ON t.tournament_id = tour.id
            LEFT JOIN institutions i ON t.institution_id = i.id
            ORDER BY t.name
        """)
        teams = [dict(r) for r in cur.fetchall()]

        suggestions = []
        for i, t1 in enumerate(teams):
            n1 = (t1["name"] or "").strip()
            if not n1:
                continue
            n1_lower = n1.lower()
            n1_nospace = "".join(n1_lower.split())
            m1 = re.search(r"\b([a-d]|1|2|3|vi|vii|viii|ix|x)\b$", n1_lower)
            suf1 = m1.group(1) if m1 else None

            for t2 in teams[i + 1:]:
                id_a, id_b = t1["id"], t2["id"]
                if (id_a, id_b) in dismissed:
                    continue

                n2 = (t2["name"] or "").strip()
                if not n2:
                    continue
                n2_lower = n2.lower()
                n2_nospace = "".join(n2_lower.split())
                m2 = re.search(r"\b([a-d]|1|2|3|vi|vii|viii|ix|x)\b$", n2_lower)
                suf2 = m2.group(1) if m2 else None

                # Suffix must match: NEVER suggest merging Team A with Team B or Team VI with Team VII!
                if suf1 and suf2 and suf1 != suf2:
                    continue

                # Must belong to the same institution
                same_inst = (t1["institution_id"] is not None and t1["institution_id"] == t2["institution_id"]) or (
                    t1["institution_name"] and t1["institution_name"] == t2["institution_name"]
                )
                if not same_inst:
                    continue

                # Must belong to the same tournament
                if t1["tournament_id"] != t2["tournament_id"]:
                    continue

                is_match = False
                match_type = ""
                reason = ""
                confidence = 0.0

                # Rule 1: Capitalization
                if n1_lower == n2_lower and n1 != n2:
                    is_match = True
                    match_type = "Exact Match (Capitalization Difference)"
                    reason = f"Identical team name with different capitalization: '{n1}' vs '{n2}'"
                    confidence = 100.0

                # Rule 2: Spacing
                elif n1_nospace == n2_nospace and n1_lower != n2_lower:
                    is_match = True
                    match_type = "Spacing / Whitespace Variation"
                    reason = f"Identical team characters with different spacing: '{n1}' vs '{n2}'"
                    confidence = 98.0

                # Rule 3: 1-2 edits away
                else:
                    d = levenshtein_distance_le_2(n1_lower, n2_lower)
                    if d == 1 and min(len(n1_lower), len(n2_lower)) >= 3:
                        is_match = True
                        match_type = "1 Character Change Away (Typo / Missing Letter)"
                        reason = f"Team names differ by 1 character change: '{n1}' vs '{n2}'"
                        confidence = 95.0
                    elif d == 2 and min(len(n1_lower), len(n2_lower)) >= 4:
                        is_match = True
                        match_type = "2 Character Changes Away (Transposition / Minor Typo)"
                        reason = f"Team names differ by 2 character changes: '{n1}' vs '{n2}'"
                        confidence = 90.0

                if is_match:
                    if t1["speech_count"] >= t2["speech_count"]:
                        primary, dup = t1, t2
                    else:
                        primary, dup = t2, t1

                    suggestions.append({
                        "type": "team",
                        "match_type": match_type,
                        "reason": reason,
                        "confidence": confidence,
                        "primary": primary,
                        "duplicate": dup,
                    })

        suggestions.sort(key=lambda s: -s["confidence"])
        return suggestions

    def execute_person_merge(self, primary_id: int, duplicate_id: int) -> Dict[str, Any]:
        """Merge duplicate person into primary person, cascading all records."""
        if primary_id == duplicate_id:
            raise ValueError("Cannot merge a person into themselves.")

        from atomos.normalizer.identity_merger import IdentityMerger as NormalizerMerger
        merger = NormalizerMerger(self.conn)
        success = merger.merge_persons(canonical_id=primary_id, duplicate_id=duplicate_id)
        if not success:
            raise RuntimeError(f"Failed to merge person {duplicate_id} into {primary_id}")

        cur = self.conn.cursor()
        cur.execute("SELECT canonical_name FROM persons WHERE id = ?", (primary_id,))
        row = cur.fetchone()
        pname = row["canonical_name"] if row else f"#{primary_id}"

        return {
            "success": True,
            "message": f"Successfully merged person ID {duplicate_id} into '{pname}' (ID {primary_id}).",
            "primary_name": pname,
        }

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
