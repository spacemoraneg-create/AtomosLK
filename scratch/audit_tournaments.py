import urllib.request
import re
import json

tournaments = [
    ("AISDC 2026", "https://aisdc.calicotab.com/aisdc26"),
    ("APIIT ISDC 2026", "https://apiitisdc2026.calicotab.com/apiitisdc2026"),
    ("SLSDC 2026", "https://slsdc2026.calicotab.com/slsdc26"),
    ("VIJIS 2026", "https://vijis26.calicotab.com/vijis26"),
]

for name, base_url in tournaments:
    print(f"\n==================================================")
    print(f"Auditing: {name} ({base_url})")
    print(f"==================================================")
    url = base_url if base_url.endswith('/') else base_url + '/'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='replace')
            
        # Title
        t_match = re.search(r'<title>\s*(.*?)\s*</title>', html, re.DOTALL)
        title = re.sub(r'\s+', ' ', t_match.group(1)).strip() if t_match else "Unknown"
        print(f"Title: {title}")
        
        # Discover all href links in navbar
        links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', html)
        interesting = []
        for l in links:
            if any(term in l for term in ['tab', 'results', 'break', 'participants', 'motions', 'draw']):
                if l not in interesting:
                    interesting.append(l)
        print(f"Discovered {len(interesting)} key navigation links:")
        for l in sorted(interesting):
            print(f"   {l}")
            
    except Exception as e:
        print(f"Error fetching {name}: {e}")
