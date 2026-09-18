from test_vue_data import fetch
import re

html = fetch("https://slsdc2026.calicotab.com/slsdc26/results/debate/676447/scoresheets/")

# Find all cards
cards = re.findall(r'<div class="card mt-3">(.*?)</div>\s*</div>\s*(?=<div class="card mt-3"|</body>|</main>)', html, re.DOTALL)
print(f"Found {len(cards)} card containers")

# Also look for card headers
titles = re.findall(r'<h4[^>]*class="card-title"[^>]*>(.*?)</h4>', html, re.DOTALL)
print("Card titles:", [re.sub(r'<[^>]+>', '', t).strip() for t in titles])

for i, t in enumerate(titles):
    clean_t = re.sub(r'<[^>]+>', '', t).strip()
    print(f"\n--- Card {i}: {clean_t} ---")
