import urllib.request
import re
import json

def parse_scoresheet_html(html: str) -> dict:
    result = {
        "title": "",
        "round_info": "",
        "motion": "",
        "proposition": {"team": "", "total": None, "speeches": []},
        "opposition": {"team": "", "total": None, "speeches": []},
    }
    
    # Title: Ballot for Team A vs Team B
    m_title = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL) or re.search(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL)
    if m_title:
        result["title"] = re.sub(r'<[^>]+>', '', m_title.group(1)).strip()
        
    # Motion
    m_mot = re.search(r'<div[^>]*class="[^"]*motion[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL) or re.search(r'Motion\s*</div>\s*<div[^>]*>(.*?)</div>', html, re.DOTALL)
    if m_mot:
        result["motion"] = re.sub(r'<[^>]+>', '', m_mot.group(1)).strip()
        
    # Let's extract clean text lines from the main container
    lines = [re.sub(r'<[^>]+>', '', l).strip() for l in html.splitlines()]
    lines = [l for l in lines if l]
    
    # Let's parse speech blocks
    # Looking for sequence: (1st|2nd|3rd|Reply) -> Speaker -> Total -> Content -> val -> Style -> val -> Strategy -> val
    speeches = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line in ["1st", "2nd", "3rd", "Reply"]:
            pos = line
            speaker = lines[i+1] if i+1 < len(lines) else ""
            total_score = float(lines[i+2]) if i+2 < len(lines) and lines[i+2].replace('.', '', 1).isdigit() else None
            
            content = None
            style = None
            strategy = None
            
            # Look ahead for Content, Style, Strategy
            j = i + 3
            while j < min(i + 12, len(lines)):
                if lines[j] == "Content" and j+1 < len(lines):
                    try: content = float(lines[j+1])
                    except: pass
                elif lines[j] == "Style" and j+1 < len(lines):
                    try: style = float(lines[j+1])
                    except: pass
                elif lines[j] == "Strategy" and j+1 < len(lines):
                    try: strategy = float(lines[j+1])
                    except: pass
                j += 1
                
            speeches.append({
                "position": pos,
                "speaker": speaker,
                "total": total_score,
                "content": content,
                "style": style,
                "strategy": strategy,
            })
            i = j - 1
        i += 1
        
    # If 8 speeches found: first 4 are Proposition, next 4 are Opposition
    if len(speeches) == 8:
        result["proposition"]["speeches"] = speeches[:4]
        result["opposition"]["speeches"] = speeches[4:]
    else:
        result["all_speeches"] = speeches
        
    # Team totals
    for l in lines:
        m_prop = re.search(r'Total for (.*?) \(Proposition\)', l)
        if m_prop:
            result["proposition"]["team"] = m_prop.group(1).strip()
        m_opp = re.search(r'Total for (.*?) \(Opposition\)', l)
        if m_opp:
            result["opposition"]["team"] = m_opp.group(1).strip()
            
    return result

# Test on debate 635036
req = urllib.request.Request('https://vijis26.calicotab.com/vijis26/results/debate/635036/scoresheets/', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='replace')
    
parsed = parse_scoresheet_html(html)
print(json.dumps(parsed, indent=2))
