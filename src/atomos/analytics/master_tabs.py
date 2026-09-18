"""
Atomos Master Tabs Engine

Calculates:
1. Master Speaker Tab (per-tournament 3-round eligibility, Iron Man higher score, mean of tournament averages)
2. Master Reply Tab (reply speech averages across tournaments)
3. Master Team Tab (Wins -> ATSS -> Margin tiebreaker sequence)
"""

import sqlite3
from typing import Dict, List, Optional, Tuple


class MasterTabEngine:
    """Calculates official master rankings and leaderboards."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def get_master_speaker_tab(
        self,
        min_tournaments: int = 1,
        category: str = "ALL",
        regulation: str = "new",
    ) -> List[dict]:
        """
        Computes Master Speaker Tab rankings.
        Rule: Debater must have >= 3 prelim rounds in a tournament to have an official
              tournament average.
              Iron Man: Higher substantive score in that round counts.
              New Regulation (Priority): Cumulative speech average (sum of all qualifying
                  prelim speeches / total qualifying speeches).
              Legacy Regulation: Average of tournament averages across eligible tournaments.
              regulation: 'new' (default, priority) or 'legacy'.
        """
        cur = self.conn.cursor()

        # Query latest host institution for all debaters
        cur.execute("""
            SELECT sp.person_id, inst.name as inst_name
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN tournaments tour ON r.tournament_id = tour.id
            JOIN teams t ON sp.team_id = t.id
            LEFT JOIN institutions inst ON t.institution_id = inst.id
            WHERE sp.total_score > 0 AND inst.name IS NOT NULL
            ORDER BY tour.id DESC, r.round_number DESC
        """)
        latest_inst: Dict[int, str] = {}
        for row in cur.fetchall():
            pid_val = row["person_id"]
            if pid_val not in latest_inst:
                latest_inst[pid_val] = row["inst_name"]

        # Query win rate for debaters in debates they actually spoke in
        cur.execute("""
            SELECT sp.person_id, sp.debate_id, sp.side,
                   SUM(CASE WHEN b.winner_side = 'Proposition' THEN 1 ELSE 0 END) as p_ballots,
                   SUM(CASE WHEN b.winner_side = 'Opposition' THEN 1 ELSE 0 END) as o_ballots
            FROM speech_performances sp
            JOIN debates d ON sp.debate_id = d.id
            JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE d.is_walkover = 0 AND b.winner_side IS NOT NULL
            GROUP BY sp.person_id, sp.debate_id, sp.side
        """)
        from collections import defaultdict
        person_wins: Dict[int, list] = defaultdict(list)
        for m in cur.fetchall():
            won = (m["side"] == "Proposition" and m["p_ballots"] > m["o_ballots"]) or \
                  (m["side"] == "Opposition" and m["o_ballots"] > m["p_ballots"])
            person_wins[m["person_id"]].append(won)

        # Query breaking teams
        from atomos.analytics.critical_stats import CriticalStatsEngine
        crit_engine = CriticalStatsEngine(self.conn)
        breaking_teams = crit_engine._get_breaking_teams()

        # 1. Fetch all preliminary substantive speeches with tournament, round, and person info
        # In paneled debates, average the adjudicator ballots for each speech position
        cur.execute("""
            SELECT p.id as person_id, p.canonical_name as speaker_name,
                   p.national_level,
                   inst.name as institution_name,
                   COALESCE(tm.canonical_name, tm.name) as team_name,
                   t.id as tournament_id, t.name as tournament_name, t.slug as tournament_slug,
                   r.round_number,
                   sp.debate_id, sp.position,
                   AVG(sp.total_score) as speech_score,
                   MAX(sp.is_iron_man) as is_iron_man
            FROM speech_performances sp
            JOIN debates d ON sp.debate_id = d.id
            JOIN rounds r ON sp.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN teams tm ON sp.team_id = tm.id
            JOIN persons p ON sp.person_id = p.id
            LEFT JOIN institutions inst ON tm.institution_id = inst.id
            WHERE sp.speech_type = 'SUBSTANTIVE'
              AND r.round_type = 'PRELIMINARY'
              AND d.is_walkover = 0
              AND sp.total_score > 0
            GROUP BY p.id, t.id, r.round_number, sp.debate_id, sp.position
            ORDER BY p.id, t.id, r.round_number
        """)
        rows = cur.fetchall()

        # Group speeches by person -> tournament -> round
        # In case of Iron Man, take max score across positions for that round
        person_tour_rounds: Dict[int, Dict[int, Dict[int, float]]] = {}
        person_tour_teams: Dict[int, Dict[int, str]] = defaultdict(dict)
        person_meta: Dict[int, dict] = {}

        for row in rows:
            pid = row["person_id"]
            tid = row["tournament_id"]
            r_num = row["round_number"]
            score = float(row["speech_score"])

            if pid not in person_meta:
                person_meta[pid] = {
                    "person_id": pid,
                    "speaker_name": row["speaker_name"],
                    "institution_name": row["institution_name"] or "Independent / Composite",
                    "national_level": row["national_level"],
                }

            person_tour_teams[pid][tid] = row["team_name"]
            tour_dict = person_tour_rounds.setdefault(pid, {})
            round_dict = tour_dict.setdefault(tid, {})
            # If debater spoke multiple substantive positions in same round (Iron Man), keep the higher substantive score
            round_dict[r_num] = max(round_dict.get(r_num, 0.0), score)

        # Calculate per-tournament averages and master scores
        leaderboard = []

        for pid, tour_dict in person_tour_rounds.items():
            eligible_tour_averages: List[float] = []
            tour_details: List[dict] = []
            total_eligible_rounds = 0
            all_scores: List[float] = []
            eligible_scores: List[float] = []
            breaks_count = 0
            all_tours_cnt = len(tour_dict)

            for tid, rounds in tour_dict.items():
                scores = list(rounds.values())
                all_scores.extend(scores)
                round_count = len(scores)

                # WSDC Rule: >= 3 preliminary rounds to be eligible in a tournament
                is_eligible = (round_count >= 3)
                tour_avg = sum(scores) / round_count if round_count > 0 else 0.0

                tour_details.append({
                    "tournament_id": tid,
                    "rounds_debated": round_count,
                    "is_eligible": is_eligible,
                    "tournament_average": round(tour_avg, 5),
                    "scores": scores,
                })

                if is_eligible:
                    eligible_tour_averages.append(tour_avg)
                    eligible_scores.extend(scores)
                    total_eligible_rounds += round_count

                t_name = person_tour_teams[pid].get(tid)
                if (t_name, tid) in breaking_teams:
                    breaks_count += 1

            eligible_tour_count = len(eligible_tour_averages)
            if eligible_tour_count < min_tournaments and min_tournaments > 1:
                continue

            # Legacy Regulation: Arithmetic mean of tournament averages
            avg_of_avgs = (sum(eligible_tour_averages) / eligible_tour_count) if eligible_tour_count > 0 else 0.0

            # Cumulative speech average across qualifying tournaments (or all speeches if no eligible tournament)
            used_scores = eligible_scores if eligible_scores else all_scores
            cumulative_speech_avg = (sum(used_scores) / len(used_scores)) if used_scores else 0.0

            # Circuit-wide raw average across all speeches
            all_speech_avg = (sum(all_scores) / len(all_scores)) if all_scores else 0.0

            # Priority selection based on regulation parameter
            if regulation in ("legacy", "avg_of_avgs") and eligible_tour_count > 0:
                active_score = avg_of_avgs
            else:
                active_score = cumulative_speech_avg

            peak_score = max(all_scores) if all_scores else 0.0

            # Win % and Break % without eligibility restrictions
            matches = person_wins.get(pid, [])
            win_rate = (sum(matches) / len(matches) * 100.0) if matches else 0.0
            break_pct = (breaks_count / all_tours_cnt * 100.0) if all_tours_cnt > 0 else 0.0

            inst_name = latest_inst.get(pid, person_meta[pid]["institution_name"])

            leaderboard.append({
                "person_id": pid,
                "speaker_name": person_meta[pid]["speaker_name"],
                "institution": inst_name,
                "institution_name": inst_name,
                "national_level": person_meta[pid]["national_level"],
                "master_score": round(active_score, 5),
                "speaker_avg": round(active_score, 2),
                "speech_avg": round(active_score, 2),
                "speech_average": round(cumulative_speech_avg, 5),
                "cumulative_speech_avg": round(cumulative_speech_avg, 5),
                "avg_of_avgs": round(avg_of_avgs, 5),
                "all_speech_average": round(all_speech_avg, 5),
                "regulation": regulation,
                "win_percentage": round(win_rate, 1),
                "win_rate": round(win_rate, 1),
                "prelims": len(all_scores),
                "total_rounds": len(all_scores),
                "break_percentage": round(break_pct, 1),
                "tournaments": all_tours_cnt,
                "eligible_tournaments": eligible_tour_count,
                "peak_score": round(peak_score, 5),
                "tournament_breakdown": tour_details,
            })

        # Sort: Highest Master Score -> Win % -> Tournaments
        leaderboard.sort(
            key=lambda x: (x["master_score"], x["win_percentage"], x["tournaments"]),
            reverse=True
        )

        for rank, entry in enumerate(leaderboard, start=1):
            entry["rank"] = rank

        return leaderboard

    def get_master_reply_tab(self, min_speeches: int = 1) -> List[dict]:
        """
        Computes Master Reply Tab rankings.
        Rule: No minimum round threshold (unlike substantive speakers).
              Ranked by average of preliminary reply speech scores.
        """
        cur = self.conn.cursor()

        cur.execute("""
            SELECT p.id as person_id, p.canonical_name as speaker_name,
                   p.national_level,
                   inst.name as institution_name,
                   sp.debate_id,
                   AVG(sp.total_score) as reply_score
            FROM speech_performances sp
            JOIN debates d ON sp.debate_id = d.id
            JOIN rounds r ON sp.round_id = r.id
            JOIN teams tm ON sp.team_id = tm.id
            JOIN persons p ON sp.person_id = p.id
            LEFT JOIN institutions inst ON tm.institution_id = inst.id
            WHERE sp.speech_type = 'REPLY'
              AND r.round_type = 'PRELIMINARY'
              AND d.is_walkover = 0
              AND sp.total_score > 0
            GROUP BY p.id, sp.debate_id
            ORDER BY p.id
        """)
        rows = cur.fetchall()

        person_replies: Dict[int, List[float]] = {}
        person_meta: Dict[int, dict] = {}

        for row in rows:
            pid = row["person_id"]
            score = float(row["reply_score"])

            if pid not in person_meta:
                person_meta[pid] = {
                    "person_id": pid,
                    "speaker_name": row["speaker_name"],
                    "institution_name": row["institution_name"] or "Independent / Composite",
                    "national_level": row["national_level"],
                }
            person_replies.setdefault(pid, []).append(score)


        leaderboard = []
        for pid, scores in person_replies.items():
            if len(scores) < min_speeches:
                continue
            avg_reply = sum(scores) / len(scores)
            leaderboard.append({
                "person_id": pid,
                "speaker_name": person_meta[pid]["speaker_name"],
                "institution_name": person_meta[pid]["institution_name"],
                "national_level": person_meta[pid]["national_level"],
                "reply_average": round(avg_reply, 5),
                "reply_count": len(scores),
                "peak_reply": round(max(scores), 5),
            })

        # Sort: Highest Reply Average -> Most Replies Delivered -> Peak Reply
        leaderboard.sort(
            key=lambda x: (x["reply_average"], x["reply_count"], x["peak_reply"]),
            reverse=True
        )

        for rank, entry in enumerate(leaderboard, start=1):
            entry["rank"] = rank

        return leaderboard

    def get_master_team_tab(self, min_tournaments: int = 1) -> List[dict]:
        """
        Computes Master Team Tab rankings across tournaments.
        Tiebreaker sequence: Total Wins -> ATSS -> Average Win Margin
        """
        cur = self.conn.cursor()

        # Query all debated matches with ballots
        cur.execute("""
            SELECT t.id as tournament_id, t.name as tournament_name,
                   d.id as debate_id, d.prop_team_id, d.opp_team_id,
                   COALESCE(pt.canonical_name, pt.name) as prop_name,
                   COALESCE(ot.canonical_name, ot.name) as opp_name,
                   inst_p.name as prop_institution,
                   inst_o.name as opp_institution,
                   b.prop_total_score, b.opp_total_score, b.win_margin, b.winner_side
            FROM adjudicator_ballots b
            JOIN debates d ON b.debate_id = d.id
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN teams pt ON d.prop_team_id = pt.id
            JOIN teams ot ON d.opp_team_id = ot.id
            LEFT JOIN institutions inst_p ON pt.institution_id = inst_p.id
            LEFT JOIN institutions inst_o ON ot.institution_id = inst_o.id
            WHERE r.round_type = 'PRELIMINARY'
              AND d.is_walkover = 0
        """)
        rows = cur.fetchall()

        # Aggregate by team name / canonical institution
        team_stats: Dict[str, dict] = {}

        for row in rows:
            # Proposition
            p_name = row["prop_name"]
            p_inst = row["prop_institution"] or "Independent"
            p_tot = row["prop_total_score"]
            margin = row["win_margin"]
            is_prop_win = (row["winner_side"] == "Proposition")

            p_entry = team_stats.setdefault(p_name, {
                "team_name": p_name,
                "institution": p_inst,
                "tournaments": set(),
                "debates_count": 0,
                "wins": 0,
                "total_speaker_points": 0.0,
                "win_margins": [],
            })
            p_entry["tournaments"].add(row["tournament_id"])
            p_entry["debates_count"] += 1
            p_entry["total_speaker_points"] += p_tot
            if is_prop_win:
                p_entry["wins"] += 1
                p_entry["win_margins"].append(abs(margin))

            # Opposition
            o_name = row["opp_name"]
            o_inst = row["opp_institution"] or "Independent"
            o_tot = row["opp_total_score"]
            is_opp_win = (row["winner_side"] == "Opposition")

            o_entry = team_stats.setdefault(o_name, {
                "team_name": o_name,
                "institution": o_inst,
                "tournaments": set(),
                "debates_count": 0,
                "wins": 0,
                "total_speaker_points": 0.0,
                "win_margins": [],
            })
            o_entry["tournaments"].add(row["tournament_id"])
            o_entry["debates_count"] += 1
            o_entry["total_speaker_points"] += o_tot
            if is_opp_win:
                o_entry["wins"] += 1
                o_entry["win_margins"].append(abs(margin))

        leaderboard = []
        for name, entry in team_stats.items():
            t_count = len(entry["tournaments"])
            if t_count < min_tournaments:
                continue

            debates = entry["debates_count"]
            wins = entry["wins"]
            atss = (entry["total_speaker_points"] / debates) if debates > 0 else 0.0
            avg_win_margin = (sum(entry["win_margins"]) / wins) if wins > 0 else 0.0
            win_rate = (wins / debates * 100.0) if debates > 0 else 0.0

            leaderboard.append({
                "team_name": name,
                "institution": entry["institution"],
                "tournaments_count": t_count,
                "debates_count": debates,
                "wins": wins,
                "win_rate": round(win_rate, 5),
                "atss": round(atss, 5),
                "avg_win_margin": round(avg_win_margin, 5),
                "is_master_eligible": (t_count >= 3),  # 3+ tournaments for national master honors
            })

        # Official WSDC Tiebreaker sequence: Wins -> ATSS -> Average Win Margin
        leaderboard.sort(
            key=lambda x: (x["wins"], x["atss"], x["avg_win_margin"]),
            reverse=True
        )

        for rank, entry in enumerate(leaderboard, start=1):
            entry["rank"] = rank

        return leaderboard
