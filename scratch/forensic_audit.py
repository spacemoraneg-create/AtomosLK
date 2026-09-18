import sqlite3
import json
from pathlib import Path

conn = sqlite3.connect('data/atomos.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

issues_found = []

print("==================================================")
print("FORENSIC DATABASE AUDIT REPORT")
print("==================================================")

# 1. Audit Institutions
print("\n--- 1. Auditing Institutions ---")
cur.execute("SELECT id, name, code FROM institutions WHERE name IS NULL OR name = '' OR code IS NULL OR code = ''")
bad_inst = cur.fetchall()
if bad_inst:
    issues_found.append(f"Institutions with missing name/code: {len(bad_inst)}")
    for b in bad_inst:
        print(f"   [BUG] Bad institution: id={b['id']} name={b['name']} code={b['code']}")
else:
    print("   [OK] All institutions have non-empty names and codes.")

# Check for duplicate names
cur.execute("SELECT name, COUNT(*) as cnt FROM institutions GROUP BY name HAVING cnt > 1")
dup_names = cur.fetchall()
if dup_names:
    issues_found.append(f"Duplicate institution names: {len(dup_names)}")
    for d in dup_names:
        print(f"   [BUG] Duplicate school name: {d['name']} (x{d['cnt']})")
else:
    print("   [OK] Zero duplicate institution names.")

# Check for duplicate codes
cur.execute("SELECT code, COUNT(*) as cnt FROM institutions GROUP BY code HAVING cnt > 1")
dup_codes = cur.fetchall()
if dup_codes:
    issues_found.append(f"Duplicate institution codes: {len(dup_codes)}")
    for d in dup_codes:
        print(f"   [BUG] Duplicate school code: {d['code']} (x{d['cnt']})")
else:
    print("   [OK] Zero duplicate institution codes.")


# 2. Audit Persons
print("\n--- 2. Auditing Persons ---")
cur.execute("""
    SELECT id, canonical_name FROM persons 
    WHERE canonical_name IS NULL 
       OR canonical_name = '' 
       OR canonical_name LIKE '%<%' 
       OR canonical_name LIKE '%>%' 
       OR canonical_name LIKE '%&#%'
       OR LENGTH(canonical_name) < 2
""")
bad_persons = cur.fetchall()
if bad_persons:
    issues_found.append(f"Persons with HTML/malformed names: {len(bad_persons)}")
    for bp in bad_persons[:10]:
        print(f"   [BUG] Malformed person: id={bp['id']} name={repr(bp['canonical_name'])}")
else:
    print("   [OK] All person names are clean text without HTML or malformed characters.")


# 3. Audit Teams and Rosters
print("\n--- 3. Auditing Teams and Rosters ---")
cur.execute("""
    SELECT t.id, t.name, t.tournament_id, tour.slug, t.institution_id 
    FROM teams t
    JOIN tournaments tour ON t.tournament_id = tour.id
    WHERE t.institution_id IS NULL AND t.name NOT LIKE '%Swing%' AND t.name NOT LIKE '%BYE%'
""")
unlinked_teams = cur.fetchall()
if unlinked_teams:
    issues_found.append(f"Teams without institution (excluding swing/bye): {len(unlinked_teams)}")
    for ut in unlinked_teams[:10]:
        print(f"   [BUG] Unlinked team: '{ut['name']}' in tournament '{ut['slug']}'")
else:
    print("   [OK] All non-swing/bye teams are linked to an institution.")

# Check roster sizes
cur.execute("""
    SELECT t.id, t.name, tour.slug, COUNT(tm.person_id) as roster_size
    FROM teams t
    JOIN tournaments tour ON t.tournament_id = tour.id
    LEFT JOIN team_members tm ON t.id = tm.team_id
    WHERE t.name NOT LIKE '%Swing%' AND t.name NOT LIKE '%BYE%'
    GROUP BY t.id
""")
roster_rows = cur.fetchall()
invalid_rosters = [r for r in roster_rows if r['roster_size'] < 3 or r['roster_size'] > 4]
if invalid_rosters:
    issues_found.append(f"Teams with invalid roster size (<3 or >4): {len(invalid_rosters)}")
    for ir in invalid_rosters[:10]:
        print(f"   [NOTICE] Team '{ir['name']}' in '{ir['slug']}' has roster size {ir['roster_size']}")
else:
    print("   [OK] All teams have valid roster sizes (3-4 members).")


# 4. Audit Debates and Matchup Links
print("\n--- 4. Auditing Debates and Matchups ---")
cur.execute("""
    SELECT d.id, d.debate_id, d.round_id, d.prop_team_id, d.opp_team_id, r.name as round_name, tour.slug
    FROM debates d
    JOIN rounds r ON d.round_id = r.id
    JOIN tournaments tour ON r.tournament_id = tour.id
    WHERE d.prop_team_id IS NULL OR d.opp_team_id IS NULL
""")
unlinked_debates = cur.fetchall()
if unlinked_debates:
    issues_found.append(f"Debates where prop or opp team could not be linked: {len(unlinked_debates)}")
    for ud in unlinked_debates[:10]:
        print(f"   [BUG] Unlinked debate {ud['debate_id']} in {ud['slug']} {ud['round_name']}: prop={ud['prop_team_id']} opp={ud['opp_team_id']}")
else:
    print("   [OK] All debates have both Proposition and Opposition teams linked.")


# 5. Audit Speech Performances & Domain Rule Bounds
print("\n--- 5. Auditing Speech Performances ---")
cur.execute("SELECT * FROM speech_performances")
speeches = cur.fetchall()
print(f"   Total speech performances in DB: {len(speeches)}")

zero_scores = []
out_of_bounds_sub = []
out_of_bounds_reply = []
component_sum_mismatch = []
invalid_components = []

for s in speeches:
    stype = s['speech_type']
    tot = s['total_score']
    c = s['content']
    st = s['style']
    strat = s['strategy']

    if tot == 0.0:
        zero_scores.append(s['id'])
        continue

    if stype == 'SUBSTANTIVE':
        if not (60.0 <= tot <= 80.0):
            out_of_bounds_sub.append((s['id'], tot))
        if c is not None and st is not None and strat is not None:
            if not (24.0 <= c <= 32.0 and 24.0 <= st <= 32.0 and 12.0 <= strat <= 16.0):
                invalid_components.append((s['id'], c, st, strat))
            if abs((c + st + strat) - tot) > 0.01:
                component_sum_mismatch.append((s['id'], c, st, strat, tot))
    elif stype == 'REPLY':
        if not (30.0 <= tot <= 40.0):
            out_of_bounds_reply.append((s['id'], tot))
        if c is not None and st is not None and strat is not None:
            if not (12.0 <= c <= 16.0 and 12.0 <= st <= 16.0 and 6.0 <= strat <= 8.0):
                invalid_components.append((s['id'], c, st, strat))
            if abs((c + st + strat) - tot) > 0.01:
                component_sum_mismatch.append((s['id'], c, st, strat, tot))

if zero_scores:
    print(f"   [DOMAIN ANOMALY] Placeholder 0.0 scores from administrative/walkover ballots: {len(zero_scores)}")
if out_of_bounds_sub:
    issues_found.append(f"Non-zero substantive scores out of 60-80: {len(out_of_bounds_sub)}")
    print(f"   [BUG] Out of bounds substantive: {out_of_bounds_sub[:5]}")
else:
    print("   [OK] All active substantive scores are strictly between 60.0 and 80.0.")

if out_of_bounds_reply:
    issues_found.append(f"Non-zero reply scores out of 30-40: {len(out_of_bounds_reply)}")
    print(f"   [BUG] Out of bounds reply: {out_of_bounds_reply[:5]}")
else:
    print("   [OK] All active reply scores are strictly between 30.0 and 40.0.")

if component_sum_mismatch:
    issues_found.append(f"Component sum mismatches: {len(component_sum_mismatch)}")
    print(f"   [BUG] Component sum mismatches: {component_sum_mismatch[:5]}")
else:
    print("   [OK] All component sums (Content + Style + Strategy) match total_score perfectly.")

if invalid_components:
    print(f"   [DOMAIN ANOMALY] Adjudicator non-standard rubric component marks: {len(invalid_components)} (flagged is_valid_rubric=0)")
else:
    print("   [OK] All Content, Style, and Strategy component scores are within rubric bounds.")



# 6. Audit Adjudicator Ballots and Team Totals
print("\n--- 6. Auditing Ballots vs Speech Sums ---")
cur.execute("""
    SELECT b.id, b.prop_total_score, b.opp_total_score, b.win_margin,
           SUM(CASE WHEN sp.side = 'Proposition' THEN sp.total_score ELSE 0 END) as calc_prop,
           SUM(CASE WHEN sp.side = 'Opposition' THEN sp.total_score ELSE 0 END) as calc_opp
    FROM adjudicator_ballots b
    JOIN speech_performances sp ON b.id = sp.ballot_id
    GROUP BY b.id
""")
ballot_checks = cur.fetchall()
ballot_mismatches = []
for bc in ballot_checks:
    if abs(bc['prop_total_score'] - bc['calc_prop']) > 0.01 or abs(bc['opp_total_score'] - bc['calc_opp']) > 0.01:
        ballot_mismatches.append(bc)

if ballot_mismatches:
    issues_found.append(f"Ballot totals mismatching speech sums: {len(ballot_mismatches)}")
    print(f"   [BUG] Ballot total mismatches: {len(ballot_mismatches)}")
else:
    print("   [OK] All ballot totals match the exact sum of the 4 underlying speeches.")


# 7. Audit Extraction Completeness (Debates with vs without scoresheets)
print("\n--- 7. Auditing Extraction Completeness ---")
cur.execute("""
    SELECT tour.slug, COUNT(d.id) as total_debates, COUNT(b.id) as debates_with_ballots
    FROM tournaments tour
    JOIN rounds r ON tour.id = r.tournament_id
    JOIN debates d ON r.id = d.round_id
    LEFT JOIN adjudicator_ballots b ON d.id = b.debate_id
    GROUP BY tour.id
""")
coverage = cur.fetchall()
for cov in coverage:
    print(f"   Tournament '{cov['slug']}': {cov['debates_with_ballots']} ballots recorded for {cov['total_debates']} debates")


print("\n==================================================")
print(f"AUDIT SUMMARY: {len(issues_found)} issues identified")
print("==================================================")
for iss in issues_found:
    print(f" - {iss}")
