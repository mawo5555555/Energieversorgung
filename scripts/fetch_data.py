#!/usr/bin/env python3
"""Holt Energiedaten aus offenen Quellen und schreibt sie als JSON nach data/.

Läuft im GitHub-Job (siehe .github/workflows/daten.yml). Jede Quelle ist einzeln abgesichert:
Fällt eine aus, bleibt der letzte gute Stand in data/ erhalten und die Datei bekommt ein Feld "fehler".

Schlüssel kommen aus Umgebungsvariablen (im Repository unter Settings, Secrets):
  GIE_API_KEY            Gasspeicher (AGSI+) und LNG (ALSI), kostenlos bei GIE
  TANKERKOENIG_API_KEY   Kraftstoffpreise (Tankerkönig), kostenlos
Nur Standardbibliothek, keine Abhängigkeiten.
"""
import csv
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CFG = os.path.join(ROOT, "config")
UA = "energieversorgung-brandenburg/0.1 (+https://github.com)"
NOW = datetime.now(timezone.utc)


def http(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def get_json(url, headers=None, timeout=60):
    return json.loads(http(url, headers, timeout))


def read(name, default=None):
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write(name, obj):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def stamp():
    return NOW.strftime("%Y-%m-%dT%H:%M:%SZ")


def keep_on_error(name, fn):
    """Führt eine Quelle aus; bei Fehler bleibt der alte Stand, nur "fehler" wird gesetzt."""
    try:
        out = fn()
        if out is not None:
            write(name, out)
        print("ok  ", name)
    except Exception as e:  # noqa: BLE001
        old = read(name, {})
        old["fehler"] = f"{type(e).__name__}: {e}"[:300]
        old["fehler_stand"] = stamp()
        write(name, old)
        print("FEHL", name, old["fehler"], file=sys.stderr)


# ---------- Netzfrequenz ----------
def frequenz():
    # Inoffizielle Quelle (netzfrequenz.info), liefert nur die Zahl, z. B. 50.002
    hz = float(http("https://www.netzfrequenz.info/json/act.json", timeout=20).strip())
    if not 45 <= hz <= 55:
        raise ValueError(f"unplausibler Wert {hz}")
    old = read("frequenz.json", {})
    verlauf = [p for p in old.get("verlauf", []) if p[0] > (NOW - timedelta(hours=24)).timestamp()]
    verlauf.append([int(NOW.timestamp()), hz])
    return {"stand": stamp(), "hz": hz, "quelle": "netzfrequenz.info (inoffiziell)", "verlauf": verlauf[-300:]}


# ---------- Strom (SMARD, Bundesnetzagentur) ----------
SMARD = "https://www.smard.de/app/chart_data"
ERZEUGUNG = {
    1223: "Braunkohle", 4069: "Steinkohle", 4071: "Erdgas", 1224: "Kernenergie",
    1225: "Wind offshore", 4067: "Wind onshore", 4068: "Photovoltaik", 1226: "Wasserkraft",
    1227: "Sonstige Konventionelle", 1228: "Sonstige Erneuerbare", 4070: "Pumpspeicher",
}


def smard_series(filter_id, region, res):
    idx = get_json(f"{SMARD}/{filter_id}/{region}/index_{res}.json")["timestamps"]
    ts = idx[-1]
    rows = get_json(f"{SMARD}/{filter_id}/{region}/{filter_id}_{region}_{res}_{ts}.json")["series"]
    return [(t, v) for t, v in rows if v is not None]


def strom():
    mix, stand = {}, None
    for fid, name in ERZEUGUNG.items():
        s = smard_series(fid, "DE", "quarterhour")
        if s:
            mix[name] = round(s[-1][1])
            stand = max(stand or 0, s[-1][0])
    last = smard_series(410, "DE", "quarterhour")
    preis = smard_series(4169, "DE-LU", "hour")
    return {
        "stand": stamp(),
        "daten_stand_ms": stand,
        "erzeugung_mw": mix,
        "verbrauch_mw": round(last[-1][1]) if last else None,
        "preis_eur_mwh": preis[-1][1] if preis else None,
        "preis_verlauf": [[t // 1000, v] for t, v in preis[-48:]],
        "quelle": "Bundesnetzagentur | SMARD.de",
        "lizenz": "CC BY 4.0",
    }


# ---------- Gas: Pipelines und LNG (ENTSOG Transparency Platform) ----------
def entsog_tage(punkte, tage=14):
    von = (NOW - timedelta(days=tage)).strftime("%Y-%m-%d")
    bis = NOW.strftime("%Y-%m-%d")
    q = urllib.parse.urlencode({
        "indicator": "Physical Flow", "periodType": "day", "timezone": "CET",
        "from": von, "to": bis, "pointKey": ",".join(punkte), "limit": -1,
    })
    rows = get_json("https://transparency.entsog.eu/api/v1/operationaldatas?" + q, timeout=120).get("operationaldatas", [])
    best = {}  # (Punkt, Tag) -> höchster Wert der Betreiber, nur Richtung entry
    for r in rows:
        if r.get("directionKey") != "entry":
            continue
        try:
            v = float(str(r.get("value")).replace(",", "."))
        except (TypeError, ValueError):
            continue
        k = (r["pointKey"], r["periodFrom"][:10])
        best[k] = max(best.get(k, 0), v)
    return best


def gruppen_summe(gruppen):
    alle = sorted({p for pts in gruppen.values() for p in pts})
    best = entsog_tage(alle)
    tage = sorted({t for (_, t) in best})
    out = {}
    for name, pts in gruppen.items():
        reihe = []
        for t in tage:
            werte = [best[(p, t)] for p in pts if (p, t) in best]
            reihe.append([t, round(sum(werte) / 1e6, 1) if werte else None])  # kWh/d -> GWh/d
        out[name] = reihe
    return tage, out


def gas_pipeline():
    cfg = read_cfg("gas-punkte.json")
    tage, out = gruppen_summe(cfg["pipeline"])
    return {"stand": stamp(), "einheit": "GWh/Tag", "tage": tage, "gruppen": out,
            "quelle": "ENTSOG Transparency Platform", "hinweis": cfg["hinweis"]}


def gas_lng():
    cfg = read_cfg("gas-punkte.json")
    tage, out = gruppen_summe(cfg["lng"])
    return {"stand": stamp(), "einheit": "GWh/Tag", "tage": tage, "terminals": out,
            "quelle": "ENTSOG Transparency Platform (Einspeisung ins Netz)"}


def read_cfg(name):
    with open(os.path.join(CFG, name), encoding="utf-8") as f:
        return json.load(f)


# ---------- Gasspeicher (GIE AGSI+) ----------
def gas_speicher():
    key = os.environ.get("GIE_API_KEY", "").strip()
    if not key:
        return {"stand": stamp(), "hinweis": "Noch kein GIE-Schlüssel hinterlegt (Secret GIE_API_KEY).", "deutschland": None, "brandenburg": []}
    h = {"x-key": key}
    von = (NOW - timedelta(days=30)).strftime("%Y-%m-%d")
    land = get_json(f"https://agsi.gie.eu/api?country=DE&from={von}&size=60", h)
    rows = land.get("data", [])
    if not rows:
        raise ValueError("AGSI+ lieferte keine Daten: " + str(land.get("message", ""))[:100])
    rows.sort(key=lambda r: r["gasDayStart"])
    letzte = rows[-1]
    out = {
        "stand": stamp(), "quelle": "GIE AGSI+ (agsi.gie.eu)",
        "deutschland": {
            "gastag": letzte["gasDayStart"], "fuellstand_prozent": float(letzte["full"]),
            "gas_twh": float(letzte["gasInStorage"]), "kapazitaet_twh": float(letzte["workingGasVolume"]),
            "einspeicherung_gwh": float(letzte["injection"]), "ausspeicherung_gwh": float(letzte["withdrawal"]),
            "verlauf": [[r["gasDayStart"], float(r["full"])] for r in rows],
        },
        "brandenburg": [],
    }
    # Brandenburger Speicher aus config/brandenburg-speicher.json
    for a in read_cfg("brandenburg-speicher.json").get("speicher", []):
        url = f"https://agsi.gie.eu/api?country=DE&company={a['company']}&facility={a['eic']}&from={von}&size=60"
        d = get_json(url, h).get("data", [])
        d.sort(key=lambda r: r["gasDayStart"])
        if d:
            l = d[-1]
            out["brandenburg"].append({"eic": a["eic"], "name": a.get("name") or a["eic"], "gastag": l["gasDayStart"],
                                       "fuellstand_prozent": float(l["full"]), "gas_twh": float(l["gasInStorage"]),
                                       "kapazitaet_twh": float(l["workingGasVolume"]),
                                       "verlauf": [[r["gasDayStart"], float(r["full"])] for r in d]})
    return out


# ---------- Kraftstoffpreise (Tankerkönig, Brandenburg) ----------
def kraftstoff():
    key = os.environ.get("TANKERKOENIG_API_KEY", "").strip()
    if not key:
        return {"stand": stamp(), "hinweis": "Noch kein Tankerkönig-Schlüssel hinterlegt (Secret TANKERKOENIG_API_KEY).", "preise": None}
    cfg = read_cfg("tankstellen-zentren.json")
    stationen = {}
    for z in cfg["zentren"]:
        q = urllib.parse.urlencode({"lat": z["lat"], "lng": z["lng"], "rad": cfg["radius_km"], "sort": "dist", "type": "all", "apikey": key})
        d = get_json("https://creativecommons.tankerkoenig.de/json/list.php?" + q)
        if not d.get("ok"):
            raise ValueError(d.get("message", "Tankerkönig-Fehler"))
        for s in d.get("stations", []):
            stationen[s["id"]] = s
    preise = {}
    for sorte in ("diesel", "e5", "e10"):
        w = sorted(s[sorte] for s in stationen.values() if s.get("isOpen") and isinstance(s.get(sorte), (int, float)) and s[sorte] > 0)
        if w:
            preise[sorte] = {"min": w[0], "median": w[len(w) // 2], "max": w[-1], "anzahl": len(w)}
    old = read("kraftstoff.json", {})
    verlauf = [p for p in old.get("verlauf", []) if p[0] > (NOW - timedelta(days=14)).timestamp()]
    tag = int(NOW.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    if preise and (not verlauf or verlauf[-1][0] != tag):
        verlauf.append([tag, {k: v["median"] for k, v in preise.items()}])
    return {"stand": stamp(), "preise": preise, "stationen": len(stationen), "verlauf": verlauf,
            "quelle": "Tankerkönig.de (Markttransparenzstelle für Kraftstoffe), CC BY 4.0"}


# ---------- Rohöl (Brent), Quelle stooq.com ----------
def rohoel():
    txt = http("https://stooq.com/q/d/l/?s=cb.f&i=d", timeout=30)
    rows = list(csv.DictReader(io.StringIO(txt)))
    rows = [r for r in rows if r.get("Close") not in (None, "", "null")]
    if len(rows) < 2:
        raise ValueError("keine Kursdaten, Antwort: " + txt[:80].replace("\n", " "))
    letzte, vor = rows[-1], rows[-2]
    c, p = float(letzte["Close"]), float(vor["Close"])
    return {"stand": stamp(), "datum": letzte["Date"], "brent_usd": c, "aenderung_prozent": round((c - p) / p * 100, 2),
            "verlauf": [[r["Date"], float(r["Close"])] for r in rows[-60:]], "quelle": "stooq.com (Brent Future, verzögert)"}


def main():
    nur = set(sys.argv[1:])
    jobs = [
        ("frequenz.json", frequenz), ("strom.json", strom), ("gas_pipeline.json", gas_pipeline),
        ("gas_lng.json", gas_lng), ("gas_speicher.json", gas_speicher), ("kraftstoff.json", kraftstoff), ("rohoel.json", rohoel),
    ]
    for name, fn in jobs:
        if nur and name.split(".")[0] not in nur:
            continue
        keep_on_error(name, fn)
    meta = read("meta.json", {})
    meta["letzter_lauf"] = stamp()
    write("meta.json", meta)


if __name__ == "__main__":
    main()
