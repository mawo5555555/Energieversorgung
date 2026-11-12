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
def fl(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


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
            "fluss": [[r["gasDayStart"], fl(r["injection"]), fl(r["withdrawal"])] for r in rows[-14:]],
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
                                       "verlauf": [[r["gasDayStart"], float(r["full"])] for r in d],
                                       "fluss": [[r["gasDayStart"], fl(r["injection"]), fl(r["withdrawal"])] for r in d[-14:]]})
    return out


# ---------- Gasspeicher Europa und einzelne Länder (AGSI+) ----------
EUROPA = [("EU", "continent=eu", "Europäische Union"), ("DE", "country=DE", "Deutschland"), ("NL", "country=NL", "Niederlande"),
          ("AT", "country=AT", "Österreich"), ("FR", "country=FR", "Frankreich"), ("IT", "country=IT", "Italien"),
          ("PL", "country=PL", "Polen"), ("CZ", "country=CZ", "Tschechien"), ("HU", "country=HU", "Ungarn"), ("ES", "country=ES", "Spanien")]


def agsi_letzte(query, h, tage=10):
    von = (NOW - timedelta(days=tage)).strftime("%Y-%m-%d")
    d = get_json(f"https://agsi.gie.eu/api?{query}&from={von}&size=30", h, 60).get("data", [])
    d = [r for r in d if r.get("full") not in (None, "", "-")]
    d.sort(key=lambda r: r["gasDayStart"])
    return d


def gas_europa():
    key = os.environ.get("GIE_API_KEY", "").strip()
    if not key:
        return {"stand": stamp(), "hinweis": "Noch kein GIE-Schlüssel hinterlegt."}
    h = {"x-key": key}
    laender, fehler = [], []
    for code, q, name in EUROPA:
        try:
            d = agsi_letzte(q, h)
            if not d:
                fehler.append(code)
                continue
            l = d[-1]
            laender.append({"code": code, "name": name, "gastag": l["gasDayStart"], "fuellstand_prozent": fl(l["full"]),
                            "gas_twh": fl(l["gasInStorage"]), "kapazitaet_twh": fl(l["workingGasVolume"]),
                            "einspeicherung_gwh": fl(l["injection"]), "ausspeicherung_gwh": fl(l["withdrawal"])})
        except Exception as e:  # noqa: BLE001
            fehler.append(f"{code}: {str(e)[:60]}")
    if not laender:
        raise ValueError("keine Länderdaten: " + "; ".join(fehler))
    return {"stand": stamp(), "quelle": "GIE AGSI+ (agsi.gie.eu)", "laender": laender, "ohne_daten": fehler}


# ---------- Große Speicher in Deutschland einzeln (AGSI+) ----------
AUSSCHLUSS = ("VGS", "Zone", "Hub", "historical", "decommissioned", "aggregated", "GPL", "INNEXPOOL", "VSP", "Pool")


def gas_anlagen():
    key = os.environ.get("GIE_API_KEY", "").strip()
    if not key:
        return {"stand": stamp(), "hinweis": "Noch kein GIE-Schlüssel hinterlegt."}
    old = read("gas_anlagen.json", {})
    try:
        alt = datetime.strptime(old["stand"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if NOW - alt < timedelta(hours=6) and old.get("anlagen") and not old.get("fehler"):
            return None  # viele Einzelabrufe, deshalb nur alle paar Stunden
    except (KeyError, ValueError):
        pass
    with open(os.path.join(DATA, "agsi_anlagen.json"), encoding="utf-8") as f:
        firmen = json.load(f)["roh"]
    kand, gesehen = [], set()
    for c in firmen:
        if c.get("country") != "DE":
            continue
        for f in c.get("facilities", []):
            ende = f.get("operational_end_date")
            if (ende and ende < NOW.strftime("%Y-%m-%d")) or f["eic"] in gesehen or any(w in f["name"] for w in AUSSCHLUSS):
                continue
            gesehen.add(f["eic"])
            kand.append((c["name"], c["eic"], f["eic"], f["name"]))
    h = {"x-key": key}
    out, fehler = [], 0
    for firma, ceic, feic, name in kand:
        try:
            d = agsi_letzte(f"country=DE&company={ceic}&facility={feic}", h)
            if d and fl(d[-1]["workingGasVolume"]) > 0:
                l = d[-1]
                out.append({"name": name.replace("UGS ", ""), "firma": firma.strip(), "gastag": l["gasDayStart"], "fuellstand_prozent": fl(l["full"]),
                            "gas_twh": fl(l["gasInStorage"]), "kapazitaet_twh": fl(l["workingGasVolume"]),
                            "einspeicherung_gwh": fl(l["injection"]), "ausspeicherung_gwh": fl(l["withdrawal"])})
        except Exception:  # noqa: BLE001
            fehler += 1
    if not out:
        raise ValueError("keine Anlagendaten")
    out.sort(key=lambda a: a["kapazitaet_twh"], reverse=True)
    return {"stand": stamp(), "quelle": "GIE AGSI+ (agsi.gie.eu)", "anlagen": out, "ohne_daten": fehler}


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


# ---------- Rohöl (Brent) ----------
def yahoo_reihe(symbol, quelle, nachkomma=2):
    d = get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=3mo&interval=1d", {"User-Agent": "Mozilla/5.0"}, 30)
    res = d["chart"]["result"][0]
    rows = [(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), c) for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c is not None]
    if len(rows) < 2:
        raise ValueError("keine Kursdaten")
    c, p = rows[-1][1], rows[-2][1]
    return {"stand": stamp(), "datum": rows[-1][0], "preis": round(c, nachkomma), "aenderung_prozent": round((c - p) / p * 100, 2),
            "verlauf": [[d_, round(v, nachkomma)] for d_, v in rows[-60:]], "quelle": quelle}


def gaspreis():
    return yahoo_reihe("TTF=F", "Yahoo Finance (TTF Erdgas-Future, Euro je MWh, verzögert)")


# ---------- LNG-Terminals: Tankfüllstand und Ausspeisung (GIE ALSI) ----------
def zahl(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def alsi_zeile(r, name, firma=""):
    inv = r.get("inventory")
    inv_gwh = zahl(inv.get("gwh")) if isinstance(inv, dict) else zahl(inv)
    return {"name": name, "firma": firma, "gastag": r.get("gasDayStart"), "fuellstand_prozent": zahl(r.get("full")),
            "inhalt_gwh": inv_gwh, "ausspeisung_gwh": zahl(r.get("sendOut")), "anlieferung_schiffe": zahl(r.get("dtmi"))}


def lng_tanks():
    key = os.environ.get("GIE_API_KEY", "").strip()
    if not key:
        return {"stand": stamp(), "hinweis": "Noch kein GIE-Schlüssel hinterlegt."}
    h = {"x-key": key}
    von = (NOW - timedelta(days=10)).strftime("%Y-%m-%d")

    def letzte(query):
        d = get_json(f"https://alsi.gie.eu/api?{query}&from={von}&size=30", h, 60).get("data", [])
        d = [r for r in d if r.get("full") not in (None, "", "-")]
        d.sort(key=lambda r: r["gasDayStart"])
        return d

    lst = get_json("https://alsi.gie.eu/api/about?show=listing", h, 60)
    # Struktur: Liste von Firmen mit Anlagen (wie bei AGSI+), je mit Länderkennung
    firmen = lst if isinstance(lst, list) else next((v for v in lst.values() if isinstance(v, list)), [])
    terminals, de_roh = [], None
    d = letzte("country=DE")
    if d:
        de_roh = alsi_zeile(d[-1], "Deutschland gesamt")
        de_roh["verlauf"] = [[r["gasDayStart"], zahl(r["full"])] for r in d]
    for c in firmen:
        if c.get("country") != "DE":
            continue
        for f in c.get("facilities", []):
            ende = f.get("operational_end_date")
            if ende and ende < NOW.strftime("%Y-%m-%d"):
                continue
            try:
                dd = letzte(f"country=DE&company={c['eic']}&facility={f['eic']}")
                if dd:
                    terminals.append(alsi_zeile(dd[-1], f["name"], c["name"].strip()))
            except Exception:  # noqa: BLE001
                pass
    if not terminals and not de_roh:
        raise ValueError("keine LNG-Daten")
    return {"stand": stamp(), "quelle": "GIE ALSI (alsi.gie.eu)", "deutschland": de_roh, "terminals": terminals}


def rohoel_yahoo():
    d = get_json("https://query1.finance.yahoo.com/v8/finance/chart/BZ%3DF?range=3mo&interval=1d", {"User-Agent": "Mozilla/5.0"}, 30)
    res = d["chart"]["result"][0]
    ts, close = res["timestamp"], res["indicators"]["quote"][0]["close"]
    rows = [(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), c) for t, c in zip(ts, close) if c is not None]
    if len(rows) < 2:
        raise ValueError("keine Kursdaten")
    c, p = rows[-1][1], rows[-2][1]
    return {"stand": stamp(), "datum": rows[-1][0], "brent_usd": round(c, 2), "aenderung_prozent": round((c - p) / p * 100, 2),
            "verlauf": [[d_, round(v, 2)] for d_, v in rows[-60:]], "quelle": "Yahoo Finance (Brent Future BZ=F, verzögert)"}


def rohoel_stooq():
    txt = http("https://stooq.com/q/d/l/?s=cb.f&i=d", timeout=30)
    rows = [r for r in csv.DictReader(io.StringIO(txt)) if r.get("Close") not in (None, "", "null")]
    if len(rows) < 2:
        raise ValueError("keine Kursdaten, Antwort: " + txt[:80].replace("\n", " "))
    c, p = float(rows[-1]["Close"]), float(rows[-2]["Close"])
    return {"stand": stamp(), "datum": rows[-1]["Date"], "brent_usd": c, "aenderung_prozent": round((c - p) / p * 100, 2),
            "verlauf": [[r["Date"], float(r["Close"])] for r in rows[-60:]], "quelle": "stooq.com (Brent Future, verzögert)"}


def rohoel():
    try:
        return rohoel_yahoo()
    except Exception as e:  # noqa: BLE001
        print("Yahoo fehlgeschlagen:", e, file=sys.stderr)
        return rohoel_stooq()


# ---------- Wetter (Open-Meteo): Temperaturen für Heizbedarf ----------
STAEDTE_DE = [(52.52, 13.40), (53.55, 10.00), (50.94, 6.96), (48.14, 11.58), (50.11, 8.68), (51.34, 12.37)]  # Berlin, Hamburg, Köln, München, Frankfurt, Leipzig
POTSDAM = (52.39, 13.06)


def wetter():
    old = read("wetter.json", {})
    try:
        if old.get("stand") and not old.get("fehler") and (NOW - datetime.strptime(old["stand"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)) < timedelta(hours=3):
            return None  # frisch genug, Abrufe schonen
    except ValueError:
        pass
    orte = [POTSDAM] + STAEDTE_DE
    q = urllib.parse.urlencode({"latitude": ",".join(str(o[0]) for o in orte), "longitude": ",".join(str(o[1]) for o in orte),
                                "daily": "temperature_2m_mean", "past_days": 7, "forecast_days": 14, "timezone": "Europe/Berlin"})
    d = get_json("https://api.open-meteo.com/v1/forecast?" + q, timeout=60)
    if isinstance(d, dict):
        d = [d]
    tage = d[0]["daily"]["time"]
    bb = [round(v, 1) if v is not None else None for v in d[0]["daily"]["temperature_2m_mean"]]
    de = []
    for i in range(len(tage)):
        w = [x["daily"]["temperature_2m_mean"][i] for x in d[1:] if x["daily"]["temperature_2m_mean"][i] is not None]
        de.append(round(sum(w) / len(w), 1) if w else None)
    return {"stand": stamp(), "tage": tage, "heute_index": 7, "brandenburg": bb, "deutschland": de,
            "quelle": "Open-Meteo.com (CC BY 4.0), Brandenburg = Potsdam, Deutschland = Mittel aus 6 Großstädten"}


# ---------- Füllstand im Jahresvergleich (AGSI+, Deutschland) ----------
def gas_historie():
    key = os.environ.get("GIE_API_KEY", "").strip()
    old = read("gas_historie.json", {})
    if not key:
        return {"stand": stamp(), "hinweis": "Noch kein GIE-Schlüssel hinterlegt."}
    if old.get("stand", "")[:10] == NOW.strftime("%Y-%m-%d") and not old.get("fehler") and old.get("jahre"):
        return None  # einmal pro Tag genügt
    von = f"{NOW.year - 6}-01-01"
    rows, page = [], 1
    while page <= 20:
        d = get_json(f"https://agsi.gie.eu/api?country=DE&from={von}&size=300&page={page}", {"x-key": key}, 90)
        rows += d.get("data", [])
        if page >= int(d.get("last_page", 1) or 1):
            break
        page += 1
    if not rows:
        raise ValueError("AGSI+ lieferte keine Verlaufsdaten")
    jahre = {}
    for r in rows:
        try:
            dt = datetime.strptime(r["gasDayStart"], "%Y-%m-%d")
            jahre.setdefault(dt.year, {})[dt.timetuple().tm_yday] = round(float(r["full"]), 1)
        except (ValueError, TypeError, KeyError):
            continue
    heute = NOW.year
    vorjahre = [y for y in range(heute - 5, heute) if y in jahre]
    band = []
    for t in range(1, 367):
        v = [jahre[y][t] for y in vorjahre if t in jahre[y]]
        band.append([t, min(v), max(v), round(sum(v) / len(v), 1)] if v else [t, None, None, None])
    return {"stand": stamp(), "quelle": "GIE AGSI+ (agsi.gie.eu)", "aktuelles_jahr": heute, "vorjahre": vorjahre,
            "jahre": {str(y): sorted([t, v] for t, v in jahre[y].items()) for y in [*vorjahre, heute] if y in jahre}, "band": band}


# ---------- Reichweite der Gasspeicher (Schätzung) ----------
def hdd(t):
    return max(0.0, 15.0 - t) if t is not None else None  # Heizgradtage, Basis 15 °C


def projektion(stock, kap, w7, i7, temps, idx):
    """Füllstand der nächsten Tage: Ausspeicherung folgt dem Heizbedarf, Einspeicherung bleibt wie in den letzten 7 Tagen."""
    ref = [hdd(t) for t in temps[max(0, idx - 7):idx] if t is not None]
    ref = sum(ref) / len(ref) if ref else None
    pro = []
    ist = stock
    for k, t in enumerate(temps[idx:]):
        h = hdd(t)
        faktor = (h / ref) if (ref and ref > 0.5 and h is not None) else 1.0
        netto = w7 * faktor - i7
        ist = min(kap, max(0.0, ist - netto / 1000.0))  # GWh -> TWh
        pro.append(round(ist / kap * 100, 1) if kap else None)
    return pro


def reichweite_fuer(name, fluss, stock, kap, temps, tage, idx):
    if not fluss or not kap:
        return None
    letzte = fluss[-7:]
    w7 = sum(f[2] for f in letzte) / len(letzte)
    i7 = sum(f[1] for f in letzte) / len(letzte)
    netto7 = w7 - i7
    out = {"name": name, "inhalt_twh": round(stock, 3), "kapazitaet_twh": round(kap, 3), "fuellstand_prozent": round(stock / kap * 100, 1),
           "ausspeicherung_7t_gwh": round(w7, 1), "einspeicherung_7t_gwh": round(i7, 1), "netto_7t_gwh": round(netto7, 1)}
    out["tage_aktuell"] = round(stock * 1000 / netto7) if netto7 > 0.01 else None
    pro = projektion(stock, kap, w7, i7, temps, idx) if temps and temps[idx:] else []
    out["projektion"] = [[tage[idx + k], v] for k, v in enumerate(pro)]
    # Tage bis leer mit Wetter: Vorhersagezeitraum, danach Mittel der Vorhersage fortschreiben
    leer = None
    if pro:
        if any(v is not None and v <= 0.05 for v in pro):
            leer = next(k for k, v in enumerate(pro) if v is not None and v <= 0.05) + 1
        else:
            fall = (pro[-2] - pro[-1]) if len(pro) > 1 and pro[-2] is not None and pro[-1] is not None else 0
            if fall > 0.01:
                leer = len(pro) + round(pro[-1] / fall)
    out["tage_wetter"] = leer
    return out


def reichweite():
    sp, we = read("gas_speicher.json", {}), read("wetter.json", {})
    if not sp.get("deutschland"):
        return {"stand": stamp(), "hinweis": "Keine Speicherdaten."}
    tage, idx = we.get("tage", []), we.get("heute_index", 7)
    de = sp["deutschland"]
    out = {"stand": stamp(), "annahmen": ("Reine Schätzung nur für die Gasspeicher, ohne Importe, LNG und Verbrauchsänderungen. Grundlage: mittlere Ein- und Ausspeicherung der letzten 7 Tage. "
                                           "Mit Wetter: Die Ausspeicherung folgt dem Heizbedarf (Heizgradtage, Basis 15 °C) der Temperaturvorhersage."),
           "deutschland": reichweite_fuer("Deutschland", de.get("fluss"), de["gas_twh"], de["kapazitaet_twh"], we.get("deutschland"), tage, idx),
           "brandenburg": [r for r in (reichweite_fuer(b["name"], b.get("fluss"), b["gas_twh"], b["kapazitaet_twh"], we.get("brandenburg"), tage, idx)
                                       for b in sp.get("brandenburg", [])) if r]}
    return out


def main():
    nur = set(sys.argv[1:])
    jobs = [
        ("frequenz.json", frequenz), ("strom.json", strom), ("gas_pipeline.json", gas_pipeline),
        ("gas_lng.json", gas_lng), ("gas_speicher.json", gas_speicher), ("kraftstoff.json", kraftstoff), ("rohoel.json", rohoel),
        ("wetter.json", wetter), ("gas_historie.json", gas_historie), ("reichweite.json", reichweite),
        ("gas_europa.json", gas_europa), ("gas_anlagen.json", gas_anlagen),
        ("gaspreis.json", gaspreis), ("lng_tanks.json", lng_tanks),
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
