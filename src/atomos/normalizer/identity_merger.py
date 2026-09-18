"""
Atomos Identity Merger Engine

Safely resolves and merges duplicate debater and adjudicator records
across all relational tables in the Atomos SQLite database.
Enforces strict foreign key integrity, handles uniqueness collisions,
and records permanent audit entries in identity_resolutions and person_aliases.
"""

from dataclasses import dataclass, field
import difflib
import re
import sqlite3
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class PersonSummary:
    id: int
    canonical_name: str
    institutions: List[str] = field(default_factory=list)
    teams: List[str] = field(default_factory=list)
    tournaments: List[str] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)
    speech_count: int = 0
    sample_scores: List[float] = field(default_factory=list)

    @property
    def institution_str(self) -> str:
        return ", ".join(self.institutions) if self.institutions else "None / Independent"

    @property
    def team_str(self) -> str:
        return ", ".join(self.teams) if self.teams else "None"

    @property
    def tournament_str(self) -> str:
        return ", ".join(self.tournaments) if self.tournaments else "None"


@dataclass
class CandidatePair:
    person_a: PersonSummary
    person_b: PersonSummary
    match_type: str  # 'EXACT_CASE', 'SPACING_PUNCTUATION', 'SAME_INSTITUTION_TYPO', 'CROSS_INSTITUTION'
    similarity: float
    reason: str


class IdentityMerger:
    """Handles entity resolution, relational merging, and candidate discovery."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

    def get_person_summary(self, person_id: int) -> Optional[PersonSummary]:
        """Fetch rich context for a person including speeches, teams, and institutions."""
        cur = self.conn.cursor()
        cur.execute("SELECT id, canonical_name FROM persons WHERE id = ?", (person_id,))
        p_row = cur.fetchone()
        if not p_row:
            return None

        # Fetch institutions
        cur.execute(
            """
            SELECT DISTINCT inst.name
            FROM institutions inst
            JOIN teams t ON t.institution_id = inst.id
            JOIN team_members tm ON tm.team_id = t.id
            WHERE tm.person_id = ?
            UNION
            SELECT DISTINCT inst.name
            FROM institutions inst
            JOIN tournament_roles tr ON tr.institution_id = inst.id
            WHERE tr.person_id = ?
            """,
            (person_id, person_id),
        )
        insts = [r[0] for r in cur.fetchall() if r[0]]

        # Fetch teams
        cur.execute(
            """
            SELECT DISTINCT t.name
            FROM teams t
            JOIN team_members tm ON tm.team_id = t.id
            WHERE tm.person_id = ?
            """,
            (person_id,),
        )
        teams = [r[0] for r in cur.fetchall() if r[0]]

        # Fetch tournaments
        cur.execute(
            """
            SELECT DISTINCT tour.name
            FROM tournaments tour
            JOIN rounds r ON r.tournament_id = tour.id
            JOIN speech_performances sp ON sp.round_id = r.id
            WHERE sp.person_id = ?
            UNION
            SELECT DISTINCT tour.name
            FROM tournaments tour
            JOIN tournament_roles tr ON tr.tournament_id = tour.id
            WHERE tr.person_id = ?
            """,
            (person_id, person_id),
        )
        tournaments = [r[0] for r in cur.fetchall() if r[0]]

        # Fetch roles
        cur.execute("SELECT DISTINCT role FROM tournament_roles WHERE person_id = ?", (person_id,))
        roles = [r[0] for r in cur.fetchall() if r[0]]
        if not roles:
            roles = ["DEBATER"]

        # Fetch speech count and sample scores
        cur.execute(
            """
            SELECT total_score
            FROM speech_performances
            WHERE person_id = ? AND total_score > 0
            ORDER BY id ASC
            """,
            (person_id,),
        )
        scores = [round(float(r[0]), 5) for r in cur.fetchall()]
        sample_scores = scores[:5] if len(scores) <= 5 else scores[:3] + scores[-2:]

        return PersonSummary(
            id=p_row["id"],
            canonical_name=p_row["canonical_name"],
            institutions=insts,
            teams=teams,
            tournaments=tournaments,
            roles=roles,
            speech_count=len(scores),
            sample_scores=sample_scores,
        )

    def search_persons(self, query: str, limit: int = 15) -> List[PersonSummary]:
        """Search persons by name or ID."""
        cur = self.conn.cursor()
        clean_q = query.strip()
        if clean_q.isdigit():
            p = self.get_person_summary(int(clean_q))
            return [p] if p else []

        cur.execute(
            """
            SELECT id FROM persons 
            WHERE canonical_name LIKE ?
            ORDER BY canonical_name ASC
            LIMIT ?
            """,
            (f"%{clean_q}%", limit),
        )
        rows = cur.fetchall()
        results = []
        for r in rows:
            summary = self.get_person_summary(r["id"])
            if summary:
                results.append(summary)
        return results

    def get_debate_collisions(self) -> Set[Tuple[int, int]]:
        """Find all person pairs who competed in the same debate (and therefore cannot be the same person)."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT sp1.person_id, sp2.person_id
            FROM speech_performances sp1
            JOIN speech_performances sp2 ON sp1.debate_id = sp2.debate_id
            WHERE sp1.person_id < sp2.person_id
            """
        )
        return {(int(r[0]), int(r[1])) for r in cur.fetchall()}

    def has_debate_collision(self, id1: int, id2: int) -> bool:
        """Check if two persons ever competed in the same debate."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM speech_performances sp1
            JOIN speech_performances sp2 ON sp1.debate_id = sp2.debate_id
            WHERE sp1.person_id = ? AND sp2.person_id = ?
            LIMIT 1
            """,
            (id1, id2),
        )
        return cur.fetchone() is not None

    def find_candidate_pairs(self) -> List[CandidatePair]:
        """
        Discover potential duplicate person pairs across the entire database.
        Excludes pairs that have already been reviewed/decided in identity_resolutions,
        and strictly excludes pairs who competed in the same debate (collision safety).
        """
        cur = self.conn.cursor()

        # Load all existing decided pairs
        cur.execute(
            """
            SELECT person_a_id, person_b_id 
            FROM identity_resolutions 
            WHERE status IN ('CONFIRMED_MATCH', 'CONFIRMED_DIFFERENT')
               OR reviewed_by_user = 1
            """
        )
        decided_pairs: Set[Tuple[int, int]] = set()
        for r in cur.fetchall():
            a, b = r["person_a_id"], r["person_b_id"]
            if a and b:
                decided_pairs.add((min(a, b), max(a, b)))

        debate_collisions = self.get_debate_collisions()

        # Fetch all persons with basic metadata (look up institutions via team_members and roles)
        cur.execute(
            """
            SELECT p.id, p.canonical_name,
                   (SELECT GROUP_CONCAT(DISTINCT inst.name)
                    FROM institutions inst
                    JOIN teams t ON t.institution_id = inst.id
                    JOIN team_members tm ON tm.team_id = t.id
                    WHERE tm.person_id = p.id) as institutions,
                   COUNT(sp.id) as speech_count
            FROM persons p
            LEFT JOIN speech_performances sp ON p.id = sp.person_id
            GROUP BY p.id
            ORDER BY p.id ASC
            """
        )
        all_p = cur.fetchall()

        candidates: List[CandidatePair] = []
        seen_pairs: Set[Tuple[int, int]] = set()

        def is_pair_available(id1: int, id2: int) -> bool:
            pair_key = (min(id1, id2), max(id1, id2))
            if pair_key in decided_pairs or pair_key in seen_pairs:
                return False
            if pair_key in debate_collisions:
                return False
            return True

        # 1. Exact case-insensitive matches
        by_lower: Dict[str, List[sqlite3.Row]] = {}
        for p in all_p:
            by_lower.setdefault(p["canonical_name"].strip().lower(), []).append(p)

        for low, plist in by_lower.items():
            if len(plist) > 1:
                for i in range(len(plist)):
                    for j in range(i + 1, len(plist)):
                        p1, p2 = plist[i], plist[j]
                        if is_pair_available(p1["id"], p2["id"]):
                            sum1 = self.get_person_summary(p1["id"])
                            sum2 = self.get_person_summary(p2["id"])
                            if sum1 and sum2:
                                candidates.append(
                                    CandidatePair(
                                        person_a=sum1,
                                        person_b=sum2,
                                        match_type="EXACT_CASE",
                                        similarity=1.0,
                                        reason="Exact case-insensitive name match",
                                    )
                                )
                                seen_pairs.add((min(p1["id"], p2["id"]), max(p1["id"], p2["id"])))

        # 2. Normalized spacing / punctuation matches (e.g. S.M. vs S. M. or missing dots)
        def normalize_name(n: str) -> str:
            return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", n.lower())).strip()

        by_norm: Dict[str, List[sqlite3.Row]] = {}
        for p in all_p:
            by_norm.setdefault(normalize_name(p["canonical_name"]), []).append(p)

        for norm, plist in by_norm.items():
            if len(plist) > 1:
                for i in range(len(plist)):
                    for j in range(i + 1, len(plist)):
                        p1, p2 = plist[i], plist[j]
                        if is_pair_available(p1["id"], p2["id"]):
                            sum1 = self.get_person_summary(p1["id"])
                            sum2 = self.get_person_summary(p2["id"])
                            if sum1 and sum2:
                                candidates.append(
                                    CandidatePair(
                                        person_a=sum1,
                                        person_b=sum2,
                                        match_type="SPACING_PUNCTUATION",
                                        similarity=0.99,
                                        reason="Punctuation or spacing variation",
                                    )
                                )
                                seen_pairs.add((min(p1["id"], p2["id"]), max(p1["id"], p2["id"])))

        # 3. High-precision structured matches (Middle names, affixes, single names, inversions, initials)
        for i in range(len(all_p)):
            p1 = all_p[i]
            n1 = p1["canonical_name"].strip()
            inst1 = set((p1["institutions"] or "").split(",")) if p1["institutions"] else set()
            tok1 = [t.lower() for t in n1.split()]

            for j in range(i + 1, len(all_p)):
                p2 = all_p[j]
                if not is_pair_available(p1["id"], p2["id"]):
                    continue

                n2 = p2["canonical_name"].strip()
                inst2 = set((p2["institutions"] or "").split(",")) if p2["institutions"] else set()
                same_inst = bool(inst1.intersection(inst2)) and bool(inst1)
                tok2 = [t.lower() for t in n2.split()]

                sum1: Optional[PersonSummary] = None
                sum2: Optional[PersonSummary] = None

                def load_summaries():
                    nonlocal sum1, sum2
                    if sum1 is None:
                        sum1 = self.get_person_summary(p1["id"])
                        sum2 = self.get_person_summary(p2["id"])
                    return sum1 and sum2

                if same_inst:
                    # Inverted name order (e.g. Jathuran Selvendra vs Selvendra Jathuran)
                    if set(tok1) == set(tok2) and len(tok1) >= 2:
                        if load_summaries():
                            candidates.append(
                                CandidatePair(
                                    person_a=sum1,
                                    person_b=sum2,
                                    match_type="NAME_INVERSION",
                                    similarity=0.98,
                                    reason=f"Inverted name order in same school ({', '.join(inst1.intersection(inst2))})",
                                )
                            )
                            seen_pairs.add((min(p1["id"], p2["id"]), max(p1["id"], p2["id"])))
                            continue

                    # Middle name addition (e.g. Kumal Premathunga vs Kumal Seniru Premathunga)
                    if len(tok1) >= 2 and len(tok2) >= 2 and tok1[0] == tok2[0] and tok1[-1] == tok2[-1]:
                        if load_summaries():
                            candidates.append(
                                CandidatePair(
                                    person_a=sum1,
                                    person_b=sum2,
                                    match_type="MIDDLE_NAME",
                                    similarity=0.95,
                                    reason=f"Matching first & last name with middle name added in {', '.join(inst1.intersection(inst2))}",
                                )
                            )
                            seen_pairs.add((min(p1["id"], p2["id"]), max(p1["id"], p2["id"])))
                            continue

                    # Prefix / Suffix Substring (e.g. Kenuli Esara vs H. A. Kenuli Esara)
                    if n1.lower().endswith(n2.lower()) or n2.lower().endswith(n1.lower()):
                        if load_summaries():
                            candidates.append(
                                CandidatePair(
                                    person_a=sum1,
                                    person_b=sum2,
                                    match_type="NAME_AFFIX",
                                    similarity=0.92,
                                    reason=f"Name prefix/suffix variation in {', '.join(inst1.intersection(inst2))}",
                                )
                            )
                            seen_pairs.add((min(p1["id"], p2["id"]), max(p1["id"], p2["id"])))
                            continue

                    # Single name substring (e.g. Ananya vs Ananya Nandakumar)
                    if (len(tok1) == 1 and tok1[0] in tok2 and len(tok1[0]) >= 4) or (len(tok2) == 1 and tok2[0] in tok1 and len(tok2[0]) >= 4):
                        if load_summaries():
                            candidates.append(
                                CandidatePair(
                                    person_a=sum1,
                                    person_b=sum2,
                                    match_type="SINGLE_NAME",
                                    similarity=0.90,
                                    reason=f"Single name matches part of full name in {', '.join(inst1.intersection(inst2))}",
                                )
                            )
                            seen_pairs.add((min(p1["id"], p2["id"]), max(p1["id"], p2["id"])))
                            continue

                    # Initials matching (e.g. A. S. Sharwin vs Anson Satheez Sharwin)
                    if tok1[-1] == tok2[-1] and (len(tok1[0]) <= 2 or len(tok2[0]) <= 2) and tok1[0][0] == tok2[0][0]:
                        if load_summaries():
                            candidates.append(
                                CandidatePair(
                                    person_a=sum1,
                                    person_b=sum2,
                                    match_type="INITIALS_MATCH",
                                    similarity=0.88,
                                    reason=f"Initials match with same surname in {', '.join(inst1.intersection(inst2))}",
                                )
                            )
                            seen_pairs.add((min(p1["id"], p2["id"]), max(p1["id"], p2["id"])))
                            continue

                    # Typo in same institution (first name initial must match)
                    ratio = difflib.SequenceMatcher(None, n1.lower(), n2.lower()).ratio()
                    if ratio >= 0.82 and abs(len(n1) - len(n2)) <= 3 and tok1[0][0] == tok2[0][0]:
                        if load_summaries():
                            candidates.append(
                                CandidatePair(
                                    person_a=sum1,
                                    person_b=sum2,
                                    match_type="SAME_INSTITUTION_TYPO",
                                    similarity=ratio,
                                    reason=f"Same institution typo ({int(ratio*100)}%) in {', '.join(inst1.intersection(inst2))}",
                                )
                            )
                            seen_pairs.add((min(p1["id"], p2["id"]), max(p1["id"], p2["id"])))
                            continue

                else:
                    # Cross institution high similarity (first name initial must match)
                    ratio = difflib.SequenceMatcher(None, n1.lower(), n2.lower()).ratio()
                    if ratio >= 0.88 and abs(len(n1) - len(n2)) <= 3 and tok1 and tok2 and tok1[0][0] == tok2[0][0]:
                        if load_summaries():
                            candidates.append(
                                CandidatePair(
                                    person_a=sum1,
                                    person_b=sum2,
                                    match_type="CROSS_INSTITUTION",
                                    similarity=ratio,
                                    reason=f"High name similarity ({int(ratio*100)}%) across institutions",
                                )
                            )
                            seen_pairs.add((min(p1["id"], p2["id"]), max(p1["id"], p2["id"])))
                            continue

        # Sort order: priority by tier, then similarity, then total speech volume
        type_priority = {
            "EXACT_CASE": 7,
            "SPACING_PUNCTUATION": 6,
            "NAME_INVERSION": 5,
            "MIDDLE_NAME": 4,
            "NAME_AFFIX": 3,
            "SINGLE_NAME": 2,
            "INITIALS_MATCH": 2,
            "SAME_INSTITUTION_TYPO": 1,
            "CROSS_INSTITUTION": 0,
        }
        candidates.sort(
            key=lambda c: (
                type_priority.get(c.match_type, 0),
                c.similarity,
                c.person_a.speech_count + c.person_b.speech_count,
            ),
            reverse=True,
        )
        return candidates

    def merge_persons(
        self,
        canonical_id: int,
        duplicate_id: int,
        canonical_name: Optional[str] = None,
        check_collision: bool = False,
    ) -> bool:
        """
        Merge duplicate_id into canonical_id in an atomic SQLite transaction.
        All dependent records are transferred to canonical_id.
        Unique constraints on team_members, tournament_roles, adjudicator_assignments are protected.
        Duplicate's canonical name is added to person_aliases for future automated resolution.
        """
        if canonical_id == duplicate_id:
            raise ValueError("Cannot merge a person into themselves")

        if check_collision and self.has_debate_collision(canonical_id, duplicate_id):
            raise ValueError(f"Cannot merge Person #{canonical_id} and Person #{duplicate_id}: both competed in the same debate.")

        cur = self.conn.cursor()

        # Verify both exist
        cur.execute("SELECT id, canonical_name FROM persons WHERE id = ?", (canonical_id,))
        canon_p = cur.fetchone()
        if not canon_p:
            raise ValueError(f"Canonical person with ID {canonical_id} does not exist")

        cur.execute("SELECT id, canonical_name FROM persons WHERE id = ?", (duplicate_id,))
        dup_p = cur.fetchone()
        if not dup_p:
            raise ValueError(f"Duplicate person with ID {duplicate_id} does not exist")

        target_name = canonical_name.strip() if canonical_name and canonical_name.strip() else canon_p["canonical_name"]
        dup_name = dup_p["canonical_name"]

        try:
            cur.execute("SAVEPOINT identity_merge")

            # 1. Re-link speech_performances
            cur.execute(
                "UPDATE speech_performances SET person_id = ? WHERE person_id = ?",
                (canonical_id, duplicate_id),
            )

            # 2. Re-link team_members (handle UNIQUE(team_id, person_id))
            cur.execute("SELECT team_id FROM team_members WHERE person_id = ?", (duplicate_id,))
            dup_teams = [r[0] for r in cur.fetchall()]
            for t_id in dup_teams:
                cur.execute(
                    "SELECT id FROM team_members WHERE team_id = ? AND person_id = ?",
                    (t_id, canonical_id),
                )
                if cur.fetchone():
                    cur.execute(
                        "DELETE FROM team_members WHERE team_id = ? AND person_id = ?",
                        (t_id, duplicate_id),
                    )
                else:
                    cur.execute(
                        "UPDATE team_members SET person_id = ? WHERE team_id = ? AND person_id = ?",
                        (canonical_id, t_id, duplicate_id),
                    )

            # 3. Re-link tournament_roles (handle UNIQUE(tournament_id, person_id, role))
            cur.execute(
                "SELECT tournament_id, role FROM tournament_roles WHERE person_id = ?",
                (duplicate_id,),
            )
            dup_roles = cur.fetchall()
            for r in dup_roles:
                t_id, role = r["tournament_id"], r["role"]
                cur.execute(
                    "SELECT id FROM tournament_roles WHERE tournament_id = ? AND person_id = ? AND role = ?",
                    (t_id, canonical_id, role),
                )
                if cur.fetchone():
                    cur.execute(
                        "DELETE FROM tournament_roles WHERE tournament_id = ? AND person_id = ? AND role = ?",
                        (t_id, duplicate_id, role),
                    )
                else:
                    cur.execute(
                        "UPDATE tournament_roles SET person_id = ? WHERE tournament_id = ? AND person_id = ?",
                        (canonical_id, t_id, duplicate_id),
                    )

            # 4. Re-link adjudicator_assignments (handle UNIQUE(debate_id, person_id))
            cur.execute(
                "SELECT debate_id FROM adjudicator_assignments WHERE person_id = ?",
                (duplicate_id,),
            )
            dup_debates = [r[0] for r in cur.fetchall()]
            for d_id in dup_debates:
                cur.execute(
                    "SELECT id FROM adjudicator_assignments WHERE debate_id = ? AND person_id = ?",
                    (d_id, canonical_id),
                )
                if cur.fetchone():
                    cur.execute(
                        "DELETE FROM adjudicator_assignments WHERE debate_id = ? AND person_id = ?",
                        (d_id, duplicate_id),
                    )
                else:
                    cur.execute(
                        "UPDATE adjudicator_assignments SET person_id = ? WHERE debate_id = ? AND person_id = ?",
                        (canonical_id, d_id, duplicate_id),
                    )

            # 5. Re-link adjudicator_ballots
            cur.execute(
                "UPDATE adjudicator_ballots SET adjudicator_person_id = ? WHERE adjudicator_person_id = ?",
                (canonical_id, duplicate_id),
            )

            # 6. Re-link person_aliases (handle UNIQUE(person_id, raw_name))
            cur.execute(
                "SELECT raw_name, source_tournament_id FROM person_aliases WHERE person_id = ?",
                (duplicate_id,),
            )
            dup_aliases = cur.fetchall()
            for al in dup_aliases:
                raw_n, t_src = al["raw_name"], al["source_tournament_id"]
                cur.execute(
                    "SELECT id FROM person_aliases WHERE person_id = ? AND raw_name = ?",
                    (canonical_id, raw_n),
                )
                if cur.fetchone():
                    cur.execute(
                        "DELETE FROM person_aliases WHERE person_id = ? AND raw_name = ?",
                        (duplicate_id, raw_n),
                    )
                else:
                    cur.execute(
                        "UPDATE person_aliases SET person_id = ? WHERE person_id = ? AND raw_name = ?",
                        (canonical_id, duplicate_id, raw_n),
                    )

            # Also add duplicate's canonical name as an alias for canonical_id
            cur.execute(
                "INSERT OR IGNORE INTO person_aliases (person_id, raw_name) VALUES (?, ?)",
                (canonical_id, dup_name),
            )

            # 7. Update identity_resolutions
            # Find the direct resolution ID(s)
            cur.execute(
                """
                SELECT id FROM identity_resolutions
                WHERE (person_a_id = ? AND person_b_id = ?)
                   OR (person_a_id = ? AND person_b_id = ?)
                """,
                (canonical_id, duplicate_id, duplicate_id, canonical_id),
            )
            match_rows = cur.fetchall()
            match_ids = [r["id"] for r in match_rows]

            if match_ids:
                cur.execute(
                    f"""
                    UPDATE identity_resolutions
                    SET status = 'CONFIRMED_MATCH', reviewed_by_user = 1, decided_at = CURRENT_TIMESTAMP
                    WHERE id IN ({','.join('?' * len(match_ids))})
                    """,
                    match_ids,
                )
            else:
                cur.execute(
                    """
                    INSERT INTO identity_resolutions 
                    (raw_name_a, raw_name_b, person_a_id, person_b_id, status, confidence_score, reason, reviewed_by_user, decided_at)
                    VALUES (?, ?, ?, ?, 'CONFIRMED_MATCH', 1.0, 'User merged identity', 1, CURRENT_TIMESTAMP)
                    """,
                    (canon_p["canonical_name"], dup_name, canonical_id, duplicate_id),
                )
                match_ids = [cur.lastrowid]

            # Re-point other pending pairs referencing duplicate_id to canonical_id (excluding match_ids)
            cur.execute(
                f"UPDATE identity_resolutions SET person_a_id = ? WHERE person_a_id = ? AND id NOT IN ({','.join('?' * len(match_ids))})",
                [canonical_id, duplicate_id] + match_ids,
            )
            cur.execute(
                f"UPDATE identity_resolutions SET person_b_id = ? WHERE person_b_id = ? AND id NOT IN ({','.join('?' * len(match_ids))})",
                [canonical_id, duplicate_id] + match_ids,
            )
            # Remove redundant self-referencing pairs if any other resolutions collapsed
            cur.execute(
                f"DELETE FROM identity_resolutions WHERE person_a_id = person_b_id AND id NOT IN ({','.join('?' * len(match_ids))})",
                match_ids,
            )


            # 8. Update target person's name if customized
            if target_name != canon_p["canonical_name"]:
                cur.execute(
                    "UPDATE persons SET canonical_name = ? WHERE id = ?",
                    (target_name, canonical_id),
                )
                cur.execute(
                    "INSERT OR IGNORE INTO person_aliases (person_id, raw_name) VALUES (?, ?)",
                    (canonical_id, canon_p["canonical_name"]),
                )

            # 9. Delete duplicate person record
            cur.execute("DELETE FROM persons WHERE id = ?", (duplicate_id,))

            # 10. Check SQLite foreign key integrity
            cur.execute("PRAGMA foreign_key_check;")
            fk_errors = cur.fetchall()
            if fk_errors:
                raise RuntimeError(f"Foreign key integrity check failed after merge: {fk_errors}")

            cur.execute("RELEASE identity_merge")
            self.conn.commit()
            return True

        except Exception as e:
            cur.execute("ROLLBACK TO identity_merge")
            cur.execute("RELEASE identity_merge")
            raise e

    def reject_match(
        self, person_a_id: int, person_b_id: int, reason: str = "Different people"
    ) -> bool:
        """Mark a candidate pair as CONFIRMED_DIFFERENT so it is permanently dismissed."""
        cur = self.conn.cursor()

        cur.execute(
            """
            UPDATE identity_resolutions
            SET status = 'CONFIRMED_DIFFERENT', reviewed_by_user = 1, decided_at = CURRENT_TIMESTAMP, reason = ?
            WHERE (person_a_id = ? AND person_b_id = ?)
               OR (person_a_id = ? AND person_b_id = ?)
            """,
            (reason, person_a_id, person_b_id, person_b_id, person_a_id),
        )

        if cur.rowcount == 0:
            cur.execute("SELECT canonical_name FROM persons WHERE id = ?", (person_a_id,))
            r_a = cur.fetchone()
            cur.execute("SELECT canonical_name FROM persons WHERE id = ?", (person_b_id,))
            r_b = cur.fetchone()
            name_a = r_a["canonical_name"] if r_a else f"ID {person_a_id}"
            name_b = r_b["canonical_name"] if r_b else f"ID {person_b_id}"

            cur.execute(
                """
                INSERT INTO identity_resolutions
                (raw_name_a, raw_name_b, person_a_id, person_b_id, status, confidence_score, reason, reviewed_by_user, decided_at)
                VALUES (?, ?, ?, ?, 'CONFIRMED_DIFFERENT', 0.0, ?, 1, CURRENT_TIMESTAMP)
                """,
                (name_a, name_b, person_a_id, person_b_id, reason),
            )

        self.conn.commit()
        return True
