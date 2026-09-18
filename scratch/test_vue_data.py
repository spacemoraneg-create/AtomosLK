import urllib.request
import json
import re

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode('utf-8', errors='replace')

def extract_tables_data(html):
    marker = 'tablesData:'
    idx = html.find(marker)
    if idx == -1:
        return None
    start = idx + len(marker)
    open_bracket = html.find('[', start)
    if open_bracket == -1:
        return None
    
    count = 0
    in_string = False
    escape = False
    end_bracket = -1
    
    for i in range(open_bracket, len(html)):
        char = html[i]
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char == '[':
                count += 1
            elif char == ']':
                count -= 1
                if count == 0:
                    end_bracket = i + 1
                    break
                    
    if end_bracket == -1:
        return None
        
    tables_json = html[open_bracket:end_bracket]
    return json.loads(tables_json)

urls = [
    ("Team Tab", "https://vijis26.calicotab.com/vijis26/tab/team/"),
    ("Speaker Tab", "https://vijis26.calicotab.com/vijis26/tab/speaker/"),
    ("Round 1 Results", "https://vijis26.calicotab.com/vijis26/results/round/1/"),
    ("Participants List", "https://vijis26.calicotab.com/vijis26/participants/list/"),
    ("SLSDC Replies Tab", "https://slsdc2026.calicotab.com/slsdc26/tab/replies/"),
]

for label, url in urls:
    print(f"\n=================== {label} ({url}) ===================")
    html = fetch(url)
    tables = extract_tables_data(html)
    if tables is not None:
        print(f"Extracted {len(tables)} tables")
        for idx, t in enumerate(tables):
            headers = [col.get('key', '') or col.get('tooltip', '') for col in t.get('head', [])]
            rows = t.get('data', [])
            print(f"Table {idx} columns: {headers}")
            print(f"Table {idx} rows: {len(rows)}")
            if rows:
                print("Row 0 sample data:", json.dumps(rows[0], indent=2)[:600])
    else:
        print("Could not extract tablesData")
