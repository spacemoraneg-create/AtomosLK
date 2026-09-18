#!/usr/bin/env python3
"""
Atomos Interactive Identity Verification CLI

Allows interactive or automated review and merging of duplicate debater
and adjudicator records across the Atomos database.
"""

import argparse
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.database.connection import get_connection
from atomos.normalizer.identity_merger import IdentityMerger, CandidatePair, PersonSummary


def format_person_box(num: int, p: PersonSummary) -> str:
    lines = [
        f"  [{num}] ID: {p.id:<4} | Name: {p.canonical_name}",
        f"      Institution: {p.institution_str}",
        f"      Teams:       {p.team_str}",
        f"      Speeches:    {p.speech_count} across {len(p.tournaments)} tournament(s) ({p.tournament_str})",
    ]
    if p.sample_scores:
        lines.append(f"      Sample:      {p.sample_scores}")
    return "\n".join(lines)


def list_candidates(merger: IdentityMerger):
    """Print a clean summary list of all discovered candidate duplicate pairs."""
    candidates = merger.find_candidate_pairs()
    if not candidates:
        print("\n[INFO] No pending candidate duplicates found! All records are clean and resolved.")
        return

    print("\n" + "=" * 110)
    print(f"                       ATOMOS PENDING IDENTITY CANDIDATES ({len(candidates)} PAIRS)")
    print("=" * 110)
    print(f"{'#':<3} {'Type':<22} {'Person A':<26} {'Person B':<26} {'School':<24} {'Spk':<5}")
    print("-" * 110)

    for idx, c in enumerate(candidates, 1):
        p1, p2 = c.person_a, c.person_b
        name1 = f"#{p1.id} {p1.canonical_name}"[:25]
        name2 = f"#{p2.id} {p2.canonical_name}"[:25]
        inst = (p1.institution_str or p2.institution_str or "Unknown")[:23]
        spk_str = f"{p1.speech_count}+{p2.speech_count}"
        print(f"{idx:<3} {c.match_type:<22} {name1:<26} {name2:<26} {inst:<24} {spk_str:<5}")
        print(f"    ↳ Reason: {c.reason}")

    print("=" * 110)
    print("Run 'python scripts/verify_identities.py' to review and merge interactively,")
    print("or 'python scripts/verify_identities.py --auto-safe' to auto-merge exact matches.\n")


def auto_merge_safe_duplicates(merger: IdentityMerger, interactive: bool = True) -> int:
    """Find and merge all 100% safe exact matches (EXACT_CASE, SPACING_PUNCTUATION, NAME_INVERSION)."""
    candidates = merger.find_candidate_pairs()
    safe_types = {"EXACT_CASE", "SPACING_PUNCTUATION", "NAME_INVERSION"}
    safe_candidates = [c for c in candidates if c.match_type in safe_types]

    if not safe_candidates:
        print("[INFO] No exact case/spacing/inversion duplicates found.")
        return 0

    print(f"\n[NOTICE] Found {len(safe_candidates)} safe duplicate pair(s):")
    for c in safe_candidates:
        print(f"  * [{c.match_type}] #{c.person_a.id} '{c.person_a.canonical_name}' <-> #{c.person_b.id} '{c.person_b.canonical_name}' ({c.person_a.institution_str})")

    if interactive:
        ans = input("\nAuto-merge these safe pairs now? (Prefers the standard capitalized/full name) [Y/n]: ").strip().lower()
        if ans not in ("", "y", "yes"):
            print("[INFO] Skipped batch auto-merge.")
            return 0

    merged_count = 0
    for c in safe_candidates:
        p1, p2 = c.person_a, c.person_b
        # Choose canonical: more capital letters, longer name, or more speeches
        score1 = sum(1 for ch in p1.canonical_name if ch.isupper()) * 2 + len(p1.canonical_name) + p1.speech_count
        score2 = sum(1 for ch in p2.canonical_name if ch.isupper()) * 2 + len(p2.canonical_name) + p2.speech_count

        if score1 >= score2:
            canon_id, dup_id = p1.id, p2.id
            chosen_name = p1.canonical_name
        else:
            canon_id, dup_id = p2.id, p1.id
            chosen_name = p2.canonical_name

        try:
            merger.merge_persons(canonical_id=canon_id, duplicate_id=dup_id, canonical_name=chosen_name, check_collision=True)
            print(f"  [MERGED] Absorbed ID {dup_id} into ID {canon_id} as '{chosen_name}'")
            merged_count += 1
        except Exception as e:
            print(f"  [ERROR] Failed to merge ID {dup_id} into {canon_id}: {e}")

    print(f"[SUCCESS] Successfully merged {merged_count} safe duplicate(s).\n")
    return merged_count


def manual_merge_flow(merger: IdentityMerger):
    """Prompt user for two IDs and merge them."""
    print("\n" + "=" * 60)
    print("           MANUAL IDENTITY MERGE")
    print("=" * 60)
    id1_str = input("Enter Primary/Canonical Person ID: ").strip()
    id2_str = input("Enter Duplicate Person ID to Merge & Delete: ").strip()

    if not id1_str.isdigit() or not id2_str.isdigit():
        print("[ERROR] Invalid IDs entered. Must be numbers.")
        return

    id1, id2 = int(id1_str), int(id2_str)
    p1 = merger.get_person_summary(id1)
    p2 = merger.get_person_summary(id2)

    if not p1:
        print(f"[ERROR] Person with ID {id1} not found.")
        return
    if not p2:
        print(f"[ERROR] Person with ID {id2} not found.")
        return

    print("\nCanonical Target:")
    print(format_person_box(1, p1))
    print("\nDuplicate to be absorbed:")
    print(format_person_box(2, p2))

    confirm = input(f"\nAre you sure you want to merge #{id2} into #{id1}? [y/N]: ").strip().lower()
    if confirm in ("y", "yes"):
        try:
            merger.merge_persons(canonical_id=id1, duplicate_id=id2, check_collision=True)
            print(f"[SUCCESS] Successfully merged #{id2} into #{id1} ('{p1.canonical_name}').")
        except Exception as e:
            print(f"[ERROR] Merge failed: {e}")
    else:
        print("[INFO] Merge cancelled.")


def search_flow(merger: IdentityMerger, query: str):
    """Search persons and display matching summaries."""
    results = merger.search_persons(query)
    print(f"\n[SEARCH] Found {len(results)} match(es) for '{query}':")
    for idx, p in enumerate(results, 1):
        print(f"\nMatch #{idx}:")
        print(format_person_box(idx, p))


def interactive_verification_flow(merger: IdentityMerger):
    """Step through candidate pairs interactively."""
    # Step 1: Offer auto-merge for safe duplicates
    auto_merge_safe_duplicates(merger, interactive=True)

    # Step 2: Fetch remaining candidate pairs
    candidates = merger.find_candidate_pairs()
    if not candidates:
        print("\n[INFO] No pending identity candidates found! All records are resolved.")
        return

    total = len(candidates)
    print(f"\n========================================================================")
    print(f"       ATOMOS INTERACTIVE IDENTITY VERIFICATION ({total} CANDIDATES)")
    print(f"========================================================================")
    print("Review each pair and select an action:")
    print("  [1] Keep #1 (Merge #2 into #1)")
    print("  [2] Keep #2 (Merge #1 into #2)")
    print("  [N] No (Different people - record permanent rejection)")
    print("  [S] Skip for now")
    print("  [M] Custom name (Merge & set custom canonical name)")
    print("  [Q] Quit & Save progress\n")

    merged_count = 0
    rejected_count = 0
    skipped_count = 0

    for idx, cand in enumerate(candidates, 1):
        p1, p2 = cand.person_a, cand.person_b
        pct = int(cand.similarity * 100)

        # Suggest default recommendation
        rec = "1" if len(p1.canonical_name) >= len(p2.canonical_name) else "2"
        rec_name = p1.canonical_name if rec == "1" else p2.canonical_name

        print("-" * 80)
        print(f"[{idx}/{total}] Category: {cand.match_type} (Confidence: {pct}%)")
        print(f"Reason: {cand.reason}")
        print(f"Recommended: [{rec}] Keep '{rec_name}'")
        print("-" * 80)
        print(format_person_box(1, p1))
        print()
        print(format_person_box(2, p2))
        print("-" * 80)

        while True:
            choice = input(f"Action (Enter=[{rec}], [1]=Keep #1, [2]=Keep #2, [N]=No, [S]=Skip, [M]=Custom, [Q]=Quit): ").strip()
            ch_lower = choice.lower()

            if ch_lower == "":
                ch_lower = rec

            if ch_lower == "1":
                # Merge p2 into p1
                try:
                    merger.merge_persons(canonical_id=p1.id, duplicate_id=p2.id, check_collision=True)
                    print(f"-> [MERGED] Absorbed #{p2.id} into #{p1.id} ('{p1.canonical_name}').\n")
                    merged_count += 1
                except Exception as e:
                    print(f"-> [ERROR] Merge failed: {e}\n")
                break

            elif ch_lower == "2":
                # Merge p1 into p2
                try:
                    merger.merge_persons(canonical_id=p2.id, duplicate_id=p1.id, check_collision=True)
                    print(f"-> [MERGED] Absorbed #{p1.id} into #{p2.id} ('{p2.canonical_name}').\n")
                    merged_count += 1
                except Exception as e:
                    print(f"-> [ERROR] Merge failed: {e}\n")
                break

            elif ch_lower == "n":
                # Reject
                try:
                    merger.reject_match(p1.id, p2.id, reason="Marked different by user")
                    print(f"-> [REJECTED] Recorded #{p1.id} and #{p2.id} as different individuals.\n")
                    rejected_count += 1
                except Exception as e:
                    print(f"-> [ERROR] Rejection failed: {e}\n")
                break

            elif ch_lower == "s":
                print("-> [SKIPPED] Left pending.\n")
                skipped_count += 1
                break

            elif ch_lower == "m":
                cname = input("Enter custom canonical name: ").strip()
                if not cname:
                    print("[WARN] Empty name entered. Cancelled.")
                    continue
                keep = input(f"Merge into which ID? [1 for #{p1.id}, 2 for #{p2.id}]: ").strip()
                target_id = p2.id if keep == "2" else p1.id
                dup_id = p1.id if keep == "2" else p2.id
                try:
                    merger.merge_persons(canonical_id=target_id, duplicate_id=dup_id, canonical_name=cname, check_collision=True)
                    print(f"-> [MERGED] Consolidated as '{cname}' (ID {target_id}).\n")
                    merged_count += 1
                except Exception as e:
                    print(f"-> [ERROR] Merge failed: {e}\n")
                break

            elif ch_lower == "q":
                print("\n[INFO] Exiting verification session.")
                print(f"Session Summary: {merged_count} merged, {rejected_count} rejected, {skipped_count} skipped.")
                return

            else:
                print("[WARN] Invalid option. Please enter 1, 2, N, S, M, or Q.")

    print("\n" + "=" * 60)
    print(f"VERIFICATION COMPLETE: {merged_count} merged, {rejected_count} rejected, {skipped_count} skipped.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Atomos Identity Verification & Merger Tool")
    parser.add_argument("--db", type=str, default="data/atomos.db", help="Path to SQLite database")
    parser.add_argument("--list", action="store_true", help="List all pending duplicate candidates grouped by category")
    parser.add_argument("--auto-safe", action="store_true", help="Batch auto-merge exact case, spacing, and inverted name matches")
    parser.add_argument("--auto-case", action="store_true", help="Batch auto-merge exact case-insensitive duplicates")
    parser.add_argument("--manual", action="store_true", help="Manually merge two person IDs")
    parser.add_argument("--search", type=str, default=None, help="Search debaters by name")

    args = parser.parse_args()

    conn = get_connection(Path(args.db))
    merger = IdentityMerger(conn)

    try:
        if args.list:
            list_candidates(merger)
        elif args.auto_safe:
            auto_merge_safe_duplicates(merger, interactive=False)
        elif args.auto_case:
            auto_merge_safe_duplicates(merger, interactive=False)
        elif args.manual:
            manual_merge_flow(merger)
        elif args.search:
            search_flow(merger, args.search)
        else:
            interactive_verification_flow(merger)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
