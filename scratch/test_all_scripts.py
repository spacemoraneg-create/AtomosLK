"""
Automated CLI Script Audit for Atomos
Tests all scripts in scripts/ to ensure clean exit codes and error-free execution.
"""

import subprocess
import sys
from pathlib import Path

PYTHON_EXE = sys.executable
ROOT_DIR = Path(__file__).resolve().parent.parent

TEST_CASES = [
    # Script, Arguments, Expected exit code
    ("scripts/db_summary.py", [], 0),
    ("scripts/master_audit.py", [], 0),
    ("scripts/view_critical_stats.py", ["--limit", "3"], 0),
    ("scripts/view_identity.py", ["Balishta"], 0),
    ("scripts/view_judge.py", ["Minithi Hewage"], 0),
    ("scripts/view_judge.py", ["--top", "3"], 0),
    ("scripts/head_to_head.py", ["Royal", "Ananda", "--school"], 0),
    ("scripts/compare_schools.py", ["RC", "AC"], 0),
    ("scripts/institutional_leaderboard.py", ["--top", "5"], 0),
    ("scripts/motion_analysis.py", ["--side-bias"], 0),
    ("scripts/circuit_report.py", ["--top", "3"], 0),
    ("scripts/resolve_teams.py", ["--list"], 0),
    ("scripts/verify_identities.py", ["--list"], 0),
    ("scripts/export_web_data.py", [], 0),
    ("scripts/extract_tournament.py", ["--help"], 0),
    ("scripts/import_tournament.py", ["--help"], 0),
    ("scripts/normalize_tournament.py", ["--help"], 0),
    ("scripts/fix_round_motions.py", ["--help"], 0),
    ("scripts/ingest_circuit_tournament.py", ["--help"], 0),
    ("scripts/ask_atomos.py", ["--help"], 0),
]

def main():
    print(f"Auditing {len(TEST_CASES)} CLI script invocations...")
    failures = []
    for script_rel, args, expected_code in TEST_CASES:
        script_path = ROOT_DIR / script_rel
        cmd = [PYTHON_EXE, str(script_path)] + args
        print(f"[*] Testing {script_rel} {' '.join(args)}...", end=" ")
        try:
            res = subprocess.run(
                cmd,
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                timeout=45
            )
            if res.returncode == expected_code:
                print(f"[PASS] (exit {res.returncode})")
            else:
                print(f"[FAIL] (exit {res.returncode}, expected {expected_code})")
                print("--- STDERR ---")
                print(res.stderr[:500])
                print("--- STDOUT ---")
                print(res.stdout[:500])
                failures.append((script_rel, res.returncode, res.stderr))
        except Exception as e:
            print(f"[EXCEPTION] {e}")
            failures.append((script_rel, -1, str(e)))

    print("=" * 60)
    if not failures:
        print(f"ALL {len(TEST_CASES)} SCRIPT INVOCATIONS PASSED CLEANLY!")
        sys.exit(0)
    else:
        print(f"{len(failures)} / {len(TEST_CASES)} SCRIPT INVOCATIONS FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    main()
