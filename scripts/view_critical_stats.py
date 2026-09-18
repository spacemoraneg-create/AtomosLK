#!/usr/bin/env python3
"""
Atomos Critical Stats Terminal Viewer

Displays high-rigor critical leaderboards for debaters and teams competing in >= 3 tournaments:
1. Individual Critical Stats (5 Metrics):
   - Substantive Average
   - Avg of Deviations in Tournaments
   - Win Rate in rounds debated
   - Preliminary rounds debated
   - Break Percentage when eligible in speaks tab

2. Team Critical Stats (7 Metrics):
   - Break Percentage
   - Overall Win Percentage
   - Opp / Prop Win Split
   - Rounds Debated
   - Break Rounds Debated
   - ATSS (Average Total Speaker Score)
   - Average Winning Margin

Usage:
    python scripts/view_critical_stats.py
    python scripts/view_critical_stats.py --limit 20
    python scripts/view_critical_stats.py --speakers-only
    python scripts/view_critical_stats.py --teams-only
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Ensure src is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.analytics.critical_stats import CriticalStatsEngine


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


def print_speaker_table(speakers: list, limit: int):
    actual_count = min(limit, len(speakers))
    print("\n" + "=" * 138)
    print(f"                 ATOMOS CRITICAL STATS — TOP {actual_count} INDIVIDUAL DEBATERS (>= 3 TOURNAMENTS)")
    print("=" * 138)
    header = f"{'Rank':<5} {'Debater':<26} {'Nat Status':<20} {'Institution':<28} {'Avg':<10} {'AvgDev':<10} {'Win%':<10} {'Prelims':<9} {'Break%'}"
    print(header)
    print("-" * 138)

    for s in speakers[:limit]:
        win_str = f"{fmt_val(s['win_rate_debated'])}%"
        break_str = f"{fmt_val(s['break_percentage'])}%"
        nat_str = s.get("national_level") or "-"
        line = (
            f"#{s['rank']:<4} "
            f"{s['speaker_name']:<26} "
            f"{nat_str:<20} "
            f"{s['institution']:<28} "
            f"{fmt_val(s['avg']):<10} "
            f"{fmt_val(s['avg_of_deviations']):<10} "
            f"{win_str:<10} "
            f"{s['prelim_rounds_debated']:<9} "
            f"{break_str}"
        )
        print(line)
    print("=" * 138)


def print_team_table(teams: list, limit: int):
    actual_count = min(limit, len(teams))
    print("\n" + "=" * 130)
    print(f"                 ATOMOS CRITICAL STATS — TOP {actual_count} DEBATING TEAMS (>= 3 TOURNAMENTS)")
    print("=" * 130)
    header = (
        f"{'Rank':<5} {'Team':<12} {'Institution':<30} {'Break%':<10} {'Win%':<10} "
        f"{'Prop/Opp Split':<20} {'Rounds':<8} {'Out-Rounds':<12} {'ATSS':<10} {'Avg Margin'}"
    )
    print(header)
    print("-" * 130)

    for t in teams[:limit]:
        prop_pct = fmt_val(t['opp_prop_split']['prop_win_percentage'])
        opp_pct = fmt_val(t['opp_prop_split']['opp_win_percentage'])
        split = f"{prop_pct}% / {opp_pct}%"
        break_str = f"{fmt_val(t['break_percentage'])}%"
        win_str = f"{fmt_val(t['win_percentage'])}%"
        margin_val = t['avg_margins']
        margin_str = f"+{fmt_val(margin_val)}" if margin_val and margin_val > 0 else fmt_val(margin_val)
        line = (
            f"#{t['rank']:<4} "
            f"{t['team_name']:<12} "
            f"{t['institution']:<30} "
            f"{break_str:<10} "
            f"{win_str:<10} "
            f"{split:<20} "
            f"{t['rounds_debated']:<8} "
            f"{t['break_rounds_debated']:<12} "
            f"{fmt_val(t['atss']):<10} "
            f"{margin_str}"
        )
        print(line)
    print("=" * 130)


def main():
    parser = argparse.ArgumentParser(description="View Atomos Critical Stats in Terminal")
    parser.add_argument("--db-path", default="data/atomos.db", help="Path to database")
    parser.add_argument("--limit", "-n", type=int, default=None, help="Override number of rows to display for both tables")
    parser.add_argument("--debater-limit", type=int, default=50, help="Number of debaters to display (default: 50)")
    parser.add_argument("--team-limit", type=int, default=25, help="Number of teams to display (default: 25)")
    parser.add_argument("--min-tournaments", "-m", type=int, default=3, help="Minimum tournaments threshold (default: 3)")
    parser.add_argument("--speakers-only", action="store_true", help="Display only debaters table")
    parser.add_argument("--teams-only", action="store_true", help="Display only teams table")

    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"[ERROR] Database not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    engine = CriticalStatsEngine(conn)

    show_speakers = not args.teams_only
    show_teams = not args.speakers_only

    debater_limit = args.limit if args.limit is not None else args.debater_limit
    team_limit = args.limit if args.limit is not None else args.team_limit

    if show_speakers:
        speakers = engine.get_critical_speaker_stats(min_tournaments=args.min_tournaments)
        print_speaker_table(speakers, debater_limit)

    if show_teams:
        teams = engine.get_critical_team_stats(min_tournaments=args.min_tournaments)
        print_team_table(teams, team_limit)

    conn.close()


if __name__ == "__main__":
    main()
