from test_vue_data import fetch
import re

html_mot = fetch("https://slsdc2026.calicotab.com/slsdc26/motions/")
print("=== SLSDC Motions Page Sample ===")
for line in html_mot.splitlines():
    if any(k in line.lower() for k in ['round', 'this house', 'motion', 'infoslide']):
        clean = re.sub(r'<[^>]+>', ' ', line).strip()
        if clean:
            print("   ", clean[:120])

html_stat = fetch("https://slsdc2026.calicotab.com/slsdc26/motions/statistics/")
print("\n=== SLSDC Motion Stats Sample ===")
for line in html_stat.splitlines():
    if any(k in line.lower() for k in ['round', 'prop', 'opp', 'veto', 'balance', 'table']):
        clean = re.sub(r'<[^>]+>', ' ', line).strip()
        if clean:
            print("   ", clean[:120])
