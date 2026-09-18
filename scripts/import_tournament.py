#!/usr/bin/env python3
"""
Atomos Tournament Importer CLI

Allows importing tournaments into Atomos with a single command from the terminal.
Handles the entire pipeline: extraction -> normalization -> reconciliation -> validation.

Examples:
    # 1. Import a new tournament from public Tabbycat URL:
    python scripts/import_tournament.py "https://aisdc.calicotab.com/aisdc26/"

    # 2. Re-process an existing extracted tournament without re-downloading:
    python scripts/import_tournament.py --slug slsdc26 --skip-extract

    # 3. Import to a custom database file:
    python scripts/import_tournament.py "https://site.calicotab.com/tour26/" --db-path "data/custom.db"
"""

import argparse
import sys
from pathlib import Path

# Ensure src is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.pipeline.ingestion import IngestionPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Atomos Single-Command Tournament Ingestion Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="Public Tabbycat URL (e.g., https://site.calicotab.com/slug/) or tournament slug",
    )
    parser.add_argument(
        "--slug",
        "-s",
        help="Tournament slug (alternative to positional URL)",
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Skip web scraping and use existing raw JSON in data/raw/<slug>/",
    )
    parser.add_argument(
        "--db-path",
        default="data/atomos.db",
        help="Target SQLite database path (default: data/atomos.db)",
    )

    args = parser.parse_args()
    target = args.target or args.slug

    # If no URL or slug provided on command line, prompt interactively
    if not target:
        print("=" * 65)
        print("               ATOMOS TOURNAMENT INGESTION ENGINE")
        print("=" * 65)
        print("Paste the Tabbycat tournament URL below to import it into Atomos.")
        print("Example: https://aisdc.calicotab.com/aisdc26/")
        print("-" * 65)
        try:
            target = input("Enter Tabbycat URL or tournament slug: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[CANCELLED] Operation aborted by user.")
            sys.exit(0)

    # Clean target string (remove quotes, whitespace)
    target = target.strip("\"' ")

    if not target:
        print("\n[ERROR] No tournament URL or slug entered. Aborting.")
        sys.exit(1)

    # Determine slug and check if local data already exists
    possible_slug = target.rstrip("/").split("/")[-1] if "/" in target else target
    raw_dir = Path("data/raw") / possible_slug

    skip_extract = args.skip_extract
    if not skip_extract and raw_dir.exists() and not (args.target or args.slug):
        try:
            choice = input(
                f"\nFound existing data in data/raw/{possible_slug}.\n"
                f"Use existing local data without re-downloading? [Y/n]: "
            ).strip().lower()
            if choice in ("", "y", "yes"):
                skip_extract = True
        except (KeyboardInterrupt, EOFError):
            print("\n[CANCELLED] Operation aborted.")
            sys.exit(0)

    print("\n" + "=" * 65)
    print("           ATOMOS TOURNAMENT INGESTION ENGINE")
    print("=" * 65)
    print(f"Target:     {target}")
    print(f"Database:   {args.db_path}")
    print(f"Mode:       {'Re-process local data' if skip_extract else 'Full extraction + processing'}")
    print("-" * 65)

    pipeline = IngestionPipeline(db_path=Path(args.db_path))

    try:
        summary = pipeline.ingest_tournament(
            target=target,
            skip_extract=skip_extract,
            verbose=True,
        )

        print("-" * 60)
        print("          INGESTION SUCCESSFUL - TOURNAMENT METRICS")
        print("-" * 60)
        print(f"Tournament Name:     {summary['tournament_name']}")
        print(f"Slug:                {summary['slug']}")
        print(f"Total Rounds:        {summary['rounds_count']}")
        print(f"Teams Fielded:       {summary['teams_count']}")
        print(f"Debates Processed:   {summary['debates_count']}")
        print(f"Speeches Recorded:   {summary['speeches_recorded']}")
        print(f"Integrity Status:    {'CLEAN (0 Critical Errors)' if summary['is_valid'] else 'FLAGGED'}")
        print("=" * 60)

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"[FATAL ERROR] Ingestion failed: {e}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
