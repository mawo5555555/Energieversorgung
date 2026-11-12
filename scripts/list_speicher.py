#!/usr/bin/env python3
"""Schreibt die AGSI+-Anlagenliste (nur Deutschland) nach data/agsi_anlagen.json, damit die Brandenburger Speicher festgelegt werden können."""
import json, os, urllib.request

key = os.environ.get("GIE_API_KEY", "").strip()
if not key:
    raise SystemExit("GIE_API_KEY fehlt")
req = urllib.request.Request("https://agsi.gie.eu/api/about?show=listing", headers={"x-key": key, "User-Agent": "energieversorgung/0.1"})
raw = json.load(urllib.request.urlopen(req, timeout=60))
out = {}
# Struktur: Region -> Land -> Firmen -> Anlagen; wir nehmen alles, was zu Deutschland gehört
def walk(o, path=()):
    if isinstance(o, dict):
        if o.get("code") == "DE" or o.get("name") == "Germany":
            out["deutschland"] = o
        for k, v in o.items():
            walk(v, path + (k,))
    elif isinstance(o, list):
        for v in o:
            walk(v, path)
walk(raw)
os.makedirs("data", exist_ok=True)
with open("data/agsi_anlagen.json", "w", encoding="utf-8") as f:
    json.dump(out or {"roh": raw}, f, ensure_ascii=False, indent=1)
print("geschrieben", list(out) or "roh")
