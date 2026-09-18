import json
import glob
import re

def extract_school_and_team(short_name: str, full_title: str):
    clean_short = short_name.strip()
    clean_full = (
        full_title.replace('&#x27;', "'")
        .replace('&amp;', '&')
        .replace('’', "'")
        .replace('`', "'")
        .strip()
    )
    
    parts = clean_short.split()
    if len(parts) >= 2:
        code = parts[0]
        identifier = " ".join(parts[1:])
        
        # If full title ends with identifier
        if clean_full.endswith(identifier):
            school_name = clean_full[:-len(identifier)].strip()
            return code, school_name, identifier
        else:
            return code, clean_full, identifier
    else:
        return clean_short, clean_full, ""

schools = {}  # code/name -> count
teams_seen = []

for team_file in glob.glob('data/raw/*/team_tab*.json') + glob.glob('data/raw/*/tab_team*.json'):
    data = json.load(open(team_file))
    if data and 'data' in data[0]:
        for row in data[0]['data']:
            t_cell = None
            for cell in row:
                if isinstance(cell, dict) and 'team-name' in cell.get('class', ''):
                    t_cell = cell
                    break
            if not t_cell and len(row) > 1 and isinstance(row[1], dict):
                t_cell = row[1]
                
            if t_cell:
                short_name = t_cell.get('text', '')
                full_title = t_cell.get('popover', {}).get('title', '') or short_name
                code, school, ident = extract_school_and_team(short_name, full_title)
                schools[school] = schools.get(school, 0) + 1
                teams_seen.append((short_name, code, school, ident))

print(f"Total teams analyzed: {len(teams_seen)}")
print(f"Total UNIQUE actual schools: {len(schools)}")
print("\nUnique Schools List:")
for s, cnt in sorted(schools.items()):
    print(f"   - {s} ({cnt} teams)")
