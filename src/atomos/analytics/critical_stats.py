"""
Atomos Critical Stats Engine (Parallel Engine)

High-rigor analytical layer with strict eligibility:
1. Individual Critical Stats:
   - Must be eligible (>= 3 prelim rounds) in AT LEAST 3 tournaments (minimum 9 prelim rounds).
   - 5 Required Stats:
     1. Avg: Overall substantive average across eligible tournaments
     2. Avg of deviations in tournaments: Mean of within-tournament score standard deviations
     3. Win rate in rounds the person debated: Win % when person actually debated
     4. How many preliminary rounds debated: Total preliminary rounds debated
     5. Break percentage when he was eligible in speaks tab: % of eligible tournaments where team broke

2. Team Critical Stats:
   - Must have participated in AT LEAST 3 tournaments.
   - 7 Required Stats:
     1. Break percentage: % of tournaments where team broke into out-rounds
     2. Win percentage: Overall win % across all rounds (prelims + eliminations)
     3. Opp/Prop win split: Proposition Win % vs Opposition Win %
     4. Rounds debated: Total matches debated across all tournaments
     5. Break rounds debated: Total elimination matches debated (Octos, Quarters, etc.)
     6. ATSS: Average Total Speaker Score across prelims
     7. Avg Margins: Average margin in won debates
"""

import math
import sqlite3
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple


class CriticalStatsEngine:
    """Computes high-rigor, high-threshold critical stats for debaters and teams."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def _get_breaking_teams(self) -> Set[Tuple[str, int]]:
        """Identifies (team_name, tournament_id) pairs that reached elimination rounds."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT DISTINCT COALESCE(t.canonical_name, t.name) as name, tour.id as tour_id
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments tour ON r.tournament_id = tour.id
            JOIN teams t ON (d.prop_team_id = t.id OR d.opp_team_id = t.id)
            WHERE ((r.round_type = 'ELIMINATION' OR 
                    (tour.slug = 'slsdc26' AND r.round_number >= 8) OR
                    (tour.slug = 'vijis26' AND r.round_number >= 6) OR
                    (tour.slug = 'aisdc26' AND r.round_number >= 7) OR
                    (tour.slug = 'apiitisdc2026' AND r.round_number >= 6 AND r.round_number < 10) OR
                    (tour.slug = 'metho2026' AND r.round_number >= 6) OR
                    (tour.slug = 'vvidc2026' AND r.round_number >= 6) OR
                    (tour.slug = 'Chaps2026' AND r.round_number >= 6) OR
                    (tour.slug = 'ric2026' AND r.round_number >= 6))
                   AND LOWER(r.name) NOT LIKE '%novice%')
        """)
        return set((row["name"], row["tour_id"]) for row in cur.fetchall())

    def get_critical_speaker_stats(
        self,
        min_tournaments: int = 3,
        regulation: str = "new",
    ) -> List[dict]:
        """
        Computes Individual Critical Stats for debaters eligible in >= min_tournaments.
        Supports both new regulation (cumulative speech average, priority) and legacy (avg of avgs).
        """
        cur = self.conn.cursor()
        breaking_teams = self._get_breaking_teams()

        # Query latest host institution for each debater
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

        # 1. Fetch all preliminary substantive speeches
        # In paneled debates, average the adjudicator ballots for each speech position
        cur.execute("""
            SELECT p.id as person_id, p.canonical_name as speaker_name,
                    p.national_level,
                    inst.name as institution_name,
                    COALESCE(t.canonical_name, t.name) as team_name,
                    r.tournament_id, r.round_number,
                    sp.debate_id, sp.side, sp.position,
                    AVG(sp.total_score) as speech_score
            FROM speech_performances sp
            JOIN debates d ON sp.debate_id = d.id
            JOIN rounds r ON sp.round_id = r.id
            JOIN persons p ON sp.person_id = p.id
            JOIN teams t ON sp.team_id = t.id
            LEFT JOIN institutions inst ON t.institution_id = inst.id
            WHERE sp.speech_type = 'SUBSTANTIVE'
              AND r.round_type = 'PRELIMINARY'
              AND d.is_walkover = 0
              AND sp.total_score > 0
            GROUP BY p.id, r.tournament_id, r.round_number, sp.debate_id, sp.position
            ORDER BY p.id, r.tournament_id, r.round_number
        """)
        speeches = cur.fetchall()

        # 2. Query all debate results where debaters actually debated
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
        debater_matches = cur.fetchall()

        person_match_results = defaultdict(list)
        for m in debater_matches:
            won = (m["side"] == "Proposition" and m["p_ballots"] > m["o_ballots"]) or \
                  (m["side"] == "Opposition" and m["o_ballots"] > m["p_ballots"])
            person_match_results[m["person_id"]].append(won)

        # 3. Group speeches by person -> tournament -> round
        person_tours = defaultdict(lambda: defaultdict(dict))
        person_tour_teams = defaultdict(dict)
        person_meta = {}

        for sp in speeches:
            pid = sp["person_id"]
            tid = sp["tournament_id"]
            r_num = sp["round_number"]
            score = float(sp["speech_score"])

            if pid not in person_meta:
                person_meta[pid] = {
                    "name": sp["speaker_name"],
                    "institution": sp["institution_name"] or "Independent",
                    "national_level": sp["national_level"],
                }
            person_tour_teams[pid][tid] = sp["team_name"]
            # For paneled debates, speech_score is the panel average for that position.
            # For Iron Man debates (multiple positions in round), take the higher substantive position.
            existing = person_tours[pid][tid].get(r_num, 0.0)
            person_tours[pid][tid][r_num] = max(existing, score)


        # 4. Compute 5 stats
        leaderboard = []
        for pid, tours in person_tours.items():
            eligible_tour_avgs = []
            eligible_tour_stdevs = []
            eligible_scores = []
            breaks_count = 0
            total_prelim_rounds = 0

            for tid, round_scores in tours.items():
                scores = list(round_scores.values())
                cnt = len(scores)
                # Count every preliminary round debated across all tournaments
                total_prelim_rounds += cnt
                # Eligibility rule: >= 3 prelim rounds in tournament
                if cnt >= 3:
                    avg = sum(scores) / cnt
                    eligible_tour_avgs.append(avg)
                    eligible_scores.extend(scores)

                    # Within-tournament standard deviation
                    variance = sum((x - avg) ** 2 for x in scores) / cnt
                    stdev = math.sqrt(variance)
                    eligible_tour_stdevs.append(stdev)

                    # Did team break?
                    t_name = person_tour_teams[pid].get(tid)
                    if (t_name, tid) in breaking_teams:
                        breaks_count += 1

            eligible_tours_count = len(eligible_tour_avgs)
            if eligible_tours_count >= min_tournaments:
                avg_of_avgs = sum(eligible_tour_avgs) / eligible_tours_count
                speech_avg = sum(eligible_scores) / len(eligible_scores) if eligible_scores else 0.0
                avg_dev = sum(eligible_tour_stdevs) / eligible_tours_count

                # New regulation (priority) uses cumulative speech average, legacy uses avg of avgs
                if regulation in ("legacy", "avg_of_avgs"):
                    overall_avg = avg_of_avgs
                else:
                    overall_avg = speech_avg

                matches = person_match_results.get(pid, [])
                win_rate = (sum(matches) / len(matches) * 100.0) if matches else 0.0
                break_pct = (breaks_count / eligible_tours_count * 100.0)

                inst_name = latest_inst.get(pid, person_meta[pid]["institution"] or "Independent")

                leaderboard.append({
                    "person_id": pid,
                    "speaker_name": person_meta[pid]["name"],
                    "institution": inst_name,
                    "institution_name": inst_name,
                    "national_level": person_meta[pid]["national_level"],
                    "speaker_avg": round(overall_avg, 2),
                    "win_percentage": round(win_rate, 1),
                    "prelims": total_prelim_rounds,
                    "break_percentage": round(break_pct, 1),
                    "tournaments": eligible_tours_count,
                    "avg": round(overall_avg, 5),
                    "speech_avg": round(speech_avg, 5),
                    "cumulative_speech_avg": round(speech_avg, 5),
                    "avg_of_avgs": round(avg_of_avgs, 5),
                    "regulation": regulation,
                    "avg_of_deviations": round(avg_dev, 5),
                    "win_rate_debated": round(win_rate, 5),
                    "prelim_rounds_debated": total_prelim_rounds,
                    "eligible_tournaments": eligible_tours_count,
                })

        # Rank by Avg -> Win Rate -> Consistency (lower deviation)
        leaderboard.sort(key=lambda x: (x["avg"], x["win_rate_debated"], -x["avg_of_deviations"]), reverse=True)
        for rank, entry in enumerate(leaderboard, start=1):
            entry["rank"] = rank

        return leaderboard

    def _get_highest_achievements(self) -> Dict[str, str]:
        """
        Computes the highest elimination achievement for all teams using BracketEngine.
        Returns mapping of team_name -> 'Champion' | 'Finalist' | 'Semifinalist' | 'Quarterfinalist' | 'Octofinalist' | '-'
        """
        try:
            from atomos.analytics.brackets import BracketEngine
            bracket_engine = BracketEngine(self.conn)
            cur = self.conn.cursor()
            cur.execute("SELECT id, slug FROM tournaments ORDER BY id")
            all_tourns = cur.fetchall()

            team_highest: Dict[str, Tuple[int, str]] = defaultdict(lambda: (0, "-"))

            for t in all_tourns:
                slug = t["slug"]
                try:
                    b = bracket_engine.get_tournament_bracket(slug)
                except Exception:
                    continue
                if not b:
                    continue
                stages = b.get("stages", [])
                for stage in stages:
                    sname = stage.get("stage_name", "")
                    slower = sname.lower()
                    matchups = stage.get("matchups", [])
                    for m in matchups:
                        p_team = m.get("proposition", {}).get("team_name")
                        o_team = m.get("opposition", {}).get("team_name")
                        res = m.get("result", {})
                        w_side = res.get("winner_side")
                        p_won = (w_side == "Proposition")
                        o_won = (w_side == "Opposition")

                        if "novice" in slower:
                            if "grand final" in slower or (slower == "novice final" and stage.get("matches_count") == 1):
                                n_champ = p_team if p_won else (o_team if o_won else None)
                                n_runner = o_team if p_won else (p_team if o_won else None)
                                if n_champ and 0.5 > team_highest[n_champ][0]:
                                    team_highest[n_champ] = (0.5, "Novice Champion")
                                if n_runner and 0.4 > team_highest[n_runner][0]:
                                    team_highest[n_runner] = (0.4, "Novice Finalist")
                            elif "semi" in slower:
                                n_winner = p_team if p_won else (o_team if o_won else None)
                                n_loser = o_team if p_won else (p_team if o_won else None)
                                if n_winner and 0.4 > team_highest[n_winner][0]:
                                    team_highest[n_winner] = (0.4, "Novice Finalist")
                                if n_loser and 0.3 > team_highest[n_loser][0]:
                                    team_highest[n_loser] = (0.3, "Novice Semifinalist")
                            continue

                        if "grand final" in slower or (slower == "final" and stage.get("matches_count") == 1):
                            champ = p_team if p_won else (o_team if o_won else None)
                            runner_up = o_team if p_won else (p_team if o_won else None)
                            if champ and 5 > team_highest[champ][0]:
                                team_highest[champ] = (5, "Champion")
                            if runner_up and 4 > team_highest[runner_up][0]:
                                team_highest[runner_up] = (4, "Finalist")
                        elif "semi" in slower:
                            loser = o_team if p_won else (p_team if o_won else None)
                            winner = p_team if p_won else (o_team if o_won else None)
                            if loser and 3 > team_highest[loser][0]:
                                team_highest[loser] = (3, "Semifinalist")
                            if winner and 4 > team_highest[winner][0]:
                                team_highest[winner] = (4, "Finalist")
                        elif "quarter" in slower or slower == "quarters":
                            loser = o_team if p_won else (p_team if o_won else None)
                            winner = p_team if p_won else (o_team if o_won else None)
                            if loser and 2 > team_highest[loser][0]:
                                team_highest[loser] = (2, "Quarterfinalist")
                            if winner and 3 > team_highest[winner][0]:
                                team_highest[winner] = (3, "Semifinalist")
                        elif "octo" in slower:
                            loser = o_team if p_won else (p_team if o_won else None)
                            winner = p_team if p_won else (o_team if o_won else None)
                            if loser and 1 > team_highest[loser][0]:
                                team_highest[loser] = (1, "Octofinalist")
                            if winner and 2 > team_highest[winner][0]:
                                team_highest[winner] = (2, "Quarterfinalist")

            return {k: v[1] for k, v in team_highest.items()}
        except Exception:
            return {}

    def get_critical_team_stats(self, min_tournaments: int = 3) -> List[dict]:
        """
        Computes Team Critical Stats for teams participating in >= min_tournaments.
        Ranked by ATSS -> Win % -> Break % -> Tournaments Debated.
        """
        cur = self.conn.cursor()
        breaking_teams = self._get_breaking_teams()
        highest_achievements = self._get_highest_achievements()

        # Query distinct debates aggregating paneled adjudicator ballots
        cur.execute("""
            SELECT d.id as debate_id, r.round_type, r.round_number, r.name as round_name, tour.slug, tour.id as tour_id,
                   COALESCE(pt.canonical_name, pt.name) as prop_name,
                   COALESCE(ot.canonical_name, ot.name) as opp_name,
                   inst_p.name as prop_inst, inst_o.name as opp_inst,
                   AVG(CASE WHEN b.prop_total_score > 0 THEN b.prop_total_score END) as p_score,
                   AVG(CASE WHEN b.opp_total_score > 0 THEN b.opp_total_score END) as o_score,
                   AVG(b.win_margin) as avg_margin,
                   SUM(CASE WHEN b.winner_side = 'Proposition' THEN 1 ELSE 0 END) as p_ballots,
                   SUM(CASE WHEN b.winner_side = 'Opposition' THEN 1 ELSE 0 END) as o_ballots
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments tour ON r.tournament_id = tour.id
            JOIN teams pt ON d.prop_team_id = pt.id
            JOIN teams ot ON d.opp_team_id = ot.id
            LEFT JOIN institutions inst_p ON pt.institution_id = inst_p.id
            LEFT JOIN institutions inst_o ON ot.institution_id = inst_o.id
            LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE (d.is_walkover = 0 OR (d.is_walkover = 1 AND b.winner_side IS NOT NULL))
            GROUP BY d.id
        """)
        debates = cur.fetchall()

        team_stats = defaultdict(lambda: {
            "inst": "",
            "tournaments": set(),
            "rounds_debated": 0,
            "break_rounds_debated": 0,
            "wins": 0,
            "prop_debates": 0,
            "prop_wins": 0,
            "opp_debates": 0,
            "opp_wins": 0,
            "prelim_speaker_points": 0.0,
            "prelim_rounds": 0,
            "win_margins": [],
            "loss_margins": [],
            "all_margins": [],
        })

        for d in debates:
            p = d["prop_name"]
            o = d["opp_name"]
            tid = d["tour_id"]
            r_name_lower = (d["round_name"] or "").lower()
            is_novice = "novice" in r_name_lower
            is_break_round = (not is_novice) and (
                d["round_type"] == "ELIMINATION" or 
                (d["slug"] == "slsdc26" and d["round_number"] >= 8) or
                (d["slug"] == "vijis26" and d["round_number"] >= 6) or
                (d["slug"] == "aisdc26" and d["round_number"] >= 7) or
                (d["slug"] == "apiitisdc2026" and d["round_number"] >= 6 and d["round_number"] < 10) or
                (d["slug"] == "metho2026" and d["round_number"] >= 6) or
                (d["slug"] == "vvidc2026" and d["round_number"] >= 6) or
                (d["slug"] == "Chaps2026" and d["round_number"] >= 6) or
                (d["slug"] == "ric2026" and d["round_number"] >= 6)
            )
            is_prelim = (not is_novice) and (d["round_type"] == "PRELIMINARY")

            p_won = (d["p_ballots"] > d["o_ballots"])
            o_won = (d["o_ballots"] > d["p_ballots"])
            m = d["avg_margin"]

            # Proposition
            ps = team_stats[p]
            ps["inst"] = d["prop_inst"] or "Independent"
            ps["tournaments"].add(tid)
            ps["rounds_debated"] += 1
            ps["prop_debates"] += 1
            if is_break_round:
                ps["break_rounds_debated"] += 1
            elif is_prelim:
                if d["p_score"]:
                    ps["prelim_speaker_points"] += d["p_score"]
                    ps["prelim_rounds"] += 1

            if m is not None:
                ps["all_margins"].append(m)

            if p_won:
                ps["wins"] += 1
                ps["prop_wins"] += 1
                if m is not None:
                    ps["win_margins"].append(abs(m))
            elif o_won:
                if m is not None:
                    ps["loss_margins"].append(abs(m))

            # Opposition
            os = team_stats[o]
            os["inst"] = d["opp_inst"] or "Independent"
            os["tournaments"].add(tid)
            os["rounds_debated"] += 1
            os["opp_debates"] += 1
            if is_break_round:
                os["break_rounds_debated"] += 1
            elif is_prelim:
                if d["o_score"]:
                    os["prelim_speaker_points"] += d["o_score"]
                    os["prelim_rounds"] += 1

            if m is not None:
                os["all_margins"].append(-m)

            if o_won:
                os["wins"] += 1
                os["opp_wins"] += 1
                if m is not None:
                    os["win_margins"].append(abs(m))
            elif p_won:
                if m is not None:
                    os["loss_margins"].append(abs(m))

        leaderboard = []
        for name, st in team_stats.items():
            t_cnt = len(st["tournaments"])
            if t_cnt >= min_tournaments:
                breaks = sum(1 for tid in st["tournaments"] if (name, tid) in breaking_teams)
                break_pct = (breaks / t_cnt * 100.0)
                win_pct = (st["wins"] / st["rounds_debated"] * 100.0) if st["rounds_debated"] > 0 else 0.0
                prop_win_pct = (st["prop_wins"] / st["prop_debates"] * 100.0) if st["prop_debates"] > 0 else 0.0
                opp_win_pct = (st["opp_wins"] / st["opp_debates"] * 100.0) if st["opp_debates"] > 0 else 0.0
                atss = (st["prelim_speaker_points"] / st["prelim_rounds"]) if st["prelim_rounds"] > 0 else 0.0
                
                avg_win_margin = (sum(st["win_margins"]) / len(st["win_margins"])) if st["win_margins"] else 0.0
                avg_loss_margin = (sum(st["loss_margins"]) / len(st["loss_margins"])) if st["loss_margins"] else 0.0
                net_margin = (sum(st["all_margins"]) / len(st["all_margins"])) if st["all_margins"] else 0.0

                highest_ach = highest_achievements.get(name, "-")

                leaderboard.append({
                    "team_name": name,
                    "institution": st["inst"],
                    "tournaments_count": t_cnt,
                    "tournaments_debated": t_cnt,
                    "break_percentage": round(break_pct, 5),
                    "win_percentage": round(win_pct, 5),
                    "opp_prop_split": {
                        "prop_win_percentage": round(prop_win_pct, 5),
                        "opp_win_percentage": round(opp_win_pct, 5),
                    },
                    "rounds_debated": st["rounds_debated"],
                    "break_rounds_debated": st["break_rounds_debated"],
                    "atss": round(atss, 5),
                    "avg_margins": round(avg_win_margin, 5),
                    "avg_win_margin": round(avg_win_margin, 5),
                    "avg_loss_margin": round(avg_loss_margin, 5),
                    "net_margin": round(net_margin, 5),
                    "highest_achievement": highest_ach,
                    "highest_break": highest_ach,
                })

        # Rank by ATSS -> Win Rate -> Break % -> Tournaments Debated
        leaderboard.sort(key=lambda x: (x["atss"], x["win_percentage"], x["break_percentage"], x["tournaments_debated"]), reverse=True)
        for rank, entry in enumerate(leaderboard, start=1):
            entry["rank"] = rank

        return leaderboard
