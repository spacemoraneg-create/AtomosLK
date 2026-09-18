import urllib.request
# pure standard library
import json
import re

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode('utf-8', errors='replace')

# 1. Check slsdc2026 homepage
html_slsdc = fetch('https://slsdc2026.calicotab.com/')
print(f"=== SLSDC2026 Home Title & Links ===")
for line in html_slsdc.splitlines():
    if '<title>' in line or 'href=' in line:
        if any(term in line for term in ['tab', 'results', 'round', 'participants', 'slsdc']):
            print("   ", line.strip()[:150])

# 2. Check vijis26/tab/team/
html_team = fetch('https://vijis26.calicotab.com/vijis26/tab/team/')
print(f"\n=== VIJIS26 Team Tab Sample ===")
# Look for script tags with json or table data
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html_team, re.DOTALL)
print(f"Found {len(scripts)} script tags")
for i, s in enumerate(scripts):
    s_clean = s.strip()
    if any(k in s_clean for k in ['json', 'table', 'data', 'teams', 'rounds', 'Vue']):
        print(f"Script #{i} length {len(s_clean)}: {s_clean[:150]}...")

# Look for table headers
tables = re.findall(r'<table[^>]*>(.*?)</table>', html_team, re.DOTALL)
print(f"Found {len(tables)} tables")
for i, t in enumerate(tables):
    headers = re.findall(r'<th[^>]*>(.*?)</th>', t, re.DOTALL)
    clean_headers = [re.sub(r'<[^>]+>', '', h).strip() for h in headers]
    print(f"Table #{i} headers: {clean_headers[:10]}")

# 3. Check round 1 results
html_r1 = fetch('https://vijis26.calicotab.com/vijis26/results/round/1/')
print(f"\n=== VIJIS26 Round 1 Results Sample ===")
r1_tables = re.findall(r'<table[^>]*>(.*?)</table>', html_r1, re.DOTALL)
for i, t in enumerate(r1_tables):
    headers = re.findall(r'<th[^>]*>(.*?)</th>', t, re.DOTALL)
    clean_headers = [re.sub(r'<[^>]+>', '', h).strip() for h in headers]
    print(f"R1 Table #{i} headers: {clean_headers[:10]}")
    # Show first row
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.DOTALL)
    if len(rows) > 1:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', rows[1], re.DOTALL)
        clean_cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        print(f"R1 Table #{i} row 1: {clean_cells[:8]}")
        # Look for links in the row
        links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', rows[1])
        print(f"R1 Table #{i} row 1 links: {links}")
