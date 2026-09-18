#!/usr/bin/env python3
"""
Atomos Interactive Team Resolver & Grouping CLI

Allows interactive or automated grouping, tier assignment, and canonical resolution
of debate teams across tournaments in the Atomos database.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.database.connection import get_connection
from atomos.normalizer.team_resolver import TeamResolver, TeamSummary, CandidateTeamResolution, VALID_TIERS


def format_team_box(t: TeamSummary, cand: Optional[CandidateTeamResolution] = None) -> str:
    lines = [
        f"  [Team #{t.id:<3}] Raw: '{t.raw_name}' | School: {t.institution_name or 'Independent'} ({t.institution_code or 'N/A'})",
        f"        Tournament: {t.tournament_name}",
        f"        Roster:     {t.member_names_str}",
        f"        Record:     {t.record_str}",
    ]
    if t.canonical_name and t.tier:
        lines.append(f"        Current:    Canonical: '{t.canonical_name}' | Tier: {t.tier} [{t.status}]")
    if cand:
        pct = int(cand.confidence * 100)
        lines.append(f"        Suggested:  Canonical: '{cand.suggested_canonical_name}' | Tier: {cand.suggested_tier} ({pct}% conf)")
        lines.append(f"        Reason:     {cand.reason}")
    return "\n".join(lines)


def list_summary(resolver: TeamResolver, school_filter: Optional[str] = None):
    """Print an overview of institutions and resolution progress."""
    institutions = resolver.get_institutions()
    if school_filter:
        flt = school_filter.lower()
        institutions = [
            inst for inst in institutions
            if flt in inst["name"].lower() or (inst["code"] and flt in inst["code"].lower())
        ]

    total_teams = sum(i["total_teams"] for i in institutions)
    total_res = sum(i["resolved_teams"] for i in institutions)
    total_pend = total_teams - total_res

    print("\n" + "=" * 90)
    print(f"               ATOMOS TEAM RESOLUTION DASHBOARD ({len(institutions)} INSTITUTIONS)")
    print(f"               Total Teams: {total_teams} | Resolved: {total_res} | Pending: {total_pend}")
    print("=" * 90)
    print(f"{'ID':<4} {'Code':<8} {'Institution Name':<45} {'Total':<7} {'Resolved':<10} {'Pending':<8}")
    print("-" * 90)

    for inst in institutions:
        print(f"{inst['id']:<4} {inst['code'] or '-':<8} {inst['name'][:43]:<45} {inst['total_teams']:<7} {inst['resolved_teams']:<10} {inst['pending_teams']:<8}")

    print("=" * 90)


def show_school_teams(resolver: TeamResolver, query: str):
    """Show detailed list of teams for a given institution."""
    institutions = resolver.get_institutions()
    matches = [
        i for i in institutions
        if query.lower() in i["name"].lower() or (i["code"] and query.lower() in i["code"].lower())
    ]
    if not matches:
        print(f"[WARN] No institution found matching '{query}'.")
        return

    for inst in matches:
        teams = resolver.list_teams(institution_id=inst["id"])
        print("\n" + "=" * 100)
        print(f"Institution: {inst['name']} (Code: {inst['code']}) | {len(teams)} Teams")
        print("=" * 100)
        for t in teams:
            print(format_team_box(t))
            print("-" * 100)


def auto_resolve_safe_flow(resolver: TeamResolver, interactive: bool = True) -> int:
    """Find and apply safe high-confidence resolutions."""
    candidates = resolver.find_candidate_resolutions(unresolved_only=True)
    safe = [c for c in candidates if c.confidence >= 0.90]

    if not safe:
        print("\n[INFO] No pending safe candidates found.")
        return 0

    print(f"\n[NOTICE] Discovered {len(safe)} high-confidence candidate team resolution(s).")
    if interactive:
        ans = input(f"Auto-resolve these {len(safe)} safe teams now? [Y/n]: ").strip().lower()
        if ans not in ("", "y", "yes"):
            print("[INFO] Batch auto-resolve skipped.")
            return 0

    count = resolver.auto_resolve_safe(min_confidence=0.90)
    print(f"[SUCCESS] Successfully resolved {count} teams with high confidence!\n")
    return count


def interactive_school_resolution(resolver: TeamResolver, institution_id: int):
    """Step through pending teams of an institution interactively."""
    candidates = resolver.find_candidate_resolutions(institution_id=institution_id, unresolved_only=True)
    if not candidates:
        print("[INFO] All teams for this institution are already resolved!")
        return

    inst_name = candidates[0].team.institution_name or "Institution"
    code = candidates[0].team.institution_code or "Team"

    print(f"\nResolving {len(candidates)} pending team(s) for {inst_name} ({code})...")

    for idx, cand in enumerate(candidates, 1):
        t = cand.team
        print("\n" + "-" * 90)
        print(f"[{idx}/{len(candidates)}]")
        print(format_team_box(t, cand))
        print("-" * 90)

        while True:
            prompt = (
                f"Action ([Enter/A]=Accept '{cand.suggested_canonical_name}', "
                f"[1]=Tier A, [2]=Tier B, [3]=Tier C, [4]=Tier D, [M]=Custom, [G]=Group, [S]=Skip, [Q]=Back): "
            )
            choice = input(prompt).strip()
            ch_lower = choice.lower()

            if ch_lower in ("", "a", "yes", "y"):
                resolver.resolve_team(
                    team_id=t.id,
                    canonical_name=cand.suggested_canonical_name,
                    tier=cand.suggested_tier,
                    reason=cand.reason,
                    reviewed_by_user=True,
                    confidence=cand.confidence,
                )
                print(f"-> [RESOLVED] Set #{t.id} to '{cand.suggested_canonical_name}' (Tier {cand.suggested_tier}).")
                break

            elif ch_lower in ("1", "2", "3", "4"):
                tier_map = {"1": "A", "2": "B", "3": "C", "4": "D"}
                chosen_tier = tier_map[ch_lower]
                canon_name = f"{code} {chosen_tier}"
                resolver.resolve_team(
                    team_id=t.id,
                    canonical_name=canon_name,
                    tier=chosen_tier,
                    reason=f"User selected Tier {chosen_tier}",
                    reviewed_by_user=True,
                )
                print(f"-> [RESOLVED] Set #{t.id} to '{canon_name}' (Tier {chosen_tier}).")
                break

            elif ch_lower == "m":
                cname = input(f"Enter Canonical Name (default '{code} A'): ").strip() or f"{code} A"
                ctier = input("Enter Tier (A, B, C, D, NOVICE, SWING, OTHER): ").strip().upper()
                if ctier not in VALID_TIERS:
                    print(f"[ERROR] Invalid tier '{ctier}'. Must be one of: {VALID_TIERS}")
                    continue
                resolver.resolve_team(
                    team_id=t.id,
                    canonical_name=cname,
                    tier=ctier,
                    reason="User custom specification",
                    reviewed_by_user=True,
                )
                print(f"-> [RESOLVED] Set #{t.id} to '{cname}' (Tier {ctier}).")
                break

            elif ch_lower == "g":
                other_ids_str = input("Enter other Team IDs to group with this team (comma-separated): ").strip()
                if not other_ids_str:
                    print("[WARN] No IDs entered. Grouping cancelled.")
                    continue
                try:
                    all_ids = [t.id] + [int(x.strip()) for x in other_ids_str.split(",") if x.strip().isdigit()]
                except Exception as e:
                    print(f"[ERROR] Invalid IDs: {e}")
                    continue
                cname = input(f"Enter Canonical Name for this group (default '{cand.suggested_canonical_name}'): ").strip() or cand.suggested_canonical_name
                ctier = input(f"Enter Tier for this group (default '{cand.suggested_tier}'): ").strip().upper() or cand.suggested_tier
                if ctier not in VALID_TIERS:
                    print(f"[ERROR] Invalid tier '{ctier}'.")
                    continue
                grouped = resolver.group_teams(all_ids, canonical_name=cname, tier=ctier, reason="User manual group")
                print(f"-> [GROUPED] Successfully mapped {grouped} teams ({all_ids}) to '{cname}' (Tier {ctier}).")
                break

            elif ch_lower == "s":
                print("-> [SKIPPED]")
                break

            elif ch_lower == "q":
                print("[INFO] Exiting school review.")
                return

            else:
                print("[WARN] Unrecognized option. Try again.")


def manual_group_prompt(resolver: TeamResolver):
    """Prompt user to group any team IDs manually."""
    print("\n" + "=" * 60)
    print("             MANUAL TEAM GROUPING")
    print("=" * 60)
    ids_str = input("Enter comma-separated Team IDs (e.g. 76, 154, 261): ").strip()
    if not ids_str:
        return
    try:
        tids = [int(x.strip()) for x in ids_str.split(",") if x.strip().isdigit()]
    except Exception as e:
        print(f"[ERROR] Failed to parse IDs: {e}")
        return

    if not tids:
        print("[ERROR] No valid numeric IDs entered.")
        return

    print(f"\nSelected {len(tids)} team(s):")
    for tid in tids:
        s = resolver.get_team_summary(tid)
        if s:
            print(f"  * #{s.id} '{s.raw_name}' ({s.institution_name}) - {s.tournament_name}")
        else:
            print(f"  * #{tid} [NOT FOUND]")

    canon_name = input("\nEnter Canonical Group Name (e.g. 'BC A' or 'Bishop\'s College A'): ").strip()
    if not canon_name:
        print("[ERROR] Canonical name cannot be empty.")
        return

    tier = input("Enter Tier (A, B, C, D, NOVICE, SWING, OTHER): ").strip().upper()
    if tier not in VALID_TIERS:
        print(f"[ERROR] Invalid tier '{tier}'. Must be one of: {VALID_TIERS}")
        return

    cnt = resolver.group_teams(tids, canonical_name=canon_name, tier=tier, reason="Manual batch grouping", reviewed_by_user=True)
    print(f"[SUCCESS] Grouped {cnt} teams under '{canon_name}' (Tier {tier})!\n")


def view_audit_log(resolver: TeamResolver, limit: int = 25):
    """View recent resolutions audit entries."""
    audit = resolver.get_resolution_audit()
    if not audit:
        print("\n[INFO] No resolutions recorded yet.")
        return

    print("\n" + "=" * 105)
    print(f"                     ATOMOS TEAM RESOLUTION AUDIT LOG ({len(audit)} ENTRIES)")
    print("=" * 105)
    print(f"{'Team ID':<8} {'Raw Name':<16} {'Canonical Name':<18} {'Tier':<6} {'School':<26} {'Conf':<6} {'By User':<8}")
    print("-" * 105)
    for entry in audit[:limit]:
        raw = entry["raw_name"][:15]
        canon = entry["canonical_name"][:17]
        tier = entry["tier"] or "-"
        inst = (entry["institution_name"] or "None")[:24]
        conf = f"{entry['confidence']:.2f}" if entry["confidence"] is not None else "-"
        by_u = "YES" if entry["reviewed_by_user"] else "AUTO"
        print(f"#{entry['team_id']:<7} {raw:<16} {canon:<18} {tier:<6} {inst:<26} {conf:<6} {by_u:<8}")
        if entry["reason"]:
            print(f"   ↳ {entry['reason']}")
    print("=" * 105 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Atomos Team Resolver & Grouping CLI")
    parser.add_argument("--list", action="store_true", help="List institutions and resolution stats")
    parser.add_argument("--school", type=str, help="Filter or review teams for a specific institution")
    parser.add_argument("--auto-safe", action="store_true", help="Automatically resolve safe high-confidence teams")
    parser.add_argument("--group", type=str, help="Comma-separated Team IDs to group")
    parser.add_argument("--resolve", type=int, help="Single Team ID to resolve")
    parser.add_argument("--name", type=str, help="Canonical name for --group or --resolve")
    parser.add_argument("--tier", type=str, help="Tier for --group or --resolve (A, B, C, D, NOVICE, SWING, OTHER)")
    parser.add_argument("--reset", action="store_true", help="Reset resolutions back to NULL")
    args = parser.parse_args()

    conn = get_connection()
    resolver = TeamResolver(conn)

    # 1. Reset flag
    if args.reset:
        confirm = input("[CAUTION] Are you sure you want to reset ALL team resolutions? [y/N]: ").strip().lower()
        if confirm in ("y", "yes"):
            cnt = resolver.reset_resolutions()
            print(f"[SUCCESS] Cleared resolutions for {cnt} teams.")
        else:
            print("[INFO] Reset cancelled.")
        return

    # 2. Command-line single resolve
    if args.resolve:
        if not args.name or not args.tier:
            print("[ERROR] --resolve requires both --name and --tier.")
            return
        resolver.resolve_team(
            team_id=args.resolve,
            canonical_name=args.name,
            tier=args.tier,
            reason="CLI direct resolution",
            reviewed_by_user=True,
        )
        print(f"[SUCCESS] Resolved Team #{args.resolve} -> '{args.name}' (Tier {args.tier}).")
        return

    # 3. Command-line batch group
    if args.group:
        if not args.name or not args.tier:
            print("[ERROR] --group requires both --name and --tier.")
            return
        tids = [int(x.strip()) for x in args.group.split(",") if x.strip().isdigit()]
        cnt = resolver.group_teams(tids, canonical_name=args.name, tier=args.tier, reason="CLI batch group", reviewed_by_user=True)
        print(f"[SUCCESS] Grouped {cnt} teams into '{args.name}' (Tier {args.tier}).")
        return

    # 4. Auto-safe non-interactive flag
    if args.auto_safe:
        auto_resolve_safe_flow(resolver, interactive=False)
        return

    # 5. List flag
    if args.list:
        list_summary(resolver, school_filter=args.school)
        if args.school:
            show_school_teams(resolver, query=args.school)
        return

    # 6. School filter interactive review
    if args.school:
        institutions = resolver.get_institutions()
        matches = [
            i for i in institutions
            if args.school.lower() in i["name"].lower() or (i["code"] and args.school.lower() in i["code"].lower())
        ]
        if not matches:
            print(f"[ERROR] No institution found matching '{args.school}'.")
            return
        for m in matches:
            interactive_school_resolution(resolver, institution_id=m["id"])
        return

    # 7. Default Interactive Console Menu
    while True:
        insts = resolver.get_institutions()
        total_teams = sum(i["total_teams"] for i in insts)
        total_res = sum(i["resolved_teams"] for i in insts)
        total_pend = total_teams - total_res
        pct = int((total_res / total_teams) * 100) if total_teams else 0

        print("\n" + "=" * 85)
        print("                 ATOMOS TEAM RESOLVER & GROUPING CONSOLE")
        print(f"         Progress: {total_res}/{total_teams} teams resolved ({pct}%) | {total_pend} Pending")
        print("=" * 85)
        print("  [1] Auto-resolve safe teams (Standard Suffixes, Swings, Confirmed Aliases)")
        print("  [2] Interactively review pending teams by institution")
        print("  [3] Manually group teams by ID")
        print("  [4] Inspect teams for an institution")
        print("  [5] View resolution dashboard / list")
        print("  [6] View resolution audit history")
        print("  [Q] Exit")
        print("=" * 85)

        cmd = input("Select an option: ").strip().lower()
        if cmd == "1":
            auto_resolve_safe_flow(resolver, interactive=True)
        elif cmd == "2":
            # List institutions with pending teams
            pend_insts = [i for i in insts if i["pending_teams"] > 0]
            if not pend_insts:
                print("\n[SUCCESS] All teams across all institutions are resolved! Great work.")
                continue
            print(f"\nPending institutions ({len(pend_insts)}):")
            for idx, pi in enumerate(pend_insts[:15], 1):
                print(f"  [{idx}] {pi['name']} ({pi['code']}): {pi['pending_teams']} pending")
            sel = input("\nEnter number to review, or institution name/code (Enter=first): ").strip()
            if not sel:
                target_inst = pend_insts[0]["id"]
            elif sel.isdigit() and 1 <= int(sel) <= len(pend_insts):
                target_inst = pend_insts[int(sel) - 1]["id"]
            else:
                m = [i for i in pend_insts if sel.lower() in i["name"].lower() or (i["code"] and sel.lower() in i["code"].lower())]
                if m:
                    target_inst = m[0]["id"]
                else:
                    print("[WARN] School not found.")
                    continue
            interactive_school_resolution(resolver, institution_id=target_inst)
        elif cmd == "3":
            manual_group_prompt(resolver)
        elif cmd == "4":
            sch = input("Enter institution name or code (e.g. 'Bishop', 'LC', 'DS'): ").strip()
            if sch:
                show_school_teams(resolver, query=sch)
        elif cmd == "5":
            list_summary(resolver)
        elif cmd == "6":
            view_audit_log(resolver)
        elif cmd in ("q", "quit", "exit"):
            print("Exiting Team Resolver. Progress saved.")
            break
        else:
            print("[WARN] Invalid choice.")


if __name__ == "__main__":
    main()
