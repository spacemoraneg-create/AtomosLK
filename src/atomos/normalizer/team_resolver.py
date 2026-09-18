"""
Atomos Team Resolver and Grouping Engine

Provides intelligent entity resolution and grouping for debate teams across tournaments.
Links tournament-specific team instances (e.g. 'BC Gold', 'BC Purple', 'LC Red', 'LC White')
to canonical circuit identities and competitive tiers ('A', 'B', 'C', 'D', 'NOVICE', 'SWING', 'OTHER').
Employs exact pattern matching, circuit color/roman-numeral knowledge, and debater roster
overlap heuristics to propose high-confidence groupings with full auditability.
"""

from dataclasses import dataclass, field
import datetime
import re
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple


VALID_TIERS = ('A', 'B', 'C', 'D', 'NOVICE', 'SWING', 'OTHER')

# Institution-specific aliases: school_code -> {token: (tier, reason)}
KNOWN_SCHOOL_ALIASES: Dict[str, Dict[str, Tuple[str, str]]] = {
    "AIS": {
        "green": ("A", "AIS Green is Tier A (flagship team)"),
        "blue": ("B", "AIS Blue is Tier B (junior team)"),
        "lóng": ("A", "AIS Lóng is Tier A"),
        "long": ("A", "AIS Long is Tier A"),
        "tao": ("B", "AIS Tao is Tier B"),
    },
    "BC": {
        "gold": ("A", "Circuit color convention: BC Gold is Tier A"),
        "purple": ("B", "Circuit color convention: BC Purple is Tier B"),
    },
    "LC": {
        "red": ("A", "Circuit color convention: LC Red is Tier A"),
        "white": ("B", "Circuit color convention: LC White is Tier B"),
    },
    "NC": {
        "maroon": ("A", "Circuit color convention: NC Maroon is Tier A"),
        "silver": ("B", "Circuit color convention: NC Silver is Tier B"),
    },
    "HFC": {
        "blue": ("A", "Circuit color convention: HFC Blue is Tier A"),
        "white": ("B", "Circuit color convention: HFC White is Tier B"),
    },
    "VV": {
        "ix": ("A", "Visakha Grade 9 flagship team (Tier A)"),
        "vi": ("B", "Visakha Grade 6 junior team (Tier B)"),
        "vii": ("C", "Visakha Grade 7 intermediate team (Tier C)"),
    },
    "TCK": {
        "munchi": ("A", "TCK Munchi is Tier A (flagship team)"),
        "senukans": ("B", "TCK Senukans is Tier B"),
        "juchith": ("C", "TCK Juchith is Tier C"),
        "pettiya": ("D", "TCK Pettiya is Tier D"),
    },
    "AC": {
        "labhiyavasabha": ("B", "AC Labhiyavasabha is Tier B"),
        "theraputthabhaya": ("C", "AC Theraputthabhaya is Tier C"),
        "gotaimbara": ("D", "AC Gotaimbara is Tier D"),
    },
    "CIS": {
        "ram": ("A", "CIS Ram is Tier A"),
    },
    "HCK": {
        "sahas": ("A", "HCK Sahas is Tier A"),
        "sanithma": ("B", "HCK Sanithma is Tier B"),
    },
}

# Generic fallback aliases mapped to (default_tier, reason)
GENERIC_CIRCUIT_ALIASES: Dict[str, Tuple[str, str]] = {
    "gold": ("A", "Circuit color convention: Gold is Tier A"),
    "purple": ("B", "Circuit color convention: Purple is Tier B"),
    "red": ("A", "Circuit color convention: Red is Tier A"),
    "white": ("B", "Circuit color convention: White is Tier B"),
    "maroon": ("A", "Circuit color convention: Maroon is Tier A"),
    "silver": ("B", "Circuit color convention: Silver is Tier B"),
}


@dataclass
class TeamMemberInfo:
    person_id: int
    name: str
    member_order: int = 1


@dataclass
class TeamSummary:
    id: int
    raw_name: str
    canonical_name: Optional[str]
    tier: Optional[str]
    institution_id: Optional[int]
    institution_name: Optional[str]
    institution_code: Optional[str]
    tournament_id: int
    tournament_name: str
    tournament_slug: str
    members: List[TeamMemberInfo] = field(default_factory=list)
    debates_count: int = 0
    wins_count: int = 0
    avg_team_score: Optional[float] = None
    status: str = "PENDING"

    @property
    def member_names(self) -> List[str]:
        return [m.name for m in self.members]

    @property
    def member_names_str(self) -> str:
        return ", ".join(self.member_names) if self.members else "No members recorded"

    @property
    def record_str(self) -> str:
        if self.debates_count == 0:
            return "0 debates"
        losses = self.debates_count - self.wins_count
        score_str = f", ATSS {self.avg_team_score:.2f}" if self.avg_team_score else ""
        return f"{self.debates_count} debates ({self.wins_count}W - {losses}L{score_str})"


@dataclass
class CandidateTeamResolution:
    team: TeamSummary
    suggested_canonical_name: str
    suggested_tier: str
    match_type: str  # 'STANDARD_SUFFIX', 'COLOR_ALIAS', 'ROMAN_NUMERAL', 'ROSTER_OVERLAP', 'SOLO_TEAM', 'SWING_BYE'
    confidence: float
    reason: str
    overlapping_members: List[str] = field(default_factory=list)


class TeamResolver:
    """Resolves, groups, and maps teams to canonical names and tiers."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

    def get_team_summary(self, team_id: int) -> Optional[TeamSummary]:
        """Fetch complete team metadata, members, and debate stats."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT t.id, t.name as raw_name, t.canonical_name, t.tier,
                   t.institution_id, i.name as institution_name, i.code as institution_code,
                   t.tournament_id, tour.name as tournament_name, tour.slug as tournament_slug,
                   tr.status as resolution_status
            FROM teams t
            LEFT JOIN institutions i ON t.institution_id = i.id
            JOIN tournaments tour ON t.tournament_id = tour.id
            LEFT JOIN team_resolutions tr ON tr.team_id = t.id
            WHERE t.id = ?
            """,
            (team_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        # Fetch members
        cur.execute(
            """
            SELECT tm.person_id, p.canonical_name, tm.member_order
            FROM team_members tm
            JOIN persons p ON tm.person_id = p.id
            WHERE tm.team_id = ?
            ORDER BY tm.member_order, p.canonical_name
            """,
            (team_id,),
        )
        members = [
            TeamMemberInfo(person_id=m[0], name=m[1], member_order=m[2])
            for m in cur.fetchall()
        ]

        # Fetch debates and win stats
        cur.execute(
            """
            SELECT 
                COUNT(d.id) as debates_count,
                AVG(CASE WHEN d.prop_team_id = ? THEN ab.prop_total_score ELSE ab.opp_total_score END) as avg_score
            FROM debates d
            JOIN adjudicator_ballots ab ON ab.debate_id = d.id
            WHERE (d.prop_team_id = ? OR d.opp_team_id = ?)
              AND ab.prop_total_score IS NOT NULL
            """,
            (team_id, team_id, team_id),
        )
        stats = cur.fetchone()
        debates_cnt = 0
        wins_cnt = 0
        avg_score = None
        if stats and stats["debates_count"]:
            cur.execute(
                """
                SELECT d.id,
                       SUM(CASE WHEN (d.prop_team_id = ? AND ab.winner_side = 'Proposition') OR
                                    (d.opp_team_id = ? AND ab.winner_side = 'Opposition') THEN 1 ELSE 0 END) as our_votes,
                       COUNT(ab.id) as total_votes
                FROM debates d
                JOIN adjudicator_ballots ab ON ab.debate_id = d.id
                WHERE (d.prop_team_id = ? OR d.opp_team_id = ?)
                  AND ab.prop_total_score IS NOT NULL
                GROUP BY d.id
                """,
                (team_id, team_id, team_id, team_id),
            )
            debate_rows = cur.fetchall()
            debates_cnt = len(debate_rows)
            wins_cnt = sum(1 for dr in debate_rows if dr["our_votes"] > dr["total_votes"] / 2.0)
            avg_score = round(stats["avg_score"], 2) if stats["avg_score"] else None

        status = "RESOLVED" if (row["canonical_name"] and row["tier"]) else "PENDING"

        return TeamSummary(
            id=row["id"],
            raw_name=row["raw_name"],
            canonical_name=row["canonical_name"],
            tier=row["tier"],
            institution_id=row["institution_id"],
            institution_name=row["institution_name"],
            institution_code=row["institution_code"],
            tournament_id=row["tournament_id"],
            tournament_name=row["tournament_name"],
            tournament_slug=row["tournament_slug"],
            members=members,
            debates_count=debates_cnt,
            wins_count=wins_cnt,
            avg_team_score=avg_score,
            status=status,
        )

    def list_teams(
        self,
        institution_id: Optional[int] = None,
        tournament_id: Optional[int] = None,
        unresolved_only: bool = False,
    ) -> List[TeamSummary]:
        """List teams matching criteria."""
        query = "SELECT id FROM teams WHERE 1=1"
        params = []
        if institution_id is not None:
            query += " AND institution_id = ?"
            params.append(institution_id)
        if tournament_id is not None:
            query += " AND tournament_id = ?"
            params.append(tournament_id)
        if unresolved_only:
            query += " AND (canonical_name IS NULL OR tier IS NULL)"
        query += " ORDER BY institution_id, name"

        cur = self.conn.cursor()
        cur.execute(query, params)
        team_ids = [r[0] for r in cur.fetchall()]
        return [s for tid in team_ids if (s := self.get_team_summary(tid)) is not None]

    def get_institutions(self) -> List[Dict[str, Any]]:
        """Return institutions with team resolution statistics."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT i.id, i.name, i.code,
                   COUNT(t.id) as total_teams,
                   SUM(CASE WHEN t.canonical_name IS NOT NULL AND t.tier IS NOT NULL THEN 1 ELSE 0 END) as resolved_teams
            FROM institutions i
            LEFT JOIN teams t ON t.institution_id = i.id
            GROUP BY i.id
            HAVING COUNT(t.id) > 0
            ORDER BY COUNT(t.id) DESC, i.name
            """
        )
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "code": r["code"],
                "total_teams": r["total_teams"],
                "resolved_teams": r["resolved_teams"] or 0,
                "pending_teams": r["total_teams"] - (r["resolved_teams"] or 0),
            }
            for r in cur.fetchall()
        ]

    def find_candidate_resolutions(
        self,
        institution_id: Optional[int] = None,
        unresolved_only: bool = True,
    ) -> List[CandidateTeamResolution]:
        """
        Discovers and scores candidate resolutions for teams using pattern matching,
        circuit knowledge, and roster overlap analysis.
        """
        teams = self.list_teams(institution_id=institution_id, unresolved_only=unresolved_only)
        if not teams:
            return []

        # Pre-fetch all teams for the relevant institutions to enable cross-team roster comparison
        inst_ids = {t.institution_id for t in teams if t.institution_id}
        inst_teams_map: Dict[int, List[TeamSummary]] = {}
        for i_id in inst_ids:
            inst_teams_map[i_id] = self.list_teams(institution_id=i_id, unresolved_only=False)

        candidates = []
        for team in teams:
            all_inst_teams = inst_teams_map.get(team.institution_id, []) if team.institution_id else []
            cand = self._infer_team_resolution(team, all_inst_teams)
            candidates.append(cand)

        return candidates

    def _infer_team_resolution(
        self,
        team: TeamSummary,
        institution_teams: List[TeamSummary],
    ) -> CandidateTeamResolution:
        """Infer the canonical name and tier for a team."""
        name = team.raw_name.strip()
        code = team.institution_code or (team.institution_name.split()[0] if team.institution_name else "Team")

        # 1. Swing or BYE
        if re.match(r"^swing(\s+\w+)?$", name, re.IGNORECASE):
            return CandidateTeamResolution(
                team=team,
                suggested_canonical_name="Swing",
                suggested_tier="SWING",
                match_type="SWING_BYE",
                confidence=1.0,
                reason="Swing team placeholder",
            )
        if re.match(r"^bye$", name, re.IGNORECASE):
            return CandidateTeamResolution(
                team=team,
                suggested_canonical_name="BYE",
                suggested_tier="OTHER",
                match_type="SWING_BYE",
                confidence=1.0,
                reason="BYE round placeholder",
            )

        # 2. Standard Letter Suffix: e.g. 'DS A', 'BC B', 'Trinity A', 'HFC C', 'VV D'
        letter_match = re.search(r"(?:\s+|-)([A-D])$", name, re.IGNORECASE)
        if letter_match:
            tier = letter_match.group(1).upper()
            canonical = f"{code} {tier}"
            return CandidateTeamResolution(
                team=team,
                suggested_canonical_name=canonical,
                suggested_tier=tier,
                match_type="STANDARD_SUFFIX",
                confidence=1.0,
                reason=f"Standard tier suffix '{tier}' in raw name '{name}'",
            )

        # 3. Institution-Specific Aliases
        tokens = [t.lower() for t in re.split(r"[\s_-]+", name)]
        if code in KNOWN_SCHOOL_ALIASES:
            for token in tokens:
                if token in KNOWN_SCHOOL_ALIASES[code]:
                    tier, alias_reason = KNOWN_SCHOOL_ALIASES[code][token]
                    canonical = f"{code} {tier}"
                    return CandidateTeamResolution(
                        team=team,
                        suggested_canonical_name=canonical,
                        suggested_tier=tier,
                        match_type="COLOR_ALIAS",
                        confidence=0.95,
                        reason=f"Known {code} alias '{token.capitalize()}': {alias_reason}",
                    )

        # 4. Debater Roster Overlap Heuristic
        # Compare member person IDs to known A/B/C/D teams of the same institution
        if team.members and institution_teams:
            our_person_ids = {m.person_id for m in team.members}
            tier_rosters: Dict[str, Set[int]] = {"A": set(), "B": set(), "C": set(), "D": set()}
            tier_person_names: Dict[int, str] = {}

            for other in institution_teams:
                if other.id == team.id:
                    continue
                # Determine other team's tier if known
                other_tier = other.tier
                if not other_tier:
                    m = re.search(r"(?:\s+|-)([A-D])$", other.raw_name, re.IGNORECASE)
                    if m:
                        other_tier = m.group(1).upper()
                if other_tier in tier_rosters:
                    for mem in other.members:
                        tier_rosters[other_tier].add(mem.person_id)
                        tier_person_names[mem.person_id] = mem.name

            best_tier = None
            best_overlap_count = 0
            best_overlapping_names = []

            for t_code in ("A", "B", "C", "D"):
                overlap_pids = our_person_ids & tier_rosters[t_code]
                if len(overlap_pids) > best_overlap_count:
                    best_overlap_count = len(overlap_pids)
                    best_tier = t_code
                    best_overlapping_names = [tier_person_names[pid] for pid in overlap_pids]

            if best_tier and best_overlap_count > 0:
                overlap_ratio = best_overlap_count / max(1, len(our_person_ids))
                conf = round(min(0.92, 0.60 + (overlap_ratio * 0.32)), 2)
                overlap_str = ", ".join(best_overlapping_names)
                return CandidateTeamResolution(
                    team=team,
                    suggested_canonical_name=f"{code} {best_tier}",
                    suggested_tier=best_tier,
                    match_type="ROSTER_OVERLAP",
                    confidence=conf,
                    reason=f"Roster overlap ({best_overlap_count}/{len(our_person_ids)} speakers with Tier {best_tier}): {overlap_str}",
                    overlapping_members=best_overlapping_names,
                )

        # 5. Generic Circuit Aliases
        for token in tokens:
            if token in GENERIC_CIRCUIT_ALIASES:
                tier, alias_reason = GENERIC_CIRCUIT_ALIASES[token]
                canonical = f"{code} {tier}"
                return CandidateTeamResolution(
                    team=team,
                    suggested_canonical_name=canonical,
                    suggested_tier=tier,
                    match_type="COLOR_ALIAS",
                    confidence=0.85,
                    reason=f"Generic circuit alias '{token.capitalize()}': {alias_reason}",
                )

        # 6. Solo School Team Fallback
        return CandidateTeamResolution(
            team=team,
            suggested_canonical_name=f"{code} A",
            suggested_tier="A",
            match_type="SOLO_TEAM",
            confidence=0.70,
            reason=f"Sole / primary school entry '{name}', defaults to Tier A",
        )

    def resolve_team(
        self,
        team_id: int,
        canonical_name: str,
        tier: str,
        reason: str = "",
        reviewed_by_user: bool = False,
        confidence: float = 1.0,
        status: str = "CONFIRMED",
    ) -> bool:
        """
        Persistently update a team's canonical name and tier, and record an audit entry.
        """
        tier_upper = tier.strip().upper()
        if tier_upper not in VALID_TIERS:
            raise ValueError(f"Invalid tier '{tier}'. Must be one of: {VALID_TIERS}")

        cur = self.conn.cursor()
        cur.execute("SELECT id, institution_id, name FROM teams WHERE id = ?", (team_id,))
        team = cur.fetchone()
        if not team:
            raise ValueError(f"Team with ID {team_id} does not exist.")

        inst_id = team["institution_id"]

        # Update teams table
        cur.execute(
            """
            UPDATE teams
            SET canonical_name = ?, tier = ?
            WHERE id = ?
            """,
            (canonical_name.strip(), tier_upper, team_id),
        )

        # Upsert into team_resolutions audit table
        cur.execute(
            """
            INSERT INTO team_resolutions (
                team_id, canonical_name, tier, institution_id,
                status, confidence, reason, reviewed_by_user, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(team_id) DO UPDATE SET
                canonical_name = excluded.canonical_name,
                tier = excluded.tier,
                institution_id = excluded.institution_id,
                status = excluded.status,
                confidence = excluded.confidence,
                reason = excluded.reason,
                reviewed_by_user = excluded.reviewed_by_user,
                decided_at = CURRENT_TIMESTAMP
            """,
            (
                team_id,
                canonical_name.strip(),
                tier_upper,
                inst_id,
                status,
                confidence,
                reason or ("User manual grouping" if reviewed_by_user else "Automated resolution"),
                1 if reviewed_by_user else 0,
            ),
        )

        self.conn.commit()
        return True

    def group_teams(
        self,
        team_ids: List[int],
        canonical_name: str,
        tier: str,
        reason: str = "Manual grouping",
        reviewed_by_user: bool = True,
    ) -> int:
        """Assign a list of team IDs to the same canonical name and tier."""
        resolved_count = 0
        for tid in team_ids:
            if self.resolve_team(
                team_id=tid,
                canonical_name=canonical_name,
                tier=tier,
                reason=reason,
                reviewed_by_user=reviewed_by_user,
                confidence=1.0,
                status="CONFIRMED",
            ):
                resolved_count += 1
        return resolved_count

    def auto_resolve_safe(self, min_confidence: float = 0.90) -> int:
        """
        Batch-resolve high-confidence candidates (standard letters, verified color aliases, swings).
        """
        candidates = self.find_candidate_resolutions(unresolved_only=True)
        safe_cands = [c for c in candidates if c.confidence >= min_confidence]

        resolved_count = 0
        for c in safe_cands:
            self.resolve_team(
                team_id=c.team.id,
                canonical_name=c.suggested_canonical_name,
                tier=c.suggested_tier,
                reason=c.reason,
                reviewed_by_user=False,
                confidence=c.confidence,
                status="CONFIRMED",
            )
            resolved_count += 1

        return resolved_count

    def reset_resolutions(
        self,
        team_ids: Optional[List[int]] = None,
        institution_id: Optional[int] = None,
    ) -> int:
        """Reset resolution assignments back to NULL for specified teams or school."""
        cur = self.conn.cursor()
        if team_ids:
            placeholders = ",".join(["?"] * len(team_ids))
            cur.execute(f"UPDATE teams SET canonical_name = NULL, tier = NULL WHERE id IN ({placeholders})", team_ids)
            cur.execute(f"DELETE FROM team_resolutions WHERE team_id IN ({placeholders})", team_ids)
            cnt = cur.rowcount
        elif institution_id:
            cur.execute("UPDATE teams SET canonical_name = NULL, tier = NULL WHERE institution_id = ?", (institution_id,))
            cur.execute("DELETE FROM team_resolutions WHERE institution_id = ?", (institution_id,))
            cnt = cur.rowcount
        else:
            cur.execute("UPDATE teams SET canonical_name = NULL, tier = NULL")
            cur.execute("DELETE FROM team_resolutions")
            cnt = cur.rowcount
        self.conn.commit()
        return cnt

    def get_resolution_audit(self, team_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch audit entries from team_resolutions."""
        cur = self.conn.cursor()
        query = """
            SELECT tr.id, tr.team_id, t.name as raw_name, tr.canonical_name, tr.tier,
                   i.name as institution_name, tr.status, tr.confidence, tr.reason,
                   tr.reviewed_by_user, tr.created_at, tr.decided_at
            FROM team_resolutions tr
            JOIN teams t ON tr.team_id = t.id
            LEFT JOIN institutions i ON tr.institution_id = i.id
        """
        params = []
        if team_id is not None:
            query += " WHERE tr.team_id = ?"
            params.append(team_id)
        query += " ORDER BY tr.decided_at DESC"

        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
