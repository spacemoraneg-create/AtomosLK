"""
Atomos Tournament Rankings Analytics Engine

Ranks circuit tournaments by Average Participating Team Total Speaker Score (APTTSS),
and provides comprehensive metrics:
- APTTSS across contested prelim rounds
- APTTSS of breaking teams
- Participating teams count
- Prelim rounds count
- Break structure
- Substantive speeches count
- Total debates count
- Official dates from Debaters Council circuit calendar
"""

import sqlite3
from typing import Any, Dict, List, Optional


OFFICIAL_TOURNAMENT_DATES = {
    1: "June 5–8, 2026",        # Vijis '26
    2: "Jan 2–5, 2026",         # AISDC 2026
    3: "July 17–20, 2026",      # APIIT ISDC 2026
    4: "Aug 22–31, 2026",       # SLSDC 2026
    7: "March 13–16, 2026",     # VVIDC 2026
    10: "June 19–22, 2026",     # Metho 2026
    16: "July 3–6, 2026",       # RIC ISDC 2026
    18: "July 31 – Aug 3, 2026", # Chap's '26
    44: "Sept 18–21, 2026",     # Nixon's 2026
    45: "Oct 2–3, 2026",        # Stanley's '26
    46: "Oct 16–18, 2026",      # Henley 2026
}

CHRONOLOGICAL_TOURNAMENT_ORDER = {
    2: 1,   # AISDC 2026 (Jan 2–5)
    7: 2,   # VVIDC 2026 (March 13–16)
    1: 3,   # Vijis '26 (June 5–8)
    10: 4,  # Metho 2026 (June 19–22)
    16: 5,  # RIC ISDC 2026 (July 3–6)
    3: 6,   # APIIT ISDC 2026 (July 17–20)
    18: 7,  # Chap's '26 (July 31–Aug 3)
    4: 8,   # SLSDC 2026 (Aug 22–31)
    44: 9,  # Nixon's 2026 (Sept 18–21)
    45: 10, # Stanley's '26 (Oct 2–3)
    46: 11, # Henley 2026 (Oct 16–18)
}

CLEAN_TOURNAMENT_NAMES = {
    1: "Vijitha Weerasinghe Memorial (Vijis '26)",
    2: "AIS Debating Championship (AISDC 2026)",
    3: "APIIT ISDC 2026",
    4: "Sri Lanka Schools Debating Championship (SLSDC 2026)",
    7: "Visakha Vidyalaya Championship (VVIDC 2026)",
    10: "Shanthi Peiris Memorial (Metho 2026)",
    16: "RIC ISDC 2026",
    18: "Frances Chapman Memorial (Chap's '26)",
    44: "Lillian Nixon's Memorial (Nixon's 2026)",
    45: "Stanley Abeysekera Memorial (Stanley's '26)",
    46: "Henley Debating Championship (Henley 2026)",
}


def get_clean_tournament_name(tid: int, raw_name: Optional[str] = None) -> str:
    """Return clean tournament name from registry or strip Tabbycat '| Welcome to' boilerplate."""
    if tid in CLEAN_TOURNAMENT_NAMES:
        return CLEAN_TOURNAMENT_NAMES[tid]
    if not raw_name:
        return f"Tournament #{tid}"
    if "|" in raw_name:
        parts = [p.strip() for p in raw_name.split("|", 1)]
        short, welcome = parts[0], parts[1]
        for prefix in ("Welcome to ", "welcome to "):
            if welcome.startswith(prefix):
                welcome = welcome[len(prefix):].strip()
        if welcome and short and short.lower() not in welcome.lower():
            return f"{welcome} ({short})"
        return welcome or short
    return raw_name.strip()



def truncate_3(val: Optional[float]) -> Optional[float]:
    """Universal Rule: Do not round up. Up to 3 decimal places if exist."""
    if val is None:
        return None
    try:
        f = float(val)
        if f.is_integer():
            return int(f)
        s = f"{f:.8f}"
        parts = s.split(".")
        truncated = parts[0] + "." + parts[1][:3].rstrip("0")
        if truncated.endswith("."):
            return int(parts[0])
        return float(truncated)
    except Exception:
        return val


class TournamentRankingsEngine:
    """Computes tournament quality and participation rankings based on APTTSS."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_tournament_rankings(self) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()

        # Query all active tournaments with contested rounds
        cur.execute("""
            SELECT t.id, t.slug, t.name, t.hosting_dates
            FROM tournaments t
            JOIN rounds r ON t.id = r.tournament_id
            JOIN debates d ON r.id = d.round_id
            GROUP BY t.id
            HAVING COUNT(d.id) > 0
            ORDER BY t.id ASC
        """)
        tours = cur.fetchall()

        rankings: List[Dict[str, Any]] = []

        for row in tours:
            tid = row[0]
            slug = row[1]
            full_name = row[2]

            # 1. Total debates & prelim debates
            cur.execute("""
                SELECT COUNT(d.id)
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                WHERE r.tournament_id = ?
            """, (tid,))
            total_debates = cur.fetchone()[0]

            # 2. Distinct participating teams
            cur.execute("""
                SELECT COUNT(DISTINCT sp.team_id)
                FROM speech_performances sp
                JOIN rounds r ON sp.round_id = r.id
                WHERE r.tournament_id = ? AND sp.total_score > 0
            """, (tid,))
            teams_participated = cur.fetchone()[0]

            # 3. Prelim rounds count
            cur.execute("""
                SELECT COUNT(DISTINCT r.id)
                FROM rounds r
                WHERE r.tournament_id = ? AND r.round_type = 'PRELIMINARY'
            """, (tid,))
            prelim_rounds = cur.fetchone()[0]

            # 4. Total substantive speeches
            cur.execute("""
                SELECT COUNT(sp.id)
                FROM speech_performances sp
                JOIN rounds r ON sp.round_id = r.id
                WHERE r.tournament_id = ? AND sp.speech_type = 'SUBSTANTIVE' AND sp.total_score > 0
            """, (tid,))
            total_speeches = cur.fetchone()[0]

            # 5. Identify breaking teams from elimination round debates
            cur.execute("""
                SELECT DISTINCT d.prop_team_id, d.opp_team_id
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                WHERE r.tournament_id = ? AND r.round_type != 'PRELIMINARY'
            """, (tid,))
            breaking_team_ids = set()
            for prop, opp in cur.fetchall():
                if prop: breaking_team_ids.add(prop)
                if opp: breaking_team_ids.add(opp)

            # Determine break structure name
            cur.execute("""
                SELECT r.round_number, r.name
                FROM rounds r
                WHERE r.tournament_id = ? AND r.round_type != 'PRELIMINARY'
                ORDER BY r.round_number ASC
                LIMIT 1
            """, (tid,))
            first_elim = cur.fetchone()
            if first_elim:
                rname = (first_elim[1] or "").lower()
                if "partial" in rname or len(breaking_team_ids) == 12:
                    break_structure = "Partial Octos (Top 12)"
                elif "octo" in rname or len(breaking_team_ids) >= 16:
                    break_structure = "Octofinals (Top 16)"
                elif "quarter" in rname or len(breaking_team_ids) == 8:
                    break_structure = "Quarterfinals (Top 8)"
                elif len(breaking_team_ids) <= 4:
                    break_structure = "Semifinals (Top 4)"
                else:
                    break_structure = f"Top {len(breaking_team_ids)}"
            else:
                break_structure = "No Breaks"

            # 6. Refined APTTSS (Average Participating Team Total Speaker Score):
            # Rather than pooling raw debate ballots/speeches directly (which distorts averages
            # when panel sizes vary), we pool the end ATSS of teams from the tournament and divide
            # by the number of teams.
            # Team round scores are averaged across ballots for each debate, then averaged per team
            # to give the team's tournament ATSS.
            cur.execute("""
                SELECT d.id, pt.id, ot.id,
                       AVG(CASE WHEN b.prop_total_score > 0 THEN b.prop_total_score END) as p_score,
                       AVG(CASE WHEN b.opp_total_score > 0 THEN b.opp_total_score END) as o_score
                FROM debates d
                JOIN rounds r ON d.round_id = r.id
                JOIN teams pt ON d.prop_team_id = pt.id
                JOIN teams ot ON d.opp_team_id = ot.id
                LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
                WHERE r.tournament_id = ?
                  AND r.round_type = 'PRELIMINARY'
                  AND d.is_walkover = 0
                GROUP BY d.id
            """, (tid,))
            debate_rows = cur.fetchall()

            team_debate_scores: Dict[int, List[float]] = {}
            for did, pt_id, ot_id, p_score, o_score in debate_rows:
                if p_score is not None and p_score > 0:
                    team_debate_scores.setdefault(pt_id, []).append(float(p_score))
                if o_score is not None and o_score > 0:
                    team_debate_scores.setdefault(ot_id, []).append(float(o_score))

            # End ATSS per team for this tournament
            team_atss: Dict[int, float] = {}
            for team_id, scores in team_debate_scores.items():
                if scores:
                    team_atss[team_id] = sum(scores) / len(scores)

            all_team_atss = list(team_atss.values())
            apttss = truncate_3(sum(all_team_atss) / len(all_team_atss)) if all_team_atss else 0.0

            # APTTSS of breaking teams only
            breaking_atss = [team_atss[t_id] for t_id in breaking_team_ids if t_id in team_atss]
            apttss_breaking = truncate_3(sum(breaking_atss) / len(breaking_atss)) if breaking_atss else 0.0

            rankings.append({
                "tournament_id": tid,
                "tournament_slug": slug,
                "tournament_name": get_clean_tournament_name(tid, full_name),
                "dates": (row[3] if len(row) > 3 and row[3] else None) or OFFICIAL_TOURNAMENT_DATES.get(tid, "TBD"),
                "apttss": apttss,
                "apttss_breaking": apttss_breaking,
                "teams_participated": teams_participated,
                "prelim_rounds": prelim_rounds,
                "break_structure": break_structure,
                "speeches_count": total_speeches,
                "debates_count": total_debates,
                "breaking_teams_count": len(breaking_team_ids)
            })

        # Rank tournaments strictly by APTTSS descending
        rankings.sort(key=lambda x: x["apttss"], reverse=True)
        for idx, item in enumerate(rankings):
            item["rank"] = idx + 1

        return rankings
