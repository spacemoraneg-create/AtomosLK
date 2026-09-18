from test_vue_data import extract_tables_data, fetch
import json

# Check round 7 in SLSDC (final prelim round often paneled)
html = fetch("https://slsdc2026.calicotab.com/slsdc26/results/round/7/")
tables = extract_tables_data(html)
if tables:
    t = tables[0]
    col_keys = [c.get('key') for c in t['head']]
    print("Columns:", col_keys)
    adj_idx = col_keys.index('adjudicators') if 'adjudicators' in col_keys else -1
    ballot_idx = col_keys.index('ballot') if 'ballot' in col_keys else -1
    
    for row in t['data']:
        adj_cell = row[adj_idx]
        adj_text = adj_cell.get('text', '') if isinstance(adj_cell, dict) else str(adj_cell)
        # Look for commas or multiple names indicating a panel
        if ',' in adj_text or 'and' in adj_text or len(adj_cell.get('popover', {}).get('content', [])) > 1:
            ballot_link = row[ballot_idx].get('link') if isinstance(row[ballot_idx], dict) else None
            print(f"Paneled debate found! Adjudicators: {adj_text} -> Ballot: {ballot_link}")
            if ballot_link:
                # Fetch this ballot and check if multiple scoresheets exist
                b_html = fetch("https://slsdc2026.calicotab.com" + ballot_link)
                # Count scoresheets
                import re
                scoresheet_titles = re.findall(r'<h4[^>]*class="card-title"[^>]*>(.*?)</h4>', b_html, re.DOTALL)
                print(f"   Card titles in ballot: {[re.sub(r'<[^>]+>', '', s).strip() for s in scoresheet_titles]}")
            break
