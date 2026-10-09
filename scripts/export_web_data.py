#!/usr/bin/env python3
"""
Atomos Static Web Data Exporter

Exports fully precomputed JSON payloads from atomos.db into `data/web_export/`
for instant static site rendering, JAMstack hosting, or rapid frontend prototyping.

Usage:
    python scripts/export_web_data.py
    python scripts/export_web_data.py --output-dir dist/data
"""

import argparse
from datetime import datetime, timezone
import json
import sys
import time
from pathlib import Path

# Ensure src is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.database.connection import get_connection
from atomos.cache.precomputed import PrecomputedCache
from atomos.analytics.brackets import BracketEngine
from atomos.query import AtomosQuery


def export_web_data(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    cache = PrecomputedCache(conn)
    query = AtomosQuery(conn)

    print(f"\n==================================================================")
    print(f"           ATOMOS WEB DATA COMPILER & EXPORTER")
    print(f"           Target Directory: {output_dir}")
    print(f"==================================================================")

    # 1. Refresh precomputed database cache
    print("  [*] Precomputing heavy analytical rankings...")
    counts = cache.refresh_all()
    for key, count in counts.items():
        print(f"      - {key:<28}: {count} records cached")

    # 2. Export each dataset to static JSON file
    export_keys = [
        ("master_speaker_tab.json", "master_speaker_tab"),
        ("master_reply_tab.json", "master_reply_tab"),
        ("master_team_tab.json", "master_team_tab"),
        ("critical_speaker_stats.json", "critical_speaker_stats"),
        ("critical_team_stats.json", "critical_team_stats"),
        ("institutional_power_index.json", "institutional_power_index"),
        ("judge_leaderboard.json", "judge_leaderboard"),
        ("activity_leaderboard.json", "activity_leaderboard"),
        ("tournament_rankings.json", "tournament_rankings"),
        ("national_pool.json", "national_pool"),
        ("search_index.json", "search_index"),
        # V2 Multi Purpose Datasets
        ("v2_speakers_tab.json", "v2_speakers_tab"),
        ("v2_speakers_general.json", "v2_speakers_general"),
        ("v2_speakers_all.json", "v2_speakers_all"),
        ("v2_teams_tab.json", "v2_teams_tab"),
        ("v2_teams_general.json", "v2_teams_general"),
        ("v2_teams_all.json", "v2_teams_all"),
        ("v2_institutions_tab.json", "v2_institutions_tab"),
        ("v2_institutions_general.json", "v2_institutions_general"),
        ("v2_institutions_all.json", "v2_institutions_all"),
        ("v2_tournaments.json", "v2_tournaments"),
        ("v2_adjudicators.json", "v2_adjudicators"),
        ("v2_adjudicators_all.json", "v2_adjudicators_all"),
        ("v2_national_pool.json", "v2_national_pool"),
        ("v2_h2h_debates.json", "v2_h2h_debates"),
    ]

    print("\n  [*] Writing static JSON files to target...")
    for filename, cache_key in export_keys:
        data = cache.get(cache_key)
        target = output_dir / filename
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        size_kb = target.stat().st_size / 1024.0
        print(f"      + {filename:<32} -> {size_kb:6.1f} KB")

    # 3. Export all tournament knockout brackets
    print("\n  [*] Exporting tournament knockout brackets...")
    cur = conn.cursor()
    cur.execute("SELECT slug, name FROM tournaments ORDER BY id")
    tournaments = cur.fetchall()

    brackets_dir = output_dir / "brackets"
    brackets_dir.mkdir(parents=True, exist_ok=True)
    b_engine = BracketEngine(conn)

    exported_brackets = 0
    for t in tournaments:
        slug = t["slug"]
        b = b_engine.get_tournament_bracket(slug)
        if b:
            t_target = brackets_dir / f"{slug}_bracket.json"
            with open(t_target, "w", encoding="utf-8") as f:
                json.dump(b, f, indent=2, ensure_ascii=False)
            exported_brackets += 1
            print(f"      + {slug:<20} bracket exported ({len(b['stages'])} stages)")

    # 4. Circuit Summary Vitals
    summary = query.get_circuit_summary()
    with open(output_dir / "circuit_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"      + circuit_summary.json         -> {len(summary)} metrics")

    # 5. Export Manifest for Live + GitHub Synchronization
    manifest = {
        "version": int(time.time() * 1000),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": "spacemoraneg-create/AtomosLK",
        "branch": "main",
        "counts": {
            "tournaments": summary.get("total_tournaments", 0),
            "persons": summary.get("total_persons", 0),
            "institutions": summary.get("total_institutions", 0),
            "debates": summary.get("total_debates_debated", 0),
            "speeches": summary.get("total_speeches", 0),
        },
    }
    with open(output_dir / "export_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"      + export_manifest.json         -> version {manifest['version']}")

    print(f"\n==================================================================")
    print(f" [SUCCESS] Web data export complete! Total brackets: {exported_brackets}")
    print(f" All JSON payloads are 100% web-ready for Next.js / React / Vue.")
    print(f"==================================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Export Atomos web datasets")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/web_export"),
        help="Target directory for web JSON files (default: data/web_export)",
    )
    args = parser.parse_args()
    export_web_data(args.output_dir)


if __name__ == "__main__":
    main()
