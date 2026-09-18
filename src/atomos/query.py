"""
Atomos Unified Query Engine

A centralized, high-performance Python facade providing unified access to all
Atomos analytical layers, forensics, and intelligence data.

Designed for:
1. In-process execution with zero subprocess overhead (< 10ms responses).
2. Clean, typed, 100% JSON-serializable dictionary outputs.
3. Natural integration into LLM agent loops, REST APIs, and notebooks.
"""

from collections import defaultdict
import dataclasses
import sqlite3
from typing import Any, Dict, List, Optional, Union

from atomos.database.connection import get_connection
from atomos.analytics.critical_stats import CriticalStatsEngine
from atomos.analytics.debater_profile import DebaterProfileEngine
from atomos.analytics.head_to_head import HeadToHeadEngine
from atomos.analytics.institutions import InstitutionAnalytics
from atomos.analytics.master_tabs import MasterTabEngine
from atomos.analytics.motions import MotionAnalytics
from atomos.analytics.search import UnifiedSearchEngine
from atomos.analytics.brackets import BracketEngine
from atomos.analytics.judges import JudgeAnalyticsEngine
from atomos.analytics.predictor import MatchPredictor
from atomos.analytics.tournaments import TournamentRankingsEngine
from atomos.analytics.activity import ActivityLeaderboardEngine


class AtomosQuery:
    """Unified query facade for Atomos debate intelligence."""

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        self._conn = conn or get_connection()
        self._search_engine = UnifiedSearchEngine(self._conn)
        self._debater_engine = DebaterProfileEngine(self._conn)
        self._h2h_engine = HeadToHeadEngine(self._conn)
        self._inst_engine = InstitutionAnalytics(self._conn)
        self._master_engine = MasterTabEngine(self._conn)
        self._motion_engine = MotionAnalytics(self._conn)
        self._critical_engine = CriticalStatsEngine(self._conn)
        self._bracket_engine = BracketEngine(self._conn)
        self._judge_engine = JudgeAnalyticsEngine(self._conn)
        self._predictor = MatchPredictor(self._conn)
        self._tournament_engine = TournamentRankingsEngine(self._conn)
        self._activity_engine = ActivityLeaderboardEngine(self._conn)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def search(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Unified search across debaters, institutions, teams, tournaments, and motions.
        """
        return self._search_engine.search(query, entity_types=entity_types, limit=limit)

    def get_debater(
        self,
        identifier: Union[int, str],
        compact: bool = True,
    ) -> Dict[str, Any]:
        """
        Fetch full debater identity dossier, career record, and rankings.
        
        Args:
            identifier: Person ID (e.g. 42) or debater name/alias (e.g. 'Balishta Wijesinghe')
            compact: If True, omits verbose round-by-round speech arrays and derivation text
                     to minimize token usage for LLMs.
        """
        person_id: Optional[int] = None
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            person_id = int(identifier)
        else:
            # Fuzzy match debater
            matches = self._search_engine.search_debaters(str(identifier), limit=1)
            if matches:
                person_id = matches[0]["person_id"]

        if person_id is None:
            return {"error": f"Debater '{identifier}' not found in database."}

        prof = self._debater_engine.get_profile(person_id)
        if not prof:
            return {"error": f"No debater profile found for ID #{person_id}."}

        data = dataclasses.asdict(prof)
        if compact:
            data.pop("derivation_text", None)
            for t in data.get("tournaments", []):
                t.pop("prelim_rounds", None)
                t.pop("elim_rounds", None)

        return data

    def get_head_to_head(
        self,
        entity_a: str,
        entity_b: str,
        mode: str = "auto",
    ) -> Dict[str, Any]:
        """
        Compute direct head-to-head clash record between two entities.
        
        Args:
            entity_a: Name or ID of entity A
            entity_b: Name or ID of entity B
            mode: Comparison mode ('auto', 'debater', 'team', 'school')
        """
        m = mode.lower().strip()

        # School mode
        if m in ("school", "institution"):
            res = self.compare_institutions(entity_a, entity_b)
            if "error" not in res:
                res["comparison_type"] = "school"
            return res

        # Team mode
        if m == "team":
            clash = self._h2h_engine.compare_teams(entity_a, entity_b)
            if not clash:
                return {"error": f"Could not generate team comparison for '{entity_a}' and '{entity_b}'."}
            res = dataclasses.asdict(clash)
            res["comparison_type"] = "team"
            return res

        # Debater mode
        if m == "debater":
            p_a = self._resolve_debater_id(entity_a)
            p_b = self._resolve_debater_id(entity_b)
            if not p_a or not p_b:
                return {"error": f"Could not resolve debaters '{entity_a}' and '{entity_b}'."}
            clash = self._h2h_engine.compare_debaters(p_a, p_b)
            if not clash:
                return {"error": f"Could not generate debater comparison for #{p_a} and #{p_b}."}
            res = dataclasses.asdict(clash)
            res["comparison_type"] = "debater"
            return res

        # Auto mode
        # 1. Try school first
        pa = self._inst_engine.get_institution_profile(entity_a)
        pb = self._inst_engine.get_institution_profile(entity_b)
        if pa and pb:
            res = self.compare_institutions(entity_a, entity_b)
            if "error" not in res:
                res["comparison_type"] = "school"
            return res

        # 2. Try debaters
        p_a = self._resolve_debater_id(entity_a)
        p_b = self._resolve_debater_id(entity_b)
        if p_a and p_b:
            clash = self._h2h_engine.compare_debaters(p_a, p_b)
            if clash:
                res = dataclasses.asdict(clash)
                res["comparison_type"] = "debater"
                return res

        # 3. Try teams
        clash = self._h2h_engine.compare_teams(entity_a, entity_b)
        if clash:
            res = dataclasses.asdict(clash)
            res["comparison_type"] = "team"
            return res

        return {"error": f"Could not resolve or compare '{entity_a}' and '{entity_b}' in auto mode."}

    def _resolve_debater_id(self, val: Union[int, str]) -> Optional[int]:
        """Helper to resolve debater identifier to person_id."""
        if isinstance(val, int) or (isinstance(val, str) and val.isdigit()):
            return int(val)
        matches = self._search_engine.search_debaters(str(val), limit=1)
        return matches[0]["person_id"] if matches else None

    def compare_institutions(
        self,
        school_a: str,
        school_b: str,
    ) -> Dict[str, Any]:
        """
        Side-by-side institutional comparison with IPI standings, direct debates, and mutual rivals.
        """
        pa = self._inst_engine.get_institution_profile(school_a)
        pb = self._inst_engine.get_institution_profile(school_b)

        if not pa:
            return {"error": f"Institution '{school_a}' not found."}
        if not pb:
            return {"error": f"Institution '{school_b}' not found."}

        cmp_res = self._inst_engine.compare_institutions(pa.institution_id, pb.institution_id)
        if not cmp_res:
            return {"error": f"Could not compare '{pa.name}' and '{pb.name}'."}

        return dataclasses.asdict(cmp_res)

    def get_institutional_leaderboard(
        self,
        min_debates: int = 5,
        sort_by: str = "ipi",
    ) -> List[Dict[str, Any]]:
        """
        Fetch national Institutional Power Index (IPI) power rankings.
        """
        if sort_by == "delta":
            return self._inst_engine.get_institutional_delta_leaderboard()
        return self._inst_engine.get_institutional_power_index(min_debates=min_debates, sort_by=sort_by)

    def get_institutional_delta_leaderboard(self) -> List[Dict[str, Any]]:
        """
        Fetch official Institutional Delta leaderboard.
        """
        return self._inst_engine.get_institutional_delta_leaderboard()

    def get_circuit_summary(self) -> Dict[str, Any]:
        """
        Fetch high-level circuit vital statistics, motions, and top performers.
        """
        cur = self._conn.cursor()
        
        cur.execute("SELECT COUNT(*) as cnt FROM persons")
        total_persons = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM institutions")
        total_institutions = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM tournaments")
        total_tournaments = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM debates WHERE is_walkover = 0")
        total_debates = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM speech_performances WHERE is_valid_rubric = 1")
        total_speeches = cur.fetchone()["cnt"]

        side_balance = self._motion_engine.get_overall_side_balance()

        return {
            "total_persons": total_persons,
            "total_institutions": total_institutions,
            "total_tournaments": total_tournaments,
            "total_debates_debated": total_debates,
            "total_valid_speeches": total_speeches,
            "national_side_balance": side_balance,
        }

    def get_motion_analytics(
        self,
        theme: Optional[str] = None,
        query: Optional[str] = None,
        extreme_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch motion analytics, side biases, and thematic topic performance.
        """
        res: Dict[str, Any] = {
            "overall_side_balance": self._motion_engine.get_overall_side_balance(),
            "tournament_side_balance": self._motion_engine.get_tournament_side_balance(),
            "round_type_side_balance": self._motion_engine.get_round_type_side_balance(),
            "thematic_analysis": self._motion_engine.get_thematic_motion_analysis(),
        }

        if extreme_only:
            res["extreme_and_balanced"] = self._motion_engine.get_extreme_motions()

        if query:
            res["search_results"] = self._search_engine.search_motions(query, limit=20)

        if theme:
            all_motions = self._motion_engine.get_motion_balance_report(min_debates=1)
            res["filtered_motions"] = [m for m in all_motions if theme.lower() in m["theme"].lower()]

        return res

    def get_critical_stats(
        self,
        min_tournaments: int = 3,
        regulation: str = "new",
    ) -> Dict[str, Any]:
        """
        Fetch high-rigor critical speaker and team statistics (>= 3 tournaments).
        Supports regulation='new' (cumulative speech average, priority) or 'legacy' (avg of avgs).
        """
        speaker_stats = self._critical_engine.get_critical_speaker_stats(
            min_tournaments=min_tournaments,
            regulation=regulation,
        )
        team_stats = self._critical_engine.get_critical_team_stats(min_tournaments=min_tournaments)
        return {
            "speakers": speaker_stats,
            "teams": team_stats,
            "regulation": regulation,
        }

    def get_speaker_leaderboard(
        self,
        metric: str = "master_tab",
        limit: int = 10,
        qualified_tournaments_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Retrieve debater leaderboards across various circuit metrics:
        - 'prelims': most preliminary rounds debated (COUNT(DISTINCT sp.round_id))
        - 'debates': total debates debated (COUNT(DISTINCT sp.debate_id))
        - 'master_tab': highest substantive speaker average on Master Tab
        - 'critical_stats': top ranked speakers on national Critical Stats
        - 'replies': highest reply speech average (min 3 replies)
        
        Args:
            metric: Metric to rank by ('prelims', 'debates', 'master_tab', 'critical_stats', 'replies')
            limit: Maximum debaters to return (default: 10, max: 50)
            qualified_tournaments_only: If True, for prelim volume rankings, only counts
                rounds from tournaments where the debater met the Speaker Tab threshold (>= 3 prelim rounds).
        """
        limit = min(max(1, limit), 50)
        cur = self._conn.cursor()

        if metric in ("prelims", "volume"):
            if qualified_tournaments_only:
                cur.execute("""
                    WITH tourn_prelims AS (
                        SELECT sp.person_id, r.tournament_id, COUNT(DISTINCT sp.round_id) as rounds_in_tourn
                        FROM speech_performances sp
                        JOIN rounds r ON sp.round_id = r.id
                        WHERE r.round_type = 'PRELIMINARY'
                        GROUP BY sp.person_id, r.tournament_id
                    )
                    SELECT p.id as person_id, p.canonical_name, p.national_level,
                           (SELECT inst.name FROM institutions inst 
                            JOIN teams tm ON tm.institution_id = inst.id 
                            JOIN team_members tmm ON tmm.team_id = tm.id 
                            WHERE tmm.person_id = p.id LIMIT 1) as institution,
                           SUM(CASE WHEN tp.rounds_in_tourn >= 3 THEN tp.rounds_in_tourn ELSE 0 END) as prelim_rounds_debated,
                           COUNT(CASE WHEN tp.rounds_in_tourn >= 3 THEN 1 END) as tournaments_debated,
                           SUM(tp.rounds_in_tourn) as raw_total_prelims,
                           COUNT(tp.tournament_id) as raw_total_tournaments
                    FROM tourn_prelims tp
                    JOIN persons p ON tp.person_id = p.id
                    GROUP BY p.id
                    ORDER BY prelim_rounds_debated DESC, raw_total_prelims DESC, p.canonical_name ASC
                    LIMIT ?
                """, (limit,))
                rows = [dict(r) for r in cur.fetchall()]
                for rank, r in enumerate(rows, 1):
                    r["rank"] = rank
                return {
                    "metric": "qualified_prelim_rounds_debated",
                    "qualified_tournaments_only": True,
                    "min_rounds_per_tournament": 3,
                    "total_returned": len(rows),
                    "leaderboard": rows,
                }
            else:
                cur.execute("""
                    SELECT p.id as person_id, p.canonical_name, p.national_level,
                           (SELECT inst.name FROM institutions inst 
                            JOIN teams tm ON tm.institution_id = inst.id 
                            JOIN team_members tmm ON tmm.team_id = tm.id 
                            WHERE tmm.person_id = p.id LIMIT 1) as institution,
                           COUNT(DISTINCT sp.round_id) as prelim_rounds_debated,
                           COUNT(DISTINCT r.tournament_id) as tournaments_debated,
                           COUNT(DISTINCT sp.debate_id) as total_debates
                    FROM speech_performances sp
                    JOIN rounds r ON sp.round_id = r.id
                    JOIN persons p ON sp.person_id = p.id
                    WHERE r.round_type = 'PRELIMINARY'
                    GROUP BY p.id
                    ORDER BY prelim_rounds_debated DESC, total_debates DESC, p.canonical_name ASC
                    LIMIT ?
                """, (limit,))
                rows = [dict(r) for r in cur.fetchall()]
                for rank, r in enumerate(rows, 1):
                    r["rank"] = rank
                return {
                    "metric": "prelim_rounds_debated",
                    "qualified_tournaments_only": False,
                    "total_returned": len(rows),
                    "leaderboard": rows,
                }

        elif metric == "debates":
            cur.execute("""
                SELECT p.id as person_id, p.canonical_name, p.national_level,
                       (SELECT inst.name FROM institutions inst 
                        JOIN teams tm ON tm.institution_id = inst.id 
                        JOIN team_members tmm ON tmm.team_id = tm.id 
                        WHERE tmm.person_id = p.id LIMIT 1) as institution,
                       COUNT(DISTINCT sp.debate_id) as total_debates,
                       COUNT(DISTINCT CASE WHEN r.round_type = 'PRELIMINARY' THEN sp.round_id END) as prelim_rounds,
                       COUNT(DISTINCT r.tournament_id) as tournaments_debated
                FROM speech_performances sp
                JOIN rounds r ON sp.round_id = r.id
                JOIN persons p ON sp.person_id = p.id
                GROUP BY p.id
                ORDER BY total_debates DESC, prelim_rounds DESC, p.canonical_name ASC
                LIMIT ?
            """, (limit,))
            rows = [dict(r) for r in cur.fetchall()]
            for rank, r in enumerate(rows, 1):
                r["rank"] = rank
            return {
                "metric": "total_debates",
                "total_returned": len(rows),
                "leaderboard": rows,
            }

        elif metric == "critical_stats":
            cstats = self._critical_engine.get_critical_speaker_stats(min_tournaments=3)
            return {
                "metric": "critical_stats",
                "total_returned": min(limit, len(cstats)),
                "leaderboard": cstats[:limit],
            }

        elif metric == "replies":
            rtab = self._master_engine.get_master_reply_tab(min_speeches=1)
            return {
                "metric": "master_reply_tab",
                "total_returned": min(limit, len(rtab)),
                "leaderboard": rtab[:limit],
            }

        else:  # default 'master_tab'
            mtab = self._master_engine.get_master_speaker_tab(min_tournaments=1)
            return {
                "metric": "master_speaker_tab",
                "total_returned": min(limit, len(mtab)),
                "leaderboard": mtab[:limit],
            }

    def get_tournament_finals(self, tournament: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch Grand Finals and elimination stage results across tournaments.
        Supports tournament name, slug, or popular circuit alias (e.g. 'Law Fac', 'SLSDC', 'Chaps', 'Visakha').
        Identifies participating teams, institutions, winner, and same-school closeouts.
        """
        cur = self._conn.cursor()

        target_tourn_ids = None
        if tournament:
            t_search = self._search_engine.search_tournaments(tournament, limit=1)
            if t_search:
                target_tourn_ids = [t_search[0]["tournament_id"]]
            else:
                cur.execute("SELECT id FROM tournaments WHERE slug LIKE ? OR name LIKE ?", (f"%{tournament}%", f"%{tournament}%"))
                target_tourn_ids = [r[0] for r in cur.fetchall()]

        query = """
            SELECT t.id as tournament_id, t.name as tournament_name, t.slug as tournament_slug, t.year,
                   r.id as round_id, r.round_number, r.name as round_name, r.round_type,
                   d.id as debate_id, d.venue,
                   prop.id as prop_team_id, prop.name as prop_team_name,
                   prop_inst.id as prop_inst_id, prop_inst.name as prop_inst_name, prop_inst.code as prop_inst_code,
                   opp.id as opp_team_id, opp.name as opp_team_name,
                   opp_inst.id as opp_inst_id, opp_inst.name as opp_inst_name, opp_inst.code as opp_inst_code,
                   ab.winner_side, ab.win_margin
            FROM tournaments t
            JOIN rounds r ON r.tournament_id = t.id
            JOIN debates d ON d.round_id = r.id
            JOIN teams prop ON d.prop_team_id = prop.id
            JOIN teams opp ON d.opp_team_id = opp.id
            JOIN institutions prop_inst ON prop.institution_id = prop_inst.id
            JOIN institutions opp_inst ON opp.institution_id = opp_inst.id
            LEFT JOIN adjudicator_ballots ab ON ab.debate_id = d.id
            WHERE (r.tournament_id, r.round_number) IN (
                SELECT tournament_id, MAX(round_number)
                FROM rounds
                WHERE round_type = 'ELIMINATION'
                GROUP BY tournament_id
            )
        """
        params: List[Any] = []
        if target_tourn_ids:
            placeholders = ",".join("?" for _ in target_tourn_ids)
            query += f" AND t.id IN ({placeholders})"
            params.extend(target_tourn_ids)

        query += " GROUP BY d.id ORDER BY t.id"

        cur.execute(query, params)
        rows = cur.fetchall()

        finals = []
        same_school_count = 0
        for r in rows:
            is_same_school = (r["prop_inst_id"] == r["opp_inst_id"])
            if is_same_school:
                same_school_count += 1

            winner_team = None
            winner_inst = None
            if r["winner_side"] == "Proposition":
                winner_team = r["prop_team_name"]
                winner_inst = r["prop_inst_name"]
            elif r["winner_side"] == "Opposition":
                winner_team = r["opp_team_name"]
                winner_inst = r["opp_inst_name"]

            finals.append({
                "tournament_id": r["tournament_id"],
                "tournament_name": r["tournament_name"],
                "tournament_slug": r["tournament_slug"],
                "year": r["year"],
                "round_number": r["round_number"],
                "round_name": r["round_name"],
                "venue": r["venue"],
                "is_same_institution_final": is_same_school,
                "institution_name": r["prop_inst_name"] if is_same_school else None,
                "proposition": {
                    "team_name": r["prop_team_name"],
                    "institution": r["prop_inst_name"],
                    "institution_code": r["prop_inst_code"],
                },
                "opposition": {
                    "team_name": r["opp_team_name"],
                    "institution": r["opp_inst_name"],
                    "institution_code": r["opp_inst_code"],
                },
                "winner_side": r["winner_side"],
                "winner_team": winner_team,
                "winner_institution": winner_inst,
                "win_margin": r["win_margin"],
            })

        return {
            "total_finals": len(finals),
            "same_institution_finals_count": same_school_count,
            "finals": finals,
        }

    def get_debate_ballot(
        self,
        tournament: Optional[str] = None,
        round_number: Optional[Union[int, str]] = None,
        round_name: Optional[str] = None,
        team: Optional[str] = None,
        debater: Optional[str] = None,
        debate_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve the official debate ballot, scoresheet, and full speaker lineup for a specific debate.
        Forensically resolves Proposition vs Opposition teams, speaker positions (1st, 2nd, 3rd, Reply),
        individual speech scores, panel ballots, margins, and adjudicators.
        """
        cur = self._conn.cursor()
        target_debate_id = debate_id

        if target_debate_id is None:
            where_clauses = []
            params = []

            if tournament:
                where_clauses.append("(t.name LIKE ? OR t.slug LIKE ?)")
                params.extend([f"%{tournament}%", f"%{tournament}%"])

            if round_number is not None:
                where_clauses.append("(r.round_number = ? OR r.name LIKE ?)")
                params.extend([int(round_number) if str(round_number).isdigit() else -1, f"%{round_number}%"])

            if round_name:
                where_clauses.append("r.name LIKE ?")
                params.append(f"%{round_name}%")

            if team:
                where_clauses.append("(prop.name LIKE ? OR opp.name LIKE ?)")
                params.extend([f"%{team}%", f"%{team}%"])

            if debater:
                where_clauses.append("""
                    d.id IN (
                        SELECT DISTINCT sp.debate_id
                        FROM speech_performances sp
                        JOIN persons p ON sp.person_id = p.id
                        LEFT JOIN person_aliases pa ON pa.person_id = p.id
                        WHERE p.canonical_name LIKE ? OR pa.raw_name LIKE ?
                    )
                """)
                params.extend([f"%{debater}%", f"%{debater}%"])

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            cand_sql = f"""
                SELECT d.id, t.name as t_name, r.round_number, r.name as r_name,
                       prop.name as prop_team, opp.name as opp_team
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                JOIN tournaments t ON r.tournament_id = t.id
                JOIN teams prop ON d.prop_team_id = prop.id
                JOIN teams opp ON d.opp_team_id = opp.id
                WHERE {where_sql}
                ORDER BY d.id
            """
            cur.execute(cand_sql, params)
            candidates = cur.fetchall()

            if not candidates:
                return {"error": "No matching debate found for the specified criteria."}
            if len(candidates) > 1 and not (team or debater):
                return {
                    "error": f"Multiple debates ({len(candidates)}) found. Please specify team or debater to disambiguate.",
                    "candidates": [
                        {
                            "debate_id": c["id"],
                            "tournament": c["t_name"],
                            "round": c["r_name"],
                            "matchup": f"{c['prop_team']} vs {c['opp_team']}"
                        }
                        for c in candidates[:10]
                    ]
                }
            target_debate_id = candidates[0]["id"]

        # Fetch debate metadata
        cur.execute("""
            SELECT d.id as debate_id, d.venue,
                   r.id as round_id, r.round_number, r.name as round_name, r.round_type, r.motion, r.info_slide,
                   t.id as tournament_id, t.name as tournament_name, t.slug as tournament_slug, t.year,
                   prop.id as prop_team_id, prop.name as prop_team_name,
                   prop_inst.id as prop_inst_id, prop_inst.name as prop_inst_name, prop_inst.code as prop_inst_code,
                   opp.id as opp_team_id, opp.name as opp_team_name,
                   opp_inst.id as opp_inst_id, opp_inst.name as opp_inst_name, opp_inst.code as opp_inst_code
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN teams prop ON d.prop_team_id = prop.id
            JOIN teams opp ON d.opp_team_id = opp.id
            JOIN institutions prop_inst ON prop.institution_id = prop_inst.id
            JOIN institutions opp_inst ON opp.institution_id = opp_inst.id
            WHERE d.id = ?
        """, (target_debate_id,))
        deb = cur.fetchone()
        if not deb:
            return {"error": f"Debate #{target_debate_id} not found."}

        # Fetch ballots
        cur.execute("""
            SELECT ab.id, ab.adjudicator_raw_name, ab.adjudicator_institution,
                   ab.prop_total_score, ab.opp_total_score, ab.win_margin, ab.winner_side
            FROM adjudicator_ballots ab
            WHERE ab.debate_id = ?
            ORDER BY ab.id
        """, (target_debate_id,))
        ballots = cur.fetchall()

        # Fetch speeches
        cur.execute("""
            SELECT sp.id, sp.ballot_id, sp.side, sp.position, sp.speech_type, sp.total_score,
                   sp.team_id, p.id as person_id, p.canonical_name,
                   ab.adjudicator_raw_name
            FROM speech_performances sp
            JOIN persons p ON sp.person_id = p.id
            LEFT JOIN adjudicator_ballots ab ON sp.ballot_id = ab.id
            WHERE sp.debate_id = ?
            ORDER BY CASE sp.position WHEN '1st' THEN 1 WHEN '2nd' THEN 2 WHEN '3rd' THEN 3 WHEN 'Reply' THEN 4 ELSE 5 END,
                     sp.ballot_id
        """, (target_debate_id,))
        speeches = cur.fetchall()

        # Group speeches by side and position
        prop_speeches: Dict[str, Any] = {}
        opp_speeches: Dict[str, Any] = {}

        for s in speeches:
            side_dict = prop_speeches if s["side"] == "Proposition" else opp_speeches
            pos = s["position"]
            if pos not in side_dict:
                side_dict[pos] = {
                    "position": pos,
                    "speech_type": s["speech_type"],
                    "speaker_name": s["canonical_name"],
                    "person_id": s["person_id"],
                    "scores": [],
                    "ballot_breakdown": []
                }
            side_dict[pos]["scores"].append(s["total_score"])
            if s["adjudicator_raw_name"]:
                side_dict[pos]["ballot_breakdown"].append({
                    "adjudicator": s["adjudicator_raw_name"],
                    "score": s["total_score"]
                })

        def format_lineup(side_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
            lineup = []
            for pos in ["1st", "2nd", "3rd", "Reply"]:
                if pos in side_dict:
                    sp = side_dict[pos]
                    avg_score = round(sum(sp["scores"]) / len(sp["scores"]), 5) if sp["scores"] else 0.0
                    entry: Dict[str, Any] = {
                        "position": pos,
                        "speaker_name": sp["speaker_name"],
                        "person_id": sp["person_id"],
                        "speech_type": sp["speech_type"],
                        "score": avg_score
                    }
                    if len(sp["ballot_breakdown"]) > 1:
                        entry["ballot_scores"] = sp["ballot_breakdown"]
                    lineup.append(entry)
            return lineup

        prop_lineup = format_lineup(prop_speeches)
        opp_lineup = format_lineup(opp_speeches)

        # Tally ballots & winner
        prop_votes = sum(1 for b in ballots if b["winner_side"] == "Proposition")
        opp_votes = sum(1 for b in ballots if b["winner_side"] == "Opposition")
        total_ballots = len(ballots)

        winner_side = None
        winner_team = None
        if prop_votes > opp_votes:
            winner_side = "Proposition"
            winner_team = deb["prop_team_name"]
        elif opp_votes > prop_votes:
            winner_side = "Opposition"
            winner_team = deb["opp_team_name"]

        prop_avg_score = round(sum(b["prop_total_score"] for b in ballots if b["prop_total_score"]) / total_ballots, 5) if total_ballots else 0.0
        opp_avg_score = round(sum(b["opp_total_score"] for b in ballots if b["opp_total_score"]) / total_ballots, 5) if total_ballots else 0.0
        margin = round(abs(prop_avg_score - opp_avg_score), 5)

        if total_ballots > 1:
            win_votes = max(prop_votes, opp_votes)
            loss_votes = min(prop_votes, opp_votes)
            decision = f"{winner_team} ({winner_side}) won on a {win_votes}-{loss_votes} decision (Avg: {prop_avg_score} vs {opp_avg_score})"
        elif total_ballots == 1:
            decision = f"{winner_team} ({winner_side}) won by {margin} pts ({opp_avg_score if winner_side == 'Opposition' else prop_avg_score} - {prop_avg_score if winner_side == 'Opposition' else opp_avg_score})"
        else:
            decision = "No ballot recorded"

        adjudicators_list = [
            {
                "name": b["adjudicator_raw_name"],
                "institution": b["adjudicator_institution"],
                "voted_for": b["winner_side"],
                "prop_score": b["prop_total_score"],
                "opp_score": b["opp_total_score"],
                "margin": b["win_margin"]
            }
            for b in ballots
        ]

        return {
            "debate_id": deb["debate_id"],
            "tournament": {
                "id": deb["tournament_id"],
                "name": deb["tournament_name"],
                "slug": deb["tournament_slug"],
                "year": deb["year"]
            },
            "round": {
                "id": deb["round_id"],
                "round_number": deb["round_number"],
                "round_name": deb["round_name"],
                "round_type": deb["round_type"],
                "motion": deb["motion"],
                "info_slide": deb["info_slide"]
            },
            "venue": deb["venue"],
            "proposition": {
                "team_name": deb["prop_team_name"],
                "team_id": deb["prop_team_id"],
                "institution": deb["prop_inst_name"],
                "institution_code": deb["prop_inst_code"],
                "lineup": prop_lineup,
                "total_score": prop_avg_score
            },
            "opposition": {
                "team_name": deb["opp_team_name"],
                "team_id": deb["opp_team_id"],
                "institution": deb["opp_inst_name"],
                "institution_code": deb["opp_inst_code"],
                "lineup": opp_lineup,
                "total_score": opp_avg_score
            },
            "result": {
                "winner_side": winner_side,
                "winner_team": winner_team,
                "decision": decision,
                "prop_ballots": prop_votes,
                "opp_ballots": opp_votes,
                "margin": margin
            },
            "adjudicators": adjudicators_list
        }

    def get_team_record(
        self,
        team_name: str,
        tournament: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve comprehensive team debate records, highest team score, highest quality debate
        (highest combined score), tournament campaign summaries (ATSS, wins/losses), and official
        round-by-round scores averaged across adjudicators.
        """
        cur = self._conn.cursor()

        tourn_clause = "AND (t.name LIKE ? OR t.slug LIKE ?)" if tournament else ""
        sql = f"""
            SELECT t.id as tournament_id, t.name as tournament_name, t.slug as tournament_slug, t.year,
                   r.id as round_id, r.round_number, r.name as round_name, r.round_type,
                   d.id as debate_id, d.venue,
                   prop.name as prop_name, prop.canonical_name as prop_canon, opp.name as opp_name, opp.canonical_name as opp_canon,
                   CASE WHEN (prop.name LIKE ? OR prop.canonical_name LIKE ?) THEN 'Proposition' ELSE 'Opposition' END as side,
                   CASE WHEN (prop.name LIKE ? OR prop.canonical_name LIKE ?) THEN opp.name ELSE prop.name END as opponent_team,
                   ROUND(AVG(CASE WHEN (prop.name LIKE ? OR prop.canonical_name LIKE ?) THEN ab.prop_total_score ELSE ab.opp_total_score END), 2) as team_score,
                   ROUND(AVG(CASE WHEN (prop.name LIKE ? OR prop.canonical_name LIKE ?) THEN ab.opp_total_score ELSE ab.prop_total_score END), 2) as opponent_score,
                   ROUND(AVG(ab.prop_total_score + ab.opp_total_score), 2) as combined_score,
                   COUNT(ab.id) as judges_count,
                   ab.winner_side
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN teams prop ON d.prop_team_id = prop.id
            JOIN teams opp ON d.opp_team_id = opp.id
            JOIN adjudicator_ballots ab ON ab.debate_id = d.id
            WHERE (prop.name LIKE ? OR prop.canonical_name LIKE ? OR opp.name LIKE ? OR opp.canonical_name LIKE ?)
              {tourn_clause}
              AND ab.prop_total_score IS NOT NULL
            GROUP BY d.id
            ORDER BY t.id, r.round_number
        """
        bind_params = [f"%{team_name}%"] * 12
        if tournament:
            bind_params.extend([f"%{tournament}%", f"%{tournament}%"])

        cur.execute(sql, bind_params)
        debates = cur.fetchall()
        if not debates:
            return {"error": f"No debate records found for team '{team_name}'."}

        all_debates = []
        for d in debates:
            is_win = (d["winner_side"] == d["side"])
            all_debates.append({
                "tournament_name": d["tournament_name"],
                "tournament_slug": d["tournament_slug"],
                "round_number": d["round_number"],
                "round_name": d["round_name"],
                "round_type": d["round_type"],
                "side": d["side"],
                "opponent_team": d["opponent_team"],
                "team_score": d["team_score"],
                "opponent_score": d["opponent_score"],
                "combined_score": d["combined_score"],
                "result": "Win" if is_win else "Loss",
                "judges_count": d["judges_count"]
            })

        highest_score_deb = max(all_debates, key=lambda x: x["team_score"] if x["team_score"] is not None else -1)
        highest_quality_deb = max(all_debates, key=lambda x: x["combined_score"] if x["combined_score"] is not None else -1)

        tourn_map: Dict[str, Any] = {}
        for d in all_debates:
            ts = d["tournament_slug"]
            if ts not in tourn_map:
                tourn_map[ts] = {
                    "tournament_name": d["tournament_name"],
                    "tournament_slug": ts,
                    "debates": [],
                    "scores": [],
                    "wins": 0,
                }
            tourn_map[ts]["debates"].append(d)
            if d["team_score"] is not None:
                tourn_map[ts]["scores"].append(d["team_score"])
            if d["result"] == "Win":
                tourn_map[ts]["wins"] += 1

        tournaments_summary = []
        for ts, tdata in tourn_map.items():
            scores = tdata["scores"]
            avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
            max_score = max(scores) if scores else 0.0
            best_round = next((d for d in tdata["debates"] if d["team_score"] == max_score), None)
            tournaments_summary.append({
                "tournament_name": tdata["tournament_name"],
                "tournament_slug": ts,
                "debates_count": len(tdata["debates"]),
                "wins": tdata["wins"],
                "atss": avg_score,
                "max_team_score": max_score,
                "best_round": f"{best_round['round_name']} ({max_score} vs {best_round['opponent_team']})" if best_round else None
            })

        return {
            "team_name": team_name,
            "total_debates_logged": len(all_debates),
            "highest_team_score": {
                "score": highest_score_deb["team_score"],
                "tournament": highest_score_deb["tournament_name"],
                "tournament_slug": highest_score_deb["tournament_slug"],
                "round": highest_score_deb["round_name"],
                "opponent": highest_score_deb["opponent_team"],
                "result": f"{highest_score_deb['result']} ({highest_score_deb['team_score']} - {highest_score_deb['opponent_score']})",
                "side": highest_score_deb["side"],
            },
            "highest_quality_debate": {
                "combined_score": highest_quality_deb["combined_score"],
                "team_score": highest_quality_deb["team_score"],
                "opponent_score": highest_quality_deb["opponent_score"],
                "tournament": highest_quality_deb["tournament_name"],
                "tournament_slug": highest_quality_deb["tournament_slug"],
                "round": highest_quality_deb["round_name"],
                "opponent": highest_quality_deb["opponent_team"],
                "result": f"{highest_quality_deb['result']} ({highest_quality_deb['team_score']} - {highest_quality_deb['opponent_score']})",
                "side": highest_quality_deb["side"],
            },
            "tournaments_summary": tournaments_summary,
            "detailed_rounds": all_debates if tournament else None
        }

    def get_tier_matchup_stats(
        self,
        tier_a: str = "A",
        tier_b: str = "B",
        tournament: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compute head-to-head matchup win rates, total bouts, and score margins
        between two competitive tiers (e.g. Tier A vs Tier B) circuit-wide
        or for a specific tournament. Grounded in canonical team tier groupings.
        """
        cur = self._conn.cursor()
        def _norm_tier(val: str) -> str:
            v = str(val).strip().upper()
            if v in ("A", "B", "C", "D", "NOVICE", "SWING", "OTHER"):
                return v
            v_lower = str(val).lower()
            if any(tok in v_lower for tok in ("gold", "red", "maroon", "green", "ix", "a-team", "a team")) or v_lower.endswith(" a"):
                return "A"
            if any(tok in v_lower for tok in ("purple", "white", "silver", "blue", "vi", "b-team", "b team")) or v_lower.endswith(" b"):
                return "B"
            if any(tok in v_lower for tok in ("vii", "c-team", "c team")) or v_lower.endswith(" c"):
                return "C"
            if any(tok in v_lower for tok in ("d-team", "d team")) or v_lower.endswith(" d"):
                return "D"
            if "swing" in v_lower:
                return "SWING"
            return v

        t_a = _norm_tier(tier_a)
        t_b = _norm_tier(tier_b)

        tourn_clause = "AND (t.name LIKE ? OR t.slug LIKE ?)" if tournament else ""
        sql = f"""
            SELECT d.id, t.name as tournament_name, t.slug as tournament_slug,
                   r.round_number, r.name as round_name, r.round_type,
                   prop.name as prop_name, prop.canonical_name as prop_canon, prop.tier as prop_tier,
                   opp.name as opp_name, opp.canonical_name as opp_canon, opp.tier as opp_tier,
                   ab.winner_side,
                   ROUND(AVG(ab.prop_total_score), 2) as prop_score,
                   ROUND(AVG(ab.opp_total_score), 2) as opp_score
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN teams prop ON d.prop_team_id = prop.id
            JOIN teams opp ON d.opp_team_id = opp.id
            JOIN adjudicator_ballots ab ON ab.debate_id = d.id
            WHERE ((prop.tier = ? AND opp.tier = ?) OR (prop.tier = ? AND opp.tier = ?))
              {tourn_clause}
              AND ab.prop_total_score IS NOT NULL
            GROUP BY d.id
            ORDER BY t.id, r.round_number
        """
        params = [t_a, t_b, t_b, t_a]
        if tournament:
            params.extend([f"%{tournament}%", f"%{tournament}%"])

        cur.execute(sql, params)
        debates = cur.fetchall()
        if not debates:
            return {
                "tier_a": t_a,
                "tier_b": t_b,
                "total_matchups": 0,
                "message": f"No matchups recorded between Tier {t_a} and Tier {t_b}.",
            }

        tier_a_wins = 0
        tier_b_wins = 0
        matchups_list = []

        for d in debates:
            prop_is_a = (d["prop_tier"] == t_a)
            if d["winner_side"] == "Proposition":
                winner_tier = d["prop_tier"]
                winner_name = d["prop_canon"] or d["prop_name"]
            else:
                winner_tier = d["opp_tier"]
                winner_name = d["opp_canon"] or d["opp_name"]

            if winner_tier == t_a:
                tier_a_wins += 1
            elif winner_tier == t_b:
                tier_b_wins += 1

            matchups_list.append({
                "tournament": d["tournament_name"],
                "round": d["round_name"],
                "tier_a_team": (d["prop_canon"] or d["prop_name"]) if prop_is_a else (d["opp_canon"] or d["opp_name"]),
                "tier_b_team": (d["opp_canon"] or d["opp_name"]) if prop_is_a else (d["prop_canon"] or d["prop_name"]),
                "winner_tier": winner_tier,
                "winner_team": winner_name,
                "tier_a_score": d["prop_score"] if prop_is_a else d["opp_score"],
                "tier_b_score": d["opp_score"] if prop_is_a else d["prop_score"],
            })

        total = len(debates)
        pct_a = round((tier_a_wins / total) * 100, 1) if total else 0.0
        pct_b = round((tier_b_wins / total) * 100, 1) if total else 0.0
        ratio_str = f"{tier_a_wins / tier_b_wins:.2f} : 1" if tier_b_wins else "Undefeated"

        return {
            "tier_a": t_a,
            "tier_b": t_b,
            "total_matchups": total,
            "tier_a_wins": tier_a_wins,
            "tier_b_wins": tier_b_wins,
            "tier_a_win_pct": pct_a,
            "tier_b_win_pct": pct_b,
            "ratio_a_to_b": ratio_str,
            "sample_matchups": matchups_list[:10],
        }

    def get_national_pool(
        self,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all debaters with a National Level designation ('Nat Trials',
        'Nat Pool, Trialed', 'Nat Pool, Direct'), including their institution,
        overall score, Master Tab ranking, and preliminary round counts.
        """
        cur = self._conn.cursor()
        query = """
            SELECT p.id, p.canonical_name, p.national_level,
                   i.name as institution_name, i.code as institution_code
            FROM persons p
            LEFT JOIN (
                SELECT tm.person_id, t.institution_id
                FROM team_members tm
                JOIN teams t ON tm.team_id = t.id
                GROUP BY tm.person_id
            ) primary_inst ON p.id = primary_inst.person_id
            LEFT JOIN institutions i ON primary_inst.institution_id = i.id
            WHERE p.national_level IS NOT NULL
        """
        params = []
        if status:
            query += " AND p.national_level LIKE ?"
            params.append(f"%{status}%")
        query += " ORDER BY p.national_level, p.canonical_name"

        cur.execute(query, params)
        rows = cur.fetchall()

        mt_engine = MasterTabEngine(self._conn)
        tab = mt_engine.get_master_speaker_tab(min_tournaments=1)
        rank_map = {r["person_id"]: r for r in tab}

        results = []
        for r in rows:
            pid = r["id"]
            mt = rank_map.get(pid, {})
            results.append({
                "person_id": pid,
                "name": r["canonical_name"],
                "national_level": r["national_level"],
                "institution": r["institution_name"] or "Independent",
                "institution_code": r["institution_code"] or "-",
                "master_tab_rank": mt.get("rank"),
                "master_score": mt.get("master_score"),
                "total_speeches": mt.get("total_speeches", 0),
            })
        return results

    def get_tournament_bracket(self, tournament: str) -> Dict[str, Any]:
        """
        Fetch full tournament elimination bracket tree (Octos -> Quarters -> Semis -> Grand Final).
        """
        bracket = self._bracket_engine.get_tournament_bracket(tournament)
        if not bracket:
            return {"error": f"Tournament elimination bracket not found for '{tournament}'."}
        return bracket

    def get_judge_dossier(self, identifier: Union[int, str]) -> Dict[str, Any]:
        """
        Fetch comprehensive adjudicator dossier including strictness index, side bias, and margin profile.
        """
        dossier = self._judge_engine.get_judge_dossier(identifier)
        if not dossier:
            return {"error": f"Adjudicator '{identifier}' not found."}
        return dossier

    def get_judge_leaderboard(
        self,
        min_debates: int = 3,
        sort_by: str = "debates",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve national adjudicator leaderboard.
        sort_by: 'debates', 'margin', 'avg_score', 'outrounds'.
        """
        return self._judge_engine.get_judge_leaderboard(min_debates=min_debates, sort_by=sort_by, limit=limit)

    def predict_matchup(self, team_a: str, team_b: str) -> Dict[str, Any]:
        """
        Simulate a match clash between two teams predicting win probability, margin, and tactical keys.
        """
        pred = self._predictor.predict_matchup(team_a, team_b)
        if not pred:
            return {"error": f"Unable to resolve teams for prediction: '{team_a}' or '{team_b}'."}
        return pred

    def get_tournament_rankings(self) -> List[Dict[str, Any]]:
        """
        Retrieve tournament rankings based on APTTSS, breaking APTTSS, and participation metadata.
        """
        return self._tournament_engine.get_tournament_rankings()

    def get_activity_leaderboard(self) -> List[Dict[str, Any]]:
        """
        Retrieve activity leaderboard ranked strictly by preliminary rounds debated.
        """
        return self._activity_engine.get_activity_leaderboard()

    def close(self):
        """Close underlying database connection if owned."""
        if self._conn:
            self._conn.close()
