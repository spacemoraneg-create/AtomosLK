import urllib.request
import json
from inspect_ballot import extract_tables_data, fetch

url = 'https://vijis26.calicotab.com/vijis26/results/debate/635036/scoresheets/'
html = fetch(url)
tables = extract_tables_data(html)
if tables:
    print(f'Found {len(tables)} tables on scoresheet page!')
    for idx, t in enumerate(tables):
        headers = [col.get('key', '') or col.get('tooltip', '') for col in t.get('head', [])]
        print(f'Table {idx} columns: {headers}')
        rows = t.get('data', [])
        print(f'Table {idx} rows: {len(rows)}')
        for r_idx, r in enumerate(rows):
            clean_row = [c.get('text', '') if isinstance(c, dict) else str(c) for c in r]
            print(f'   Row {r_idx}: {clean_row}')
else:
    print('No tablesData found, checking HTML snippet:')
    for line in html.splitlines():
        if any(k in line.lower() for k in ['score', 'adjudicator', 'ballot', 'substantive', 'reply', 'speaker', 'table']):
            if len(line.strip()) > 0:
                print(line.strip()[:140])
