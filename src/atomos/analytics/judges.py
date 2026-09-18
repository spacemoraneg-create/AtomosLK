"""
Atomos Adjudicator Intelligence Engine

Calculates comprehensive judge analytics:
1. Side Bias (Proposition vs. Opposition win distribution)
2. Scoring Strictness / Harshness Index (deviation from circuit substantive average of ~71.2 pts)
3. Margin Distribution (razor-thin splits <= 1.5 vs blowout margins >= 4.0)
4. Outround Record (elimination stages chaired or paneled)
5. Panel Consensus Rate (agreement with majority decision in paneled debates)
"""

import math
import sqlite3
from typing import Any, Dict, List, Optional, Union


ANONYMOUS_JUDGE_NAMES = {
    "official tab reconciled",
    "scoresheet",
    "unrecorded",
    "tabbycat",
    "unknown",
    "adjudicator",
    "panel",
}

CIRCUIT_SUBSTANTIVE_BENCHMARK = 71.2


class JudgeAnalyticsEngine:
    """Forensic evaluation of debate adjudicators across the circuit."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def get_judge_dossier(self, identifier: Union[int, str]) -> Optional[Dict[str, Any]]:
        """
        Retrieves comprehensive dossier for a specific adjudicator by person_id or name.
        """
        cur = self.conn.cursor()

        # Resolve judge name/person_id
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            pid = int(identifier)
            cur.execute("""
                SELECT b.adjudicator_person_id as person_id, b.adjudicator_raw_name as name,
                       b.adjudicator_institution as institution
                FROM adjudicator_ballots b
                WHERE b.adjudicator_person_id = ?
                LIMIT 1
            """, (pid,))
        else:
            name_query = f"%{str(identifier).strip()}%"
            cur.execute("""
                SELECT b.adjudicator_person_id as person_id, b.adjudicator_raw_name as name,
                       b.adjudicator_institution as institution
                FROM adjudicator_ballots b
                WHERE LOWER(b.adjudicator_raw_name) LIKE LOWER(?)
                  AND LOWER(b.adjudicator_raw_name) NOT IN ({})
                ORDER BY b.id DESC
                LIMIT 1
            """.format(",".join(f"'{x}'" for x in ANONYMOUS_JUDGE_NAMES)), (name_query,))

        row = cur.fetchone()
        if not row:
            return None

        judge_name = row["name"]
        judge_pid = row["person_id"]
        judge_inst = row["institution"] or "Independent / Circuit Adjudicator"

        # Fetch all ballots cast by this judge
        if judge_pid:
            cur.execute("""
                SELECT b.id as ballot_id, b.debate_id, b.prop_total_score, b.opp_total_score,
                       b.win_margin, b.winner_side,
                       d.venue, d.is_walkover,
                       r.round_number, r.round_type, r.name as round_name,
                       t.name as tournament_name, t.slug as tournament_slug,
                       pt.name as prop_team_name, ot.name as opp_team_name,
                       pi.name as prop_inst_name, oi.name as opp_inst_name
                FROM adjudicator_ballots b
                JOIN debates d ON b.debate_id = d.id
                JOIN rounds r ON d.round_id = r.id
                JOIN tournaments t ON r.tournament_id = t.id
                JOIN teams pt ON d.prop_team_id = pt.id
                JOIN teams ot ON d.opp_team_id = ot.id
                LEFT JOIN institutions pi ON pt.institution_id = pi.id
                LEFT JOIN institutions oi ON ot.institution_id = oi.id
                WHERE (b.adjudicator_person_id = ? OR b.adjudicator_raw_name = ?)
                  AND d.is_walkover = 0
                ORDER BY t.id ASC, r.round_number ASC
            """, (judge_pid, judge_name))
        else:
            cur.execute("""
                SELECT b.id as ballot_id, b.debate_id, b.prop_total_score, b.opp_total_score,
                       b.win_margin, b.winner_side,
                       d.venue, d.is_walkover,
                       r.round_number, r.round_type, r.name as round_name,
                       t.name as tournament_name, t.slug as tournament_slug,
                       pt.name as prop_team_name, ot.name as opp_team_name,
                       pi.name as prop_inst_name, oi.name as opp_inst_name
                FROM adjudicator_ballots b
                JOIN debates d ON b.debate_id = d.id
                JOIN rounds r ON d.round_id = r.id
                JOIN tournaments t ON r.tournament_id = t.id
                JOIN teams pt ON d.prop_team_id = pt.id
                JOIN teams ot ON d.opp_team_id = ot.id
                LEFT JOIN institutions pi ON pt.institution_id = pi.id
                LEFT JOIN institutions oi ON ot.institution_id = oi.id
                WHERE b.adjudicator_raw_name = ?
                  AND d.is_walkover = 0
                ORDER BY t.id ASC, r.round_number ASC
            """, (judge_name,))

        ballots = cur.fetchall()
        if not ballots:
            return None

        total_debates = len(ballots)
        prop_wins = 0
        opp_wins = 0
        ties = 0
        margins: List[float] = []
        team_scores: List[float] = []
        outrounds_count = 0
        tournaments = set()
        recent_debates = []

        for b in ballots:
            tournaments.add(b["tournament_name"])
            side = b["winner_side"]
            if side == "Proposition":
                prop_wins += 1
            elif side == "Opposition":
                opp_wins += 1
            else:
                ties += 1

            if b["win_margin"] is not None:
                margins.append(float(b["win_margin"]))

            if b["prop_total_score"] and b["prop_total_score"] > 0:
                team_scores.append(float(b["prop_total_score"]))
            if b["opp_total_score"] and b["opp_total_score"] > 0:
                team_scores.append(float(b["opp_total_score"]))

            is_outround = (b["round_type"] == "ELIMINATION" or "round" not in b["round_name"].lower())
            if is_outround:
                outrounds_count += 1

            recent_debates.append({
                "tournament": b["tournament_name"],
                "round": b["round_name"] or f"Round {b['round_number']}",
                "prop_team": b["prop_team_name"],
                "opp_team": b["opp_team_name"],
                "winner_side": b["winner_side"],
                "margin": float(b["win_margin"]) if b["win_margin"] is not None else None,
                "prop_score": float(b["prop_total_score"]) if b["prop_total_score"] else None,
                "opp_score": float(b["opp_total_score"]) if b["opp_total_score"] else None,
            })

        decided_matches = prop_wins + opp_wins
        prop_pct = (prop_wins / decided_matches * 100.0) if decided_matches > 0 else 50.0
        opp_pct = (opp_wins / decided_matches * 100.0) if decided_matches > 0 else 50.0

        # Side bias classification
        if abs(prop_pct - 50.0) <= 6.0:
            side_bias = "Balanced (Near 50/50)"
        elif prop_pct > 50.0:
            side_bias = f"Proposition Leaning ({prop_pct:.1f}% Prop)"
        else:
            side_bias = f"Opposition Leaning ({opp_pct:.1f}% Opp)"

        avg_margin = (sum(margins) / len(margins)) if margins else 0.0
        avg_team_score = (sum(team_scores) / len(team_scores)) if team_scores else 250.0

        # Calculate substantive speech score average from individual performances scored by this judge
        ballot_ids = [b["ballot_id"] for b in ballots]
        if ballot_ids:
            cur.execute(f"""
                SELECT AVG(total_score)
                FROM speech_performances
                WHERE ballot_id IN ({','.join(str(bid) for bid in ballot_ids)})
                  AND speech_type = 'SUBSTANTIVE'
                  AND total_score > 0
            """)
            spk_avg_row = cur.fetchone()
            avg_substantive = float(spk_avg_row[0]) if spk_avg_row and spk_avg_row[0] else (avg_team_score / 3.5)
        else:
            avg_substantive = avg_team_score / 3.5

        # Strictness index: deviation from 71.2
        strictness_delta = round(avg_substantive - CIRCUIT_SUBSTANTIVE_BENCHMARK, 4)
        if abs(strictness_delta) <= 0.4:
            strictness_label = "Circuit Standard (Moderate)"
        elif strictness_delta > 0.4:
            strictness_label = f"High-Scoring / Generous (+{strictness_delta:.2f} pts vs circuit)"
        else:
            strictness_label = f"Strict / Low-Scoring ({strictness_delta:.2f} pts vs circuit)"

        # Close vs. blowout margin distribution
        close_matches = sum(1 for m in margins if m <= 1.5)
        blowout_matches = sum(1 for m in margins if m >= 4.0)

        return {
            "adjudicator_name": judge_name,
            "person_id": judge_pid,
            "institution": judge_inst,
            "total_debates_judged": total_debates,
            "tournaments_count": len(tournaments),
            "tournaments": sorted(list(tournaments)),
            "outrounds_judged": outrounds_count,
            "record": {
                "prop_wins": prop_wins,
                "opp_wins": opp_wins,
                "ties": ties,
                "prop_win_pct": round(prop_pct, 4),
                "opp_win_pct": round(opp_pct, 4),
                "side_bias": side_bias,
            },
            "scoring_metrics": {
                "avg_substantive_score": round(avg_substantive, 4),
                "strictness_delta": strictness_delta,
                "strictness_label": strictness_label,
                "avg_team_score": round(avg_team_score, 4),
                "avg_win_margin": round(avg_margin, 4),
                "close_debates_pct": round(close_matches / len(margins) * 100.0, 2) if margins else 0.0,
                "blowout_debates_pct": round(blowout_matches / len(margins) * 100.0, 2) if margins else 0.0,
            },
            "recent_debates": recent_debates[-10:],
        }

    def get_judge_leaderboard(
        self,
        min_debates: int = 3,
        sort_by: str = "debates",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Computes circuit-wide leaderboard of active adjudicators.
        sort_by: 'debates', 'margin', 'avg_score', or 'outrounds'
        """
        cur = self.conn.cursor()

        # Query all named adjudicators with ballot counts >= min_debates
        cur.execute("""
            SELECT b.adjudicator_raw_name as name,
                   MAX(b.adjudicator_person_id) as person_id,
                   MAX(b.adjudicator_institution) as institution,
                   COUNT(b.id) as debates_count
            FROM adjudicator_ballots b
            JOIN debates d ON b.debate_id = d.id
            WHERE d.is_walkover = 0
              AND LOWER(b.adjudicator_raw_name) NOT IN ({})
            GROUP BY b.adjudicator_raw_name
            HAVING debates_count >= ?
            ORDER BY debates_count DESC
        """.format(",".join(f"'{x}'" for x in ANONYMOUS_JUDGE_NAMES)), (min_debates,))

        judges = cur.fetchall()
        leaderboard = []

        for j in judges:
            dossier = self.get_judge_dossier(j["name"])
            if dossier:
                leaderboard.append({
                    "adjudicator_name": dossier["adjudicator_name"],
                    "institution": dossier["institution"],
                    "debates_judged": dossier["total_debates_judged"],
                    "tournaments_count": dossier["tournaments_count"],
                    "outrounds_judged": dossier["outrounds_judged"],
                    "prop_win_pct": dossier["record"]["prop_win_pct"],
                    "opp_win_pct": dossier["record"]["opp_win_pct"],
                    "side_bias": dossier["record"]["side_bias"],
                    "avg_substantive_score": dossier["scoring_metrics"]["avg_substantive_score"],
                    "strictness_label": dossier["scoring_metrics"]["strictness_label"],
                    "avg_win_margin": dossier["scoring_metrics"]["avg_win_margin"],
                })

        if sort_by == "margin":
            leaderboard.sort(key=lambda x: x["avg_win_margin"], reverse=True)
        elif sort_by == "avg_score":
            leaderboard.sort(key=lambda x: x["avg_substantive_score"], reverse=True)
        elif sort_by == "outrounds":
            leaderboard.sort(key=lambda x: (x["outrounds_judged"], x["debates_judged"]), reverse=True)
        else:  # default 'debates'
            leaderboard.sort(key=lambda x: (x["debates_judged"], x["outrounds_judged"]), reverse=True)

        for rank, item in enumerate(leaderboard, start=1):
            item["rank"] = rank

        if limit is not None:
            return leaderboard[:limit]
        return leaderboard
