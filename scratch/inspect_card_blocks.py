from test_vue_data import fetch
import re

html = fetch("https://slsdc2026.calicotab.com/slsdc26/results/debate/676447/scoresheets/")

# Find all cards by matching <div class="card...">
# Let's find each card title and its following content
card_blocks = re.split(r'<div class="card(?:\s+[^"]*)?">', html)
print(f"Split into {len(card_blocks)} blocks")

for idx, b in enumerate(card_blocks[1:], 1):
    # Find card title
    t_match = re.search(r'<h4[^>]*class="card-title"[^>]*>(.*?)</h4>', b, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', t_match.group(1)).strip() if t_match else f"Card {idx}"
    
    # Check if this card contains scoresheets (speeches)
    has_speeches = "1st" in b and "Reply" in b
    print(f"\nBlock {idx}: Title='{title}' | has_speeches={has_speeches}")
    
    if has_speeches:
        # Check team totals in this card
        totals = re.findall(r'Total for (.*?) \((Proposition|Opposition)\).*?<span[^>]*badge[^>]*>\s*([\d\.]+)\s*</span>', b, re.DOTALL)
        for t_name, side, pts in totals:
            print(f"   {side} ({t_name}): {pts} pts")
        
        # Check speeches count
        speeches = re.findall(r'<strong>(1st|2nd|3rd|Reply)</strong>\s*(.*?)\s*<span class="badge[^"]*badge-secondary[^"]*float-right">\s*([\d\.]+)\s*</span>', b, re.DOTALL)
        print(f"   Speeches count: {len(speeches)}")
        for pos, spk, score in speeches[:4]:
            spk_clean = re.sub(r'<[^>]+>', '', spk).strip()
            print(f"      {pos}: {spk_clean} -> {score}")
