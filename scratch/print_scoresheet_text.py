import urllib.request
import re

url = 'https://vijis26.calicotab.com/vijis26/results/debate/635036/scoresheets/'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='replace')

# Extract main container content
start = html.find('<main')
if start == -1:
    start = html.find('<div class="container')
end = html.find('</main>')
if end == -1:
    end = html.find('</body>')

section = html[start:end]
# Strip scripts and styles
clean_section = re.sub(r'<script.*?</script>', '', section, flags=re.DOTALL)
clean_section = re.sub(r'<style.*?</style>', '', clean_section, flags=re.DOTALL)

lines = [re.sub(r'<[^>]+>', ' ', l).strip() for l in clean_section.splitlines()]
non_empty = [re.sub(r'\s+', ' ', l) for l in lines if l]
print('\n'.join(non_empty[:100]))
