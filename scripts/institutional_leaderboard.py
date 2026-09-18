#!/usr/bin/env python3
"""
Atomos National Institutional Power Index (IPI) Leaderboard & School Dossier CLI

Features:
1. National School Leaderboard: Top 25 Debating Schools ranked by Institutional Power Index (IPI)
2. Detailed Institutional Dossier: Squad depth, top debaters, campaigns, and school rivalries
3. School Head-to-Head Clash: Side-by-side comparison and direct match history between any two institutions

Usage:
    python scripts/institutional_leaderboard.py
    python scripts/institutional_leaderboard.py --top 30
    python scripts/institutional_leaderboard.py --school "Royal College"
    python scripts/institutional_leaderboard.py --school "DS"
    python scripts/institutional_leaderboard.py --compare "Royal College" "D. S. Senanayake College"
"""

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Optional, List

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.database.connection import get_connection
from atomos.analytics.institutions import (
    InstitutionAnalytics,
    InstitutionProfile,
    InstitutionHeadToHead,
    InstitutionRivalryRecord,
    TournamentCampaign,
    TopDebater,
)


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


def format_margin(margin: Optional[float]) -> str:
    if margin is None:
        return "  -  "
    val_str = fmt_val(abs(margin))
    if margin > 0:
        return f"+{val_str}"
    elif margin < 0:
        return f"-{val_str}"
    return "0"


def render_leaderboard(analytics: InstitutionAnalytics, top_n: int = 25):
    ipi_list = analytics.get_institutional_power_index(min_debates=2)
    display_list = ipi_list[:top_n]

    term_width = 120
    banner = "=" * term_width
    divider = "-" * term_width
    sub_div = "." * term_width

    print("\n" + banner)
    print("                 ATOMOS NATIONAL INSTITUTIONAL POWER INDEX (IPI) LEADERBOARD")
    print("                    Top Ranked Debating Institutions in Sri Lanka Circuit")
    print(banner)

    header = f"  {'RK':<3} {'SCHOOL / INSTITUTION':<32} {'CODE':<5} {'IPI':<8} {'ELO':<8} {'RECORD':<12} {'WIN %':<10} {'OUTROUNDS':<11} {'BREAKS':<8} {'ATSS':<10} {'DEPTH'}"
    print(header)
    print(divider)

    for r in display_list:
        rank_str = f"#{r['rank']}"
        name_str = r['name'][:30]
        code_str = r['code'] or "-"
        ipi_str = fmt_val(r['ipi'])
        elo_str = fmt_val(r['squad_peak_elo'])
        rec_str = f"{r['wins']}-{r['total_debates'] - r['wins']}"
        win_str = f"{fmt_val(r['win_rate'])}%"
        elim_str = f"{r['elim_wins']}/{r['elim_debates']}" if r['elim_debates'] > 0 else "0/0"
        brk_str = f"{r['breaks_count']} brk"
        atss_str = fmt_val(r['atss']) if r['atss'] else " - "
        depth_str = f"{r['debater_count']} deb / {r['teams_fielded']} tm"

        print(f"  {rank_str:<3} {name_str:<32} {code_str:<5} {ipi_str:<8} {elo_str:<8} {rec_str:<12} {win_str:<10} {elim_str:<11} {brk_str:<8} {atss_str:<10} {depth_str}")

    print(banner)
    total_active = len(ipi_list)
    total_debates = sum(r['total_debates'] for r in ipi_list) // 2
    print(f"  Circuit Coverage: {total_active} active institutions ranked across {total_debates} contested debate rounds.")
    print(f"  IPI Weights: Top Squad Elo (35%) | Win Rate (30%) | Outround Success (20%) | Squad Depth (15%)")
    print(banner + "\n")


def render_school_dossier(prof: InstitutionProfile):
    term_width = 110
    banner = "=" * term_width
    divider = "-" * term_width
    sub_div = "." * term_width

    print("\n" + banner)
    print(f"                      ATOMOS INSTITUTIONAL DOSSIER: {prof.name.upper()}")
    print(banner)
    code_str = f"({prof.code})" if prof.code else ""
    rank_str = f"#{prof.ipi_rank} in Sri Lanka" if prof.ipi_rank else "Unranked"
    ipi_val = f"{fmt_val(prof.ipi_score)} / 100.0" if prof.ipi_score is not None else "N/A"
    print(f"  Institution:          {prof.name} {code_str} (ID: #{prof.institution_id})")
    print(f"  National Standing:    {rank_str} (IPI: {ipi_val}) — [{prof.tier}]")
    print(f"  Squad Strength:       Peak Team Elo: {fmt_val(prof.squad_peak_elo)} | Top Squad Avg Elo: {fmt_val(prof.squad_avg_elo)}")
    if prof.atss:
        print(f"  Team Speaker Score:   {fmt_val(prof.atss)} pts (Average Team Speaker Score across prelims)")
    print(divider)

    # Career & Outround Record
    print("  CAREER & ELIMINATION RECORD")
    print(divider)
    print(f"  Total Contested Debates:   {prof.total_debates} debates ({prof.wins} wins - {prof.losses} losses, {fmt_val(prof.win_rate)}% win rate)")
    print(f"  Proposition Performance:   {prof.prop_wins}/{prof.prop_debates} ({fmt_val(prof.prop_win_pct)}% win rate)")
    print(f"  Opposition Performance:    {prof.opp_wins}/{prof.opp_debates} ({fmt_val(prof.opp_win_pct)}% win rate)")
    print(f"  Knockout Elimination:      {prof.elim_wins}/{prof.elim_debates} ({fmt_val(prof.elim_win_pct)}% outround win rate)")
    brk_detail = f"{prof.total_breaks} team breaks across {prof.tournaments_entered} tournaments ({fmt_val(prof.break_rate)}% tournament break rate)"
    print(f"  Championship Breaks:       {brk_detail}")
    print(divider)

    # Squad Depth & Bench Strength
    print(f"  SQUAD DEPTH & BENCH STRENGTH ({prof.debater_count} Active Debaters Fielded)")
    print(divider)
    teams_str = ", ".join(prof.teams_fielded) if prof.teams_fielded else "None"
    print(f"  Teams Fielded:  {teams_str}")
    
    if prof.top_debaters:
        print(f"\n  Top Ranked Debaters Representing {prof.name}:")
        print(f"    {'NATL RK':<8} {'DEBATER NAME':<28} {'MASTER AVG':<14} {'TOURNAMENTS':<14} {'ROUNDS'}")
        print("    " + "." * 72)
        for deb in prof.top_debaters[:8]:
            rk_s = f"#{deb.national_rank}" if deb.national_rank else "Unranked"
            score_s = f"{fmt_val(deb.master_score)} pts" if deb.master_score else "N/A"
            tour_s = f"{deb.eligible_tournaments} eligible"
            print(f"    {rk_s:<8} {deb.name:<28} {score_s:<14} {tour_s:<14} {deb.total_rounds} rds")
    print(divider)

    # Tournament Campaigns
    if prof.campaigns:
        print(f"  TOURNAMENT CAMPAIGN HISTORY ({len(prof.campaigns)} Tournaments Contested)")
        print(divider)
        print(f"  {'TOURNAMENT':<16} {'TEAMS ENTERED':<22} {'DEBATE RECORD':<16} {'WIN %':<10} {'BREAK STATUS'}")
        print(sub_div)
        for c in prof.campaigns:
            t_str = c.tournament_slug[:14]
            tms_str = ", ".join(c.teams_entered)[:20]
            rec_str = f"{c.wins}-{c.losses} ({c.debates} rds)"
            pct_str = f"{fmt_val(c.win_pct)}%"
            if c.broke_to_knockouts:
                brk_str = f"🏆 Broke ({', '.join(c.breaking_teams)})"
            else:
                brk_str = "Did not break"
            print(f"  {t_str:<16} {tms_str:<22} {rec_str:<16} {pct_str:<10} {brk_str}")
        print(divider)

    # School Rivalries
    if prof.rivalries:
        print(f"  HISTORIC SCHOOL RIVALRIES (Top Opponents by Debates Contested)")
        print(divider)
        print(f"  {'OPPOSING SCHOOL':<32} {'CODE':<6} {'DEBATES':<9} {'RECORD (W-L)':<14} {'WIN %':<10} {'NET MARGIN'}")
        print(sub_div)
        for riv in prof.rivalries[:10]:
            opp_name = riv.opponent_name[:30]
            opp_c = riv.opponent_code or "-"
            rec_s = f"{riv.wins}-{riv.losses}"
            pct_s = f"{fmt_val(riv.win_pct)}%"
            mar_s = format_margin(riv.avg_margin)
            print(f"  {opp_name:<32} {opp_c:<6} {riv.debates:<9} {rec_s:<14} {pct_s:<10} {mar_s}")
    print(banner + "\n")


def render_school_comparison(cmp: InstitutionHeadToHead):
    term_width = 110
    banner = "=" * term_width
    divider = "-" * term_width
    sub_div = "." * term_width

    sa: InstitutionProfile = cmp.inst_a
    sb: InstitutionProfile = cmp.inst_b

    print("\n" + banner)
    print("               ATOMOS INSTITUTIONAL HEAD-TO-HEAD CLASH")
    print(banner)

    # Side by side overview
    print(f"  {'METRIC':<30} | {sa.name[:36]:<36} | {sb.name[:36]:<36}")
    print(divider)
    print(f"  {'Institution Code / ID':<30} | {sa.code or 'None':<15} (#{sa.institution_id:<3}) | {sb.code or 'None':<15} (#{sb.institution_id:<3})")
    
    ipi_a = f"#{sa.ipi_rank} ({fmt_val(sa.ipi_score)})" if sa.ipi_rank else "Unranked"
    ipi_b = f"#{sb.ipi_rank} ({fmt_val(sb.ipi_score)})" if sb.ipi_rank else "Unranked"
    print(f"  {'National IPI Rank (Score)':<30} | {ipi_a:<36} | {ipi_b:<36}")
    print(f"  {'Program Tier':<30} | {sa.tier:<36} | {sb.tier:<36}")

    rec_a = f"{sa.wins}-{sa.losses} ({fmt_val(sa.win_rate)}%)"
    rec_b = f"{sb.wins}-{sb.losses} ({fmt_val(sb.win_rate)}%)"
    print(f"  {'Career Record (Win %)':<30} | {rec_a:<36} | {rec_b:<36}")

    elim_a = f"{sa.elim_wins}/{sa.elim_debates} ({fmt_val(sa.elim_win_pct)}%)" if sa.elim_debates > 0 else "0/0"
    elim_b = f"{sb.elim_wins}/{sb.elim_debates} ({fmt_val(sb.elim_win_pct)}%)" if sb.elim_debates > 0 else "0/0"
    print(f"  {'Knockout Outround Record':<30} | {elim_a:<36} | {elim_b:<36}")

    brk_a = f"{sa.total_breaks} brk / {sa.tournaments_entered} tours ({fmt_val(sa.break_rate)}%)"
    brk_b = f"{sb.total_breaks} brk / {sb.tournaments_entered} tours ({fmt_val(sb.break_rate)}%)"
    print(f"  {'Championship Break Rate':<30} | {brk_a:<36} | {brk_b:<36}")

    atss_a = f"{fmt_val(sa.atss)} pts" if sa.atss else "N/A"
    atss_b = f"{fmt_val(sb.atss)} pts" if sb.atss else "N/A"
    print(f"  {'Team Speaker Avg (ATSS)':<30} | {atss_a:<36} | {atss_b:<36}")

    depth_a = f"{sa.debater_count} debaters ({len(sa.teams_fielded)} teams)"
    depth_b = f"{sb.debater_count} debaters ({len(sb.teams_fielded)} teams)"
    print(f"  {'Squad Depth':<30} | {depth_a:<36} | {depth_b:<36}")
    print(banner)

    # Direct Clashes
    total_clashes = len(cmp.direct_debates)
    print("\n" + divider)
    print(f"  DIRECT SCHOOL CLASHES ({total_clashes} Encounters Between Teams)")
    print(divider)

    if total_clashes == 0:
        print("  [INFO] No direct debate encounters recorded between these two institutions.")
    else:
        rec_str = f"{sa.name} {cmp.a_direct_wins} - {cmp.b_direct_wins} {sb.name}"
        print(f"  Direct Institutional Record:  {rec_str}")
        avg_a_str = format_margin(cmp.a_direct_margin_avg)
        avg_b_str = format_margin(cmp.b_direct_margin_avg)
        print(f"  Direct Net Margin Avg:        {sa.name.split()[0]}: {avg_a_str} pts | {sb.name.split()[0]}: {avg_b_str} pts")
        print(sub_div)

        header = f"  {'Tournament':<14} {'Round':<10} {'Type':<8} {'Team A':<14} {'Team B':<14} {'Ballots':<8} {'Margin':<8} {'Winner'}"
        print(header)
        print(sub_div)
        for m in cmp.direct_debates:
            win_flag = f"🏆 {m.winner_school_name}" if m.winner_school_name else "Draw"
            mar_s = format_margin(m.margin_a)
            print(f"  {m.tournament_slug:<14} {m.round_name:<10} {m.round_type[:4]:<8} {m.team_a_name:<14} {m.team_b_name:<14} {m.ballot_split:<8} {mar_s:<8} {win_flag}")
        print(divider)

    # Mutual Rival Schools
    if cmp.common_rivals:
        print("\n" + divider)
        print(f"  MUTUAL RIVAL SCHOOL COMPARISON ({len(cmp.common_rivals)} Common Opponents)")
        print(divider)
        name_a_short = sa.name.split()[0]
        name_b_short = sb.name.split()[0]
        h_line = f"  {'Opponent School':<28} | {name_a_short+' (W/L)':<12} {name_a_short+' (%)':<12} {'Margin':<8} | {name_b_short+' (W/L)':<12} {name_b_short+' (%)':<12} {'Margin'}"
        print(h_line)
        print(sub_div)
        for cr in cmp.common_rivals[:12]:
            opp_n = cr["opponent_name"][:26]
            rec_a = f"{cr['a_wins']}-{cr['a_debates'] - cr['a_wins']} ({cr['a_debates']})"
            pct_a = f"{fmt_val(cr['a_win_pct'])}%"
            mar_a = format_margin(cr['a_avg_margin'])

            rec_b = f"{cr['b_wins']}-{cr['b_debates'] - cr['b_wins']} ({cr['b_debates']})"
            pct_b = f"{fmt_val(cr['b_win_pct'])}%"
            mar_b = format_margin(cr['b_avg_margin'])

            print(f"  {opp_n:<28} | {rec_a:<12} {pct_a:<12} {mar_a:<8} | {rec_b:<12} {pct_b:<12} {mar_b}")
        print(banner + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Atomos National Institutional Power Index & School Leaderboard CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("schools", nargs="*", help="Optional: 1 school for dossier, or 2 schools to compare head-to-head")
    parser.add_argument("--top", type=int, default=25, help="Number of schools to display on leaderboard (default: 25)")
    parser.add_argument("-s", "--school", help="View comprehensive institutional dossier for a specific school")
    parser.add_argument("-c", "--compare", nargs=2, metavar=("SCHOOL_A", "SCHOOL_B"), help="Compare two schools head-to-head")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON for LLM querying")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive institutional menu")

    args = parser.parse_args()
    conn = get_connection()
    analytics = InstitutionAnalytics(conn)

    # 1. Positional arguments handling
    if len(args.schools) >= 2:
        args.compare = [args.schools[0], args.schools[1]]
    elif len(args.schools) == 1 and not args.school:
        args.school = args.schools[0]

    # 2. School Dossier Mode
    if args.school:
        prof = analytics.get_institution_profile(args.school)
        if not prof:
            if args.json:
                print(json.dumps({"error": f"Could not find any institution matching '{args.school}'"}))
            else:
                print(f"[ERROR] Could not find any institution matching '{args.school}'.")
            sys.exit(1)
        if args.json:
            print(json.dumps(dataclasses.asdict(prof), indent=2))
        else:
            render_school_dossier(prof)
        return

    # 3. School Comparison Mode
    if args.compare:
        sa_str, sb_str = args.compare
        pa = analytics.get_institution_profile(sa_str)
        pb = analytics.get_institution_profile(sb_str)
        if not pa:
            if args.json:
                print(json.dumps({"error": f"Could not find institution '{sa_str}'"}))
            else:
                print(f"[ERROR] Could not find institution '{sa_str}'.")
            sys.exit(1)
        if not pb:
            if args.json:
                print(json.dumps({"error": f"Could not find institution '{sb_str}'"}))
            else:
                print(f"[ERROR] Could not find institution '{sb_str}'.")
            sys.exit(1)
        cmp_res = analytics.compare_institutions(pa.institution_id, pb.institution_id)
        if args.json:
            print(json.dumps(dataclasses.asdict(cmp_res), indent=2))
        else:
            render_school_comparison(cmp_res)
        return

    # 3. Interactive Mode
    if args.interactive:
        print("=" * 60)
        print("          ATOMOS INSTITUTIONAL ANALYTICS")
        print("=" * 60)
        print("1. View National Institutional Leaderboard")
        print("2. View Specific School Dossier")
        print("3. Compare Two Schools Head-to-Head")
        choice = input("Select option [1-3, default 1]: ").strip()

        if choice == "2":
            q = input("Enter School Name or Code: ").strip()
            if not q:
                sys.exit(0)
            prof = analytics.get_institution_profile(q)
            if not prof:
                print(f"[ERROR] No institution found matching '{q}'.")
                sys.exit(1)
            render_school_dossier(prof)
        elif choice == "3":
            sa_q = input("Enter School 1 (Name or Code): ").strip()
            sb_q = input("Enter School 2 (Name or Code): ").strip()
            if not sa_q or not sb_q:
                sys.exit(0)
            pa = analytics.get_institution_profile(sa_q)
            pb = analytics.get_institution_profile(sb_q)
            if not pa or not pb:
                print("[ERROR] One or both institutions could not be found.")
                sys.exit(1)
            cmp = analytics.compare_institutions(pa.institution_id, pb.institution_id)
            if cmp is not None:
                render_school_comparison(cmp)
            else:
                print(f"[ERROR] Could not compare '{pa.name}' and '{pb.name}'.")
        else:
            render_leaderboard(analytics, top_n=args.top)
        return

    # 4. Default: National Leaderboard
    if args.json:
        ipi_list = analytics.get_institutional_power_index(min_debates=2)
        print(json.dumps(ipi_list[:args.top], indent=2))
    else:
        render_leaderboard(analytics, top_n=args.top)


if __name__ == "__main__":
    main()
