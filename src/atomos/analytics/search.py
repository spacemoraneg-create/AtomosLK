"""
Atomos Unified Entity & Motion Search Engine

Enables fast, zero-hallucination entity discovery and resolution across:
1. Debaters (canonical names, aliases, IDs)
2. Institutions (names, codes, acronyms)
3. Teams (tournament rosters, team names)
4. Tournaments (names, slugs)
5. Motions (thematic topics, round info, motion texts)

Designed specifically for LLM tool calling and conversational disambiguation.
"""

from difflib import SequenceMatcher
import html
import re
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple


class UnifiedSearchEngine:
    """Unified search engine across all Atomos entities."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """Compute normalized similarity ratio between two strings."""
        a_clean = a.lower().strip()
        b_clean = b.lower().strip()
        if not a_clean or not b_clean:
            return 0.0
        if a_clean == b_clean:
            return 1.0
        if a_clean in b_clean or b_clean in a_clean:
            return 0.85 + 0.14 * (min(len(a_clean), len(b_clean)) / max(len(a_clean), len(b_clean)))
        return round(SequenceMatcher(None, a_clean, b_clean).ratio(), 5)

    def search_debaters(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search debaters by ID, canonical name, or alias."""
        cur = self.conn.cursor()
        q = query.strip()
        if not q:
            return []

        results = []
        seen_persons: Set[int] = set()

        # 1. Exact ID check
        if q.isdigit():
            cur.execute("""
                SELECT p.id, p.canonical_name,
                       (SELECT i.name FROM tournament_roles tr 
                        JOIN institutions i ON tr.institution_id = i.id 
                        WHERE tr.person_id = p.id AND tr.role = 'DEBATER' 
                        ORDER BY tr.id DESC LIMIT 1) as institution
                FROM persons p
                WHERE p.id = ?
            """, (int(q),))
            row = cur.fetchone()
            if row:
                results.append({
                    "entity_type": "debater",
                    "person_id": row["id"],
                    "name": row["canonical_name"],
                    "institution": row["institution"] or "Independent / Unknown",
                    "matched_on": "person_id",
                    "similarity": 1.0,
                })
                seen_persons.add(row["id"])

        # 2. Database substring search on canonical name and aliases
        like_term = f"%{q}%"
        cur.execute("""
            SELECT p.id, p.canonical_name,
                   (SELECT i.name FROM tournament_roles tr 
                    JOIN institutions i ON tr.institution_id = i.id 
                    WHERE tr.person_id = p.id AND tr.role = 'DEBATER' 
                    ORDER BY tr.id DESC LIMIT 1) as institution,
                   GROUP_CONCAT(pa.raw_name, ' | ') as aliases
            FROM persons p
            LEFT JOIN person_aliases pa ON p.id = pa.person_id
            WHERE p.canonical_name LIKE ? OR pa.raw_name LIKE ?
            GROUP BY p.id
            LIMIT 30
        """, (like_term, like_term))
        rows = cur.fetchall()

        for r in rows:
            pid = r["id"]
            if pid in seen_persons:
                continue

            c_name = r["canonical_name"]
            sim = self._similarity(q, c_name)
            matched_on = "canonical_name"

            # Check aliases
            aliases_str = r["aliases"] or ""
            alias_list = [a.strip() for a in aliases_str.split("|") if a.strip()]
            for alias in alias_list:
                a_sim = self._similarity(q, alias)
                if a_sim > sim:
                    sim = a_sim
                    matched_on = f"alias ({alias})"

            if sim >= 0.5:
                results.append({
                    "entity_type": "debater",
                    "person_id": pid,
                    "name": c_name,
                    "institution": r["institution"] or "Independent / Unknown",
                    "matched_on": matched_on,
                    "similarity": round(sim, 5),
                })
                seen_persons.add(pid)

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    def search_institutions(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search institutions by name or short code."""
        cur = self.conn.cursor()
        q = query.strip()
        if not q:
            return []

        cur.execute("SELECT id, name, code FROM institutions")
        rows = cur.fetchall()

        results = []
        for r in rows:
            name = r["name"]
            code = r["code"] or ""
            sim_name = self._similarity(q, name)
            sim_code = self._similarity(q, code)

            # Acronym / code priority boost
            if q.upper() == code.upper():
                sim = 1.0
                matched_on = f"code ({code})"
            elif sim_code > sim_name:
                sim = sim_code
                matched_on = f"code ({code})"
            else:
                sim = sim_name
                matched_on = "name"

            if sim >= 0.5 or q.lower() in name.lower() or (code and q.lower() == code.lower()):
                results.append({
                    "entity_type": "institution",
                    "institution_id": r["id"],
                    "name": name,
                    "code": code,
                    "matched_on": matched_on,
                    "similarity": round(sim, 5),
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    def search_teams(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search teams across tournaments."""
        cur = self.conn.cursor()
        q = query.strip()
        if not q:
            return []

        like_term = f"%{q}%"
        cur.execute("""
            SELECT t.id, t.name as team_name, t.category,
                   tour.name as tournament_name, tour.slug as tournament_slug,
                   inst.name as institution_name
            FROM teams t
            JOIN tournaments tour ON t.tournament_id = tour.id
            LEFT JOIN institutions inst ON t.institution_id = inst.id
            WHERE t.name LIKE ? OR tour.name LIKE ? OR tour.slug LIKE ?
            LIMIT 30
        """, (like_term, like_term, like_term))
        rows = cur.fetchall()

        results = []
        for r in rows:
            sim = self._similarity(q, r["team_name"])
            if sim >= 0.45 or q.lower() in r["team_name"].lower():
                results.append({
                    "entity_type": "team",
                    "team_id": r["id"],
                    "name": r["team_name"],
                    "institution": r["institution_name"] or "Independent / Composite",
                    "tournament": r["tournament_slug"],
                    "category": r["category"],
                    "similarity": round(sim, 5),
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    CIRCUIT_TOURNAMENT_ALIASES = {
        "slsdc26": ["slsdc", "law fac", "law facs", "law faculty", "faculty of law", "colombo law", "slsdc 2026", "slsdc 26"],
        "Chaps2026": ["chaps", "chaps 26", "chapmans", "chapman", "frances chapman", "chundikuli", "chaps 2026"],
        "vvidc2026": ["vvidc", "visakha", "vishaka", "vvidc 2026"],
        "metho2026": ["metho", "methodist", "shanthi peiris", "metho 2026"],
        "vijis26": ["vijis", "vijis 26", "vijitha", "vijitha weerasinghe", "vijis 2026"],
        "aisdc26": ["aisdc", "ais", "aisdc 2026", "asian international school"],
        "apiitisdc2026": ["apiit", "apiit isdc", "apiit 2026"],
        "ric2026": ["ric", "ric isdc", "royal institute", "isdc 26", "ric 2026"],
    }

    def search_tournaments(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search tournaments by name, slug, or popular circuit alias."""
        cur = self.conn.cursor()
        q = query.strip()
        if not q:
            return []

        cur.execute("SELECT id, name, slug, year, format FROM tournaments")
        rows = cur.fetchall()

        results = []
        q_lower = q.lower()

        for r in rows:
            slug = r["slug"]
            sim_name = self._similarity(q, r["name"])
            sim_slug = self._similarity(q, slug)
            sim = max(sim_name, sim_slug)
            matched_on = "slug" if sim_slug > sim_name else "name"

            if q_lower == slug.lower():
                sim = 1.0

            # Check circuit aliases
            aliases = self.CIRCUIT_TOURNAMENT_ALIASES.get(slug, [])
            for alias in aliases:
                if q_lower == alias or q_lower in alias or alias in q_lower:
                    alias_sim = self._similarity(q_lower, alias)
                    if alias_sim > sim:
                        sim = max(sim, 0.95 if q_lower == alias else 0.88)
                        matched_on = f"alias ({alias})"

            if sim >= 0.45 or q_lower in r["name"].lower() or q_lower in slug.lower():
                results.append({
                    "entity_type": "tournament",
                    "tournament_id": r["id"],
                    "name": r["name"],
                    "slug": slug,
                    "year": r["year"],
                    "format": r["format"],
                    "matched_on": matched_on,
                    "similarity": round(sim, 5),
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    def search_motions(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search motions by motion text, info slide, or round name."""
        from atomos.analytics.motions import MotionAnalytics

        cur = self.conn.cursor()
        q = query.strip()
        if not q:
            return []

        cur.execute("""
            SELECT r.id as round_id, r.name as round_name, r.round_type, r.motion, r.info_slide,
                   tour.name as tournament_name, tour.slug as tournament_slug
            FROM rounds r
            JOIN tournaments tour ON r.tournament_id = tour.id
            WHERE r.motion IS NOT NULL
        """)
        rows = cur.fetchall()

        results = []
        is_short = len(q) <= 3
        pattern = re.compile(rf"\b{re.escape(q)}\b", re.IGNORECASE) if is_short else None

        for r in rows:
            raw_m = html.unescape(r["motion"]).strip()
            theme = MotionAnalytics.classify_motion_theme(raw_m)
            
            matched = False
            sim = 0.0

            if is_short:
                if pattern.search(raw_m) or pattern.search(theme):
                    matched = True
                    sim = 0.95
            else:
                if q.lower() in raw_m.lower():
                    matched = True
                    sim = self._similarity(q, raw_m)
                elif q.lower() in theme.lower():
                    matched = True
                    sim = 0.85
                else:
                    s = self._similarity(q, raw_m)
                    if s >= 0.55:
                        matched = True
                        sim = s

            if matched:
                results.append({
                    "entity_type": "motion",
                    "round_id": r["round_id"],
                    "motion": raw_m,
                    "theme": theme,
                    "round_name": r["round_name"],
                    "round_type": r["round_type"],
                    "tournament": r["tournament_slug"],
                    "similarity": round(sim, 5),
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    def search(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Unified search dispatcher across all entity types.
        
        Args:
            query: The search term (e.g. 'Royal', 'Balishta', 'ISDC', 'Economy')
            entity_types: Optional list of entity types to search ('debater', 'institution', 'team', 'tournament', 'motion').
                          If None, searches across all entity types.
            limit: Maximum total results to return.
        """
        if not entity_types:
            types = ["debater", "institution", "team", "tournament", "motion"]
        else:
            types = [t.lower().strip() for t in entity_types]

        all_matches: List[Dict[str, Any]] = []

        if "debater" in types or "debaters" in types:
            all_matches.extend(self.search_debaters(query, limit=limit))
        if "institution" in types or "institutions" in types or "school" in types or "schools" in types:
            all_matches.extend(self.search_institutions(query, limit=limit))
        if "tournament" in types or "tournaments" in types:
            all_matches.extend(self.search_tournaments(query, limit=limit))
        if "team" in types or "teams" in types:
            all_matches.extend(self.search_teams(query, limit=limit))
        if "motion" in types or "motions" in types:
            all_matches.extend(self.search_motions(query, limit=limit))

        # Sort combined results by similarity score
        all_matches.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)
        return all_matches[:limit]
