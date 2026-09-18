import sqlite3

conn = sqlite3.connect('data/atomos.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== ATOMOS DATABASE SUMMARY ===")
tables = [
    'tournaments', 'institutions', 'persons', 'teams', 
    'rounds', 'debates', 'adjudicator_ballots', 
    'speech_performances', 'identity_resolutions'
]
for t in tables:
    cur.execute(f"SELECT COUNT(*) as cnt FROM {t}")
    print(f"  {t}: {cur.fetchone()['cnt']}")

print("\n=== TOURNAMENTS INGESTED ===")
cur.execute("SELECT id, slug, name, year, scoring_scale FROM tournaments")
for r in cur.fetchall():
    print(f"  [{r['id']}] {r['slug']} - {r['name']} ({r['year']}) Scale: {r['scoring_scale']}")

print("\n=== IDENTITY RESOLUTIONS SAMPLE ===")
cur.execute("SELECT raw_name_a, raw_name_b, status, reason FROM identity_resolutions LIMIT 5")
for r in cur.fetchall():
    print(f"  {r['raw_name_a']} <-> {r['raw_name_b']} [{r['status']}] ({r['reason']})")
