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
    if idx == -1: return None
    start = idx + len(marker)
    open_bracket = html.find('[', start)
    if open_bracket == -1: return None
    count = 0; in_string = False; escape = False; end_bracket = -1
    for i in range(open_bracket, len(html)):
        char = html[i]
        if escape: escape = False; continue
        if char == '\\': escape = True; continue
        if char == '"': in_string = not in_string; continue
        if not in_string:
            if char == '[': count += 1
            elif char == ']':
                count -= 1
                if count == 0:
                    end_bracket = i + 1
                    break
    if end_bracket == -1: return None
    return json.loads(html[open_bracket:end_bracket])

html_r1 = fetch("https://vijis26.calicotab.com/vijis26/results/round/1/")
tables = extract_tables_data(html_r1)
if tables:
    r0 = tables[0]['data'][0]
    for idx, cell in enumerate(r0):
        col_name = tables[0]['head'][idx].get('key')
        print(f"Col '{col_name}': {json.dumps(cell, indent=2)}")
