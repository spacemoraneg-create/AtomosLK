#!/usr/bin/env python3
"""
Atomos Motion & Side Bias Intelligence CLI

Provides comprehensive analytics on:
1. Overall Proposition vs Opposition Win Rates & Side Bias
2. Preliminary vs Elimination Round Side Splits
3. Tournament-by-Tournament Side Bias
4. Thematic Topic Breakdown (Geopolitics, Economics, Tech/AI, Social, etc.)
5. Most Extreme & Balanced Motions
6. Keyword-Based Motion Search

Usage:
    python scripts/motion_analysis.py --side-bias
    python scripts/motion_analysis.py --themes
    python scripts/motion_analysis.py --extreme
    python scripts/motion_analysis.py --search "AI"
    python scripts/motion_analysis.py --theme "Economics & Development"
    python scripts/motion_analysis.py --json
"""

import argparse
import html
import json
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.database.connection import get_connection
from atomos.analytics.motions import MotionAnalytics


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


def render_side_bias(analytics: MotionAnalytics):
    overall = analytics.get_overall_side_balance()
    tourneys = analytics.get_tournament_side_balance()
    rounds = analytics.get_round_type_side_balance()

    term_width = 80
    print("\n" + "=" * term_width)
    print("                 NATIONAL MOTION & SIDE BIAS INTELLIGENCE")
    print("=" * term_width)
    print(f"  Total Debates Analyzed:   {overall['total_decisions']}")
    print(f"  Proposition Wins:         {overall['prop_wins']} ({fmt_val(overall['prop_win_rate'])}%)")
    print(f"  Opposition Wins:          {overall['opp_wins']} ({fmt_val(overall['opp_win_rate'])}%)")
    if overall['ties'] > 0:
        print(f"  Ties / Drawn Decisions:   {overall['ties']}")
    print(f"  Dominant Circuit Side:    {overall['dominant_side'].upper()} (+{fmt_val(overall['bias_margin'])}%)")
    print(f"  National Classification:  {overall['bias_classification']}")
    print("-" * term_width)

    print("\n  STAGE BREAKDOWN (PRELIMS vs ELIMINATIONS):")
    print(f"  {'Stage':<20} {'Decisions':<12} {'Prop Win %':<15} {'Opp Win %':<15} {'Classification':<20}")
    print("  " + "-" * 76)
    for st_name, st in rounds.items():
        print(f"  {st_name:<20} {st['total_decisions']:<12} {fmt_val(st['prop_win_rate']):<15} {fmt_val(st['opp_win_rate']):<15} {st['bias_classification']:<20}")

    print("\n  TOURNAMENT BREAKDOWN:")
    print(f"  {'Tournament':<32} {'Decisions':<10} {'Prop %':<12} {'Opp %':<12} {'Dominant':<12} {'Classification'}")
    print("  " + "-" * 92)
    for t in tourneys:
        tname = t["tournament_name"][:30]
        print(f"  {tname:<32} {t['total_decisions']:<10} {fmt_val(t['prop_win_rate']):<12} {fmt_val(t['opp_win_rate']):<12} {t['dominant_side']:<12} {t['bias_classification']}")
    print("=" * term_width + "\n")


def render_themes(analytics: MotionAnalytics):
    themes = analytics.get_thematic_motion_analysis()
    term_width = 95
    print("\n" + "=" * term_width)
    print("                         THEMATIC MOTION PERFORMANCE")
    print("=" * term_width)
    print(f"  {'Thematic Category':<35} {'Motions':<10} {'Debates':<10} {'Prop %':<12} {'Opp %':<12} {'Classification'}")
    print("  " + "-" * 95)
    for th in themes:
        print(f"  {th['theme']:<35} {th['motions_count']:<10} {th['debates_count']:<10} {fmt_val(th['prop_win_rate']):<12} {fmt_val(th['opp_win_rate']):<12} {th['bias_classification']}")
    print("=" * term_width + "\n")


def render_extreme_motions(analytics: MotionAnalytics):
    ext = analytics.get_extreme_motions()
    term_width = 100
    print("\n" + "=" * term_width)
    print("                         EXTREME & BALANCED MOTIONS")
    print("=" * term_width)

    print("\n  [TOP PROPOSITION-LEANING MOTIONS]")
    for m in ext.get("most_prop_biased", []):
        print(f"  * [{m['tournament_slug']}] {m['motion']}")
        print(f"    Debates: {m['debates_count']} | Prop Win: {m['prop_win_rate']}% | Opp Win: {m['opp_win_rate']}% | Avg Margin: {m['avg_win_margin']}")

    print("\n  [TOP OPPOSITION-LEANING MOTIONS]")
    for m in ext.get("most_opp_biased", []):
        print(f"  * [{m['tournament_slug']}] {m['motion']}")
        print(f"    Debates: {m['debates_count']} | Opp Win: {m['opp_win_rate']}% | Prop Win: {m['prop_win_rate']}% | Avg Margin: {m['avg_win_margin']}")

    print("\n  [MOST BALANCED MOTIONS (Near 50/50 Split)]")
    for m in ext.get("most_balanced", []):
        print(f"  * [{m['tournament_slug']}] {m['motion']}")
        print(f"    Debates: {m['debates_count']} | Prop Win: {m['prop_win_rate']}% | Opp Win: {m['opp_win_rate']}% | Avg Margin: {m['avg_win_margin']}")
    print("\n" + "=" * term_width + "\n")


def main():
    parser = argparse.ArgumentParser(description="Atomos Motion Intelligence & Side Bias Analytics")
    parser.add_argument("--side-bias", action="store_true", help="Display overall, stage, and tournament side balance")
    parser.add_argument("--themes", action="store_true", help="Display thematic topic win rates and distribution")
    parser.add_argument("--extreme", action="store_true", help="Display most Prop-biased, Opp-biased, and balanced motions")
    parser.add_argument("--search", type=str, help="Search motions by keyword")
    parser.add_argument("--theme", type=str, help="Filter motions by thematic category")
    parser.add_argument("--min-debates", type=int, default=2, help="Minimum debates threshold (default: 2)")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON for LLM ingestion")
    args = parser.parse_args()

    conn = get_connection()
    analytics = MotionAnalytics(conn)

    # If --json is requested
    if args.json:
        data = {
            "overall_side_balance": analytics.get_overall_side_balance(),
            "tournament_side_balance": analytics.get_tournament_side_balance(),
            "round_type_side_balance": analytics.get_round_type_side_balance(),
            "thematic_analysis": analytics.get_thematic_motion_analysis(),
            "extreme_and_balanced": analytics.get_extreme_motions(),
        }
        if args.search:
            from atomos.analytics.search import UnifiedSearchEngine
            se = UnifiedSearchEngine(conn)
            data["search_results"] = se.search_motions(args.search, limit=20)
        if args.theme:
            motions = analytics.get_motion_balance_report(min_debates=1)
            data["filtered_motions"] = [m for m in motions if args.theme.lower() in m["theme"].lower()]
        print(json.dumps(data, indent=2))
        conn.close()
        return

    # Specific human CLI modes
    if args.search:
        from atomos.analytics.search import UnifiedSearchEngine
        se = UnifiedSearchEngine(conn)
        matches = se.search_motions(args.search, limit=15)
        print(f"\n  Found {len(matches)} motion(s) matching '{args.search}':")
        print("  " + "-" * 80)
        for m in matches:
            print(f"  * [{m['tournament']} - {m['round_name']}] ({m['theme']})")
            print(f"    \"{m['motion']}\"")
        print("  " + "-" * 80 + "\n")
    elif args.theme:
        motions = analytics.get_motion_balance_report(min_debates=1)
        filtered = [m for m in motions if args.theme.lower() in m["theme"].lower()]
        print(f"\n  Motions under Theme '{args.theme}' ({len(filtered)} found):")
        print("  " + "-" * 90)
        for m in filtered:
            print(f"  * [{m['tournament_slug']}] {m['motion']}")
            print(f"    Debates: {m['debates_count']} | Prop: {m['prop_win_rate']}% | Opp: {m['opp_win_rate']}% | Bias: {m['bias_classification']}")
        print("  " + "-" * 90 + "\n")
    elif args.themes:
        render_themes(analytics)
    elif args.extreme:
        render_extreme_motions(analytics)
    else:
        render_side_bias(analytics)

    conn.close()


if __name__ == "__main__":
    main()
