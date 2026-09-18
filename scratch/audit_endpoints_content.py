import urllib.request
from test_vue_data import extract_tables_data, fetch

test_urls = [
    # Novice tabs on APIIT
    ("APIIT Novice Team Tab", "https://apiitisdc2026.calicotab.com/apiitisdc2026/tab/team/novice/"),
    ("APIIT Novice Speaker Tab", "https://apiitisdc2026.calicotab.com/apiitisdc2026/tab/speaker/novice/"),
    # Institutions on AISDC
    ("AISDC Institutions", "https://aisdc.calicotab.com/aisdc26/participants/institutions/"),
    # Motions on SLSDC
    ("SLSDC Motions", "https://slsdc2026.calicotab.com/slsdc26/motions/"),
    ("SLSDC Motion Stats", "https://slsdc2026.calicotab.com/slsdc26/motions/statistics/"),
    # Break on VJIS
    ("VIJIS Break Teams", "https://vijis26.calicotab.com/vijis26/break/teams/open/"),
]

for label, url in test_urls:
    try:
        html = fetch(url)
        tables = extract_tables_data(html)
        if tables:
            headers = [c.get('key','') or c.get('tooltip','') for c in tables[0]['head']]
            print(f"[OK] {label} -> {len(tables)} tables, {len(tables[0]['data'])} rows. Headers: {headers}")
        else:
            print(f"[NO-TABLES] {label} -> {len(html)} bytes HTML")
    except Exception as e:
        print(f"[ERR] {label} -> {e}")
