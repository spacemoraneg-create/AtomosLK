from test_vue_data import extract_tables_data, fetch

urls = [
    'https://slsdc2026.calicotab.com/slsdc26/tab/team/',
    'https://slsdc2026.calicotab.com/slsdc26/tab/speaker/',
    'https://slsdc2026.calicotab.com/slsdc26/tab/replies/',
    'https://slsdc2026.calicotab.com/slsdc26/results/round/1/',
]

for u in urls:
    try:
        html = fetch(u)
        tables = extract_tables_data(html)
        cols = [c.get('key','') or c.get('tooltip','') for c in tables[0]['head']] if tables else []
        row_count = len(tables[0]['data']) if tables else 0
        print(f"{u} -> {len(tables)} tables, cols: {cols[:6]} ({row_count} rows)")
    except Exception as e:
        print(f"{u} -> Err: {e}")
