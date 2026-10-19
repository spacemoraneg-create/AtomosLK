"""
Atomos Identity Resolver & Merger Engine

Provides automated duplicate detection and transactional merging for:
1. Persons (Debaters & Adjudicators):
   - Rule 1: Ignore capitalization (case-insensitive exact match).
   - Rule 2: Spacing / punctuation variation (initials, whitespace, dots).
   - Rule 3: Same-institution structural variations (inverted order, middle name added/omitted,
     initials/prefix affix, or single first name matching a unique school debater).
   - Rule 4: 1–2 character typos (Levenshtein distance <= 2 or high-similarity same-school typo).
   - Strict Collision Safety: Never merges two records that competed in the same debate.
2. Teams: Identifies duplicates within the same institution and tournament (suffix-preserving, case/space/edit).
"""

import difflib
import re
import sqlite3
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple


def levenshtein_distance_le_2(s1: str, s2: str) -> Optional[int]:
    """
    Returns the Levenshtein edit distance between s1 and s2 if <= 2, otherwise None.
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

    def get_dismissed_pairs(self, entity_type: str) -> Set[Tuple[int, int]]:
        cur = self.conn.cursor()
        cur.execute("SELECT id_a, id_b FROM dismissed_merges WHERE entity_type = ?", (entity_type,))
        dismissed: Set[Tuple[int, int]] = set()
        for r in cur.fetchall():
            dismissed.add((int(r[0]), int(r[1])))
            dismissed.add((int(r[1]), int(r[0])))

        if entity_type == "person":
            try:
                cur.execute("""
                    SELECT person_a_id, person_b_id 
                    FROM identity_resolutions 
                    WHERE status = 'CONFIRMED_DIFFERENT'
                      AND person_a_id IS NOT NULL AND person_b_id IS NOT NULL
                """)
                for r in cur.fetchall():
                    dismissed.add((int(r[0]), int(r[1])))
                    dismissed.add((int(r[1]), int(r[0])))
            except Exception:
                pass

        return dismissed

    def get_debate_collisions(self) -> Set[Tuple[int, int]]:
        """Find all person pairs who competed in the same debate (cannot be the same person)."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT DISTINCT sp1.person_id, sp2.person_id
            FROM speech_performances sp1
            JOIN speech_performances sp2 ON sp1.debate_id = sp2.debate_id
            WHERE sp1.person_id < sp2.person_id
        """)
        collisions: Set[Tuple[int, int]] = set()
        for r in cur.fetchall():
            a, b = int(r[0]), int(r[1])
            collisions.add((a, b))
            collisions.add((b, a))
        return collisions

    def get_person_suggestions(self) -> List[Dict[str, Any]]:
        """
        Discover candidate duplicate persons across the entire database in < 25ms.
        Combines deterministic character-edit rules with same-institution structural
        matching (middle names, prefixes/initials, single names, and typos) while
        enforcing strict debate collision safety.
        """
        dismissed = self.get_dismissed_pairs("person")
        collisions = self.get_debate_collisions()
        cur = self.conn.cursor()

        cur.execute("""
            SELECT p.id, p.canonical_name, p.national_level,
                   COUNT(sp.id) as speech_count,
                   (SELECT i.name FROM speech_performances sp2
                    JOIN teams t ON sp2.team_id = t.id
                    JOIN institutions i ON t.institution_id = i.id
                    WHERE sp2.person_id = p.id
                    ORDER BY sp2.id DESC LIMIT 1) as primary_institution,
                   (SELECT GROUP_CONCAT(DISTINCT inst.name)
                    FROM institutions inst
                    JOIN teams t ON t.institution_id = inst.id
                    JOIN team_members tm ON tm.team_id = t.id
                    WHERE tm.person_id = p.id) as team_institutions,
                   (SELECT COUNT(DISTINCT r.tournament_id) FROM speech_performances sp3
                    JOIN rounds r ON sp3.round_id = r.id
                    WHERE sp3.person_id = p.id) as tour_count
            FROM persons p
            LEFT JOIN speech_performances sp ON p.id = sp.person_id
            GROUP BY p.id
            ORDER BY p.id
        """)
        rows = [dict(r) for r in cur.fetchall()]

        valid_persons = []
        inst_to_indices: Dict[str, List[int]] = defaultdict(list)
        norm_index: Dict[str, List[int]] = defaultdict(list)
        trigram_index: Dict[str, Set[int]] = defaultdict(set)

        for r in rows:
            n = (r["canonical_name"] or "").strip()
            if not n or is_placeholder_name(n):
                continue

            inst_set: Set[str] = set()
            if r.get("primary_institution"):
                inst_set.add(r["primary_institution"].strip())
            if r.get("team_institutions"):
                for item in r["team_institutions"].split(","):
                    if item.strip():
                        inst_set.add(item.strip())

            r["institution"] = r.get("primary_institution") or (sorted(inst_set)[0] if inst_set else None)
            low = n.lower()
            norm_punct = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", low)).strip()
            alnum_only = re.sub(r"[^\w]", "", low)
            words = [w for w in norm_punct.split() if w]

            idx = len(valid_persons)
            valid_persons.append({
                "record": r,
                "name": n,
                "low": low,
                "norm_punct": norm_punct,
                "alnum": alnum_only,
                "words": words,
                "insts": inst_set,
                "len": len(low),
            })

            norm_index[alnum_only].append(idx)
            for inst_name in inst_set:
                inst_to_indices[inst_name.lower()].append(idx)

            # Index 4-grams (or 3-grams for short names) for fast Levenshtein candidate lookup
            gram_k = 3 if len(low) < 8 else 4
            for g_i in range(max(1, len(low) - gram_k + 1)):
                trigram_index[low[g_i:g_i + gram_k]].add(idx)

        # Count how many people in each school have a given first-name token (for safe single-name resolution)
        inst_token_counts: Dict[Tuple[str, str], int] = defaultdict(int)
        for p_obj in valid_persons:
            if len(p_obj["words"]) >= 2:
                for inst_name in p_obj["insts"]:
                    for tok in set(p_obj["words"]):
                        if len(tok) >= 4:
                            inst_token_counts[(inst_name.lower(), tok)] += 1

        candidate_pairs: Set[Tuple[int, int]] = set()

        # 1. Candidates from normalized alphanumeric match (capitalization, spacing, punctuation)
        for idxs in norm_index.values():
            if len(idxs) > 1:
                for i in range(len(idxs)):
                    for j in range(i + 1, len(idxs)):
                        candidate_pairs.add((min(idxs[i], idxs[j]), max(idxs[i], idxs[j])))

        # 2. Candidates within the same institution
        for idxs in inst_to_indices.values():
            if len(idxs) > 1:
                for i in range(len(idxs)):
                    for j in range(i + 1, len(idxs)):
                        candidate_pairs.add((min(idxs[i], idxs[j]), max(idxs[i], idxs[j])))

        # 3. Candidates sharing at least 2 n-grams and length difference <= 2 (catches all Levenshtein <= 2 pairs)
        for idx, p_obj in enumerate(valid_persons):
            s = p_obj["low"]
            L = p_obj["len"]
            gram_k = 3 if L < 8 else 4
            counts: Dict[int, int] = defaultdict(int)
            for g_i in range(max(1, L - gram_k + 1)):
                for other_idx in trigram_index.get(s[g_i:g_i + gram_k], ()):
                    if other_idx > idx and abs(L - valid_persons[other_idx]["len"]) <= 2:
                        counts[other_idx] += 1
            for other_idx, shared in counts.items():
                if shared >= 1:
                    candidate_pairs.add((idx, other_idx))

        suggestions = []
        for idx1, idx2 in sorted(candidate_pairs):
            p1_obj = valid_persons[idx1]
            p2_obj = valid_persons[idx2]
            p1 = p1_obj["record"]
            p2 = p2_obj["record"]
            id_a, id_b = int(p1["id"]), int(p2["id"])

            if (id_a, id_b) in dismissed or (id_a, id_b) in collisions:
                continue

            n1, n2 = p1_obj["name"], p2_obj["name"]
            low1, low2 = p1_obj["low"], p2_obj["low"]
            w1, w2 = p1_obj["words"], p2_obj["words"]
            shared_insts = p1_obj["insts"].intersection(p2_obj["insts"])
            same_inst = bool(shared_insts)

            is_match = False
            match_type = ""
            reason = ""
            confidence = 0.0

            # Rule 1: Exact case-insensitive match
            if low1 == low2:
                is_match = True
                match_type = "Exact Match (Capitalization Difference)"
                reason = f"Identical name with different capitalization: '{n1}' vs '{n2}'"
                confidence = 100.0

            # Rule 2: Spacing / Punctuation variation
            elif p1_obj["alnum"] == p2_obj["alnum"] and len(p1_obj["alnum"]) >= 4:
                is_match = True
                match_type = "Spacing / Punctuation Variation"
                reason = f"Identical characters with spacing or punctuation difference: '{n1}' vs '{n2}'"
                confidence = 99.0

            # Rule 3: Same-Institution Structural Matches
            if not is_match and same_inst:
                inst_label = ", ".join(sorted(shared_insts))
                # 3a. Inverted name order (e.g. Jathuran Selvendra vs Selvendra Jathuran)
                if set(w1) == set(w2) and len(w1) >= 2:
                    is_match = True
                    match_type = "Inverted Name Order (Same School)"
                    reason = f"Inverted token order in {inst_label}: '{n1}' vs '{n2}'"
                    confidence = 98.0

                # 3b. Middle name addition/omission (e.g. Chenul Nethmira Jayakody vs Chenul Jayakody, or with 1-char surname typo)
                elif (
                    len(w1) >= 2
                    and len(w2) >= 2
                    and len(w1) != len(w2)
                    and w1[0] == w2[0]
                    and (w1[-1] == w2[-1] or (min(len(w1[-1]), len(w2[-1])) >= 6 and (levenshtein_distance_le_2(w1[-1], w2[-1]) or 99) <= 1))
                ):
                    is_match = True
                    match_type = "Middle Name Variation (Same School)"
                    reason = f"Matching first & last name with middle name in {inst_label}: '{n1}' vs '{n2}'"
                    confidence = 96.0

                # 3c. Prefix / Initials affix (e.g. S.M.Yuthmi Vinethya vs Yuthmi Vinethya)
                elif (
                    len(min(low1, low2, key=len)) >= 6
                    and (
                        p1_obj["norm_punct"].endswith(p2_obj["norm_punct"])
                        or p2_obj["norm_punct"].endswith(p1_obj["norm_punct"])
                    )
                ):
                    is_match = True
                    match_type = "Initials / Name Prefix Variation (Same School)"
                    reason = f"Name prefix/initials variation in {inst_label}: '{n1}' vs '{n2}'"
                    confidence = 94.0

                # 3d. Single first name matching a unique debater in the same school (e.g. Chaniel -> Chaniel Obeyesekere)
                elif (len(w1) == 1 and len(w2) >= 2 and w1[0] == w2[0] and len(w1[0]) >= 4) or (
                    len(w2) == 1 and len(w1) >= 2 and w2[0] == w1[0] and len(w2[0]) >= 4
                ):
                    single_tok = w1[0] if len(w1) == 1 else w2[0]
                    # Only auto-match if only 1 full-named debater in that school has this first name
                    max_count = max(inst_token_counts.get((inst_n.lower(), single_tok), 0) for inst_n in shared_insts)
                    if max_count <= 1:
                        is_match = True
                        match_type = "Single First Name Match (Same School)"
                        reason = f"Single name '{single_tok.title()}' uniquely matches full name in {inst_label}"
                        confidence = 92.0

            # Rule 4: Character Typos (Levenshtein <= 2 or high-similarity same-school typo)
            if not is_match:
                d = levenshtein_distance_le_2(low1, low2)
                if d is not None:
                    min_len = min(len(low1), len(low2))
                    # Guardrail 1: Never match short unrelated single names like 'Adam' vs 'Ama' or 'Binuga' vs 'Dinuka'
                    if len(w1) == 1 and len(w2) == 1:
                        if not same_inst or low1[0] != low2[0] or min_len < 5:
                            d = None

                    # Guardrail 2: Don't match different first names sharing a common surname (e.g. Binupa vs Vinuja Bandara, Ethan vs Jehan Fernando, Nesath vs Thesath)
                    if d is not None and len(w1) >= 2 and len(w2) >= 2 and w1[-1] == w2[-1] and w1[0] != w2[0]:
                        fn_d = levenshtein_distance_le_2(w1[0], w2[0])
                        # Must start with the same first letter AND either differ by 1 char or be in the same school with a long first name
                        if w1[0][0] != w2[0][0]:
                            d = None
                        elif fn_d is None or (fn_d == 2 and (not same_inst or min(len(w1[0]), len(w2[0])) < 7)):
                            d = None

                    # Guardrail 3: If first names are identical (e.g. Ashaz Hasan vs Ashaz Hussain), require same institution
                    if d is not None and len(w1) >= 2 and len(w2) >= 2 and w1[0] == w2[0] and w1[-1] != w2[-1]:
                        if not same_inst and d > 1:
                            d = None

                    if d == 1 and min_len >= 5:
                        is_match = True
                        match_type = "1 Character Change Away (Typo / Missing Letter)"
                        reason = f"Names differ by 1 character change: '{n1}' vs '{n2}'"
                        confidence = 96.0 if same_inst else 94.0
                    elif d == 2 and min_len >= 6 and low1[0] == low2[0]:
                        if same_inst or (len(w1) >= 2 and len(w2) >= 2 and (w1[0] == w2[0] or w1[-1] == w2[-1])):
                            is_match = True
                            match_type = "2 Character Changes Away (Transposition / Minor Typo)"
                            reason = f"Names differ by 2 character changes: '{n1}' vs '{n2}'"
                            confidence = 93.0 if same_inst else 90.0

                # Same-school multi-character phonetic spelling variation (e.g. Methuki Weratunga vs Methuki Weerathunga, Umanda Pemarathe vs Umanda Premarathne, Anishka Tissarachi vs Anishka Tissaarachchi, Alosha Sammarachci vs Alosha Samararachchi, Radini Handunnetti vs Randini Handuneththi)
                if not is_match and same_inst and w1 and w2 and w1[0][0] == w2[0][0]:
                    ratio = difflib.SequenceMatcher(None, low1, low2).ratio()
                    if ratio >= 0.88 and abs(len(low1) - len(low2)) <= 3 and len(w1) == len(w2) and len(w1) >= 2:
                        fn_ratio = difflib.SequenceMatcher(None, w1[0], w2[0]).ratio()
                        ln_ratio = difflib.SequenceMatcher(None, w1[-1], w2[-1]).ratio()
                        if fn_ratio >= 0.80 and ln_ratio >= 0.80:
                            inst_label = ", ".join(sorted(shared_insts))
                            is_match = True
                            match_type = "Same-School Phonetic / Spelling Variation"
                            reason = f"High spelling similarity ({int(ratio * 100)}%) in {inst_label}: '{n1}' vs '{n2}'"
                            confidence = 92.0

            if is_match:
                if same_inst and "Same School" not in match_type and shared_insts:
                    reason += f" (Both from {', '.join(sorted(shared_insts))})"

                # Prefer full/longer canonical name if one is a single name or missing middle name,
                # or if speech counts are close (within 5 speeches) and one name has dropped letters
                prefer_longer = match_type in (
                    "Single First Name Match (Same School)",
                    "Middle Name Variation (Same School)",
                )
                if prefer_longer and len(w1) != len(w2):
                    primary, dup = (p1, p2) if len(w1) > len(w2) else (p2, p1)
                elif abs((p1["speech_count"] or 0) - (p2["speech_count"] or 0)) <= 5 and len(n1) != len(n2):
                    primary, dup = (p1, p2) if len(n1) > len(n2) else (p2, p1)
                elif p1["speech_count"] > p2["speech_count"]:
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

    def get_recent_confirmed_merges(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Return recently confirmed/auto-merged person identity resolutions for admin audit visibility."""
        cur = self.conn.cursor()
        try:
            cur.execute("""
                SELECT ir.id, ir.raw_name_a, ir.raw_name_b, ir.person_a_id, ir.person_b_id,
                       ir.confidence_score, ir.reason, ir.decided_at,
                       p.canonical_name as active_canonical_name
                FROM identity_resolutions ir
                LEFT JOIN persons p ON p.id = ir.person_a_id
                WHERE ir.status = 'CONFIRMED_MATCH'
                ORDER BY ir.decided_at DESC, ir.id DESC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []

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

                if suf1 and suf2 and suf1 != suf2:
                    continue

                same_inst = (t1["institution_id"] is not None and t1["institution_id"] == t2["institution_id"]) or (
                    t1["institution_name"] and t1["institution_name"] == t2["institution_name"]
                )
                if not same_inst:
                    continue

                if t1["tournament_id"] != t2["tournament_id"]:
                    continue

                is_match = False
                match_type = ""
                reason = ""
                confidence = 0.0

                if n1_lower == n2_lower and n1 != n2:
                    is_match = True
                    match_type = "Exact Match (Capitalization Difference)"
                    reason = f"Identical team name with different capitalization: '{n1}' vs '{n2}'"
                    confidence = 100.0
                elif n1_nospace == n2_nospace and n1_lower != n2_lower:
                    is_match = True
                    match_type = "Spacing / Whitespace Variation"
                    reason = f"Identical team characters with different spacing: '{n1}' vs '{n2}'"
                    confidence = 98.0
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

    def auto_merge_all(self, min_confidence: float = 90.0) -> Dict[str, Any]:
        """
        Automatically execute merges for all high-confidence duplicate persons and teams
        (confidence >= min_confidence) across up to 3 transitive passes.
        """
        merged_persons: List[Dict[str, Any]] = []
        merged_teams: List[Dict[str, Any]] = []

        for _pass in range(3):
            p_suggs = [s for s in self.get_person_suggestions() if s["confidence"] >= min_confidence]
            t_suggs = [s for s in self.get_team_suggestions() if s["confidence"] >= min_confidence]
            if not p_suggs and not t_suggs:
                break

            merged_in_pass = 0
            consumed_person_ids: Set[int] = set()
            for s in p_suggs:
                pri_id = int(s["primary"]["id"])
                dup_id = int(s["duplicate"]["id"])
                if pri_id in consumed_person_ids or dup_id in consumed_person_ids:
                    continue
                try:
                    res = self.execute_person_merge(pri_id, dup_id)
                    if res.get("success"):
                        consumed_person_ids.add(dup_id)
                        merged_in_pass += 1
                        merged_persons.append({
                            "primary_id": pri_id,
                            "primary_name": s["primary"]["canonical_name"],
                            "duplicate_id": dup_id,
                            "duplicate_name": s["duplicate"]["canonical_name"],
                            "match_type": s["match_type"],
                            "confidence": s["confidence"],
                        })
                except Exception:
                    continue

            consumed_team_ids: Set[int] = set()
            for s in t_suggs:
                pri_id = int(s["primary"]["id"])
                dup_id = int(s["duplicate"]["id"])
                if pri_id in consumed_team_ids or dup_id in consumed_team_ids:
                    continue
                try:
                    res = self.execute_team_merge(pri_id, dup_id)
                    if res.get("success"):
                        consumed_team_ids.add(dup_id)
                        merged_in_pass += 1
                        merged_teams.append({
                            "primary_id": pri_id,
                            "primary_name": s["primary"]["name"],
                            "duplicate_id": dup_id,
                            "duplicate_name": s["duplicate"]["name"],
                            "match_type": s["match_type"],
                            "confidence": s["confidence"],
                        })
                except Exception:
                    continue

            if merged_in_pass == 0:
                break

        return {
            "success": True,
            "merged_persons_count": len(merged_persons),
            "merged_teams_count": len(merged_teams),
            "total_merged": len(merged_persons) + len(merged_teams),
            "merged_persons": merged_persons,
            "merged_teams": merged_teams,
        }

    def execute_person_merge(self, primary_id: int, duplicate_id: int) -> Dict[str, Any]:
        """Merge duplicate person into primary person, cascading all records."""
        if primary_id == duplicate_id:
            raise ValueError("Cannot merge a person into themselves.")

        cur = self.conn.cursor()
        cur.execute("SELECT id, canonical_name FROM persons WHERE id = ?", (primary_id,))
        p1 = cur.fetchone()
        if not p1:
            raise ValueError(f"Target person with ID #{primary_id} does not exist.")

        cur.execute("SELECT id, canonical_name FROM persons WHERE id = ?", (duplicate_id,))
        p2 = cur.fetchone()
        if not p2:
            return {
                "success": True,
                "message": f"Person #{duplicate_id} has already been merged or removed. Canonical target '{p1['canonical_name']}' is current.",
                "primary_name": p1["canonical_name"],
            }

        from atomos.normalizer.identity_merger import IdentityMerger as NormalizerMerger
        merger = NormalizerMerger(self.conn)
        success = merger.merge_persons(canonical_id=primary_id, duplicate_id=duplicate_id, check_collision=True)
        if not success:
            raise RuntimeError(f"Failed to merge person #{duplicate_id} into #{primary_id}")

        return {
            "success": True,
            "message": f"Successfully merged '{p2['canonical_name']}' (#{duplicate_id}) into '{p1['canonical_name']}' (#{primary_id}).",
            "primary_name": p1["canonical_name"],
        }

    def execute_team_merge(self, primary_id: int, duplicate_id: int) -> Dict[str, Any]:
        """Merge duplicate team into primary team."""
        if primary_id == duplicate_id:
            raise ValueError("Cannot merge a team into itself.")

        cur = self.conn.cursor()
        cur.execute("SELECT id, name, canonical_name FROM teams WHERE id = ?", (primary_id,))
        t1 = cur.fetchone()
        if not t1:
            raise ValueError(f"Target team with ID #{primary_id} does not exist.")

        cur.execute("SELECT id, name, canonical_name FROM teams WHERE id = ?", (duplicate_id,))
        t2 = cur.fetchone()
        if not t2:
            return {
                "success": True,
                "message": f"Team #{duplicate_id} has already been merged or removed. Canonical target '{t1['name']}' is current.",
                "primary_name": t1["name"],
            }

        try:
            cur.execute("UPDATE speech_performances SET team_id = ? WHERE team_id = ?", (primary_id, duplicate_id))
            cur.execute("UPDATE OR IGNORE team_members SET team_id = ? WHERE team_id = ?", (primary_id, duplicate_id))
            cur.execute("DELETE FROM team_members WHERE team_id = ?", (duplicate_id,))
            cur.execute("UPDATE debates SET prop_team_id = ? WHERE prop_team_id = ?", (primary_id, duplicate_id))
            cur.execute("UPDATE debates SET opp_team_id = ? WHERE opp_team_id = ?", (primary_id, duplicate_id))
            cur.execute("UPDATE debates SET walkover_winner_id = ? WHERE walkover_winner_id = ?", (primary_id, duplicate_id))
            cur.execute("DELETE FROM team_resolutions WHERE team_id = ?", (duplicate_id,))
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

        if entity_type == "person":
            try:
                cur.execute("SELECT canonical_name FROM persons WHERE id = ?", (id_a,))
                p_a = cur.fetchone()
                cur.execute("SELECT canonical_name FROM persons WHERE id = ?", (id_b,))
                p_b = cur.fetchone()
                name_a = p_a["canonical_name"] if p_a else f"#{id_a}"
                name_b = p_b["canonical_name"] if p_b else f"#{id_b}"
                cur.execute("""
                    INSERT INTO identity_resolutions 
                    (raw_name_a, raw_name_b, person_a_id, person_b_id, status, confidence_score, reason, reviewed_by_user, decided_at)
                    VALUES (?, ?, ?, ?, 'CONFIRMED_DIFFERENT', 0.0, 'Marked different by user', 1, CURRENT_TIMESTAMP)
                """, (name_a, name_b, id_a, id_b))
            except Exception:
                pass

        self.conn.commit()
