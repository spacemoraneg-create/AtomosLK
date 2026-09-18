import urllib.request

url = 'https://vijis26.calicotab.com/vijis26/results/debate/635036/scoresheets/'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='replace')

idx = html.find('class="col-6 list-group mb-3"')
if idx != -1:
    print("=== Preceding snippet ===")
    print(html[idx-300:idx+150])
