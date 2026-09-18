#!/usr/bin/env python3
"""
Atomos National Circuit Report Generator

Generates comprehensive, multi-dimensional analytics for the Sri Lankan Parliamentary Debating Circuit:
1. Circuit High-Level Overview (Tournaments, Debates, Ballots, Debaters, Schools, Motions)
2. Motion & Side Bias Analytics (Overall balance, Prelims vs Outrounds, Per-Tournament breakdown, Thematic breakdown, Motion Extremes)
3. National Institutional Power Index (IPI) Top Schools
4. National Master Debater Leaderboard (Top Speakers by Official Tab Average)
5. Top Performing Circuit Teams
6. Markdown Export (--export <path>) for automated publication

Usage:
    python scripts/circuit_report.py
    python scripts/circuit_report.py --motions
    python scripts/circuit_report.py --schools
    python scripts/circuit_report.py --debaters
    python scripts/circuit_report.py --tournament slsdc26
    python scripts/circuit_report.py --export circuit_report_2026.md
"""

import argparse
import html
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# Ensure src is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.database.connection import get_connection
from atomos.analytics.motions import MotionAnalytics
from atomos.analytics.institutions import InstitutionAnalytics
from atomos.analytics.master_tabs import MasterTabEngine


def fmt_val(v, max_decimals=5) -> str:
    if v is None:
        return "N/A"
    try:
        f = float(v)
        rounded = round(f, max_decimals)
        s = f"{rounded:.{max_decimals}f}".rstrip('0').rstrip('.')
        return s if s else "0"
    except (ValueError, TypeError):
        return str(v)


def get_circuit_high_level_stats(conn: sqlite3.Connection, tournament_slug: Optional[str] = None) -> dict:
    """Computes high-level counts and totals across the circuit."""
    cur = conn.cursor()

    tourney_filter = ""
    params: list = []
    if tournament_slug:
        tourney_filter = "WHERE t.slug = ?"
        params = [tournament_slug]

    # Tournaments
    cur.execute(f"SELECT COUNT(*) FROM tournaments t {tourney_filter}", params)
    total_tournaments = cur.fetchone()[0]

    # Debates
    deb_sql = """
        SELECT COUNT(DISTINCT d.id)
        FROM debates d
        JOIN rounds r ON d.round_id = r.id
        JOIN tournaments t ON r.tournament_id = t.id
    """
    if tournament_slug:
        deb_sql += " WHERE t.slug = ?"
    cur.execute(deb_sql, params)
    total_debates = cur.fetchone()[0]

    # Ballots / Decisions
    bal_sql = """
        SELECT COUNT(*)
        FROM adjudicator_ballots b
        JOIN debates d ON b.debate_id = d.id
        JOIN rounds r ON d.round_id = r.id
        JOIN tournaments t ON r.tournament_id = t.id
        WHERE d.is_walkover = 0 AND b.winner_side IS NOT NULL
    """
    if tournament_slug:
        bal_sql += " AND t.slug = ?"
    cur.execute(bal_sql, params)
    total_ballots = cur.fetchone()[0]

    # Debaters
    sp_sql = """
        SELECT COUNT(DISTINCT sp.person_id)
        FROM speech_performances sp
        JOIN rounds r ON sp.round_id = r.id
        JOIN tournaments t ON r.tournament_id = t.id
    """
    if tournament_slug:
        sp_sql += " WHERE t.slug = ?"
    cur.execute(sp_sql, params)
    total_debaters = cur.fetchone()[0]

    # Schools
    inst_sql = """
        SELECT COUNT(DISTINCT tm.institution_id)
        FROM teams tm
        JOIN tournaments t ON tm.tournament_id = t.id
        WHERE tm.institution_id IS NOT NULL
    """
    if tournament_slug:
        inst_sql += " AND t.slug = ?"
    cur.execute(inst_sql, params)
    total_schools = cur.fetchone()[0]

    # Motions
    mot_sql = """
        SELECT COUNT(DISTINCT r.motion)
        FROM rounds r
        JOIN tournaments t ON r.tournament_id = t.id
        WHERE r.motion IS NOT NULL AND r.motion != ''
    """
    if tournament_slug:
        mot_sql += " AND t.slug = ?"
    cur.execute(mot_sql, params)
    total_motions = cur.fetchone()[0]

    return {
        "tournaments": total_tournaments,
        "debates": total_debates,
        "ballots": total_ballots,
        "debaters": total_debaters,
        "schools": total_schools,
        "motions": total_motions,
    }


class CircuitReportRenderer:
    """Renders formatted console output or markdown document."""

    def __init__(self, conn: sqlite3.Connection, tournament_slug: Optional[str] = None):
        self.conn = conn
        self.tournament_slug = tournament_slug
        self.motion_analytics = MotionAnalytics(conn)
        self.institution_analytics = InstitutionAnalytics(conn)
        self.master_tab_engine = MasterTabEngine(conn)
        self.md_lines: List[str] = []

    def log(self, text: str = "", md_only: bool = False, console_only: bool = False):
        if not console_only:
            self.md_lines.append(text)
        if not md_only:
            print(text)

    def render_full_report(self, limit: int = 10, sections: Optional[List[str]] = None):
        """Generates the full circuit report."""
        stats = get_circuit_high_level_stats(self.conn, self.tournament_slug)
        t_label = f" ({self.tournament_slug.upper()})" if self.tournament_slug else " (NATIONAL CIRCUIT)"

        term_width = 110
        banner = "=" * term_width
        divider = "-" * term_width

        self.log(banner)
        self.log(f"                   ATOMOS STATE OF THE SRI LANKAN DEBATING CIRCUIT 2026{t_label}")
        self.log("                     Official Analytics, Motion Dynamics & Competitive Standings")
        self.log(banner)

        # Overview Table
        self.log(f"\n* Circuit Vital Statistics:")
        self.log(f"  * Tournaments Tracked : {stats['tournaments']}")
        self.log(f"  * Total Debates       : {stats['debates']:,}")
        self.log(f"  * Total Decisions     : {stats['ballots']:,}")
        self.log(f"  * Active Debaters     : {stats['debaters']:,}")
        self.log(f"  * Debating Schools    : {stats['schools']:,}")
        self.log(f"  * Unique Motions      : {stats['motions']:,}")

        if not sections or "motions" in sections:
            self.render_motion_section(limit)

        if not sections or "schools" in sections:
            self.render_school_section(limit)

        if not sections or "debaters" in sections:
            self.render_debater_section(limit)

        self.log("\n" + banner)
        self.log("                            END OF ATOMOS CIRCUIT INTELLIGENCE REPORT")
        self.log(banner)

    def render_motion_section(self, limit: int = 10):
        divider = "-" * 110
        self.log("\n" + "=" * 110)
        self.log(" SECTION 1: MOTION ANALYTICS & SIDE BIAS ENGINE")
        self.log("=" * 110)

        # 1. Overall Side Balance
        overall = self.motion_analytics.get_overall_side_balance()
        self.log(f"\n[1.1 National Side Balance]")
        self.log(f"  * Total Adjudicator Decisions : {overall['total_decisions']:,}")
        self.log(f"  * Proposition Wins            : {overall['prop_wins']:,} ({overall['prop_win_rate']}%)")
        self.log(f"  * Opposition Wins             : {overall['opp_wins']:,} ({overall['opp_win_rate']}%)")
        self.log(f"  * Adjudicator Ties            : {overall['ties']}")
        self.log(f"  * Dominant Side               : {overall['dominant_side']} (Margin: {overall['bias_margin']}%)")
        self.log(f"  * Circuit Balance Rating      : {overall['bias_classification']}")

        # 2. Prelims vs Outrounds
        round_breakdown = self.motion_analytics.get_round_type_side_balance()
        self.log(f"\n[1.2 Side Balance by Tournament Stage]")
        self.log(f"  {'STAGE':<16} {'DECISIONS':<12} {'PROP WINS':<14} {'OPP WINS':<14} {'DOMINANT':<12} {'STATUS'}")
        self.log(divider)
        for stage in ["PRELIMINARY", "ELIMINATION"]:
            st = round_breakdown.get(stage)
            if st:
                lbl = "Preliminary" if stage == "PRELIMINARY" else "Outrounds"
                prop_str = f"{st['prop_wins']} ({st['prop_win_rate']}%)"
                opp_str = f"{st['opp_wins']} ({st['opp_win_rate']}%)"
                self.log(f"  {lbl:<16} {st['total_decisions']:<12} {prop_str:<14} {opp_str:<14} {st['dominant_side']:<12} {st['bias_classification']}")

        # 3. Per-Tournament Side Bias
        tourneys = self.motion_analytics.get_tournament_side_balance()
        self.log(f"\n[1.3 Tournament Side Bias Breakdown]")
        self.log(f"  {'TOURNAMENT':<30} {'SLUG':<14} {'DECISIONS':<11} {'PROP WIN %':<12} {'OPP WIN %':<12} {'LEAN':<12} {'CLASSIFICATION'}")
        self.log(divider)
        for t in tourneys:
            name_clean = t['tournament_name'].split('|')[0].strip()
            self.log(f"  {name_clean:<30} {t['tournament_slug']:<14} {t['total_decisions']:<11} {fmt_val(t['prop_win_rate']):<12} {fmt_val(t['opp_win_rate']):<12} {t['dominant_side']:<12} {t['bias_classification']}")

        # 4. Thematic Motion Breakdown
        themes = self.motion_analytics.get_thematic_motion_analysis()
        self.log(f"\n[1.4 Thematic Topic Dynamics (Motion Classification)]")
        self.log(f"  {'THEMATIC TOPIC':<36} {'MOTIONS':<9} {'DECISIONS':<11} {'PROP %':<11} {'OPP %':<11} {'AVG SCORE':<12} {'BIAS STATUS'}")
        self.log(divider)
        for th in themes:
            self.log(f"  {th['theme']:<36} {th['motions_count']:<9} {th['decisions_count']:<11} {fmt_val(th['prop_win_rate']):<11} {fmt_val(th['opp_win_rate']):<11} {fmt_val(th['avg_team_score']):<12} {th['bias_classification']}")

        # 5. Motion Extremes
        extremes = self.motion_analytics.get_extreme_motions(min_debates=4)
        self.log(f"\n[1.5 Motion Extremes & Outliers (Min 4 Debates)]")
        
        self.log(f"\n  * Top Proposition-Favored Motions:")
        for idx, m in enumerate(extremes["most_prop_biased"][:3], 1):
            self.log(f"    {idx}. [{m['tournament_slug'].upper()}] Prop {fmt_val(m['prop_win_rate'])}% / Opp {fmt_val(m['opp_win_rate'])}% ({m['debates_count']} debates)")
            self.log(f"       \"{m['motion']}\"")

        self.log(f"\n  * Top Opposition-Favored Motions:")
        for idx, m in enumerate(extremes["most_opp_biased"][:3], 1):
            self.log(f"    {idx}. [{m['tournament_slug'].upper()}] Opp {fmt_val(m['opp_win_rate'])}% / Prop {fmt_val(m['prop_win_rate'])}% ({m['debates_count']} debates)")
            self.log(f"       \"{m['motion']}\"")

        self.log(f"\n  * Most Evenly Balanced Motions (50/50 Split):")
        for idx, m in enumerate(extremes["most_balanced"][:3], 1):
            self.log(f"    {idx}. [{m['tournament_slug'].upper()}] Prop {fmt_val(m['prop_win_rate'])}% / Opp {fmt_val(m['opp_win_rate'])}% ({m['debates_count']} debates)")
            self.log(f"       \"{m['motion']}\"")

        # 6. Scoring Extremes (Difficulty)
        toughest = self.motion_analytics.get_motion_difficulty_ranking(min_debates=4, reverse=False)
        highest = self.motion_analytics.get_motion_difficulty_ranking(min_debates=4, reverse=True)

        self.log(f"\n[1.6 Scoring Difficulty (Team Speech Total per Motion)]")
        if toughest:
            self.log(f"  * Toughest / Lowest-Scoring Motion: Avg {fmt_val(toughest[0]['avg_team_score'])} pts")
            self.log(f"    [{toughest[0]['tournament_slug'].upper()} {toughest[0]['round_name']}] \"{toughest[0]['motion']}\"")
        if highest:
            self.log(f"  * Highest-Scoring Motion: Avg {fmt_val(highest[0]['avg_team_score'])} pts")
            self.log(f"    [{highest[0]['tournament_slug'].upper()} {highest[0]['round_name']}] \"{highest[0]['motion']}\"")

    def render_school_section(self, limit: int = 10):
        divider = "-" * 110
        self.log("\n" + "=" * 110)
        self.log(" SECTION 2: NATIONAL INSTITUTIONAL POWER INDEX (IPI) - TOP SCHOOLS")
        self.log("=" * 110)

        ipi_list = self.institution_analytics.get_institutional_power_index(min_debates=2)
        display_list = ipi_list[:limit]

        header = f"  {'RK':<4} {'SCHOOL / INSTITUTION':<32} {'CODE':<6} {'IPI':<9} {'PEAK ELO':<10} {'AVG ELO':<10} {'RECORD':<12} {'WIN %':<10} {'ELIM W':<8} {'BREAKS'}"
        self.log(header)
        self.log(divider)

        for sc in display_list:
            losses = sc["total_debates"] - sc["wins"]
            rec = f"{sc['wins']}W-{losses}L"
            win_pct_str = f"{fmt_val(sc['win_rate'])}%"
            self.log(f"  #{sc['rank']:<3} {sc['name']:<32} {sc['code']:<6} {fmt_val(sc['ipi']):<9} {fmt_val(sc['squad_peak_elo']):<10} {fmt_val(sc['squad_avg_elo']):<10} {rec:<12} {win_pct_str:<10} {sc['elim_wins']:<8} {sc['breaks_count']}")

    def render_debater_section(self, limit: int = 10):
        divider = "-" * 130
        self.log("\n" + "=" * 130)
        self.log(" SECTION 3: NATIONAL MASTER TAB - TOP DEBATERS")
        self.log("=" * 130)

        speakers = self.master_tab_engine.get_master_speaker_tab(min_tournaments=2)
        display_list = speakers[:limit]

        header = f"  {'RK':<4} {'DEBATER NAME':<26} {'NAT STATUS':<20} {'SCHOOL / INSTITUTION':<26} {'MASTER AVG':<14} {'TOURNAMENTS':<13} {'ROUNDS':<8} {'PEAK SCORE'}"
        self.log(header)
        self.log(divider)

        for sp in display_list:
            nat_str = sp.get("national_level") or "-"
            self.log(f"  #{sp['rank']:<3} {sp['speaker_name']:<26} {nat_str:<20} {sp['institution_name']:<26} {fmt_val(sp['master_score']):<14} {sp['eligible_tournaments']:<13} {sp['total_rounds']:<8} {fmt_val(sp['peak_score']):<12}")

    def export_markdown(self, target_file: Path):
        """Formats collected output into clean GitHub-flavored Markdown and saves."""
        lines = []
        lines.append(f"# Atomos State of the Sri Lankan Debating Circuit 2026")
        lines.append(f"\n> *Comprehensive Intelligence & Analytic Report for Sri Lankan Parliamentary Debating*")
        lines.append(f"\nGenerated by **Atomos Intelligence Engine** | Database: `atomos.db`\n")

        # Convert text buffer into clean markdown formatting
        in_code_block = False
        for l in self.md_lines:
            if l.startswith("=" * 30):
                if in_code_block:
                    lines.append("```\n")
                    in_code_block = False
                continue
            elif l.strip().startswith("SECTION"):
                if in_code_block:
                    lines.append("```\n")
                    in_code_block = False
                lines.append(f"\n## {l.strip()}\n")
            elif re.match(r'^\s*\[\d+\.\d+', l):
                if in_code_block:
                    lines.append("```\n")
                    in_code_block = False
                lines.append(f"\n### {l.strip()}\n")
            elif any(l.strip().startswith(kw) for kw in ["STAGE", "TOURNAMENT", "THEMATIC TOPIC", "RK"]):
                if not in_code_block:
                    lines.append("```text")
                    in_code_block = True
                lines.append(l)
            elif l.startswith("-" * 30):
                lines.append(l)
            elif in_code_block and (l.strip() == "" or l.strip().startswith("*") or l.strip().startswith("END")):
                lines.append("```\n")
                in_code_block = False
                lines.append(l)
            else:
                lines.append(l)

        if in_code_block:
            lines.append("```\n")

        target_file.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n[SUCCESS] Successfully exported circuit report to: {target_file.resolve()}")

    def to_dict(self, limit: int = 15) -> Dict[str, Any]:
        """Returns complete circuit analytics as a structured dictionary for JSON / LLM consumption."""
        return {
            "high_level_stats": get_circuit_high_level_stats(self.conn, self.tournament_slug),
            "motions": {
                "overall_balance": self.motion_analytics.get_overall_side_balance(),
                "stage_balance": self.motion_analytics.get_round_type_side_balance(),
                "thematic_stats": self.motion_analytics.get_thematic_motion_analysis(),
                "motion_extremes": self.motion_analytics.get_extreme_motions(min_debates=4),
                "toughest_motions": self.motion_analytics.get_motion_difficulty_ranking(min_debates=4, reverse=False)[:5],
                "highest_scoring_motions": self.motion_analytics.get_motion_difficulty_ranking(min_debates=4, reverse=True)[:5],
            },
            "institutions": self.institution_analytics.get_institutional_power_index(min_debates=2)[:limit],
            "debaters": self.master_tab_engine.get_master_speaker_tab(min_tournaments=2)[:limit],
        }


def main():
    parser = argparse.ArgumentParser(
        description="Atomos National Circuit Intelligence Report Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--motions", action="store_true", help="Display only Motion Analytics & Side Bias Engine")
    parser.add_argument("--schools", action="store_true", help="Display only Institutional Power Index (IPI) Leaderboard")
    parser.add_argument("--debaters", action="store_true", help="Display only National Master Debater Leaderboard")
    parser.add_argument("--tournament", type=str, default=None, help="Filter analytics for a specific tournament slug")
    parser.add_argument("--top", type=int, default=12, help="Number of entries to display per table (default: 12)")
    parser.add_argument("--export", type=str, default=None, help="Export output as a markdown report file (e.g. report.md)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON for LLM querying")

    args = parser.parse_args()

    conn = get_connection()
    renderer = CircuitReportRenderer(conn, tournament_slug=args.tournament)

    if args.json:
        data = renderer.to_dict(limit=args.top)
        if args.motions:
            data = {"high_level_stats": data["high_level_stats"], "motions": data["motions"]}
        elif args.schools:
            data = {"institutions": data["institutions"]}
        elif args.debaters:
            data = {"debaters": data["debaters"]}
        print(json.dumps(data, indent=2))
        conn.close()
        return

    sections = []
    if args.motions:
        sections.append("motions")
    if args.schools:
        sections.append("schools")
    if args.debaters:
        sections.append("debaters")

    # Render report
    renderer.render_full_report(limit=args.top, sections=sections if sections else None)

    # Export if requested
    if args.export:
        renderer.export_markdown(Path(args.export))

    conn.close()


if __name__ == "__main__":
    main()
