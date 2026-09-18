"""
Atomos Tournament Extraction Script

Usage:
    python scripts/extract_tournament.py <url> [--output-dir <dir>] [--sample-ballots <n>]
"""

import argparse
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.extractor.tabbycat import TabbycatExtractor


def main():
    parser = argparse.ArgumentParser(description="Extract tournament data from Tabbycat")
    parser.add_argument("url", help="Base URL or homepage of the tournament")
    parser.add_argument(
        "--output-dir",
        default="data/raw",
        help="Directory to save raw extracted data (default: data/raw)",
    )
    parser.add_argument(
        "--sample-ballots",
        type=int,
        default=None,
        help="Max ballots to extract per round (omit to extract all)",
    )

    args = parser.parse_args()
    output_path = Path(args.output_dir)

    print(f"[*] Initializing TabbycatExtractor...")
    extractor = TabbycatExtractor()

    print(f"[*] Extracting tournament from {args.url}...")
    data = extractor.extract_tournament(
        base_url=args.url,
        output_dir=output_path,
        max_ballots_per_round=args.sample_ballots,
    )

    meta = data["metadata"]
    print(f"[+] Extraction complete for '{meta['title']}' (slug: {meta['slug']})")
    print(f"    - Output Directory: {output_path / meta['slug']}")
    print(f"    - Tabs Extracted: {list(data['tabs'].keys())}")
    print(f"    - Rounds Extracted: {list(data['rounds'].keys())}")
    total_debates = len(data.get("debates", []))
    total_ballots = sum(len(d.get("ballots", [])) for d in data.get("debates", []))
    print(f"    - Debates Extracted: {total_debates}")
    print(f"    - Total Adjudicator Ballots Extracted: {total_ballots}")


if __name__ == "__main__":
    main()
