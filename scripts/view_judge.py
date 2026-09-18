#!/usr/bin/env python3
"""
Atomos Adjudicator Dossier & Intelligence Viewer

Usage:
    python scripts/view_judge.py "Rudhesh Ram"
    python scripts/view_judge.py --top 15
    python scripts/view_judge.py --sort margin
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Ensure src is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.database.connection import get_connection
from atomos.analytics.judges import JudgeAnalyticsEngine


def print_judge_dossier(dossier: dict):
    rec = dossier["record"]
    sc = dossier["scoring_metrics"]

    print("\n" + "=" * 90)
    print("                      ATOMOS ADJUDICATOR FORENSIC DOSSIER")
    print("=" * 90)
    print(f"  Adjudicator:         {dossier['adjudicator_name']}")
    print(f"  Institution:         {dossier['institution']}")
    print(f"  Debates Judged:      {dossier['total_debates_judged']} debates across {dossier['tournaments_count']} tournament(s)")
    print(f"  Outrounds Judged:    {dossier['outrounds_judged']} knockout elimination rounds")
    print(f"  Tournaments:         {', '.join(dossier['tournaments'])}")
    print("-" * 90)
    print("  DECISION RECORD & SIDE BIAS")
    print("-" * 90)
    print(f"  Proposition Wins:    {rec['prop_wins']} ({rec['prop_win_pct']}%)")
    print(f"  Opposition Wins:     {rec['opp_wins']} ({rec['opp_win_pct']}%)")
    print(f"  Side Bias Analysis:  {rec['side_bias']}")
    print("-" * 90)
    print("  SCORING PROFILE & STRICTNESS INDEX")
    print("-" * 90)
    print(f"  Substantive Average: {sc['avg_substantive_score']} pts")
    print(f"  Strictness Delta:    {'+' if sc['strictness_delta'] > 0 else ''}{sc['strictness_delta']} pts vs circuit avg (71.2)")
    print(f"  Strictness Rating:   {sc['strictness_label']}")
    print(f"  Average Team Score:  {sc['avg_team_score']} pts")
    print(f"  Average Margin:      +{sc['avg_win_margin']} pts")
    print(f"  Razor Margin (<=1.5):{sc['close_debates_pct']}% of decisions")
    print(f"  Blowouts (>=4.0):    {sc['blowout_debates_pct']}% of decisions")
    print("-" * 90)
    print("  RECENT DEBATES OFFICIATED")
    print("-" * 90)
    for m in dossier["recent_debates"]:
        margin_str = f"+{m['margin']}" if m['margin'] is not None else "N/A"
        winner = m['winner_side'] or "Unrecorded"
        print(f"  * {m['tournament']:<18} | {m['round']:<12} | {m['prop_team']} vs {m['opp_team']} -> {winner} ({margin_str} margin)")
    print("=" * 90 + "\n")


def print_judge_leaderboard(leaderboard: list):
    print("\n" + "=" * 125)
    print(f"                 ATOMOS NATIONAL ADJUDICATOR LEADERBOARD (CIRCUIT BENCHMARK)")
    print("=" * 125)
    header = f"{'RK':<4} {'ADJUDICATOR NAME':<26} {'INSTITUTION':<26} {'DEBATES':<9} {'OUTROUNDS':<11} {'PROP%':<9} {'OPP%':<9} {'AVG SUB':<10} {'AVG MARGIN'}"
    print(header)
    print("-" * 125)
    for j in leaderboard:
        line = (
            f"#{j['rank']:<3} "
            f"{j['adjudicator_name']:<26} "
            f"{j['institution']:<26} "
            f"{j['debates_judged']:<9} "
            f"{j['outrounds_judged']:<11} "
            f"{j['prop_win_pct']:<9.1f} "
            f"{j['opp_win_pct']:<9.1f} "
            f"{j['avg_substantive_score']:<10.2f} "
            f"+{j['avg_win_margin']:<8.2f}"
        )
        print(line)
    print("=" * 125 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Atomos Adjudicator Dossier and Intelligence Viewer")
    parser.add_argument("name", nargs="?", help="Adjudicator name or person ID")
    parser.add_argument("--top", type=int, default=15, help="Number of top judges to list")
    parser.add_argument("--sort", choices=["debates", "margin", "avg_score", "outrounds"], default="debates")
    parser.add_argument("--min-debates", type=int, default=3, help="Minimum debates to qualify on leaderboard")

    args = parser.parse_args()

    conn = get_connection()
    engine = JudgeAnalyticsEngine(conn)

    if args.name:
        dossier = engine.get_judge_dossier(args.name)
        if not dossier:
            print(f"\n[!] No adjudicator found matching '{args.name}'. Try a different spelling or check --top.\n")
            sys.exit(1)
        print_judge_dossier(dossier)
    else:
        lb = engine.get_judge_leaderboard(min_debates=args.min_debates, sort_by=args.sort)
        print_judge_leaderboard(lb[:args.top])


if __name__ == "__main__":
    main()
