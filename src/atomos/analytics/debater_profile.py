"""
Atomos Debater Profile & Identity Viewer Engine

Extracts complete debater dossiers including aliases, institutional affiliation,
teams debated, official Master Tab & Critical Stats rankings, preliminary round counts,
win rates, break rates, and a step-by-step mathematical derivation of the overall average.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import math
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union

from atomos.analytics.critical_stats import CriticalStatsEngine
from atomos.analytics.master_tabs import MasterTabEngine


def _fmt_val(v: Optional[float], max_decimals: int = 5) -> str:
    if v is None:
        return "N/A"
    try:
        f = float(v)
        rounded = round(f, max_decimals)
        s = f"{rounded:.{max_decimals}f}".rstrip('0').rstrip('.')
        return s if s else "0"
    except (ValueError, TypeError):
        return str(v)


@dataclass
class SpeechEntry:

    id: int
    position: str  # '1st', '2nd', '3rd', 'Reply'
    speech_type: str  # 'SUBSTANTIVE', 'REPLY'
    total_score: float
    is_iron_man: bool
    is_counted_in_tab: bool  # True if counted towards substantive tournament avg
    judge_name: Optional[str] = None


@dataclass
class RoundPerformance:
    round_number: int
    round_name: str
    round_type: str  # 'PRELIMINARY', 'ELIMINATION'
    team_name: str
    opp_team_name: str
    side: str  # 'Proposition', 'Opposition'
    speeches: List[SpeechEntry]
    is_walkover: bool
    is_win: bool
    ballot_split: str  # e.g. '1-0', '3-0', '2-1'
    margin: Optional[float]
    substantive_score: Optional[float]  # The score counted for this round
    reply_score: Optional[float] = None



@dataclass
class TournamentPerformance:
    tournament_id: int
    tournament_name: str
    tournament_slug: str
    team_name: str
    is_eligible: bool  # >= 3 prelim rounds
    prelim_rounds: List[RoundPerformance]
    elim_rounds: List[RoundPerformance]
    prelim_substantive_scores: List[float]
    tournament_average: Optional[float]
    score_stdev: Optional[float]
    team_broke: bool
    highest_stage: str  # e.g. 'Champions', 'Runners-Up', 'Semifinals', 'Quarterfinals', 'Preliminaries'


@dataclass
class DebaterProfile:
    person_id: int
    canonical_name: str
    institution: str
    aliases: List[str]
    teams_debated: List[str]
    tournaments_debated: List[str]

    # Official Rankings & Metrics
    overall_substantive_avg: Optional[float]
    raw_substantive_avg: Optional[float]
    avg_of_deviations: Optional[float]
    master_tab_rank: Optional[int]
    master_tab_total: int
    critical_stats_rank: Optional[int]
    critical_stats_total: int

    prelim_rounds_debated: int
    total_debates: int
    wins_debated: int
    losses_debated: int
    win_rate: float
    break_rate: float
    eligible_tournaments_count: int
    total_tournaments_count: int

    reply_speech_count: int
    reply_average: Optional[float]

    # Detailed Tournaments
    tournaments: List[TournamentPerformance]

    # Derivation breakdown
    derivation_text: str

    # Parallel Regulation Stats
    speech_average: Optional[float] = None  # New regulation: cumulative speech average across qualifying tournaments
    avg_of_avgs: Optional[float] = None     # Legacy regulation: average of tournament averages

    # National Team Status
    national_level: Optional[str] = None    # 'Trials', 'Nat Pool, Trialed', 'Nat Pool, Direct', or None

    # Chronological Trajectory
    trajectory: Optional[List[Dict[str, Any]]] = None  # Chronological tournament progression

    # Positions Breakdown & Adjudication History
    positions_breakdown: Optional[Dict[str, Any]] = None
    adjudication_record: Optional[Dict[str, Any]] = None

    # Official V2 Leaderboard Ranks
    tab_rank: Optional[int] = None
    general_tab_rank: Optional[int] = None


@dataclass
class DebaterSearchResult:
    person_id: int
    canonical_name: str
    institution: str
    teams: List[str]
    speech_count: int
    overall_avg: Optional[float]
    master_tab_rank: Optional[int]
    national_level: Optional[str] = None


class DebaterProfileEngine:
    """Extracts forensic identity dossiers and calculates step-by-step stat breakdowns."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.master_engine = MasterTabEngine(conn)
        self.critical_engine = CriticalStatsEngine(conn)

    def search_debaters(self, query: str, limit: int = 15) -> List[DebaterSearchResult]:
        """Search debaters by name, alias, or ID."""
        cur = self.conn.cursor()
        q = query.strip()
        if not q:
            return []

        if q.isdigit():
            cur.execute(
                """
                SELECT p.id, p.canonical_name, p.national_level 
                FROM persons p 
                WHERE p.id = ?
                """,
                (int(q),),
            )
        else:
            cur.execute(
                """
                SELECT DISTINCT p.id, p.canonical_name, p.national_level
                FROM persons p
                LEFT JOIN person_aliases pa ON p.id = pa.person_id
                WHERE p.canonical_name LIKE ? OR pa.raw_name LIKE ?
                ORDER BY p.canonical_name ASC
                LIMIT ?
                """,
                (f"%{q}%", f"%{q}%", limit),
            )

        matched_persons = cur.fetchall()
        if not matched_persons:
            return []

        # Precompute master tab lookup
        mtab = self.master_engine.get_master_speaker_tab(min_tournaments=1)
        mt_map = {s["person_id"]: s for s in mtab}

        results = []
        for p in matched_persons:
            pid = p["id"]
            # Fetch current/primary institution
            cur.execute(
                """
                SELECT DISTINCT i.name 
                FROM institutions i
                JOIN teams t ON t.institution_id = i.id
                JOIN team_members tm ON tm.team_id = t.id
                WHERE tm.person_id = ?
                ORDER BY t.id DESC
                LIMIT 1
                """,
                (pid,),
            )
            inst_row = cur.fetchone()
            inst = inst_row["name"] if inst_row else "Independent"

            # Fetch teams
            cur.execute(
                """
                SELECT DISTINCT t.name
                FROM teams t
                JOIN team_members tm ON tm.team_id = t.id
                WHERE tm.person_id = ?
                """,
                (pid,),
            )
            teams = [r["name"] for r in cur.fetchall()]

            cur.execute(
                "SELECT COUNT(*) FROM speech_performances WHERE person_id = ?",
                (pid,),
            )
            spk_cnt = cur.fetchone()[0]

            mt_entry = mt_map.get(pid)
            overall_avg = mt_entry["master_score"] if mt_entry else None
            mt_rank = mt_entry["rank"] if mt_entry else None

            results.append(
                DebaterSearchResult(
                    person_id=pid,
                    canonical_name=p["canonical_name"],
                    institution=inst,
                    teams=teams,
                    speech_count=spk_cnt,
                    overall_avg=overall_avg,
                    master_tab_rank=mt_rank,
                    national_level=p["national_level"],
                )
            )

        return results

    def get_profile(self, person_id: int) -> Optional[DebaterProfile]:
        """Generate complete dossier for a debater."""
        cur = self.conn.cursor()

        # 1. Fetch Person Base
        cur.execute("SELECT id, canonical_name, national_level FROM persons WHERE id = ?", (person_id,))
        p_row = cur.fetchone()
        if not p_row:
            return None

        canonical_name = p_row["canonical_name"]
        national_level = p_row["national_level"]

        # 2. Fetch Aliases
        cur.execute(
            "SELECT raw_name FROM person_aliases WHERE person_id = ? ORDER BY id ASC",
            (person_id,),
        )
        aliases = [r["raw_name"] for r in cur.fetchall()]
        if not aliases:
            aliases = [canonical_name]

        # 3. Fetch Institution
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
        inst_rows = cur.fetchall()
        institution = ", ".join([r[0] for r in inst_rows if r[0]]) if inst_rows else "Independent / Composite"

        # 4. Official V2 Leaderboard Rankings (Tab tier: >= 18 rounds; General tier: >= 5 rounds)
        from atomos.analytics.v2_metrics import V2MetricsEngine
        v2_eng = V2MetricsEngine(self.conn)
        tab_speakers = v2_eng.get_multipurpose_speakers(tier="tab")
        gen_speakers = v2_eng.get_multipurpose_speakers(tier="general")
        cstats = self.critical_engine.get_critical_speaker_stats(min_tournaments=3)

        tab_entry = next((s for s in tab_speakers if s["person_id"] == person_id), None)
        gen_entry = next((s for s in gen_speakers if s["person_id"] == person_id), None)
        cs_entry = next((s for s in cstats if s["person_id"] == person_id), None)

        tab_rank = tab_entry["rank"] if tab_entry else None
        general_tab_rank = gen_entry["rank"] if gen_entry else None
        critical_stats_rank = cs_entry["rank"] if cs_entry else None

        mtab = self.master_engine.get_master_speaker_tab(min_tournaments=1)
        mt_entry = next((s for s in mtab if s["person_id"] == person_id), None)
        overall_substantive_avg = mt_entry["master_score"] if mt_entry else None
        speech_average = mt_entry["speech_average"] if mt_entry else None
        avg_of_avgs = mt_entry["avg_of_avgs"] if mt_entry else None

        # Sourced official tab rank (or general tab rank if < 18 rounds, fallback to mtab rank)
        master_tab_rank = tab_rank or general_tab_rank or (mt_entry["rank"] if mt_entry else None)
        mt_total = len(tab_speakers) if tab_speakers else (len(mtab) if mtab else 0)
        cs_total = len(cstats)

        avg_of_deviations = cs_entry["avg_of_deviations"] if cs_entry else None

        # 5. Fetch all speeches and debates for this debater
        cur.execute(
            """
            SELECT sp.id as speech_id, sp.total_score, sp.position, sp.side, sp.speech_type, sp.is_iron_man,
                   b.adjudicator_raw_name as judge_name,
                   r.id as round_id, r.round_number, r.name as round_name, r.round_type,
                   t.id as tour_id, t.name as tour_name, t.slug as tour_slug,
                   tm.id as team_id, tm.name as team_name,
                   opp.name as opp_team_name,
                   d.id as debate_id, d.is_walkover, d.walkover_winner_id,
                   deb_bal.prop_ballots, deb_bal.opp_ballots,
                   CASE WHEN sp.side = 'Proposition' THEN deb_bal.prop_margin ELSE -deb_bal.prop_margin END as avg_margin
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN teams tm ON sp.team_id = tm.id
            JOIN debates d ON sp.debate_id = d.id
            LEFT JOIN teams opp ON ((d.prop_team_id = tm.id AND d.opp_team_id = opp.id) 
                                 OR (d.opp_team_id = tm.id AND d.prop_team_id = opp.id))
            LEFT JOIN adjudicator_ballots b ON sp.ballot_id = b.id
            LEFT JOIN (
                SELECT debate_id,
                       SUM(CASE WHEN winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_ballots,
                       SUM(CASE WHEN winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_ballots,
                       AVG(prop_total_score - opp_total_score) as prop_margin
                FROM adjudicator_ballots
                GROUP BY debate_id
            ) deb_bal ON d.id = deb_bal.debate_id
            WHERE sp.person_id = ?
            ORDER BY t.id, r.round_number, sp.position, sp.id
            """,
            (person_id,),
        )
        speech_rows = cur.fetchall()

        # 6. Group by Tournament -> Round
        tournaments_data: Dict[int, dict] = {}
        distinct_teams = set()
        distinct_tours = set()
        reply_scores: List[float] = []

        breaking_teams = self.critical_engine._get_breaking_teams()

        for sr in speech_rows:
            t_id = sr["tour_id"]
            distinct_teams.add(sr["team_name"])
            distinct_tours.add(sr["tour_name"])

            if t_id not in tournaments_data:
                tournaments_data[t_id] = {
                    "id": t_id,
                    "name": sr["tour_name"],
                    "slug": sr["tour_slug"],
                    "team_name": sr["team_name"],
                    "rounds": defaultdict(dict),
                }

            r_key = (sr["round_number"], sr["round_name"], sr["round_type"], sr["side"], sr["opp_team_name"] or "Unknown", sr["is_walkover"])
            r_dict = tournaments_data[t_id]["rounds"].setdefault(r_key, {
                "round_number": sr["round_number"],
                "round_name": sr["round_name"],
                "round_type": sr["round_type"],
                "side": sr["side"],
                "opp_team_name": sr["opp_team_name"] or "Unknown",
                "is_walkover": bool(sr["is_walkover"]),
                "prop_ballots": sr["prop_ballots"],
                "opp_ballots": sr["opp_ballots"],
                "margin": sr["avg_margin"],
                "speeches": [],
            })

            sp_entry = SpeechEntry(
                id=sr["speech_id"],
                position=sr["position"],
                speech_type=sr["speech_type"],
                total_score=float(sr["total_score"]),
                is_iron_man=bool(sr["is_iron_man"]),
                is_counted_in_tab=False,  # Will flag next
                judge_name=sr["judge_name"],
            )
            r_dict["speeches"].append(sp_entry)


        # Process each tournament performance
        tour_perf_list: List[TournamentPerformance] = []
        all_prelim_substantive_scores: List[float] = []
        qualifying_tour_averages: List[Tuple[str, float, List[float]]] = []
        total_prelim_rounds = 0
        total_wins = 0
        total_debates = 0
        tournaments_broken = 0
        eligible_tournaments_count = 0

        for t_id, t_info in tournaments_data.items():
            team_name = t_info["team_name"]
            prelim_rounds: List[RoundPerformance] = []
            elim_rounds: List[RoundPerformance] = []
            t_prelim_substantive_scores: List[float] = []

            for r_key, r_info in sorted(t_info["rounds"].items(), key=lambda x: x[0][0]):
                side = r_info["side"]
                p_bal, o_bal = r_info["prop_ballots"], r_info["opp_ballots"]

                if r_info["is_walkover"]:
                    is_win = True
                    split_str = "WALKOVER"
                elif p_bal is not None and o_bal is not None:
                    is_win = (side == "Proposition" and p_bal > o_bal) or (side == "Opposition" and o_bal > p_bal)
                    split_str = f"{max(p_bal, o_bal)}-{min(p_bal, o_bal)}"
                else:
                    is_win = False
                    split_str = "N/A"

                if is_win:
                    total_wins += 1
                total_debates += 1

                # Substantive score selection (panel-averaged, and higher position for Iron Man)
                sub_by_pos = defaultdict(list)
                for sp in r_info["speeches"]:
                    if sp.speech_type == "SUBSTANTIVE" and sp.total_score > 0:
                        sub_by_pos[sp.position].append(sp)

                counted_sub_score: Optional[float] = None
                if sub_by_pos:
                    pos_avgs = {}
                    for pos, sp_list in sub_by_pos.items():
                        avg_s = sum(sp.total_score for sp in sp_list) / len(sp_list)
                        pos_avgs[pos] = (avg_s, sp_list)

                    # For Iron Man debates, select the position with the higher panel-averaged score
                    best_pos = max(pos_avgs.keys(), key=lambda p: pos_avgs[p][0])
                    counted_sub_score = round(pos_avgs[best_pos][0], 5)

                    # Mark counted speeches
                    for pos, (avg_s, sp_list) in pos_avgs.items():
                        is_counted = (pos == best_pos)
                        for sp in sp_list:
                            sp.is_counted_in_tab = is_counted

                # Reply score selection (panel-averaged)
                rep_speeches = [sp for sp in r_info["speeches"] if sp.speech_type == "REPLY" and sp.total_score > 0]
                counted_rep_score: Optional[float] = None
                if rep_speeches:
                    counted_rep_score = round(sum(sp.total_score for sp in rep_speeches) / len(rep_speeches), 5)
                    if r_info["round_type"] == "PRELIMINARY":
                        reply_scores.append(counted_rep_score)

                round_perf = RoundPerformance(
                    round_number=r_info["round_number"],
                    round_name=r_info["round_name"],
                    round_type=r_info["round_type"],
                    team_name=team_name,
                    opp_team_name=r_info["opp_team_name"],
                    side=r_info["side"],
                    speeches=r_info["speeches"],
                    is_walkover=r_info["is_walkover"],
                    is_win=is_win,
                    ballot_split=split_str,
                    margin=round(r_info["margin"], 5) if r_info["margin"] is not None else None,
                    substantive_score=counted_sub_score,
                    reply_score=counted_rep_score,
                )


                if r_info["round_type"] == "PRELIMINARY":
                    prelim_rounds.append(round_perf)
                    if counted_sub_score is not None:
                        t_prelim_substantive_scores.append(counted_sub_score)
                        all_prelim_substantive_scores.append(counted_sub_score)
                else:
                    elim_rounds.append(round_perf)

            p_count = len(t_prelim_substantive_scores)
            is_eligible = (p_count >= 3)
            t_avg = (sum(t_prelim_substantive_scores) / p_count) if p_count > 0 else None

            t_stdev = None
            if t_avg is not None and p_count > 1:
                variance = sum((x - t_avg) ** 2 for x in t_prelim_substantive_scores) / p_count
                t_stdev = math.sqrt(variance)

            # Did team break in this tournament?
            team_broke = (team_name, t_id) in breaking_teams
            if team_broke and is_eligible:
                tournaments_broken += 1

            if is_eligible:
                eligible_tournaments_count += 1
                total_prelim_rounds += p_count
                if t_avg is not None:
                    qualifying_tour_averages.append((t_info["name"], round(t_avg, 5), t_prelim_substantive_scores))

            # Highest stage reached & team elimination rounds
            if not elim_rounds:
                cur.execute(
                    """
                    SELECT r.round_number, r.name as round_name,
                           tm.name as team_name,
                           opp.name as opp_name,
                           d.id as debate_id, d.is_walkover,
                           SUM(CASE WHEN b.winner_side = 'Proposition' THEN 1 ELSE 0 END) as prop_ballots,
                           SUM(CASE WHEN b.winner_side = 'Opposition' THEN 1 ELSE 0 END) as opp_ballots,
                           CASE WHEN d.prop_team_id = tm.id THEN 'Proposition' ELSE 'Opposition' END as team_side
                    FROM debates d
                    JOIN rounds r ON d.round_id = r.id
                    JOIN teams tm ON (d.prop_team_id = tm.id OR d.opp_team_id = tm.id)
                    JOIN team_members tmem ON tm.id = tmem.team_id
                    LEFT JOIN teams opp ON ((d.prop_team_id = tm.id AND d.opp_team_id = opp.id) 
                                         OR (d.opp_team_id = tm.id AND d.prop_team_id = opp.id))
                    LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
                    WHERE tmem.person_id = ? AND r.tournament_id = ? AND r.round_type = 'ELIMINATION'
                    GROUP BY d.id
                    ORDER BY r.round_number ASC
                    """,
                    (person_id, t_id),
                )
                for er in cur.fetchall():
                    side = er["team_side"]
                    p_bal, o_bal = er["prop_ballots"], er["opp_ballots"]
                    if er["is_walkover"]:
                        win = True
                        split_str = "WALKOVER"
                    elif p_bal is not None and o_bal is not None:
                        win = (side == "Proposition" and p_bal > o_bal) or (side == "Opposition" and o_bal > p_bal)
                        split_str = f"{max(p_bal, o_bal)}-{min(p_bal, o_bal)}"
                    else:
                        win = False
                        split_str = "N/A"

                    elim_rounds.append(
                        RoundPerformance(
                            round_number=er["round_number"],
                            round_name=er["round_name"],
                            round_type="ELIMINATION",
                            team_name=team_name,
                            opp_team_name=er["opp_name"] or "Unknown",
                            side=side,
                            speeches=[],
                            is_walkover=bool(er["is_walkover"]),
                            is_win=win,
                            ballot_split=split_str,
                            margin=None,
                            substantive_score=None,
                        )
                    )

            if elim_rounds:
                last_elim = elim_rounds[-1]
                if last_elim.is_win and ("final" in last_elim.round_name.lower() or "championship" in last_elim.round_name.lower()):
                    highest_stage = f"Champions ({last_elim.round_name})"
                elif "final" in last_elim.round_name.lower():
                    highest_stage = f"Runners-Up ({last_elim.round_name})"
                else:
                    highest_stage = f"Knockouts ({last_elim.round_name})"
            elif team_broke:
                highest_stage = "Qualified for Knockouts"
            else:
                highest_stage = "Preliminary Rounds"


            tour_perf_list.append(
                TournamentPerformance(
                    tournament_id=t_id,
                    tournament_name=t_info["name"],
                    tournament_slug=t_info["slug"],
                    team_name=team_name,
                    is_eligible=is_eligible,
                    prelim_rounds=prelim_rounds,
                    elim_rounds=elim_rounds,
                    prelim_substantive_scores=t_prelim_substantive_scores,
                    tournament_average=round(t_avg, 5) if t_avg is not None else None,
                    score_stdev=round(t_stdev, 5) if t_stdev is not None else None,
                    team_broke=team_broke,
                    highest_stage=highest_stage,
                )
            )

        # 7. Summary metrics
        win_rate = (total_wins / total_debates * 100.0) if total_debates > 0 else 0.0
        break_rate = (tournaments_broken / eligible_tournaments_count * 100.0) if eligible_tournaments_count > 0 else 0.0
        raw_avg = (sum(all_prelim_substantive_scores) / len(all_prelim_substantive_scores)) if all_prelim_substantive_scores else None
        reply_avg = (sum(reply_scores) / len(reply_scores)) if reply_scores else None

        # 8. Build Derivation Text Walkthrough
        derivation_lines = [
            "====================================================================================================",
            "                        EXPANDED DERIVATION: HOW THE CODE ARRIVED AT THE OVERALL AVG",
            "====================================================================================================",
            "WSDC & Atomos Master Tab Standardization Rules:",
            "  1. Scope: Only preliminary rounds determine official speaker averages (elimination rounds are excluded).",
            "  2. Threshold: A debater must debate at least 3 preliminary substantive rounds in a tournament to be ELIGIBLE.",
            "  3. Paneled Ballots: When a debate has multiple adjudicators (panel), each speech score is the arithmetic mean across all ballots.",
            "  4. Iron Man Rule: When a debater speaks twice in a round, the higher panel-averaged substantive score represents the round.",
            "  5. Replies: Reply speeches are scored out of 40 and tracked separately on the Master Reply Tab.",
            "  6. Master Score Formula (New Standard Regulation - Priority): Cumulative speech average across qualifying tournaments:",
            "     Speech Average = (Sum of Qualifying Prelim Speeches) / (Total Qualifying Prelim Speeches)",
            "  7. Legacy Formula: Arithmetic mean of tournament substantive averages across all qualifying tournaments:",
            "     Overall Avg = (Sum of Qualifying Tournament Averages) / (Total Qualifying Tournaments)",
            "",
            "Tournament Qualification Audit:",
        ]

        for idx, t in enumerate(tour_perf_list, 1):
            status = f"QUALIFIED ({len(t.prelim_substantive_scores)} prelims >= 3)" if t.is_eligible else f"INELIGIBLE ({len(t.prelim_substantive_scores)} prelims < 3)"
            avg_str = f"{_fmt_val(t.tournament_average)} pts" if t.tournament_average is not None else "No scores"
            derivation_lines.append(f"  [{idx}] {t.tournament_name}")
            derivation_lines.append(f"      Team: {t.team_name} | Status: {status}")
            derivation_lines.append(f"      Prelim Scores: {t.prelim_substantive_scores}")
            if t.is_eligible and t.tournament_average is not None:
                sum_scores = sum(t.prelim_substantive_scores)
                derivation_lines.append(f"      Calculation: ({' + '.join(_fmt_val(s) for s in t.prelim_substantive_scores)}) / {len(t.prelim_substantive_scores)} = {_fmt_val(sum_scores)} / {len(t.prelim_substantive_scores)} = {avg_str}")
            else:
                derivation_lines.append(f"      [EXCLUDED] Debater spoke in fewer than 3 prelims. This tournament average is excluded from Master Tab.")
            derivation_lines.append("")

        derivation_lines.append("----------------------------------------------------------------------------------------------------")
        derivation_lines.append("Final Aggregation Step:")
        if qualifying_tour_averages:
            t_avgs = [item[1] for item in qualifying_tour_averages]
            sum_t_avgs = sum(t_avgs)
            count_t = len(t_avgs)
            calculated_legacy = sum_t_avgs / count_t

            qualifying_speeches = [s for item in qualifying_tour_averages for s in item[2]]
            sum_qualifying_speeches = sum(qualifying_speeches)
            count_speeches = len(qualifying_speeches)
            calculated_cumulative = (sum_qualifying_speeches / count_speeches) if count_speeches > 0 else 0.0

            derivation_lines.append(f"  Qualifying Tournaments ({count_t}):")
            for name, avg_val, scores in qualifying_tour_averages:
                derivation_lines.append(f"    * {name:<60} = {_fmt_val(avg_val)} pts ({len(scores)} prelim speeches: {scores})")
            derivation_lines.append("")
            derivation_lines.append(f"  [NEW REGULATION - PRIORITY] Cumulative Speech Average:")
            derivation_lines.append(f"    Sum of Qualifying Speeches = {_fmt_val(sum_qualifying_speeches)} across {count_speeches} speeches")
            derivation_lines.append(f"    Speech Average = {_fmt_val(sum_qualifying_speeches)} / {count_speeches} = {_fmt_val(calculated_cumulative)} pts")
            derivation_lines.append("")
            derivation_lines.append(f"  [LEGACY REGULATION] Mean of Tournament Averages:")
            derivation_lines.append(f"    Sum of Qualifying Tournament Averages = {' + '.join(_fmt_val(a) for a in t_avgs)} = {_fmt_val(sum_t_avgs)}")
            derivation_lines.append(f"    Overall Avg = {_fmt_val(sum_t_avgs)} / {count_t} = {_fmt_val(calculated_legacy)} pts")
        else:
            derivation_lines.append("  No tournaments met the 3-round preliminary eligibility threshold.")

        derivation_lines.append("====================================================================================================")
        derivation_text = "\n".join(derivation_lines)

        # Build chronological trajectory time-series
        trajectory: List[Dict[str, Any]] = []
        cumulative_speeches: List[float] = []
        for t_perf in tour_perf_list:
            if t_perf.tournament_average is not None:
                cumulative_speeches.extend(t_perf.prelim_substantive_scores)
                running_avg = sum(cumulative_speeches) / len(cumulative_speeches) if cumulative_speeches else t_perf.tournament_average
                trajectory.append({
                    "tournament_id": t_perf.tournament_id,
                    "tournament_name": t_perf.tournament_name,
                    "tournament_slug": t_perf.tournament_slug,
                    "substantive_avg": t_perf.tournament_average,
                    "running_cumulative_avg": round(running_avg, 4),
                    "speeches_count": len(t_perf.prelim_substantive_scores),
                    "peak_speech": max(t_perf.prelim_substantive_scores) if t_perf.prelim_substantive_scores else None,
                    "stage_reached": t_perf.highest_stage,
                    "is_eligible": t_perf.is_eligible,
                })

        # 9. Compute Speaker Positions Breakdown
        cur.execute(
            """
            SELECT position, speech_type, COUNT(DISTINCT debate_id) as cnt, AVG(total_score) as avg_sc
            FROM speech_performances
            WHERE person_id = ?
            GROUP BY position, speech_type
            """,
            (person_id,),
        )
        pos_rows = cur.fetchall()
        positions_breakdown: Dict[str, Any] = {
            "1st": {"count": 0, "avg": None, "percentage": 0.0},
            "2nd": {"count": 0, "avg": None, "percentage": 0.0},
            "3rd": {"count": 0, "avg": None, "percentage": 0.0},
            "Reply": {"count": 0, "avg": None, "percentage": 0.0},
            "total_substantive": 0,
            "total_speeches": 0,
        }
        total_sub = 0
        total_all_speeches = 0
        for pr in pos_rows:
            pos = pr["position"]
            cnt = pr["cnt"]
            avg_val = round(float(pr["avg_sc"]), 2) if pr["avg_sc"] is not None else None
            stype = pr["speech_type"]
            total_all_speeches += cnt
            if stype == "SUBSTANTIVE":
                total_sub += cnt
            if pos in positions_breakdown:
                positions_breakdown[pos]["count"] = cnt
                positions_breakdown[pos]["avg"] = avg_val

        positions_breakdown["total_substantive"] = total_sub
        positions_breakdown["total_speeches"] = total_all_speeches
        for pos in ["1st", "2nd", "3rd"]:
            if total_sub > 0:
                positions_breakdown[pos]["percentage"] = round((positions_breakdown[pos]["count"] / total_sub) * 100.0, 1)

        # 10. Compute Adjudication History ("Adjed or not")
        cur.execute(
            """
            SELECT DISTINCT t.id, t.name, t.year, tr.role
            FROM tournament_roles tr
            JOIN tournaments t ON tr.tournament_id = t.id
            WHERE tr.person_id = ? AND (tr.role = 'ADJUDICATOR' OR tr.role LIKE '%judge%')
            ORDER BY t.year DESC, t.id DESC
            """,
            (person_id,),
        )
        adj_tour_rows = cur.fetchall()

        cur.execute(
            """
            SELECT t.id as tour_id, t.name as tour_name, r.name as round_name, aa.is_chair
            FROM adjudicator_assignments aa
            JOIN debates d ON aa.debate_id = d.id
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            WHERE aa.person_id = ?
            ORDER BY t.id, r.id
            """,
            (person_id,),
        )
        adj_assign_rows = cur.fetchall()

        cur.execute(
            """
            SELECT DISTINCT t.id as tour_id, t.name as tour_name, r.name as round_name
            FROM adjudicator_ballots ab
            JOIN debates d ON ab.debate_id = d.id
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            WHERE ab.adjudicator_person_id = ?
            ORDER BY t.id, r.id
            """,
            (person_id,),
        )
        adj_ballot_rows = cur.fetchall()

        has_adjudicated = len(adj_tour_rows) > 0 or len(adj_assign_rows) > 0 or len(adj_ballot_rows) > 0
        tours_adj_map: Dict[int, Dict[str, Any]] = {}
        for tr in adj_tour_rows:
            tid = tr["id"]
            clean_tname = tr["name"].split('|')[0].strip()
            tours_adj_map[tid] = {
                "tournament_name": clean_tname,
                "year": tr["year"],
                "role": tr["role"],
                "rounds_assigned": [],
                "rounds_balloted": [],
                "chair_count": 0,
                "panel_count": 0,
            }

        for ar in adj_assign_rows:
            tid = ar["tour_id"]
            clean_tname = ar["tour_name"].split('|')[0].strip()
            if tid not in tours_adj_map:
                tours_adj_map[tid] = {
                    "tournament_name": clean_tname,
                    "year": None,
                    "role": "ADJUDICATOR",
                    "rounds_assigned": [],
                    "rounds_balloted": [],
                    "chair_count": 0,
                    "panel_count": 0,
                }
            r_name = ar["round_name"]
            if r_name not in tours_adj_map[tid]["rounds_assigned"]:
                tours_adj_map[tid]["rounds_assigned"].append(r_name)
            if ar["is_chair"]:
                tours_adj_map[tid]["chair_count"] += 1
            else:
                tours_adj_map[tid]["panel_count"] += 1

        for br in adj_ballot_rows:
            tid = br["tour_id"]
            clean_tname = br["tour_name"].split('|')[0].strip()
            if tid not in tours_adj_map:
                tours_adj_map[tid] = {
                    "tournament_name": clean_tname,
                    "year": None,
                    "role": "ADJUDICATOR",
                    "rounds_assigned": [],
                    "rounds_balloted": [],
                    "chair_count": 0,
                    "panel_count": 0,
                }
            r_name = br["round_name"]
            if r_name not in tours_adj_map[tid]["rounds_balloted"]:
                tours_adj_map[tid]["rounds_balloted"].append(r_name)

        adjudication_record = {
            "has_adjudicated": has_adjudicated,
            "tournaments_count": len(tours_adj_map),
            "tournaments": list(tours_adj_map.values()),
        }

        return DebaterProfile(
            person_id=person_id,
            canonical_name=canonical_name,
            institution=institution,
            aliases=aliases,
            teams_debated=sorted(list(distinct_teams)),
            tournaments_debated=sorted(list(distinct_tours)),
            overall_substantive_avg=overall_substantive_avg,
            raw_substantive_avg=round(raw_avg, 5) if raw_avg else None,
            avg_of_deviations=avg_of_deviations,
            master_tab_rank=master_tab_rank,
            master_tab_total=mt_total,
            critical_stats_rank=critical_stats_rank,
            critical_stats_total=cs_total,
            prelim_rounds_debated=total_prelim_rounds,
            total_debates=total_debates,
            wins_debated=total_wins,
            losses_debated=total_debates - total_wins,
            win_rate=round(win_rate, 5),
            break_rate=round(break_rate, 5),
            eligible_tournaments_count=eligible_tournaments_count,
            total_tournaments_count=len(tournaments_data),
            reply_speech_count=len(reply_scores),
            reply_average=round(reply_avg, 5) if reply_avg else None,
            tournaments=tour_perf_list,
            derivation_text=derivation_text,
            speech_average=speech_average,
            avg_of_avgs=avg_of_avgs,
            national_level=national_level,
            trajectory=trajectory,
            positions_breakdown=positions_breakdown,
            adjudication_record=adjudication_record,
            tab_rank=tab_rank,
            general_tab_rank=general_tab_rank,
        )
