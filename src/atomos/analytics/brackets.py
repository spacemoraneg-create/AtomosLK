"""
Atomos Tournament Knockout Bracket Engine

Constructs structured, hierarchical elimination trees across circuit tournaments:
- Octofinals -> Quarterfinals -> Semifinals -> Grand Final
- Matchup nodes with teams, institutions, speaker lineups, speech scores, and panel decisions
- Tournament Champion, Runner-up, and same-institution closeout detection
"""

import sqlite3
from typing import Any, Dict, List, Optional


STAGE_NAMES_BY_COUNT = {
    8: "Octofinals",
    4: "Quarterfinals",
    2: "Semifinals",
    1: "Grand Final",
}

TOURNAMENT_ALIASES = {
    "chaps": "Chaps2026",
    "chapman": "Chaps2026",
    "slsdc": "slsdc26",
    "law fac": "slsdc26",
    "law facs": "slsdc26",
    "visakha": "vvidc2026",
    "vvidc": "vvidc2026",
    "metho": "metho2026",
    "methodist": "metho2026",
    "vijis": "vijis26",
    "aisdc": "aisdc26",
    "ais": "aisdc26",
    "apiit": "apiitisdc2026",
    "ric": "ric2026",
    "isdc": "ric2026",
}


class BracketEngine:
    """Extracts and structures tournament elimination brackets."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def get_tournament_bracket(self, tournament: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()

        # Resolve tournament slug
        tourn_clean = tournament.strip().lower()
        slug_match = TOURNAMENT_ALIASES.get(tourn_clean, tourn_clean)

        cur.execute("""
            SELECT id, name, slug, year, season
            FROM tournaments
            WHERE LOWER(slug) = LOWER(?) OR LOWER(name) LIKE LOWER(?)
            ORDER BY id DESC
            LIMIT 1
        """, (slug_match, f"%{tournament.strip()}%"))

        tourn_row = cur.fetchone()
        if not tourn_row:
            return None

        tid = tourn_row["id"]
        tourn_name = tourn_row["name"]
        tourn_slug = tourn_row["slug"]

        # Fetch elimination rounds
        cur.execute("""
            SELECT r.id as round_id, r.round_number, r.name as round_name, r.round_type,
                   r.motion, r.info_slide,
                   COUNT(d.id) as debate_count
            FROM rounds r
            LEFT JOIN debates d ON d.round_id = r.id AND d.is_walkover = 0
            WHERE r.tournament_id = ?
              AND (r.round_type = 'ELIMINATION' OR 
                   (r.round_number >= 6 AND LOWER(r.name) NOT LIKE 'round%'))
            GROUP BY r.id
            HAVING debate_count > 0
            ORDER BY r.round_number ASC
        """, (tid,))

        round_rows = cur.fetchall()
        if not round_rows:
            return None

        stages: List[Dict[str, Any]] = []
        grand_final_match = None

        for r_idx, r in enumerate(round_rows):
            deb_cnt = r["debate_count"]
            r_name = r["round_name"]

            # Standardize stage label
            if "novice" in (r_name or "").lower():
                stage_label = r_name
            elif grand_final_match is not None:
                # Open Grand Final was already reached; later rounds are Novice
                stage_label = f"Novice {STAGE_NAMES_BY_COUNT.get(deb_cnt, r_name)}"
            elif deb_cnt in STAGE_NAMES_BY_COUNT and ("round" in (r_name or "").lower() or not r_name):
                stage_label = STAGE_NAMES_BY_COUNT[deb_cnt]
            elif r_idx == len(round_rows) - 1 and deb_cnt == 1:
                stage_label = "Grand Final"
            else:
                stage_label = r_name

            # Query debates in this round
            cur.execute("""
                SELECT d.id as debate_id, d.venue,
                       pt.id as prop_team_id, COALESCE(pt.canonical_name, pt.name) as prop_team_name,
                       ot.id as opp_team_id, COALESCE(ot.canonical_name, ot.name) as opp_team_name,
                       pi.name as prop_inst_name, oi.name as opp_inst_name
                FROM debates d
                JOIN teams pt ON d.prop_team_id = pt.id
                JOIN teams ot ON d.opp_team_id = ot.id
                LEFT JOIN institutions pi ON pt.institution_id = pi.id
                LEFT JOIN institutions oi ON ot.institution_id = oi.id
                WHERE d.round_id = ? AND d.is_walkover = 0
                ORDER BY d.id ASC
            """, (r["round_id"],))
            debates = cur.fetchall()

            matchups = []
            for d in debates:
                did = d["debate_id"]

                # Fetch adjudicator ballots
                cur.execute("""
                    SELECT adjudicator_raw_name, winner_side, prop_total_score, opp_total_score, win_margin
                    FROM adjudicator_ballots
                    WHERE debate_id = ? AND winner_side IS NOT NULL
                """, (did,))
                ballots = cur.fetchall()

                prop_votes = sum(1 for b in ballots if b["winner_side"] == "Proposition")
                opp_votes = sum(1 for b in ballots if b["winner_side"] == "Opposition")

                if prop_votes > opp_votes:
                    winner_side = "Proposition"
                    winner_team = d["prop_team_name"]
                    winner_inst = d["prop_inst_name"]
                elif opp_votes > prop_votes:
                    winner_side = "Opposition"
                    winner_team = d["opp_team_name"]
                    winner_inst = d["opp_inst_name"]
                else:
                    winner_side = "Undecided / Tie"
                    winner_team = "Undecided"
                    winner_inst = "Undecided"

                # Panel scores
                valid_prop_scores = [float(b["prop_total_score"]) for b in ballots if b["prop_total_score"] and b["prop_total_score"] > 0]
                valid_opp_scores = [float(b["opp_total_score"]) for b in ballots if b["opp_total_score"] and b["opp_total_score"] > 0]
                valid_margins = [float(b["win_margin"]) for b in ballots if b["win_margin"] is not None]

                avg_prop_score = round(sum(valid_prop_scores) / len(valid_prop_scores), 2) if valid_prop_scores else None
                avg_opp_score = round(sum(valid_opp_scores) / len(valid_opp_scores), 2) if valid_opp_scores else None
                avg_margin = round(sum(valid_margins) / len(valid_margins), 2) if valid_margins else None

                decision_split = f"{max(prop_votes, opp_votes)}-{min(prop_votes, opp_votes)}" if ballots else "1-0"

                # Fetch debater lineups
                cur.execute("""
                    SELECT sp.person_id, p.canonical_name, sp.side, sp.position, sp.speech_type,
                           AVG(sp.total_score) as avg_score
                    FROM speech_performances sp
                    JOIN persons p ON sp.person_id = p.id
                    WHERE sp.debate_id = ?
                    GROUP BY sp.person_id, sp.side, sp.position, sp.speech_type
                    ORDER BY sp.side DESC, sp.position ASC
                """, (did,))
                speeches = cur.fetchall()

                prop_lineup = []
                opp_lineup = []
                for sp in speeches:
                    item = {
                        "speaker_name": sp["canonical_name"],
                        "position": sp["position"],
                        "speech_type": sp["speech_type"],
                        "score": round(float(sp["avg_score"]), 2) if sp["avg_score"] else None,
                    }
                    if sp["side"] == "Proposition":
                        prop_lineup.append(item)
                    else:
                        opp_lineup.append(item)

                match_data = {
                    "debate_id": did,
                    "venue": d["venue"] or "Main Chambers",
                    "proposition": {
                        "team_name": d["prop_team_name"],
                        "institution": d["prop_inst_name"],
                        "team_score": avg_prop_score,
                        "lineup": prop_lineup,
                    },
                    "opposition": {
                        "team_name": d["opp_team_name"],
                        "institution": d["opp_inst_name"],
                        "team_score": avg_opp_score,
                        "lineup": opp_lineup,
                    },
                    "result": {
                        "winner_side": winner_side,
                        "winner_team": winner_team,
                        "winner_institution": winner_inst,
                        "decision": decision_split,
                        "margin": avg_margin,
                        "is_unanimous": (min(prop_votes, opp_votes) == 0) if (prop_votes + opp_votes) > 1 else True,
                    },
                    "adjudicators": [b["adjudicator_raw_name"] for b in ballots],
                }
                matchups.append(match_data)

                if stage_label == "Grand Final" and not grand_final_match:
                    grand_final_match = match_data
                elif r_idx == len(round_rows) - 1 and not grand_final_match:
                    grand_final_match = match_data

            stages.append({
                "stage_name": stage_label,
                "round_number": r["round_number"],
                "motion": r["motion"],
                "info_slide": r["info_slide"],
                "matches_count": len(matchups),
                "matchups": matchups,
            })

        # Determine tournament champions
        champion = grand_final_match["result"]["winner_team"] if grand_final_match else None
        champion_inst = grand_final_match["result"]["winner_institution"] if grand_final_match else None
        
        if grand_final_match:
            if grand_final_match["result"]["winner_side"] == "Proposition":
                runner_up = grand_final_match["opposition"]["team_name"]
                runner_up_inst = grand_final_match["opposition"]["institution"]
            else:
                runner_up = grand_final_match["proposition"]["team_name"]
                runner_up_inst = grand_final_match["proposition"]["institution"]
            same_school_final = (champion_inst == runner_up_inst and champion_inst is not None)
        else:
            runner_up = None
            runner_up_inst = None
            same_school_final = False

        return {
            "tournament_name": tourn_name,
            "tournament_slug": tourn_slug,
            "total_elimination_stages": len(stages),
            "champion": {
                "team": champion,
                "institution": champion_inst,
            },
            "runner_up": {
                "team": runner_up,
                "institution": runner_up_inst,
            },
            "is_same_institution_closeout": same_school_final,
            "stages": stages,
        }
