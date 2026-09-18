"""
Atomos Tournament Normalization CLI Script

Usage:
    python scripts/normalize_tournament.py <raw_dir_or_slug> [--db-path <db_path>]
"""

import argparse
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.database.connection import initialize_database
from atomos.normalizer.tournament_normalizer import TournamentNormalizer
from atomos.normalizer.validator import IntegrityValidator


def main():
    parser = argparse.ArgumentParser(description="Normalize a raw Tabbycat tournament into SQLite")
    parser.add_argument("target", help="Path to raw tournament directory or slug in data/raw")
    parser.add_argument(
        "--db-path",
        default="data/atomos.db",
        help="Path to SQLite database (default: data/atomos.db)",
    )

    args = parser.parse_args()
    target_path = Path(args.target)
    if not target_path.exists():
        candidate = Path("data/raw") / args.target
        if candidate.exists():
            target_path = candidate
        else:
            print(f"Error: Target path {target_path} not found.")
            sys.exit(1)

    db_path = Path(args.db_path)
    print(f"[*] Initializing database at {db_path}...")
    conn = initialize_database(db_path)

    print(f"[*] Normalizing tournament from {target_path}...")
    normalizer = TournamentNormalizer(conn)
    t_id = normalizer.normalize_tournament(target_path)

    cur = conn.cursor()
    cur.execute("SELECT name, slug FROM tournaments WHERE id = ?", (t_id,))
    t_row = cur.fetchone()
    print(f"[+] Normalization complete for '{t_row['name']}' (slug: {t_row['slug']})")

    # Print summary statistics
    cur.execute("SELECT COUNT(*) as cnt FROM teams WHERE tournament_id = ?", (t_id,))
    teams_cnt = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(DISTINCT person_id) as cnt FROM tournament_roles WHERE tournament_id = ?", (t_id,))
    persons_cnt = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) as cnt FROM rounds WHERE tournament_id = ?", (t_id,))
    rounds_cnt = cur.fetchone()["cnt"]

    cur.execute(
        """
        SELECT COUNT(d.id) as cnt 
        FROM debates d 
        JOIN rounds r ON d.round_id = r.id 
        WHERE r.tournament_id = ?
        """,
        (t_id,),
    )
    debates_cnt = cur.fetchone()["cnt"]

    cur.execute(
        """
        SELECT COUNT(sp.id) as cnt 
        FROM speech_performances sp 
        JOIN rounds r ON sp.round_id = r.id 
        WHERE r.tournament_id = ?
        """,
        (t_id,),
    )
    speeches_cnt = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) as cnt FROM identity_resolutions WHERE status = 'PENDING_REVIEW'")
    pending_resolutions = cur.fetchone()["cnt"]

    print(f"    - Teams: {teams_cnt}")
    print(f"    - Participants: {persons_cnt}")
    print(f"    - Rounds: {rounds_cnt}")
    print(f"    - Debates: {debates_cnt}")
    print(f"    - Speech Performances (Atomic Marks): {speeches_cnt}")
    print(f"    - Identity Resolutions Pending Review: {pending_resolutions}")

    # Run Automated Integrity Gatekeeper
    validator = IntegrityValidator(conn)
    report = validator.validate(tournament_id=t_id)
    print("\n" + report.summary())

    if not report.is_valid:
        print("\n[!] WARNING: Ingestion completed with CRITICAL INTEGRITY ERRORS. Review the report above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

