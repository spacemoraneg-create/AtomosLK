import urllib.request
from inspect_ballot import fetch
import re

url = 'https://vijis26.calicotab.com/vijis26/results/debate/635036/scoresheets/'
html = fetch(url)

# Find all tables in the HTML
tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
print(f"Scoresheet page has {len(tables)} HTML tables.")

for idx, t in enumerate(tables):
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.DOTALL)
    print(f"\n--- HTML Table {idx} ({len(rows)} rows) ---")
    for r_idx, r in enumerate(rows):
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.DOTALL)
        clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        print(f"Row {r_idx}: {clean}")
