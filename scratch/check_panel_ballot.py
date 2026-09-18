import urllib.request
import re
import json

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode('utf-8', errors='replace')

# Look at round 5 (later rounds often have panels)
url_r5 = "https://vijis26.calicotab.com/vijis26/results/round/5/"
html_r5 = fetch(url_r5)

# Find ballot links in round 5
ballots = re.findall(r'href=[\'"]([^\'"]*results/debate/\d+/scoresheets/?)[\'"]', html_r5)
print(f"Found {len(ballots)} ballot links in Round 5")
if ballots:
    sample_url = "https://vijis26.calicotab.com" + ballots[0]
    print(f"Fetching sample ballot: {sample_url}")
    sample_html = fetch(sample_url)
    # Check if multiple scoresheets or adjudicators are mentioned
    scoresheet_count = len(re.findall(r'Scoresheet', sample_html))
    print(f"Scoresheet keyword count: {scoresheet_count}")
    # Print adjudicator lines
    for line in sample_html.splitlines():
        if any(w in line.lower() for w in ['adjudicator', 'chair', 'panel', 'scoresheet']):
            print("   ", re.sub(r'<[^>]+>', ' ', line).strip()[:100])
