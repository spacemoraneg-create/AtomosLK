#!/usr/bin/env python3
"""
Atomos Debater Identity Viewer CLI

Displays complete debater identity dossiers including:
1. Canonical Name & Person ID
2. Aliases recorded in database
3. Official Master Tab & Critical Stats Rankings
4. Overall Substantive Average
5. Teams Debated & Institutional Affiliation
6. Preliminary Rounds Debated & Total Debates
7. Win Rate & Win/Loss Record
8. Break Rate & Knockout Performance
9. Expanded Step-by-Step Derivation of Overall Average

Usage:
    python scripts/view_identity.py
    python scripts/view_identity.py "Vidath Marasinghe"
    python scripts/view_identity.py 362
    python scripts/view_identity.py --search "Silva"
"""

import argparse
import dataclasses
import json
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.database.connection import get_connection
from atomos.analytics.debater_profile import DebaterProfileEngine, DebaterProfile, DebaterSearchResult


def fmt_val(v, max_decimals=5) -> str:
    """Format any numeric value without rounding off below max_decimals and without artificial zero padding."""
    if v is None:
        return "N/A"
    try:
        f = float(v)
        rounded = round(f, max_decimals)
        s = f"{rounded:.{max_decimals}f}".rstrip('0').rstrip('.')
        return s if s else "0"
    except (ValueError, TypeError):
        return str(v)


def render_profile(prof: DebaterProfile, compact: bool = False):
    """Render a debater profile to standard output with beautiful formatting."""
    term_width = 100
    banner = "=" * term_width
    divider = "-" * term_width

    # Header Box
    print("\n" + banner)
    print("                              ATOMOS DEBATER IDENTITY DOSSIER")
    print(banner)
    print(f"  Debater:        {prof.canonical_name:<40} (Person ID: #{prof.person_id})")
    print(f"  School:         {prof.institution}")
    nat_lvl_str = prof.national_level if prof.national_level else "None / Unlisted"
    print(f"  National Level: {nat_lvl_str}")
    alias_str = ", ".join(prof.aliases) if prof.aliases else "None"
    print(f"  Aliases:        {alias_str}")
    teams_str = ", ".join(prof.teams_debated) if prof.teams_debated else "None"
    print(f"  Teams Debated:  {teams_str}")
    tours_str = f"{len(prof.tournaments)} tournament(s) ({', '.join(t.tournament_slug for t in prof.tournaments)})"
    print(f"  Tournaments:    {tours_str}")
    print(divider)

    # Official Standings & Key Metrics
    print("  OFFICIAL STANDINGS & CRITICAL METRICS")
    print(divider)
    if prof.national_level:
        print(f"  National Team Status:     {prof.national_level}")

    # Master Tab Rank & Avg
    if prof.overall_substantive_avg is not None:
        mt_rank_str = f"#{prof.master_tab_rank} of {prof.master_tab_total} in Sri Lanka" if prof.master_tab_rank else "Unranked"
        print(f"  Overall Substantive Avg:  {fmt_val(prof.overall_substantive_avg)} pts (New Standard: Cumulative Speech Avg)")
        if prof.avg_of_avgs is not None:
            print(f"  Legacy Tournament Mean:   {fmt_val(prof.avg_of_avgs)} pts (Legacy: Mean of Tournament Avgs)")
        if prof.raw_substantive_avg is not None:
            print(f"  Raw Prelim Average:       {fmt_val(prof.raw_substantive_avg)} pts (All Prelim Speeches Circuit-Wide)")
        print(f"  Master Tab Rank:          {mt_rank_str}")
    else:
        print(f"  Overall Substantive Avg:  Unranked (< 3 prelim rounds in any tournament)")
        if prof.raw_substantive_avg is not None:
            print(f"  Raw Prelim Average:       {fmt_val(prof.raw_substantive_avg)} pts (from {prof.prelim_rounds_debated} prelim speeches)")
        print(f"  Master Tab Rank:          Unranked")

    # Critical Stats Rank
    if prof.critical_stats_rank is not None:
        cs_rank_str = f"#{prof.critical_stats_rank} of {prof.critical_stats_total} eligible debaters (>= 3 tournaments)"
        print(f"  Critical Stats Rank:      {cs_rank_str}")
    else:
        status_reason = f"requires >= 3 eligible tournaments (currently has {prof.eligible_tournaments_count})"
        print(f"  Critical Stats Rank:      Unranked ({status_reason})")

    # Win & Break Rates
    win_detail = f"{fmt_val(prof.win_rate)}% ({prof.wins_debated} wins / {prof.total_debates} debates)"
    print(f"  Win Rate (Rounds Debated):{win_detail}")

    if prof.eligible_tournaments_count > 0:
        brk_detail = f"{fmt_val(prof.break_rate)}% (Broke to knockouts in {int(round(prof.break_rate * prof.eligible_tournaments_count / 100.0, 5))} of {prof.eligible_tournaments_count} eligible tournaments)"
        print(f"  Break Rate:               {brk_detail}")
    else:
        print(f"  Break Rate:               N/A (No eligible tournaments completed)")

    print(f"  Prelims Debated:          {prof.prelim_rounds_debated} preliminary rounds ({prof.total_debates} total debates)")

    if prof.avg_of_deviations is not None:
        print(f"  Consistency (Avg Dev):    {fmt_val(prof.avg_of_deviations)} pts (Mean within-tournament score deviation σ)")

    if prof.reply_speech_count > 0:
        reply_str = f"{fmt_val(prof.reply_average)} / 40.0 pts across {prof.reply_speech_count} reply speeches" if prof.reply_average else "N/A"
        print(f"  Reply Tab Record:         {reply_str}")

    print(banner)

    # Chronological Trajectory
    if prof.trajectory:
        print("\n" + banner)
        print("                   CHRONOLOGICAL PERFORMANCE TRAJECTORY & CAREER TRENDLINE")
        print(banner)
        print(f"  {'#':<4} {'TOURNAMENT':<26} {'TOUR AVG':<12} {'CUMULATIVE AVG':<18} {'PEAK SPEECH':<14} {'STAGE REACHED'}")
        print("-" * 100)
        for idx, tr in enumerate(prof.trajectory, 1):
            avg_str = f"{fmt_val(tr['substantive_avg'])} pts"
            run_str = f"{fmt_val(tr['running_cumulative_avg'])} pts"
            peak_str = f"{fmt_val(tr['peak_speech'])} pts" if tr['peak_speech'] else "N/A"
            stage = tr['stage_reached']
            t_short = tr['tournament_name'].split('|')[0].strip()
            print(f"  [{idx:<2}] {t_short:<26} {avg_str:<12} {run_str:<18} {peak_str:<14} {stage}")
        print(banner)

    if compact:
        return

    # Tournament by Tournament Breakdown
    print("\n" + banner)
    print("                        TOURNAMENT PERFORMANCE BREAKDOWN")
    print(banner)

    for idx, t in enumerate(prof.tournaments, 1):
        status_badge = "QUALIFIED (Eligible for Tab)" if t.is_eligible else "INELIGIBLE (< 3 prelims)"
        print(f"\n[{idx}] {t.tournament_name}")
        print(f"    Slug: {t.tournament_slug:<16} | Team: {t.team_name:<16} | Status: {status_badge}")
        print(f"    Stage Reached: {t.highest_stage}")
        print("    " + "-" * 90)

        # Preliminary Rounds
        print("    Preliminary Rounds Debated:")
        if t.prelim_rounds:
            for pr in t.prelim_rounds:
                counted_sub = [sp for sp in pr.speeches if sp.speech_type == "SUBSTANTIVE" and sp.is_counted_in_tab]
                uncounted_sub = [sp for sp in pr.speeches if sp.speech_type == "SUBSTANTIVE" and not sp.is_counted_in_tab]

                if counted_sub and pr.substantive_score is not None:
                    pos = counted_sub[0].position
                    if len(counted_sub) > 1:
                        panel_detail = ", ".join(f"{fmt_val(sp.total_score)} ({sp.judge_name or 'Judge'})" for sp in counted_sub)
                        sub_str = f"{pos} Sub = {fmt_val(pr.substantive_score)} [Panel: {panel_detail}]"
                    else:
                        sub_str = f"{pos} Sub = {fmt_val(pr.substantive_score)}"
                elif pr.substantive_score is not None:
                    sub_str = f"Sub = {fmt_val(pr.substantive_score)}"
                else:
                    sub_str = "No Sub Score"

                rep_str = f" | Reply = {fmt_val(pr.reply_score)}" if pr.reply_score is not None else ""

                iron_str = ""
                if uncounted_sub:
                    other_pos = uncounted_sub[0].position
                    other_avg = sum(s.total_score for s in uncounted_sub) / len(uncounted_sub)
                    iron_str = f" [Iron Man: {pos} ({fmt_val(pr.substantive_score)}) counted over {other_pos} ({fmt_val(other_avg)})]"
                elif any(sp.is_iron_man for sp in pr.speeches):
                    iron_str = " [Iron Man]"

                margin_str = f"+{fmt_val(pr.margin)}" if pr.margin and pr.margin > 0 else f"{fmt_val(pr.margin)}" if pr.margin is not None else ""
                split_display = f"({pr.ballot_split}, {margin_str} margin)" if pr.margin is not None else f"({pr.ballot_split})"
                res_str = f"{'WON':<4} {split_display}" if pr.is_win else f"{'LOST':<4} {split_display}"

                matchup = f"{pr.side[:4]} vs {pr.opp_team_name}"
                print(f"      Round {pr.round_number:<2} ({matchup:<22}): {sub_str}{rep_str} | {res_str}{iron_str}")
        else:
            print("      No preliminary speeches recorded.")

        # Out-Rounds (Eliminations)
        if t.elim_rounds:
            print("    Knockout Elimination Rounds:")
            for er in t.elim_rounds:
                res_badge = "WON" if er.is_win else "LOST"
                split_badge = f"({er.ballot_split})" if er.ballot_split != "N/A" else ""
                matchup_elim = f"{er.side[:4]} vs {er.opp_team_name}"
                print(f"      {er.round_name:<16} ({matchup_elim:<22}) -> {res_badge} {split_badge}")

        # Tournament Substantive Average & Math
        scores_fmt = ", ".join(fmt_val(s) for s in t.prelim_substantive_scores) if t.prelim_substantive_scores else "None"
        print("    Scores Summary:")
        print(f"      Counted Prelim Substantive Scores: [{scores_fmt}]")
        if t.is_eligible and t.tournament_average is not None:
            sum_s = sum(t.prelim_substantive_scores)
            cnt_s = len(t.prelim_substantive_scores)
            stdev_str = f" | σ = {fmt_val(t.score_stdev)} pts" if t.score_stdev is not None else ""
            print(f"      Tournament Substantive Average:    {fmt_val(sum_s)} / {cnt_s} = {fmt_val(t.tournament_average)} pts{stdev_str}")
        else:
            print(f"      [EXCLUDED FROM MASTER TAB] Only {len(t.prelim_substantive_scores)} prelim rounds (minimum 3 required by WSDC rules).")

    # Expanded Derivation Section
    print("\n" + prof.derivation_text + "\n")


def interactive_mode(engine: DebaterProfileEngine):
    """Run an interactive debater lookup shell in the terminal."""
    print("\n" + "=" * 80)
    print("                    ATOMOS DEBATER IDENTITY VIEWER")
    print("=" * 80)
    print("Lookup debater dossiers, aliases, tournament averages, and math derivations.")
    print("Commands:")
    print("  * Type a debater name (e.g. 'Vidath', 'Kaveesha', 'Dithira')")
    print("  * Type a Person ID (e.g. '362')")
    print("  * Type 'q' or 'exit' to quit\n")

    while True:
        try:
            query = input("Enter Debater Name or Person ID: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[INFO] Exiting viewer.")
            break

        if not query:
            continue
        if query.lower() in ("q", "quit", "exit"):
            print("[INFO] Exiting viewer.")
            break

        process_query(engine, query)


def process_query(engine: DebaterProfileEngine, query: str, compact: bool = False):
    """Search and render debater profile."""
    # Direct ID lookup
    if query.isdigit():
        prof = engine.get_profile(int(query))
        if prof:
            render_profile(prof, compact=compact)
        else:
            print(f"[ERROR] No debater found with Person ID #{query}.")
        return

    # Search by Name
    results = engine.search_debaters(query)
    if not results:
        print(f"[NOTICE] No debaters found matching '{query}'. Check spelling or try a partial name.")
        return

    if len(results) == 1:
        prof = engine.get_profile(results[0].person_id)
        if prof:
            render_profile(prof, compact=compact)
        return

    # Multiple matches found -> prompt user to select
    print(f"\n[SEARCH] Found {len(results)} debater(s) matching '{query}':")
    print("-" * 80)
    for idx, r in enumerate(results, 1):
        avg_str = f"Avg: {fmt_val(r.overall_avg)}" if r.overall_avg is not None else "Avg: N/A"
        rank_str = f"MasterTab: #{r.master_tab_rank}" if r.master_tab_rank else "Unranked"
        teams_str = f"Teams: {', '.join(r.teams)}" if r.teams else ""
        print(f"  [{idx}] {r.canonical_name:<28} | {r.institution:<28} [ID: #{r.person_id}]")
        print(f"      {avg_str:<14} | {rank_str:<18} | {r.speech_count} speeches | {teams_str}")
    print("-" * 80)

    while True:
        choice = input(f"Select debater [1-{len(results)}] or 'c' to cancel: ").strip().lower()
        if choice in ("c", "cancel", "q"):
            print("[INFO] Selection cancelled.")
            break
        if choice.isdigit() and 1 <= int(choice) <= len(results):
            selected = results[int(choice) - 1]
            prof = engine.get_profile(selected.person_id)
            if prof:
                render_profile(prof, compact=compact)
            break
        print(f"[WARN] Invalid option. Enter a number between 1 and {len(results)}.")



def main():
    parser = argparse.ArgumentParser(description="Atomos Debater Identity & Derivation Viewer")
    parser.add_argument("name_or_id", nargs="?", default=None, help="Debater name or Person ID to view")
    parser.add_argument("--db", type=str, default="data/atomos.db", help="Path to SQLite database")
    parser.add_argument("--compact", action="store_true", help="Show summary profile only without full round breakdown")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON structure for LLM querying")

    args = parser.parse_args()

    conn = get_connection(Path(args.db))
    engine = DebaterProfileEngine(conn)

    try:
        if args.json:
            if not args.name_or_id:
                print(json.dumps({"error": "name_or_id required when --json is used"}))
                return
            target_prof = None
            if args.name_or_id.isdigit():
                target_prof = engine.get_profile(int(args.name_or_id))
                if not target_prof:
                    print(json.dumps({"error": f"No debater found with ID #{args.name_or_id}"}))
                    return
            else:
                results = engine.search_debaters(args.name_or_id)
                if not results:
                    print(json.dumps({"error": f"No debater found matching '{args.name_or_id}'"}))
                    return
                elif len(results) == 1:
                    target_prof = engine.get_profile(results[0].person_id)
                else:
                    exact = [r for r in results if r.canonical_name.lower() == args.name_or_id.lower()]
                    if exact:
                        target_prof = engine.get_profile(exact[0].person_id)
                    else:
                        print(json.dumps({
                            "matches_count": len(results),
                            "candidates": [dataclasses.asdict(r) for r in results]
                        }, indent=2))
                        return

            if target_prof:
                data = dataclasses.asdict(target_prof)
                if args.compact:
                    data.pop("derivation_text", None)
                    for t in data.get("tournaments", []):
                        t.pop("prelim_rounds", None)
                        t.pop("elim_rounds", None)
                print(json.dumps(data, indent=2))
            return

        if args.name_or_id:
            # Command line argument passed
            if args.name_or_id.isdigit():
                prof = engine.get_profile(int(args.name_or_id))
                if prof:
                    render_profile(prof, compact=args.compact)
                else:
                    print(f"[ERROR] No debater found with ID #{args.name_or_id}")
            else:
                process_query(engine, args.name_or_id, compact=args.compact)

        else:
            # Interactive mode
            interactive_mode(engine)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
