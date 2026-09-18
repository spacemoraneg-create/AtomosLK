import urllib.request
import json
import re

endpoints = [
    'https://vijis26.calicotab.com/api/',
    'https://vijis26.calicotab.com/vijis26/api/',
    'https://vijis26.calicotab.com/vijis26/tab/team/',
    'https://vijis26.calicotab.com/vijis26/tab/speaker/',
    'https://vijis26.calicotab.com/vijis26/tab/reply/',
    'https://vijis26.calicotab.com/vijis26/results/round/1/',
    'https://vijis26.calicotab.com/vijis26/participants/list/',
    'https://slsdc2026.calicotab.com/',
    'https://slsdc2026.calicotab.com/slsdc2026/',
]

for url in endpoints:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read()
            ct = resp.headers.get('Content-Type', '')
            print(f"[OK {resp.status}] {url} -> {ct} ({len(content)} bytes)")
    except urllib.error.HTTPError as e:
        print(f"[HTTP {e.code}] {url}")
    except Exception as e:
        print(f"[ERR] {url} -> {e}")
