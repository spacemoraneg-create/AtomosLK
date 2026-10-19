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
from typing import Any, Dict, List, Optional, Tuple, Union

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
        from atomos.analytics.v2_metrics import V2MetricsEngine
        from atomos.analytics.tournaments import get_clean_tournament_name
        v2 = V2MetricsEngine(self._conn)
        sp_summary = v2._get_person_speaker_tab_summary(person_id)
        data["avg_speaker_tab_rank"] = sp_summary["avg_speaker_tab_rank"]
        data["avg_speaker_tab_rank_full_prelims"] = sp_summary["avg_speaker_tab_rank_full_prelims"]
        data["avg_speaker_tab_rank_total_eligible"] = sp_summary["avg_speaker_tab_rank_total_eligible"]
        data["avg_speaker_tab_rank_total_all"] = sp_summary["avg_speaker_tab_rank_total_all"]
        data["best_speaker_tab_rank_avg"] = sp_summary["best_speaker_tab_rank_avg"]
        data["best_speaker_tab_rank_total"] = sp_summary["best_speaker_tab_rank_total"]
        per_tour = sp_summary["per_tournament"]

        for t in data.get("tournaments", []):
            tid = t.get("tournament_id")
            if tid is not None:
                t["tournament_name"] = get_clean_tournament_name(tid, t.get("tournament_name", ""))
                t_tab = per_tour.get(tid, {})
                t["speaker_tab_rank_avg"] = t_tab.get("rank_by_avg")
                t["speaker_tab_rank_total"] = t_tab.get("rank_by_total")
                t["eligible_speakers"] = t_tab.get("eligible_speakers")
                t["total_speakers"] = t_tab.get("total_speakers")
                t["total_points"] = t_tab.get("total_points")
                t["max_prelims"] = t_tab.get("max_prelims", 5)

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

        cur.execute("SELECT COUNT(*) as cnt FROM speech_performances")
        total_speeches_all = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM speech_performances WHERE is_valid_rubric = 1")
        total_valid_speeches = cur.fetchone()["cnt"]

        cur.execute("""
            SELECT 
                COUNT(CASE WHEN r.round_type = 'PRELIMINARY' THEN 1 END) as prelim_debates,
                COUNT(CASE WHEN r.round_type = 'ELIMINATION' THEN 1 END) as knockout_debates
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            WHERE d.is_walkover = 0
        """)
        rounds_row = cur.fetchone()
        prelim_rounds = rounds_row["prelim_debates"] if rounds_row else 0
        knockout_rounds = rounds_row["knockout_debates"] if rounds_row else 0

        side_balance = self._motion_engine.get_overall_side_balance()

        return {
            "total_persons": total_persons,
            "total_institutions": total_institutions,
            "total_tournaments": total_tournaments,
            "total_debates_debated": total_debates,
            "total_speeches": total_speeches_all,
            "total_valid_speeches": total_valid_speeches,
            "total_prelim_rounds": prelim_rounds,
            "total_knockout_rounds": knockout_rounds,
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

    def get_debater_adjudicator_record(
        self,
        debater: str,
        adjudicator: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve complete, deterministic record of all debates where an adjudicator
        officiated a specific debater. Evaluates ground-truth debate outcomes (Won/Lost),
        speech scores, winning margin, tournament, round, and opposition team.
        """
        matches = self._search_engine.search_debaters(debater, limit=1)
        if not matches:
            return {"error": f"Debater '{debater}' not found in database."}
        person_id = matches[0].get("person_id") or matches[0].get("id")
        canonical_name = matches[0].get("canonical_name") or matches[0].get("name", str(debater))

        cur = self._conn.cursor()
        sql = """
        SELECT
            d.id as debate_id,
            t.id as tournament_id,
            t.name as tournament_name,
            r.round_number,
            r.name as round_name,
            r.round_type,
            sp.side as debater_side,
            sp.position as debater_position,
            sp.speech_type,
            sp.total_score,
            tm.id as debater_team_id,
            tm.name as debater_team,
            opp.id as opp_team_id,
            opp.name as opp_team,
            ab.adjudicator_person_id,
            ab.adjudicator_raw_name,
            ab.winner_side,
            ab.win_margin,
            ab.prop_total_score,
            ab.opp_total_score,
            d.is_walkover,
            d.walkover_winner_id
        FROM speech_performances sp
        JOIN rounds r ON sp.round_id = r.id
        JOIN tournaments t ON r.tournament_id = t.id
        JOIN debates d ON sp.debate_id = d.id
        JOIN teams tm ON sp.team_id = tm.id
        LEFT JOIN teams opp ON ((d.prop_team_id = tm.id AND d.opp_team_id = opp.id) 
                             OR (d.opp_team_id = tm.id AND d.prop_team_id = opp.id))
        JOIN adjudicator_ballots ab ON sp.ballot_id = ab.id
        WHERE sp.person_id = ?
        ORDER BY t.id ASC, r.round_number ASC, sp.id ASC
        """
        cur.execute(sql, (person_id,))
        rows = cur.fetchall()

        from atomos.analytics.tournaments import CLEAN_TOURNAMENT_NAMES
        debates_map: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for r in rows:
            raw_judge = r["adjudicator_raw_name"] or "Unknown"
            import html
            clean_judge = html.unescape(raw_judge.replace("Official Reconstructed (", "").rstrip(")"))
            if clean_judge.lower().strip() in ("scoresheet", "tabbycat", "tab", "unknown", "adjudicator not recorded", ""):
                continue

            d_id = r["debate_id"]
            key = (clean_judge, d_id)

            if key not in debates_map:
                if r["is_walkover"] == 1:
                    won = (r["walkover_winner_id"] == r["debater_team_id"])
                else:
                    won = (r["debater_side"] == r["winner_side"])

                t_name = CLEAN_TOURNAMENT_NAMES.get(r["tournament_id"], r["tournament_name"])

                debates_map[key] = {
                    "adjudicator": clean_judge,
                    "raw_adjudicator_name": raw_judge,
                    "adjudicator_person_id": r["adjudicator_person_id"],
                    "debate_id": d_id,
                    "tournament_id": r["tournament_id"],
                    "tournament_name": t_name,
                    "round_number": r["round_number"],
                    "round_name": r["round_name"],
                    "round_type": r["round_type"],
                    "debater_team": r["debater_team"],
                    "opponent_team": r["opp_team"] or "Opponent",
                    "side": r["debater_side"],
                    "winner_side": r["winner_side"],
                    "win_margin": r["win_margin"],
                    "won": won,
                    "outcome": "Won" if won else "Lost",
                    "substantive_scores": [],
                    "reply_scores": [],
                }

            if r["speech_type"] == "SUBSTANTIVE":
                debates_map[key]["substantive_scores"].append(float(r["total_score"]))
            elif r["speech_type"] == "REPLY":
                debates_map[key]["reply_scores"].append(float(r["total_score"]))

        all_records = list(debates_map.values())

        if adjudicator and adjudicator.strip():
            target_adj = adjudicator.strip().lower()
            all_records = [
                d for d in all_records
                if target_adj in d["adjudicator"].lower() or target_adj in d["raw_adjudicator_name"].lower()
            ]

        judges_summary: Dict[str, Dict[str, Any]] = {}
        for d in all_records:
            j = d["adjudicator"]
            if j not in judges_summary:
                judges_summary[j] = {
                    "adjudicator": j,
                    "debates_count": 0,
                    "wins": 0,
                    "losses": 0,
                    "substantive_scores": [],
                    "tournaments": set(),
                }
            judges_summary[j]["debates_count"] += 1
            if d["won"]:
                judges_summary[j]["wins"] += 1
            else:
                judges_summary[j]["losses"] += 1
            judges_summary[j]["substantive_scores"].extend(d["substantive_scores"])
            judges_summary[j]["tournaments"].add(d["tournament_name"])

        summary_list = []
        for j, s in judges_summary.items():
            tot = s["debates_count"]
            w = s["wins"]
            l = s["losses"]
            wr = round(w / tot * 100.0, 1) if tot > 0 else 0.0
            sub_avg = round(sum(s["substantive_scores"]) / len(s["substantive_scores"]), 2) if s["substantive_scores"] else None
            summary_list.append({
                "adjudicator": j,
                "debates_judged": tot,
                "wins": w,
                "losses": l,
                "win_percentage": wr,
                "average_score_awarded": sub_avg,
                "tournaments": sorted(list(s["tournaments"])),
            })

        summary_list.sort(key=lambda x: (-x["debates_judged"], -x["win_percentage"]))

        return {
            "debater": canonical_name,
            "person_id": person_id,
            "filter_adjudicator": adjudicator,
            "total_debates_found": len(all_records),
            "judges_summary": summary_list,
            "debates": all_records,
        }

    def _resolve_tournament_id(self, tournament: str) -> Optional[int]:
        """Resolve tournament name, slug, or circuit alias to tournament_id."""
        if not tournament:
            return None
        t_clean = tournament.strip()
        if t_clean.isdigit():
            return int(t_clean)
        t_low = t_clean.lower()
        alias_map = {
            "vijis": 1, "vijitha": 1,
            "aisdc": 2, "ais": 2,
            "apiit": 3,
            "slsdc": 4, "law fac": 4, "law faculty": 4,
            "vvidc": 7, "visakha": 7,
            "metho": 10, "shanthi": 10,
            "ric": 16, "isdc": 16,
            "chaps": 18, "chap's": 18, "chapman": 18,
            "nixon": 44, "nixons": 44, "nixon's": 44, "lillian": 44,
            "stanley": 45, "stanleys": 45, "stanley's": 45,
            "henley": 46, "henleys": 46,
        }
        for k, tid in alias_map.items():
            if k in t_low:
                return tid
        t_search = self._search_engine.search_tournaments(t_clean, limit=1)
        if t_search:
            return t_search[0]["tournament_id"]
        cur = self._conn.cursor()
        cur.execute("SELECT id FROM tournaments WHERE slug LIKE ? OR name LIKE ? LIMIT 1", (f"%{t_clean}%", f"%{t_clean}%"))
        r = cur.fetchone()
        return r[0] if r else None

    def reconstruct_speaker_tab(
        self,
        identifier: Optional[str] = None,
        tournament: Optional[str] = None,
        min_tournaments: int = 3,
        limit: int = 25,
    ) -> Dict[str, Any]:
        """
        Reverse-engineer per-tournament Speaker Tabs directly from raw preliminary
        substantive speech scores in atomos.db.

        Modes:
        1. Debater Mode (identifier provided):
           Returns the debater's reconstructed Speaker Tab rank in every tournament
           they competed in (both by WSDC Qualifying Average [>=3 prelims] and by
           Tabbycat Cumulative Total Points), round-by-round scores, field sizes,
           and their career Average Speaker Tab Ranks with step-by-step derivations.
        2. Tournament Mode (tournament provided without identifier):
           Reconstructs the complete Speaker Tab for that tournament (top `limit`
           speakers by Qualifying Average and by Total Prelim Points).
        3. Circuit Leaderboard Mode (neither provided):
           Ranks circuit debaters (with >= `min_tournaments` qualifying tournaments)
           by their Average Speaker Tab Rank across tournaments.
        """
        from atomos.analytics.v2_metrics import V2MetricsEngine, truncate_3, calc_sample_stdev, CANONICAL_TEAM_ALIASES
        from atomos.analytics.tournaments import get_clean_tournament_name, CHRONOLOGICAL_TOURNAMENT_ORDER

        v2 = V2MetricsEngine(self._conn)
        tabs = v2._get_reconstructed_speaker_tabs()
        cur = self._conn.cursor()

        # Fetch tournament metadata
        cur.execute("SELECT id, slug, name FROM tournaments")
        tour_meta = {
            r["id"]: {
                "id": r["id"],
                "slug": r["slug"],
                "raw_name": r["name"],
                "clean_name": get_clean_tournament_name(r["id"], r["name"]),
            }
            for r in cur.fetchall()
        }

        # Fetch person names, schools, and per-tournament teams + round scores
        cur.execute("""
            SELECT r.tournament_id,
                   sp.person_id,
                   p.canonical_name,
                   p.national_level,
                   COALESCE(tm.canonical_name, tm.name) as team_name,
                   inst.name as inst_name,
                   r.round_number,
                   AVG(sp.total_score) as speech_score
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN debates d ON sp.debate_id = d.id
            JOIN persons p ON sp.person_id = p.id
            JOIN teams tm ON sp.team_id = tm.id
            LEFT JOIN institutions inst ON tm.institution_id = inst.id
            WHERE sp.speech_type = 'SUBSTANTIVE'
              AND r.round_type = 'PRELIMINARY'
              AND d.is_walkover = 0
              AND sp.total_score > 0
            GROUP BY r.tournament_id, sp.person_id, r.round_number, sp.debate_id, sp.position
            ORDER BY r.tournament_id, sp.person_id, r.round_number
        """)
        person_info: Dict[int, Dict[str, Any]] = {}
        person_tour_meta: Dict[Tuple[int, int], Dict[str, Any]] = {}
        for r in cur.fetchall():
            tid = r["tournament_id"]
            pid = r["person_id"]
            rnum = r["round_number"]
            sc = float(r["speech_score"])
            raw_t = r["team_name"] or "Team"
            clean_t = CANONICAL_TEAM_ALIASES.get(raw_t, raw_t)
            person_info[pid] = {
                "person_id": pid,
                "name": r["canonical_name"],
                "national_level": r["national_level"],
                "institution": r["inst_name"] or person_info.get(pid, {}).get("institution") or "Independent",
            }
            pt = person_tour_meta.setdefault((pid, tid), {"team": clean_t, "rounds": {}})
            pt["team"] = clean_t
            pt["rounds"][rnum] = max(pt["rounds"].get(rnum, 0.0), sc)

        target_tid = self._resolve_tournament_id(tournament) if tournament else None

        # MODE 1: DEBATER SPEAKER TAB RECONSTRUCTION
        if identifier:
            pid = self._resolve_debater_id(identifier)
            if not pid or pid not in person_info:
                return {"error": f"Debater '{identifier}' not found in preliminary speech records."}

            p_meta = person_info[pid]
            tournaments_list = []
            elig_avg_ranks: List[int] = []
            full_prelim_total_ranks: List[int] = []
            full_prelim_avg_ranks: List[int] = []
            elig_total_ranks: List[int] = []
            all_total_ranks: List[int] = []
            all_avg_unfiltered_ranks: List[int] = []

            sorted_tids = sorted(
                [tid for tid in tabs.keys() if pid in tabs[tid] and (target_tid is None or tid == target_tid)],
                key=lambda x: CHRONOLOGICAL_TOURNAMENT_ORDER.get(x, x),
            )

            for tid in sorted_tids:
                info = tabs[tid][pid]
                pt = person_tour_meta.get((pid, tid), {"team": "Unknown", "rounds": {}})
                r_scores = [
                    {"round": rnum, "score": truncate_3(sc)}
                    for rnum, sc in sorted(pt["rounds"].items())
                ]
                t_name = tour_meta.get(tid, {}).get("clean_name", f"Tournament #{tid}")
                t_slug = tour_meta.get(tid, {}).get("slug", "")

                r_avg = info["rank_by_avg"]
                r_tot = info["rank_by_total"]
                r_avg_all = info["rank_by_avg_all"]
                elig_cnt = info["eligible_speakers"]
                tot_cnt = info["total_speakers"]

                all_total_ranks.append(r_tot)
                all_avg_unfiltered_ranks.append(r_avg_all)
                if info["is_eligible"] and r_avg is not None:
                    elig_avg_ranks.append(r_avg)
                    elig_total_ranks.append(r_tot)
                if info["spoke_all_prelims"]:
                    full_prelim_total_ranks.append(r_tot)
                    if r_avg is not None:
                        full_prelim_avg_ranks.append(r_avg)

                pct_elig = truncate_3(r_avg / elig_cnt * 100.0) if (r_avg is not None and elig_cnt > 0) else None
                pct_tot = truncate_3(r_tot / tot_cnt * 100.0) if tot_cnt > 0 else None

                tournaments_list.append({
                    "tournament_id": tid,
                    "tournament_name": t_name,
                    "tournament_slug": t_slug,
                    "team_name": pt["team"],
                    "prelims_spoken": info["prelims_spoken"],
                    "max_prelims": info["max_prelims"],
                    "is_eligible": info["is_eligible"],
                    "spoke_all_prelims": info["spoke_all_prelims"],
                    "total_points": info["total_points"],
                    "tournament_average": info["avg_score"],
                    "stdev": info["stdev"],
                    "rank_by_avg_eligible": r_avg,
                    "rank_by_total_points": r_tot,
                    "rank_by_avg_all_speakers": r_avg_all,
                    "eligible_speakers": elig_cnt,
                    "total_speakers": tot_cnt,
                    "top_percentile_eligible": pct_elig,
                    "top_percentile_total": pct_tot,
                    "round_scores": r_scores,
                })

            def _derive_str(vals: List[int]) -> Optional[str]:
                if not vals:
                    return None
                s = sum(vals)
                n = len(vals)
                avg_v = truncate_3(s / n)
                expr = " + ".join(str(v) for v in vals)
                return f"({expr}) / {n} = {s} / {n} = {avg_v}"

            best_avg_tour = min(
                [t for t in tournaments_list if t["rank_by_avg_eligible"] is not None],
                key=lambda t: (t["rank_by_avg_eligible"], -t["tournament_average"]),
                default=None,
            )
            best_tot_tour = min(
                tournaments_list,
                key=lambda t: (t["rank_by_total_points"], -t["total_points"]),
                default=None,
            )

            return {
                "mode": "debater",
                "person_id": pid,
                "canonical_name": p_meta["name"],
                "institution": p_meta["institution"],
                "national_level": p_meta["national_level"],
                "tournaments_attended": len(tournaments_list),
                "eligible_tournaments_count": len(elig_avg_ranks),
                "full_prelim_tournaments_count": len(full_prelim_total_ranks),
                "avg_rank_by_avg_eligible": truncate_3(sum(elig_avg_ranks) / len(elig_avg_ranks)) if elig_avg_ranks else None,
                "derivation_avg_eligible": _derive_str(elig_avg_ranks),
                "avg_rank_by_total_full_prelims": truncate_3(sum(full_prelim_total_ranks) / len(full_prelim_total_ranks)) if full_prelim_total_ranks else None,
                "derivation_total_full_prelims": _derive_str(full_prelim_total_ranks),
                "avg_rank_by_avg_full_prelims": truncate_3(sum(full_prelim_avg_ranks) / len(full_prelim_avg_ranks)) if full_prelim_avg_ranks else None,
                "derivation_avg_full_prelims": _derive_str(full_prelim_avg_ranks),
                "avg_rank_by_total_eligible": truncate_3(sum(elig_total_ranks) / len(elig_total_ranks)) if elig_total_ranks else None,
                "derivation_total_eligible": _derive_str(elig_total_ranks),
                "avg_rank_by_total_all": truncate_3(sum(all_total_ranks) / len(all_total_ranks)) if all_total_ranks else None,
                "derivation_total_all": _derive_str(all_total_ranks),
                "avg_rank_by_avg_unfiltered_all": truncate_3(sum(all_avg_unfiltered_ranks) / len(all_avg_unfiltered_ranks)) if all_avg_unfiltered_ranks else None,
                "best_rank_by_avg": {
                    "rank": best_avg_tour["rank_by_avg_eligible"],
                    "eligible_speakers": best_avg_tour["eligible_speakers"],
                    "tournament_name": best_avg_tour["tournament_name"],
                    "average": best_avg_tour["tournament_average"],
                } if best_avg_tour else None,
                "best_rank_by_total": {
                    "rank": best_tot_tour["rank_by_total_points"],
                    "total_speakers": best_tot_tour["total_speakers"],
                    "tournament_name": best_tot_tour["tournament_name"],
                    "total_points": best_tot_tour["total_points"],
                    "average": best_tot_tour["tournament_average"],
                } if best_tot_tour else None,
                "tournaments": tournaments_list,
            }

        # MODE 2: SINGLE TOURNAMENT SPEAKER TAB RECONSTRUCTION
        if target_tid is not None:
            if target_tid not in tabs:
                return {"error": f"No preliminary speech data found for tournament '{tournament}'."}
            p_map = tabs[target_tid]
            t_info = tour_meta.get(target_tid, {"clean_name": f"Tournament #{target_tid}", "slug": ""})
            entries = []
            for pid, info in p_map.items():
                pm = person_info.get(pid, {"name": f"Debater #{pid}", "institution": "Independent", "national_level": None})
                pt = person_tour_meta.get((pid, target_tid), {"team": "Unknown", "rounds": {}})
                r_scores = {f"R{rnum}": truncate_3(sc) for rnum, sc in sorted(pt["rounds"].items())}
                entries.append({
                    "person_id": pid,
                    "speaker_name": pm["name"],
                    "team_name": pt["team"],
                    "institution": pm["institution"],
                    "national_level": pm["national_level"],
                    "prelims_spoken": info["prelims_spoken"],
                    "max_prelims": info["max_prelims"],
                    "is_eligible": info["is_eligible"],
                    "spoke_all_prelims": info["spoke_all_prelims"],
                    "total_points": info["total_points"],
                    "tournament_average": info["avg_score"],
                    "stdev": info["stdev"],
                    "rank_by_avg_eligible": info["rank_by_avg"],
                    "rank_by_total_points": info["rank_by_total"],
                    "round_scores": r_scores,
                })

            by_avg = [e for e in entries if e["is_eligible"] and e["rank_by_avg_eligible"] is not None]
            by_avg.sort(key=lambda e: (e["rank_by_avg_eligible"], -e["tournament_average"], -e["total_points"]))

            by_total = list(entries)
            by_total.sort(key=lambda e: (e["rank_by_total_points"], -e["total_points"], -e["tournament_average"]))

            return {
                "mode": "tournament",
                "tournament_id": target_tid,
                "tournament_name": t_info["clean_name"],
                "tournament_slug": t_info["slug"],
                "max_prelims": entries[0]["max_prelims"] if entries else 5,
                "total_speakers": len(entries),
                "eligible_speakers": len(by_avg),
                "top_by_wsdc_average": by_avg[:limit],
                "top_by_tabbycat_total_points": by_total[:limit],
            }

        # MODE 3: CIRCUIT LEADERBOARD BY AVERAGE SPEAKER TAB RANK
        leaderboard = []
        for pid, pm in person_info.items():
            summary = v2._get_person_speaker_tab_summary(pid)
            if summary["eligible_tournaments_count"] < min_tournaments:
                continue
            leaderboard.append({
                "person_id": pid,
                "speaker_name": pm["name"],
                "institution": pm["institution"],
                "national_level": pm["national_level"],
                "eligible_tournaments": summary["eligible_tournaments_count"],
                "full_prelim_tournaments": summary["full_prelim_tournaments_count"],
                "avg_speaker_tab_rank_eligible": summary["avg_speaker_tab_rank"],
                "avg_speaker_tab_rank_full_prelims": summary["avg_speaker_tab_rank_full_prelims"],
                "avg_speaker_tab_rank_total_eligible": summary["avg_speaker_tab_rank_total_eligible"],
                "best_speaker_tab_rank_avg": summary["best_speaker_tab_rank_avg"],
                "best_speaker_tab_rank_total": summary["best_speaker_tab_rank_total"],
            })

        leaderboard.sort(key=lambda x: (
            x["avg_speaker_tab_rank_eligible"] if x["avg_speaker_tab_rank_eligible"] is not None else 9999,
            -x["eligible_tournaments"],
        ))
        for idx, item in enumerate(leaderboard, 1):
            item["rank"] = idx

        return {
            "mode": "circuit_leaderboard",
            "min_tournaments": min_tournaments,
            "total_qualified_debaters": len(leaderboard),
            "leaderboard": leaderboard[:limit],
        }

    def reconstruct_team_tab(
        self,
        tournament: Optional[str] = None,
        team_name: Optional[str] = None,
        limit: int = 25,
    ) -> Dict[str, Any]:
        """
        Reverse-engineer Preliminary Team Tabs (Break Standings) for any tournament
        or team directly from raw preliminary debates, adjudicator ballots, and speeches.
        """
        from atomos.analytics.v2_metrics import truncate_3, CANONICAL_TEAM_ALIASES
        from atomos.analytics.tournaments import get_clean_tournament_name, CHRONOLOGICAL_TOURNAMENT_ORDER
        from atomos.analytics.critical_stats import CriticalStatsEngine

        cur = self._conn.cursor()
        crit = CriticalStatsEngine(self._conn)
        breaking = crit._get_breaking_teams()

        cur.execute("SELECT id, slug, name FROM tournaments")
        tour_meta = {
            r["id"]: {
                "id": r["id"],
                "slug": r["slug"],
                "clean_name": get_clean_tournament_name(r["id"], r["name"]),
            }
            for r in cur.fetchall()
        }

        # Reconstruct team prelim wins, ballots, and total substantive speaker points per debate
        cur.execute("""
            SELECT r.tournament_id,
                   d.id as debate_id,
                   r.round_number,
                   t.id as team_id,
                   COALESCE(t.canonical_name, t.name) as raw_team_name,
                   inst.name as inst_name,
                   CASE WHEN d.prop_team_id = t.id THEN 'Proposition' ELSE 'Opposition' END as side,
                   SUM(CASE WHEN (d.prop_team_id = t.id AND b.winner_side = 'Proposition')
                              OR (d.opp_team_id = t.id AND b.winner_side = 'Opposition') THEN 1 ELSE 0 END) as ballots_won,
                   SUM(CASE WHEN (d.prop_team_id = t.id AND b.winner_side = 'Opposition')
                              OR (d.opp_team_id = t.id AND b.winner_side = 'Proposition') THEN 1 ELSE 0 END) as ballots_lost,
                   AVG(CASE WHEN d.prop_team_id = t.id THEN b.prop_total_score ELSE b.opp_total_score END) as team_debate_score,
                   AVG(CASE WHEN d.prop_team_id = t.id THEN b.win_margin ELSE -b.win_margin END) as debate_margin
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN teams t ON (d.prop_team_id = t.id OR d.opp_team_id = t.id)
            LEFT JOIN institutions inst ON t.institution_id = inst.id
            JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE r.round_type = 'PRELIMINARY' AND d.is_walkover = 0
            GROUP BY r.tournament_id, d.id, t.id
        """)
        tour_teams: Dict[int, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        for r in cur.fetchall():
            tid = r["tournament_id"]
            raw_t = r["raw_team_name"]
            t_cname = CANONICAL_TEAM_ALIASES.get(raw_t, raw_t)
            entry = tour_teams[tid].setdefault(t_cname, {
                "team_name": t_cname,
                "raw_team_name": raw_t,
                "institution": r["inst_name"] or "Independent",
                "prelim_debates": 0,
                "prelim_wins": 0,
                "ballots_won": 0,
                "team_scores": [],
                "margins": [],
            })
            entry["prelim_debates"] += 1
            if (r["ballots_won"] or 0) > (r["ballots_lost"] or 0):
                entry["prelim_wins"] += 1
            entry["ballots_won"] += (r["ballots_won"] or 0)
            if r["team_debate_score"]:
                entry["team_scores"].append(float(r["team_debate_score"]))
            if r["debate_margin"] is not None:
                entry["margins"].append(float(r["debate_margin"]))

        reconstructed_team_tabs: Dict[int, List[Dict[str, Any]]] = {}
        for tid, tmap in tour_teams.items():
            tlist = []
            for t_cname, e in tmap.items():
                tot_sc = sum(e["team_scores"])
                atss = tot_sc / len(e["team_scores"]) if e["team_scores"] else 0.0
                avg_m = sum(e["margins"]) / len(e["margins"]) if e["margins"] else 0.0
                broke = ((e["raw_team_name"], tid) in breaking) or ((t_cname, tid) in breaking)
                tlist.append({
                    "tournament_id": tid,
                    "tournament_name": tour_meta.get(tid, {}).get("clean_name", f"Tournament #{tid}"),
                    "team_name": t_cname,
                    "institution": e["institution"],
                    "prelim_debates": e["prelim_debates"],
                    "prelim_wins": e["prelim_wins"],
                    "ballots_won": e["ballots_won"],
                    "total_team_score": truncate_3(tot_sc) or 0.0,
                    "atss": truncate_3(atss) or 0.0,
                    "avg_margin": truncate_3(avg_m) or 0.0,
                    "broke": broke,
                    "_sort_key": (e["prelim_wins"], round(tot_sc, 4), round(atss, 4), e["ballots_won"], round(avg_m, 4)),
                })
            tlist.sort(key=lambda x: x["_sort_key"], reverse=True)
            total_t = len(tlist)
            for idx, item in enumerate(tlist, 1):
                item.pop("_sort_key", None)
                item["prelim_tab_rank"] = idx
                item["total_teams"] = total_t
            reconstructed_team_tabs[tid] = tlist

        target_tid = self._resolve_tournament_id(tournament) if tournament else None

        if team_name:
            q_team = CANONICAL_TEAM_ALIASES.get(team_name.strip(), team_name.strip()).lower()
            campaigns = []
            for tid in sorted(reconstructed_team_tabs.keys(), key=lambda x: CHRONOLOGICAL_TOURNAMENT_ORDER.get(x, x)):
                if target_tid is not None and tid != target_tid:
                    continue
                for item in reconstructed_team_tabs[tid]:
                    if item["team_name"].lower() == q_team or q_team in item["team_name"].lower():
                        campaigns.append(item)
            if not campaigns:
                return {"error": f"Team '{team_name}' not found in reconstructed tournament team tabs."}
            all_ranks = [c["prelim_tab_rank"] for c in campaigns]
            break_ranks = [c["prelim_tab_rank"] for c in campaigns if c["broke"]]
            return {
                "mode": "team",
                "team_name": campaigns[0]["team_name"],
                "institution": campaigns[0]["institution"],
                "tournaments_competed": len(campaigns),
                "breaks_count": len(break_ranks),
                "avg_prelim_team_tab_rank_all": truncate_3(sum(all_ranks) / len(all_ranks)),
                "avg_break_seed_rank_bra": truncate_3(sum(break_ranks) / len(break_ranks)) if break_ranks else None,
                "best_prelim_tab_rank": min(all_ranks),
                "campaigns": campaigns,
            }

        if target_tid is not None:
            if target_tid not in reconstructed_team_tabs:
                return {"error": f"Tournament '{tournament}' not found in team tab records."}
            tlist = reconstructed_team_tabs[target_tid]
            return {
                "mode": "tournament",
                "tournament_id": target_tid,
                "tournament_name": tour_meta.get(target_tid, {}).get("clean_name", f"Tournament #{target_tid}"),
                "total_teams": len(tlist),
                "standings": tlist[:limit],
            }

        return {"error": "Please specify either `tournament` or `team_name` for reconstruct_team_tab."}

    def close(self):
        """Close underlying database connection if owned."""
        if self._conn:
            self._conn.close()

