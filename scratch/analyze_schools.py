import json
import re
from pathlib import Path

# Check AISDC institutions table first
aisdc_inst = json.load(open('data/raw/aisdc26/participants_institutions.json'))
print("=== AISDC Official Institutions List ===")
for r in aisdc_inst[0]['data']:
    code = r[0].get('text', '') if isinstance(r[0], dict) else str(r[0])
    name = r[1].get('text', '') if isinstance(r[1], dict) else str(r[1])
    print(f"   [{code}] {name}")

# Now let's analyze how team names and popover titles relate in VJIS 26
vijis_teams = json.load(open('data/raw/vijis26/team_tab.json'))
print("\n=== VJIS 26 Sample Team vs Popover Title ===")
for row in vijis_teams[0]['data'][:20]:
    t_cell = row[1]
    short_name = t_cell.get('text', '')
    full_title = t_cell.get('popover', {}).get('title', '')
    # Strip HTML entities like &#x27; -> '
    full_title = full_title.replace('&#x27;', "'").replace('&amp;', '&').replace('’', "'")
    print(f"   Short: {short_name:20} -> Full Title: {full_title}")
