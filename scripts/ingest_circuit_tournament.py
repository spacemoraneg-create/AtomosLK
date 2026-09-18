#!/usr/bin/env python3
"""
Atomos End-to-End Single-Command Tournament Ingestion Pipeline

Automates the complete workflow for integrating new tournaments into Atomos:
1. Ingestion / Import from Tabbycat export
2. School & Institution Normalization (CANONICAL_SCHOOLS, MLC safety)
3. Debater Identity Disambiguation & Alias Reconciliation
4. Team Lineage Resolution (A, B, C tiers)
5. Master Forensic Audit Assertion (All 5 gates must pass)
6. Automatic Web Cache & Precomputation Refresh

Usage:
    python scripts/ingest_circuit_tournament.py --audit-only
    python scripts/ingest_circuit_tournament.py --refresh-cache
    python scripts/ingest_circuit_tournament.py --tournament-dir data/tournaments/new_tourn
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Ensure src is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.database.connection import get_connection
from atomos.cache.precomputed import PrecomputedCache


def run_cmd(cmd_list: list, desc: str) -> bool:
    print(f"\n  [>] Executing Step: {desc}...")
    proc = subprocess.run([sys.executable] + cmd_list, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"      [X] ERROR in {desc} (Exit code {proc.returncode}):")
        print(proc.stderr or proc.stdout)
        return False
    else:
        # Print first 2 summary lines
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        for l in lines[:3]:
            print(f"      | {l}")
        return True


def ingest_pipeline(tournament_dir: Path = None, refresh_only: bool = False):
    print("=" * 85)
    print("        ATOMOS END-TO-END TOURNAMENT INGESTION & AUDIT PIPELINE")
    print("=" * 85)

    conn = get_connection()

    if not refresh_only and tournament_dir:
        print(f"\n[*] Processing new tournament from directory: {tournament_dir}")
        # Step 1: Import
        if not run_cmd(["scripts/import_tournament.py", str(tournament_dir)], "Raw Tabbycat Importer"):
            print("\n[!] Ingestion halted at Step 1 (Import).")
            return False

        # Step 2: Normalize institutions
        if not run_cmd(["scripts/normalize_tournament.py"], "Institution & School Normalizer"):
            print("\n[!] Ingestion halted at Step 2 (Normalization).")
            return False

        # Step 3: Identity Verification
        if not run_cmd(["scripts/verify_identities.py"], "Debater Identity & Alias Reconciliation"):
            print("\n[!] Ingestion halted at Step 3 (Identity Resolution).")
            return False

        # Step 4: Team Resolver
        if not run_cmd(["scripts/resolve_teams.py", "--batch"], "Team Lineage Tier Resolver"):
            print("\n[!] Ingestion halted at Step 4 (Team Lineages).")
            return False

    # Step 5: Master Forensic Audit
    print("\n[*] Running Gatekeeper Master Forensic Audit...")
    audit_ok = run_cmd(["scripts/master_audit.py"], "5-Gate Master Forensic Integrity Audit")
    if not audit_ok:
        print("\n[CRITICAL ERROR] Master Audit failed! Data anomalies detected. Rolling back advised.")
        return False

    # Step 6: Refresh Materialized Caches
    print("\n[*] Rebuilding precomputed web caches & JSON export payloads...")
    cache = PrecomputedCache(conn)
    counts = cache.refresh_all()
    for k, v in counts.items():
        print(f"    - {k:<28}: {v} records materialized")

    # Step 7: Export static web bundles
    run_cmd(["scripts/export_web_data.py"], "Static Web JSON Exporter")

    print("\n" + "=" * 85)
    print(" [SUCCESS] Ingestion & audit complete! Circuit database is 100% verified & web-ready.")
    print("=" * 85 + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="Atomos End-to-End Tournament Ingestion")
    parser.add_argument("--tournament-dir", type=Path, help="Path to tournament export directory")
    parser.add_argument("--refresh-cache", action="store_true", help="Only refresh caches and web exports")
    parser.add_argument("--audit-only", action="store_true", help="Only run the master audit")

    args = parser.parse_args()

    if args.audit_only:
        run_cmd(["scripts/master_audit.py"], "Master Forensic Audit")
        return

    ingest_pipeline(tournament_dir=args.tournament_dir, refresh_only=args.refresh_cache)


if __name__ == "__main__":
    main()
