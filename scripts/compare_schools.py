#!/usr/bin/env python3
"""
Atomos School vs. School Comparison CLI

Compares any two debating schools head-to-head:
1. Side-by-side standing, IPI rank, Elo, outround break rates, and squad depth
2. Direct encounters history between all teams from both schools
3. Records against mutual rival schools

Usage:
    python scripts/compare_schools.py "Royal College" "D. S. Senanayake College"
    python scripts/compare_schools.py "RC" "DS"
    python scripts/compare_schools.py "Ananda" "Trinity"
    python scripts/compare_schools.py
"""

import argparse
import dataclasses
import json
import sys
from pathlib import Path

# Add src and scripts to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from atomos.database.connection import get_connection
from atomos.analytics.institutions import InstitutionAnalytics
from institutional_leaderboard import render_school_comparison


def main():
    parser = argparse.ArgumentParser(
        description="Atomos School vs. School Head-to-Head Comparison CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("school_a", nargs="?", help="School 1 name or code (e.g. 'Royal', 'RC', 'Ananda')")
    parser.add_argument("school_b", nargs="?", help="School 2 name or code (e.g. 'DS', 'Trinity', 'Ladies')")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON for LLM querying")

    args = parser.parse_args()
    conn = get_connection()
    analytics = InstitutionAnalytics(conn)

    # Interactive mode if arguments are missing
    if not args.school_a or not args.school_b:
        if args.json:
            print(json.dumps({"error": "Both school_a and school_b are required when --json is used"}))
            sys.exit(1)
        print("=" * 60)
        print("          ATOMOS SCHOOL HEAD-TO-HEAD COMPARISON")
        print("=" * 60)
        sa_str = args.school_a or input("Enter School 1 (Name or Code, e.g. 'RC' or 'Royal'): ").strip()
        sb_str = input("Enter School 2 (Name or Code, e.g. 'DS' or 'Ananda'): ").strip()
        if not sa_str or not sb_str:
            print("[ERROR] Both school names or codes are required.")
            sys.exit(1)
        args.school_a = sa_str
        args.school_b = sb_str

    pa = analytics.get_institution_profile(args.school_a)
    pb = analytics.get_institution_profile(args.school_b)

    if not pa:
        if args.json:
            print(json.dumps({"error": f"Could not find any school matching '{args.school_a}'"}))
        else:
            print(f"[ERROR] Could not find any school matching '{args.school_a}'.")
        sys.exit(1)
    if not pb:
        if args.json:
            print(json.dumps({"error": f"Could not find any school matching '{args.school_b}'"}))
        else:
            print(f"[ERROR] Could not find any school matching '{args.school_b}'.")
        sys.exit(1)

    cmp_res = analytics.compare_institutions(pa.institution_id, pb.institution_id)
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


if __name__ == "__main__":
    main()
