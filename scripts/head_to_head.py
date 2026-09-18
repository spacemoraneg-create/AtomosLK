#!/usr/bin/env python3
"""
Atomos Head-to-Head Debater & Team Comparison CLI

Compares any two debaters or teams side-by-side:
1. Career performance & official standings comparison
2. Direct face-to-face clash history (tournament, round, side, ballots, margin, speaker scores)
3. Mutual common opponents analysis (head-to-head records against mutual rivals)

Usage:
    python scripts/head_to_head.py "Vidath Marasinghe" "Kaveesha De Silva"
    python scripts/head_to_head.py --team "DS A" "RC A"
    python scripts/head_to_head.py
"""

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Optional, Tuple

# Add src and scripts to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from atomos.database.connection import get_connection
from atomos.analytics.head_to_head import (
    HeadToHeadEngine,
    DebaterHeadToHead,
    TeamHeadToHead,
    DirectDebateMatchup,
    CommonOpponentRecord,
)
from atomos.analytics.debater_profile import DebaterProfile


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


def render_debater_comparison(h2h: DebaterHeadToHead):
    term_width = 110
    banner = "=" * term_width
    divider = "-" * term_width
    sub_div = "." * term_width

    a: DebaterProfile = h2h.debater_a
    b: DebaterProfile = h2h.debater_b

    print("\n" + banner)
    print("                    ATOMOS HEAD-TO-HEAD DEBATER COMPARISON")
    print(banner)

    # Header profiles side-by-side
    print(f"  {'METRIC':<30} | {a.canonical_name[:36]:<36} | {b.canonical_name[:36]:<36}")
    print(divider)
    print(f"  {'Person ID':<30} | #{a.person_id:<35} | #{b.person_id:<35}")
    print(f"  {'Institution / School':<30} | {a.institution[:36]:<36} | {b.institution[:36]:<36}")
    
    mt_a = f"#{a.master_tab_rank} ({fmt_val(a.overall_substantive_avg)})" if a.master_tab_rank else "Unranked"
    mt_b = f"#{b.master_tab_rank} ({fmt_val(b.overall_substantive_avg)})" if b.master_tab_rank else "Unranked"
    print(f"  {'Master Tab Rank (Avg)':<30} | {mt_a:<36} | {mt_b:<36}")

    cs_a = f"#{a.critical_stats_rank} (Top Debater)" if a.critical_stats_rank else f"Unranked ({a.eligible_tournaments_count}/3 tours)"
    cs_b = f"#{b.critical_stats_rank} (Top Debater)" if b.critical_stats_rank else f"Unranked ({b.eligible_tournaments_count}/3 tours)"
    print(f"  {'Critical Stats Rank':<30} | {cs_a:<36} | {cs_b:<36}")

    win_a = f"{fmt_val(a.win_rate)}% ({a.wins_debated}/{a.total_debates})"
    win_b = f"{fmt_val(b.win_rate)}% ({b.wins_debated}/{b.total_debates})"
    print(f"  {'Win Rate (Debates)':<30} | {win_a:<36} | {win_b:<36}")

    brk_a = f"{fmt_val(a.break_rate)}% ({a.eligible_tournaments_count} tours)" if a.eligible_tournaments_count else "N/A"
    brk_b = f"{fmt_val(b.break_rate)}% ({b.eligible_tournaments_count} tours)" if b.eligible_tournaments_count else "N/A"
    print(f"  {'Break Rate':<30} | {brk_a:<36} | {brk_b:<36}")

    print(f"  {'Prelim Speeches':<30} | {a.prelim_rounds_debated:<36} | {b.prelim_rounds_debated:<36}")

    dev_a = f"{fmt_val(a.avg_of_deviations)} pts" if a.avg_of_deviations is not None else "N/A"
    dev_b = f"{fmt_val(b.avg_of_deviations)} pts" if b.avg_of_deviations is not None else "N/A"
    print(f"  {'Consistency (σ dev)':<30} | {dev_a:<36} | {dev_b:<36}")

    rep_a = f"{fmt_val(a.reply_average)} ({a.reply_speech_count} sp)" if a.reply_speech_count > 0 else "None"
    rep_b = f"{fmt_val(b.reply_average)} ({b.reply_speech_count} sp)" if b.reply_speech_count > 0 else "None"
    print(f"  {'Reply Tab (Score / Cnt)':<30} | {rep_a:<36} | {rep_b:<36}")
    print(banner)

    # 1. Direct encounters
    total_direct = len(h2h.direct_debates)
    print("\n" + divider)
    print(f"  DIRECT HEAD-TO-HEAD MATCHUPS ({total_direct} Recorded Clash{'es' if total_direct != 1 else ''})")
    print(divider)

    if total_direct == 0:
        print("  [INFO] No direct face-to-face encounters recorded between these two debaters in the database.")
    else:
        rec_str = f"{a.canonical_name} {h2h.a_direct_wins} - {h2h.b_direct_wins} {b.canonical_name}"
        print(f"  Direct Record:           {rec_str}")
        avg_a_str = fmt_val(h2h.a_direct_sub_avg) if h2h.a_direct_sub_avg is not None else "N/A"
        avg_b_str = fmt_val(h2h.b_direct_sub_avg) if h2h.b_direct_sub_avg is not None else "N/A"
        if h2h.a_direct_sub_avg is not None and h2h.b_direct_sub_avg is not None:
            diff = h2h.a_direct_sub_avg - h2h.b_direct_sub_avg
            sign = "+" if diff > 0 else ("-" if diff < 0 else "")
            diff_str = f" ({sign}{fmt_val(abs(diff))} diff for {a.canonical_name.split()[0]})"
        else:
            diff_str = ""
        print(f"  Direct Speaker Sub Avg:  {a.canonical_name.split()[0]}: {avg_a_str} pts | {b.canonical_name.split()[0]}: {avg_b_str} pts{diff_str}")
        print(sub_div)
        
        # Table of encounters
        header = f"  {'Tournament':<14} {'Round':<10} {'Type':<8} {'Side A':<6} {'Side B':<6} {'Result':<10} {a.canonical_name[:14]:<16} {b.canonical_name[:14]:<16} {'Winner'}"
        print(header)
        print(sub_div)
        for m in h2h.direct_debates:
            side_a_short = "Prop" if m.side_a == "Proposition" else "Opp"
            side_b_short = "Prop" if m.side_b == "Proposition" else "Opp"
            res_str = m.ballot_split if m.is_walkover else f"{m.ballot_split} ({format_margin(m.margin_a).strip()})"
            
            # Debater A score
            if m.sub_score_a is not None:
                sp_a_str = f"{m.pos_a} {fmt_val(m.sub_score_a)}"
                if m.rep_score_a is not None:
                    sp_a_str += f"+{fmt_val(m.rep_score_a)}R"
            else:
                sp_a_str = "No Speech"

            # Debater B score
            if m.sub_score_b is not None:
                sp_b_str = f"{m.pos_b} {fmt_val(m.sub_score_b)}"
                if m.rep_score_b is not None:
                    sp_b_str += f"+{fmt_val(m.rep_score_b)}R"
            else:
                sp_b_str = "No Speech"

            win_flag = f"🏆 {m.winner_team_name}" if m.winner_team_name else "Draw"
            print(f"  {m.tournament_slug:<14} {m.round_name:<10} {m.round_type[:4]:<8} {side_a_short:<6} {side_b_short:<6} {res_str:<10} {sp_a_str:<16} {sp_b_str:<16} {win_flag}")
        print(divider)

    # 2. Common opponents
    total_co = len(h2h.common_opponents)
    print("\n" + divider)
    print(f"  MUTUAL OPPONENTS COMPARISON ({total_co} Common Rival Team{'s' if total_co != 1 else ''})")
    print(divider)

    if total_co == 0:
        print("  [INFO] No mutual rival teams found that both debaters have faced.")
    else:
        name_a_short = a.canonical_name.split()[0]
        name_b_short = b.canonical_name.split()[0]
        h_line = f"  {'Opponent Team':<18} {'School':<18} | {name_a_short+' (W/L)':<12} {name_a_short+' (%)':<10} {'Margin':<8} | {name_b_short+' (W/L)':<12} {name_b_short+' (%)':<10} {'Margin'}"
        print(h_line)
        print(sub_div)
        for c in h2h.common_opponents:
            inst_str = (c.opponent_institution or "")[:17]
            rec_a = f"{c.a_wins}-{c.a_debates - c.a_wins} ({c.a_debates})"
            pct_a = f"{fmt_val(c.a_win_pct)}%"
            mar_a = format_margin(c.a_avg_margin)

            rec_b = f"{c.b_wins}-{c.b_debates - c.b_wins} ({c.b_debates})"
            pct_b = f"{fmt_val(c.b_win_pct)}%"
            mar_b = format_margin(c.b_avg_margin)

            print(f"  {c.opponent_name:<18} {inst_str:<18} | {rec_a:<12} {pct_a:<10} {mar_a:<8} | {rec_b:<12} {pct_b:<10} {mar_b}")
        print(banner)


def render_team_comparison(h2h: TeamHeadToHead):
    term_width = 110
    banner = "=" * term_width
    divider = "-" * term_width
    sub_div = "." * term_width

    ta = h2h.team_a_name
    tb = h2h.team_b_name
    ma = h2h.metrics_a
    mb = h2h.metrics_b

    print("\n" + banner)
    print("                      ATOMOS HEAD-TO-HEAD TEAM COMPARISON")
    print(banner)

    # Header profiles side-by-side
    print(f"  {'METRIC':<30} | {ta[:36]:<36} | {tb[:36]:<36}")
    print(divider)
    print(f"  {'Institution':<30} | {h2h.institution_a[:36]:<36} | {h2h.institution_b[:36]:<36}")
    
    dec_a = f"{ma['wins']}-{ma['debates'] - ma['wins']} ({fmt_val(ma['win_pct'])}%)"
    dec_b = f"{mb['wins']}-{mb['debates'] - mb['wins']} ({fmt_val(mb['win_pct'])}%)"
    print(f"  {'Career Debate Record':<30} | {dec_a:<36} | {dec_b:<36}")

    prop_a = f"{ma['prop_wins']}/{ma['prop_debates']} ({fmt_val(ma['prop_win_pct'])}%)" if ma['prop_debates'] else "N/A"
    prop_b = f"{mb['prop_wins']}/{mb['prop_debates']} ({fmt_val(mb['prop_win_pct'])}%)" if mb['prop_debates'] else "N/A"
    print(f"  {'Proposition Win Rate':<30} | {prop_a:<36} | {prop_b:<36}")

    opp_a = f"{ma['opp_wins']}/{ma['opp_debates']} ({fmt_val(ma['opp_win_pct'])}%)" if ma['opp_debates'] else "N/A"
    opp_b = f"{mb['opp_wins']}/{mb['opp_debates']} ({fmt_val(mb['opp_win_pct'])}%)" if mb['opp_debates'] else "N/A"
    print(f"  {'Opposition Win Rate':<30} | {opp_a:<36} | {opp_b:<36}")

    atss_a = f"{fmt_val(ma['atss'])} pts" if ma['atss'] is not None else "N/A"
    atss_b = f"{fmt_val(mb['atss'])} pts" if mb['atss'] is not None else "N/A"
    print(f"  {'Avg Team Speaker Score':<30} | {atss_a:<36} | {atss_b:<36}")

    brk_a = f"{ma['breaks']}/{ma['tournaments']} tournaments ({fmt_val(ma['break_pct'])}%)"
    brk_b = f"{mb['breaks']}/{mb['tournaments']} tournaments ({fmt_val(mb['break_pct'])}%)"
    print(f"  {'Outround Break Rate':<30} | {brk_a:<36} | {brk_b:<36}")
    print(banner)

    # 1. Direct encounters
    total_direct = len(h2h.direct_debates)
    print("\n" + divider)
    print(f"  DIRECT HEAD-TO-HEAD MATCHUPS ({total_direct} Recorded Clash{'es' if total_direct != 1 else ''})")
    print(divider)

    if total_direct == 0:
        print("  [INFO] No direct face-to-face encounters recorded between these two teams in the database.")
    else:
        rec_str = f"{ta} {h2h.a_direct_wins} - {h2h.b_direct_wins} {tb}"
        print(f"  Direct Record:           {rec_str}")
        avg_a_str = format_margin(h2h.a_direct_margin_avg)
        avg_b_str = format_margin(h2h.b_direct_margin_avg)
        print(f"  Direct Margin (Net Avg): {ta}: {avg_a_str} pts | {tb}: {avg_b_str} pts")
        print(sub_div)
        
        # Table of encounters
        header = f"  {'Tournament':<16} {'Round':<12} {'Type':<12} {'Team A Side':<14} {'Team B Side':<14} {'Ballots':<10} {'Margin':<10} {'Winner'}"
        print(header)
        print(sub_div)
        for m in h2h.direct_debates:
            res_str = m.ballot_split
            mar_str = format_margin(m.margin_a)
            win_flag = f"🏆 {m.winner_team_name}" if m.winner_team_name else "Draw"
            print(f"  {m.tournament_slug:<16} {m.round_name:<12} {m.round_type:<12} {m.side_a:<14} {m.side_b:<14} {res_str:<10} {mar_str:<10} {win_flag}")
        print(divider)

    # 2. Common opponents
    total_co = len(h2h.common_opponents)
    print("\n" + divider)
    print(f"  MUTUAL OPPONENTS COMPARISON ({total_co} Common Rival Team{'s' if total_co != 1 else ''})")
    print(divider)

    if total_co == 0:
        print("  [INFO] No mutual rival teams found that both teams have faced.")
    else:
        h_line = f"  {'Opponent Team':<18} {'School':<18} | {ta[:12]+' (W/L)':<14} {ta[:8]+' (%)':<10} {'Margin':<8} | {tb[:12]+' (W/L)':<14} {tb[:8]+' (%)':<10} {'Margin'}"
        print(h_line)
        print(sub_div)
        for c in h2h.common_opponents:
            inst_str = (c.opponent_institution or "")[:17]
            rec_a = f"{c.a_wins}-{c.a_debates - c.a_wins} ({c.a_debates})"
            pct_a = f"{fmt_val(c.a_win_pct)}%"
            mar_a = format_margin(c.a_avg_margin)

            rec_b = f"{c.b_wins}-{c.b_debates - c.b_wins} ({c.b_debates})"
            pct_b = f"{fmt_val(c.b_win_pct)}%"
            mar_b = format_margin(c.b_avg_margin)

            print(f"  {c.opponent_name:<18} {inst_str:<18} | {rec_a:<14} {pct_a:<10} {mar_a:<8} | {rec_b:<14} {pct_b:<10} {mar_b}")
        print(banner)


def resolve_debater_identifier(engine: HeadToHeadEngine, query: str) -> Optional[int]:
    """Resolve a debater query (Person ID or name substring) to a single person_id."""
    query = query.strip()
    if query.startswith("#"):
        query = query[1:]
    if query.isdigit():
        pid = int(query)
        prof = engine.profile_engine.get_profile(pid)
        if prof:
            return pid
        print(f"[ERROR] No debater found with Person ID #{pid}")
        return None

    results = engine.profile_engine.search_debaters(query)
    if not results:
        print(f"[ERROR] No debaters found matching query '{query}'.")
        return None

    # Check for exact case-insensitive match
    exact = [r for r in results if r.canonical_name.lower() == query.lower()]
    if len(exact) == 1:
        return exact[0].person_id

    if len(results) == 1:
        return results[0].person_id

    # Disambiguation
    print(f"\n[?] Multiple debaters match '{query}':")
    for idx, r in enumerate(results[:8], 1):
        school = f"({r.institution})" if r.institution else ""
        print(f"    {idx}. #{r.person_id:<4} {r.canonical_name:<28} {school}")

    try:
        choice = input(f"Select debater (1-{min(len(results), 8)}) [default 1]: ").strip()
        if not choice:
            return results[0].person_id
        choice_idx = int(choice) - 1
        if 0 <= choice_idx < min(len(results), 8):
            return results[choice_idx].person_id
    except (ValueError, IndexError):
        pass

    return results[0].person_id


def resolve_team_identifier(conn, query: str) -> Optional[str]:
    """Verify or resolve a team name."""
    query = query.strip()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT name FROM teams WHERE name LIKE ? ORDER BY name", (f"{query}%",))
    rows = cur.fetchall()
    if not rows:
        # Try full substring
        cur.execute("SELECT DISTINCT name FROM teams WHERE name LIKE ? ORDER BY name", (f"%{query}%",))
        rows = cur.fetchall()

    if not rows:
        print(f"[ERROR] No teams found matching '{query}'.")
        return None

    exact = [r[0] for r in rows if r[0].lower() == query.lower()]
    if exact:
        return exact[0]

    if len(rows) == 1:
        return rows[0][0]

    # Disambiguation
    print(f"\n[?] Multiple teams match '{query}':")
    for idx, r in enumerate(rows[:8], 1):
        print(f"    {idx}. {r[0]}")

    try:
        choice = input(f"Select team (1-{min(len(rows), 8)}) [default 1]: ").strip()
        if not choice:
            return rows[0][0]
        choice_idx = int(choice) - 1
        if 0 <= choice_idx < min(len(rows), 8):
            return rows[choice_idx][0]
    except (ValueError, IndexError):
        pass

    return rows[0][0]


def main():
    parser = argparse.ArgumentParser(
        description="Atomos Head-to-Head Debater & Team Comparison CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("name_a", nargs="?", help="Debater 1, Team 1, or School 1 identifier")
    parser.add_argument("name_b", nargs="?", help="Debater 2, Team 2, or School 2 identifier")
    parser.add_argument("--team", action="store_true", help="Compare two teams instead of debaters")
    parser.add_argument("--school", action="store_true", help="Compare two schools/institutions instead of debaters")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON for LLM querying")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive comparison prompt")

    args = parser.parse_args()
    conn = get_connection()
    engine = HeadToHeadEngine(conn)

    # Interactive mode if requested or no arguments provided
    if args.interactive or (not args.name_a and not args.name_b):
        print("=" * 60)
        print("          ATOMOS HEAD-TO-HEAD COMPARISON TOOL")
        print("=" * 60)
        mode = input("Compare (1) Debaters, (2) Teams, or (3) Schools? [default 1]: ").strip()

        if mode == "2":
            team_a_str = input("Enter Team 1 name (e.g. 'DS A'): ").strip()
            team_b_str = input("Enter Team 2 name (e.g. 'RC A'): ").strip()
            if not team_a_str or not team_b_str:
                print("[ERROR] Both team names are required.")
                sys.exit(1)
            t_a = resolve_team_identifier(conn, team_a_str)
            t_b = resolve_team_identifier(conn, team_b_str)
            if not t_a or not t_b:
                sys.exit(1)
            res = engine.compare_teams(t_a, t_b)
            if res is not None:
                if args.json:
                    print(json.dumps(dataclasses.asdict(res), indent=2))
                else:
                    render_team_comparison(res)
            else:
                print(f"[ERROR] Could not generate comparison for '{t_a}' and '{t_b}'.")
        elif mode == "3":
            from atomos.analytics.institutions import InstitutionAnalytics
            from institutional_leaderboard import render_school_comparison
            inst_engine = InstitutionAnalytics(conn)
            sa_str = input("Enter School 1 (Name or Code, e.g. 'RC' or 'Royal'): ").strip()
            sb_str = input("Enter School 2 (Name or Code, e.g. 'DS' or 'Ananda'): ").strip()
            if not sa_str or not sb_str:
                print("[ERROR] Both school names are required.")
                sys.exit(1)
            pa = inst_engine.get_institution_profile(sa_str)
            pb = inst_engine.get_institution_profile(sb_str)
            if not pa or not pb:
                print("[ERROR] One or both institutions could not be found.")
                sys.exit(1)
            cmp_res = inst_engine.compare_institutions(pa.institution_id, pb.institution_id)
            if cmp_res is not None:
                if args.json:
                    print(json.dumps(dataclasses.asdict(cmp_res), indent=2))
                else:
                    render_school_comparison(cmp_res)
            else:
                print(f"[ERROR] Could not compare '{pa.name}' and '{pb.name}'.")
        else:
            deb_a_str = input("Enter Debater 1 (Name or Person ID): ").strip()
            deb_b_str = input("Enter Debater 2 (Name or Person ID): ").strip()
            if not deb_a_str or not deb_b_str:
                print("[ERROR] Both debater names are required.")
                sys.exit(1)
            p_a = resolve_debater_identifier(engine, deb_a_str)
            p_b = resolve_debater_identifier(engine, deb_b_str)
            if not p_a or not p_b:
                sys.exit(1)
            res = engine.compare_debaters(p_a, p_b)
            if res is not None:
                if args.json:
                    print(json.dumps(dataclasses.asdict(res), indent=2))
                else:
                    render_debater_comparison(res)
            else:
                print(f"[ERROR] Could not compare Debater #{p_a} and #{p_b}.")
        return

    # Non-interactive CLI flags
    if not args.name_b:
        if args.json:
            print(json.dumps({"error": "Head-to-Head requires two entities to compare"}))
        else:
            print("[ERROR] Head-to-Head requires two entities to compare. Example: python scripts/head_to_head.py \"Vidath Marasinghe\" \"Kaveesha De Silva\"")
        sys.exit(1)

    if args.school:
        from atomos.analytics.institutions import InstitutionAnalytics
        from institutional_leaderboard import render_school_comparison
        inst_engine = InstitutionAnalytics(conn)
        pa = inst_engine.get_institution_profile(args.name_a)
        pb = inst_engine.get_institution_profile(args.name_b)
        if not pa:
            if args.json:
                print(json.dumps({"error": f"Could not find school matching '{args.name_a}'"}))
            else:
                print(f"[ERROR] Could not find school matching '{args.name_a}'.")
            sys.exit(1)
        if not pb:
            if args.json:
                print(json.dumps({"error": f"Could not find school matching '{args.name_b}'"}))
            else:
                print(f"[ERROR] Could not find school matching '{args.name_b}'.")
            sys.exit(1)
        cmp_res = inst_engine.compare_institutions(pa.institution_id, pb.institution_id)
        if cmp_res is not None:
            if args.json:
                print(json.dumps(dataclasses.asdict(cmp_res), indent=2))
            else:
                render_school_comparison(cmp_res)
        else:
            if args.json:
                print(json.dumps({"error": f"Could not compare '{pa.name}' and '{pb.name}'"}))
            else:
                print(f"[ERROR] Could not compare '{pa.name}' and '{pb.name}'.")
    elif args.team:
        t_a = resolve_team_identifier(conn, args.name_a)
        t_b = resolve_team_identifier(conn, args.name_b)
        if not t_a or not t_b:
            if args.json:
                print(json.dumps({"error": f"Could not resolve teams '{args.name_a}' and '{args.name_b}'"}))
            sys.exit(1)
        res = engine.compare_teams(t_a, t_b)
        if res is not None:
            if args.json:
                print(json.dumps(dataclasses.asdict(res), indent=2))
            else:
                render_team_comparison(res)
        else:
            if args.json:
                print(json.dumps({"error": f"Could not generate comparison for '{t_a}' and '{t_b}'"}))
            else:
                print(f"[ERROR] Could not generate comparison for '{t_a}' and '{t_b}'.")
    else:
        p_a = resolve_debater_identifier(engine, args.name_a)
        p_b = resolve_debater_identifier(engine, args.name_b)
        if not p_a or not p_b:
            if args.json:
                print(json.dumps({"error": f"Could not resolve debaters '{args.name_a}' and '{args.name_b}'"}))
            sys.exit(1)
        res = engine.compare_debaters(p_a, p_b)
        if res is not None:
            if args.json:
                print(json.dumps(dataclasses.asdict(res), indent=2))
            else:
                render_debater_comparison(res)
        else:
            if args.json:
                print(json.dumps({"error": f"Could not compare Debater #{p_a} and #{p_b}"}))
            else:
                print(f"[ERROR] Could not compare Debater #{p_a} and #{p_b}.")


if __name__ == "__main__":
    main()
