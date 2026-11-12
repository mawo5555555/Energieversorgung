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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
        old["fehler"] = f"{type(e).__name__}: {e}"[:700]
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
    best = {}  # (Punkt, Richtung, Tag) -> höchster Wert der Betreiber
    for r in rows:
        try:
            v = float(str(r.get("value")).replace(",", "."))
        except (TypeError, ValueError):
            continue
        k = (r["pointKey"], r.get("directionKey"), r["periodFrom"][:10])
        best[k] = max(best.get(k, 0), v)
    return best


def summe_gruppe(best, pts, richtung, tag):
    w = [best[(p, richtung, tag)] for p in pts if (p, richtung, tag) in best]
    return sum(w) / 1e6 if w else None  # kWh/d -> GWh/d


def gruppen_auswertung(gruppen, mit_ausfuhr):
    """Wählt den neuesten Tag, für den alle (zuletzt gemeldeten) Gruppen Daten haben, damit die Summe nicht Tage mischt."""
    alle = sorted({p for pts in gruppen.values() for p in pts})
    best = entsog_tage(alle)
    tage = sorted({t for (_, _, t) in best})
    ein = {g: {t: summe_gruppe(best, pts, "entry", t) for t in tage} for g, pts in gruppen.items()}
    aus = {g: {t: summe_gruppe(best, pts, "exit", t) for t in tage} for g, pts in gruppen.items()}
    letzte = tage[-7:]
    aktiv = [g for g in gruppen if any(ein[g][t] is not None for t in letzte)]
    vollstaendig = [t for t in tage if all(ein[g][t] is not None for g in aktiv)]
    if not vollstaendig:
        raise ValueError("kein Tag mit vollständigen Meldungen")
    tag = vollstaendig[-1]
    out, verlauf = [], []
    for g in gruppen:
        e, a = ein[g].get(tag), aus[g].get(tag)
        out.append({"name": g, "einspeisung": round(e, 1) if e is not None else None,
                    "ausfuhr": round(a or 0.0, 1) if (mit_ausfuhr and e is not None) else None,
                    "netto": (round(e - ((a or 0) if mit_ausfuhr else 0), 1) or 0.0) if e is not None else None})
    for t in vollstaendig[-10:]:
        verlauf.append([t, round(sum(ein[g][t] - ((aus[g][t] or 0) if mit_ausfuhr else 0) for g in aktiv), 1)])
    return tag, out, verlauf, [g for g in gruppen if g not in aktiv], tage[-1]


def gas_pipeline():
    cfg = read_cfg("gas-punkte.json")
    tag, gr, verlauf, leer, neuester = gruppen_auswertung(cfg["pipeline"], True)
    return {"stand": stamp(), "einheit": "GWh/Tag", "tag": tag, "neuester_tag_in_daten": neuester, "gruppen": gr,
            "summe_einspeisung": round(sum(g["einspeisung"] or 0 for g in gr), 1), "summe_netto": round(sum(g["netto"] or 0 for g in gr), 1),
            "verlauf": verlauf, "ohne_daten": leer, "quelle": "ENTSOG Transparency Platform", "hinweis": cfg["hinweis"]}


def gas_lng():
    cfg = read_cfg("gas-punkte.json")
    tag, gr, verlauf, leer, neuester = gruppen_auswertung(cfg["lng"], False)
    return {"stand": stamp(), "einheit": "GWh/Tag", "tag": tag, "neuester_tag_in_daten": neuester, "terminals": gr,
            "summe": round(sum(g["einspeisung"] or 0 for g in gr), 1), "verlauf": verlauf, "ohne_daten": leer,
            "quelle": "ENTSOG Transparency Platform (Einspeisung ins Netz)"}


def read_cfg(name):
    with open(os.path.join(CFG, name), encoding="utf-8") as f:
        return json.load(f)


# ---------- Gasspeicher (GIE AGSI+) ----------
def firma_von(eic):
    """Firmen-EIC einer Anlage aus der AGSI+-Anlagenliste (bei mehreren Einträgen der aktuellste ohne Enddatum)."""
    with open(os.path.join(DATA, "agsi_anlagen.json"), encoding="utf-8") as f:
        liste = json.load(f)["roh"]
    treffer = [(fa.get("operational_end_date") or "9999", c["eic"]) for c in liste if c.get("country") == "DE" for fa in c.get("facilities", []) if fa["eic"] == eic]
    if not treffer:
        raise ValueError("Anlage nicht in der Liste: " + eic)
    return sorted(treffer)[-1][1]


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
        url = f"https://agsi.gie.eu/api?country=DE&company={firma_von(a['eic'])}&facility={a['eic']}&from={von}&size=60"
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


# ---------- Speicher im Umfeld Brandenburgs: Vorausschau mit Leistungsgrenze ----------
def gas_umfeld():
    key = os.environ.get("GIE_API_KEY", "").strip()
    if not key:
        return {"stand": stamp(), "hinweis": "Noch kein GIE-Schlüssel hinterlegt."}
    h = {"x-key": key}
    we = read("wetter.json", {})
    temps, tage, idx = we.get("brandenburg"), we.get("tage", []), we.get("heute_index", 7)
    anlagen, fehler = [], []
    for a in read_cfg("brandenburg-speicher.json").get("umfeld", []):
        try:
            d = agsi_letzte(f"country=DE&company={firma_von(a['eic'])}&facility={a['eic']}", h, 20)
            if not d:
                fehler.append(a["name"])
                continue
            l = d[-1]
            letzte = d[-7:]
            w7 = sum(fl(r["withdrawal"]) for r in letzte) / len(letzte)
            i7 = sum(fl(r["injection"]) for r in letzte) / len(letzte)
            kap = fl(l["workingGasVolume"])
            anlagen.append({"name": a["name"], "region": a.get("region", ""), "gastag": l["gasDayStart"], "fuellstand_prozent": fl(l["full"]),
                            "gas_twh": fl(l["gasInStorage"]), "kapazitaet_twh": kap, "ausspeicherung_gwh": fl(l["withdrawal"]), "einspeicherung_gwh": fl(l["injection"]),
                            "ausspeicherleistung_gwh": fl(l.get("withdrawalCapacity")), "einspeicherleistung_gwh": fl(l.get("injectionCapacity")),
                            "ausspeicherung_7t_gwh": round(w7, 1), "einspeicherung_7t_gwh": round(i7, 1),
                            "leistung_verlauf": [[r["gasDayStart"], fl(r.get("withdrawalCapacity")), fl(r["full"])] for r in d]})
        except Exception as e:  # noqa: BLE001
            fehler.append(f"{a['name']}: {str(e)[:60]}")
    if not anlagen:
        raise ValueError("keine Umfeld-Daten: " + "; ".join(fehler))
    stock = sum(a["gas_twh"] for a in anlagen)
    kap = sum(a["kapazitaet_twh"] for a in anlagen)
    grenz = []
    try:
        best = entsog_tage(["ITP-00096", "ITP-00497"], 10)
        for pk, nm in (("ITP-00096", "Mallnow (Polen–Deutschland, Brandenburg)"), ("ITP-00497", "GCP Gaz-System/ONTRAS (Polen–Deutschland)")):
            gestern = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")
            tg = sorted({t for (p_, _, t) in best if p_ == pk and t <= gestern})[-7:]
            grenz.append({"name": nm, "tage": [[t, round(best.get((pk, "entry", t), 0) / 1e6, 1), round(best.get((pk, "exit", t), 0) / 1e6, 1)] for t in tg]})
    except Exception:  # noqa: BLE001
        grenz = []
    out = {"stand": stamp(), "quelle": "GIE AGSI+ (agsi.gie.eu)", "ohne_daten": fehler, "anlagen": anlagen, "grenzpunkte": grenz,
           "summe": {"gas_twh": round(stock, 2), "kapazitaet_twh": round(kap, 2), "fuellstand_prozent": round(stock / kap * 100, 1) if kap else None,
                     "ausspeicherung_7t_gwh": round(sum(a["ausspeicherung_7t_gwh"] for a in anlagen), 1),
                     "einspeicherung_7t_gwh": round(sum(a["einspeicherung_7t_gwh"] for a in anlagen), 1),
                     "ausspeicherleistung_gwh": round(sum(a["ausspeicherleistung_gwh"] for a in anlagen), 1)}}
    # Projektion: Ausspeicherung folgt dem Heizbedarf (Potsdam), gedeckelt durch die gemeldete Ausspeicherleistung je Anlage
    if temps and temps[idx:]:
        ref = [hdd(t) for t in temps[max(0, idx - 7):idx] if t is not None]
        ref = sum(ref) / len(ref) if ref else None
        ist = {a["name"]: a["gas_twh"] for a in anlagen}
        pro, engpass = [], 0
        for t in temps[idx:]:
            hh = hdd(t)
            faktor = (hh / ref) if (ref and ref > 0.5 and hh is not None) else 1.0
            tag_netto = 0.0
            gedeckelt = False
            for a in anlagen:
                wunsch = a["ausspeicherung_7t_gwh"] * faktor
                gren = a["ausspeicherleistung_gwh"]
                w = min(wunsch, gren) if gren > 0 else wunsch
                if gren > 0 and wunsch > gren:
                    gedeckelt = True
                n = w - a["einspeicherung_7t_gwh"]
                ist[a["name"]] = min(a["kapazitaet_twh"], max(0.0, ist[a["name"]] - n / 1000.0))
                tag_netto += n
            engpass += 1 if gedeckelt else 0
            pro.append(round(sum(ist.values()) / kap * 100, 1) if kap else None)
        out["projektion"] = [[tage[idx + k], v] for k, v in enumerate(pro)]
        out["engpass_tage"] = engpass
    return out


# ---------- Netzausfälle und Wartung (ENTSOG Urgent Market Messages) ----------
def gas_stoerungen():
    rows = get_json("https://transparency.entsog.eu/api/v1/urgentmarketmessages?limit=-1&balancingZoneKey=DE", timeout=120).get("urgentmarketmessages", [])
    heute = NOW.date()
    horizont = heute + timedelta(days=180)
    out = []
    for r in rows:
        if r.get("isLatestVersion") is False or str(r.get("eventStatus", "")).lower() in ("withdrawn", "cancelled"):
            continue
        try:
            von = datetime.fromisoformat(r["eventStart"]).date()
            bis = datetime.fromisoformat(r["eventStop"]).date() if r.get("eventStop") else None
        except (KeyError, TypeError, ValueError):
            continue
        if (bis and bis < heute) or von > horizont:
            continue
        try:
            nicht = float(r.get("unavailableCapacity")) / 1e6
        except (TypeError, ValueError):
            nicht = None
        try:
            tech = float(r.get("technicalCapacity")) / 1e6
        except (TypeError, ValueError):
            tech = None
        out.append({"betreiber": r.get("marketParticipantName"), "anlage": r.get("affectedAssetName"), "art": r.get("unavailabilityType"), "ereignis": r.get("eventType"),
                    "von": von.isoformat(), "bis": bis.isoformat() if bis else None, "nicht_verfuegbar_gwh": round(nicht, 1) if nicht is not None else None,
                    "technisch_gwh": round(tech, 1) if tech is not None else None, "richtung": r.get("direction"), "grund": r.get("unavailabilityReason"),
                    "hinweis": (r.get("remarks") or "")[:200], "aktiv_jetzt": von <= heute})
    out.sort(key=lambda x: (x["nicht_verfuegbar_gwh"] or 0), reverse=True)
    geplant = [x for x in out if str(x["art"]).lower().startswith("planned")]
    ungeplant = [x for x in out if str(x["art"]).lower().startswith("unplanned")]
    return {"stand": stamp(), "quelle": "ENTSOG Transparency Platform, Urgent Market Messages (Deutschland)", "anzahl": len(out), "geplant": len(geplant), "ungeplant": len(ungeplant),
            "summe_nicht_verfuegbar_gwh": round(sum(x["nicht_verfuegbar_gwh"] or 0 for x in out), 1), "meldungen": out[:30]}


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
    letzter_fehler = None
    for bereich in ("3mo", "6mo", "1mo"):
        try:
            d = get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range={bereich}&interval=1d", {"User-Agent": "Mozilla/5.0"}, 30)
            res = d["chart"]["result"][0]
            rows = [(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), c) for t, c in zip(res.get("timestamp") or [], res["indicators"]["quote"][0].get("close") or []) if c is not None]
            meta = res.get("meta", {})
            if len(rows) >= 2:
                c, p = rows[-1][1], rows[-2][1]
                return {"stand": stamp(), "datum": rows[-1][0], "preis": round(c, nachkomma), "aenderung_prozent": round((c - p) / p * 100, 2),
                        "verlauf": [[d_, round(v, nachkomma)] for d_, v in rows[-60:]], "quelle": quelle}
            # Rückfall: aktueller Kurs und Vortagsschluss aus den Metadaten
            c, p = meta.get("regularMarketPrice"), meta.get("chartPreviousClose") or meta.get("previousClose")
            if c and p:
                verlauf = [[d_, round(v, nachkomma)] for d_, v in rows[-60:]]
                heute = datetime.fromtimestamp(meta.get("regularMarketTime", NOW.timestamp()), timezone.utc).strftime("%Y-%m-%d")
                return {"stand": stamp(), "datum": heute, "preis": round(c, nachkomma), "aenderung_prozent": round((c - p) / p * 100, 2),
                        "verlauf": verlauf, "quelle": quelle + ", Tageswert"}
            letzter_fehler = f"keine Kursdaten ({symbol}, {bereich})"
        except Exception as e:  # noqa: BLE001
            letzter_fehler = f"{type(e).__name__}: {e}"[:200]
    raise ValueError(letzter_fehler or "keine Kursdaten")


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
    voll = zahl(r.get("full"))
    if voll is None:
        lng = zahl(inv.get("lng")) if isinstance(inv, dict) else None
        dtmi = zahl(r.get("dtmi"))
        voll = round(lng / dtmi * 100, 1) if lng is not None and dtmi else None
    return {"name": name, "firma": firma, "gastag": r.get("gasDayStart"), "fuellstand_prozent": voll,
            "inhalt_gwh": inv_gwh, "ausspeisung_gwh": zahl(r.get("sendOut")), "anlieferung_schiffe": zahl(r.get("dtmi"))}


def lng_tanks():
    key = os.environ.get("GIE_API_KEY", "").strip()
    if not key:
        return {"stand": stamp(), "hinweis": "Noch kein GIE-Schlüssel hinterlegt."}
    h = {"x-key": key}
    von = (NOW - timedelta(days=10)).strftime("%Y-%m-%d")

    def letzte(query):
        d = get_json(f"https://alsi.gie.eu/api?{query}&from={von}&size=30", h, 60).get("data", [])
        d = [r for r in d if r.get("inventory") or r.get("sendOut") not in (None, "", "-") or r.get("full") not in (None, "", "-")]
        d.sort(key=lambda r: r["gasDayStart"])
        return d

    lst = get_json("https://alsi.gie.eu/api/about?show=listing", h, 60)
    # Struktur: Liste von Firmen mit Anlagen (wie bei AGSI+), je mit Länderkennung
    firmen = lst if isinstance(lst, list) else next((v for v in lst.values() if isinstance(v, list)), [])
    terminals, de_roh = [], None
    d = letzte("country=DE")
    if d:
        de_roh = alsi_zeile(d[-1], "Deutschland gesamt")
        de_roh["verlauf"] = [[r["gasDayStart"], alsi_zeile(r, "")["fuellstand_prozent"]] for r in d]
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
        roh = get_json(f"https://alsi.gie.eu/api?country=DE&from={von}&size=3", h, 60)
        raise ValueError("keine LNG-Daten, Zeile: " + json.dumps((roh.get("data") or [None])[0])[:600] + " | Firmen: " + str(len(firmen)))
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


# ---------- Modell-Grundlagen: Historie der Speicher und Temperaturen ----------
def agsi_de_historie(key, ab_jahr=2018, extra=""):
    rows, page = [], 1
    while page <= 30:
        d = get_json(f"https://agsi.gie.eu/api?country=DE{extra}&from={ab_jahr}-01-01&size=300&page={page}", {"x-key": key}, 90)
        rows += d.get("data", [])
        if page >= int(d.get("last_page", 1) or 1):
            break
        page += 1
    out = {}
    for r in rows:
        try:
            out[r["gasDayStart"]] = {"full": float(r["full"]), "w": fl(r["withdrawal"]), "i": fl(r["injection"]), "wcap": fl(r.get("withdrawalCapacity")),
                                     "icap": fl(r.get("injectionCapacity")), "twh": fl(r["gasInStorage"]), "kap": fl(r["workingGasVolume"])}
        except (KeyError, ValueError, TypeError):
            continue
    return out


def temp_historie():
    """Tagesmitteltemperatur Deutschland (Mittel aus 6 Großstädten), wächst bei jedem Lauf nur um die neuen Tage."""
    old = read("temp_historie.json", {"tage": {}})
    tage = old.get("tage", {})
    bis = (NOW - timedelta(days=7)).date()
    start = (datetime.strptime(max(tage), "%Y-%m-%d").date() + timedelta(days=1)) if tage else datetime(2018, 1, 1).date()
    while start <= bis:
        ende = min(bis, start + timedelta(days=730))
        q = urllib.parse.urlencode({"latitude": ",".join(str(o[0]) for o in STAEDTE_DE), "longitude": ",".join(str(o[1]) for o in STAEDTE_DE),
                                    "start_date": start.isoformat(), "end_date": ende.isoformat(), "daily": "temperature_2m_mean", "timezone": "Europe/Berlin"})
        d = get_json("https://archive-api.open-meteo.com/v1/archive?" + q, timeout=120)
        if isinstance(d, dict):
            d = [d]
        zeit = d[0]["daily"]["time"]
        for i, t in enumerate(zeit):
            w = [x["daily"]["temperature_2m_mean"][i] for x in d if x["daily"]["temperature_2m_mean"][i] is not None]
            if w:
                tage[t] = round(sum(w) / len(w), 2)
        start = ende + timedelta(days=1)
    write("temp_historie.json", {"stand": stamp(), "quelle": "Open-Meteo Archiv (CC BY 4.0), Mittel aus 6 Großstädten", "tage": tage})
    return tage


def preisanalyse(hist):
    """Zusammenhang zwischen TTF-Preis und Einspeicherung im Sommer (Apr-Okt) je Jahr, und wo der Preis jetzt im Verhältnis zur Historie steht."""
    p1 = int(datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp())
    d = get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/TTF%3DF?period1={p1}&period2={int(NOW.timestamp())}&interval=1d", {"User-Agent": "Mozilla/5.0"}, 60)
    res = d["chart"]["result"][0]
    preise = {datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"): c for t, c in zip(res.get("timestamp") or [], res["indicators"]["quote"][0].get("close") or []) if c is not None}
    if len(preise) < 500:
        raise ValueError(f"zu wenig Preisdaten ({len(preise)})")
    jahre = []
    for y in range(2018, NOW.year + 1):
        sp = [v for t, v in preise.items() if t.startswith(str(y)) and 4 <= int(t[5:7]) <= 10]
        ei = [h["i"] for t, h in hist.items() if t.startswith(str(y)) and 4 <= int(t[5:7]) <= 10]
        if len(sp) > 100 and len(ei) > 100:
            jahre.append({"jahr": y, "ttf_mittel": round(sum(sp) / len(sp), 1), "einspeicherung_mittel_gwh": round(sum(ei) / len(ei)), "tage": len(ei)})
    n = len(jahre)
    r = None
    if n >= 4:
        xs, ys = [j["ttf_mittel"] for j in jahre], [j["einspeicherung_mittel_gwh"] for j in jahre]
        mx, my = sum(xs) / n, sum(ys) / n
        sx = sum((x - mx) ** 2 for x in xs) ** 0.5
        sy = sum((y - my) ** 2 for y in ys) ** 0.5
        r = round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 2) if sx and sy else None
    alle = sorted(preise.values())
    aktuell = preise[max(preise)]
    perz = round(sum(1 for v in alle if v <= aktuell) / len(alle) * 100)
    vor30 = [v for t, v in sorted(preise.items())][-31]
    return {"stand": stamp(), "quelle": "Yahoo Finance (TTF) und GIE AGSI+", "jahre": jahre, "korrelation": r, "anzahl_jahre": n, "ttf_aktuell": round(aktuell, 1),
            "perzentil_seit_2018": perz, "aenderung_30_tage_prozent": round((aktuell - vor30) / vor30 * 100, 1), "ttf_median_seit_2018": round(alle[len(alle) // 2], 1)}


def gas_vorausschau():
    key = os.environ.get("GIE_API_KEY", "").strip()
    if not key:
        return {"stand": stamp(), "hinweis": "Noch kein GIE-Schlüssel hinterlegt."}
    old = read("gas_vorausschau.json", {})
    try:
        alt = datetime.strptime(old["stand"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if NOW - alt < timedelta(hours=5) and old.get("szenarien") and old.get("einspeicherung") and old.get("importausfall") and read("gas_umfeld_vorausschau.json", {}).get("anlagen") and not old.get("fehler"):
            return None  # aufwendig (Historie seit 2018), deshalb nur alle paar Stunden
    except (KeyError, ValueError):
        pass
    import modell
    hist = agsi_de_historie(key)
    temp = temp_historie()
    pipe, lng = read("gas_pipeline.json", {}), read("gas_lng.json", {})
    cfg = read_cfg("modell.json")
    res, ctx = modell.vorausschau(hist, temp, read("wetter.json", {}), cfg, max(hist),
                                  {"pipeline_netto": pipe.get("summe_netto"), "lng": lng.get("summe"),
                                   "norwegen": next((g["netto"] for g in pipe.get("gruppen", []) if g.get("name") == "Norwegen"), None)})
    res["stand"] = stamp()
    # Verlauf der Prognose festhalten, damit sichtbar wird, wie sie sich mit dem tatsächlichen Verlauf ändert
    try:
        pv = read("prognose_verlauf.json", {"eintraege": []}).get("eintraege", [])
        tag = max(hist)
        sz = res["szenarien"]
        eintrag = {"tag": tag, "fuellstand": res["ausgangslage"]["fuellstand_prozent"], "mild_feb": sz["mild"]["konstant"]["fuellstand_ziel_tag"],
                   "normal_feb": sz["normal"]["konstant"]["fuellstand_ziel_tag"], "kalt_feb": sz["kalt"]["konstant"]["fuellstand_ziel_tag"],
                   "normal_ende": sz["normal"]["konstant"]["fuellstand_ende"], "normal_unter30": sz["normal"]["konstant"]["erreicht"].get(30), "stand": stamp()}
        pv = [e for e in pv if e.get("tag") != tag] + [eintrag]
        write("prognose_verlauf.json", {"eintraege": sorted(pv, key=lambda e: e["tag"])[-120:]})
    except Exception as e:  # noqa: BLE001
        print("FEHL prognose_verlauf", e, file=sys.stderr)
    # Gaspreis (TTF) und Einspeicherung seit 2018
    try:
        write("gas_preisanalyse.json", preisanalyse(hist))
    except Exception as e:  # noqa: BLE001
        write("gas_preisanalyse.json", {"stand": stamp(), "fehler": f"{type(e).__name__}: {e}"[:300]})
    # Speicher im Umfeld Brandenburgs: je Anlage eigene Historie und eigene Vorausschau
    try:
        fac = []
        for a in read_cfg("brandenburg-speicher.json").get("umfeld", []):
            h = agsi_de_historie(key, 2018, f"&company={firma_von(a['eic'])}&facility={a['eic']}")
            if h:
                fac.append({"name": a["name"], "region": a.get("region", ""), "hist": h})
        ev = modell.umfeld_vorausschau(fac, hist, ctx["fit"], temp, ctx["tmaps"], ctx["start"], ctx["bis"], cfg["ziel"]["datum"], ctx["basis"])
        ev["stand"] = stamp()
        ev["quelle"] = "GIE AGSI+ (je Anlage seit 2018), Open-Meteo, eigene Berechnung"
        ev["ziel"] = cfg["ziel"]
        write("gas_umfeld_vorausschau.json", ev)
    except Exception as e:  # noqa: BLE001
        write("gas_umfeld_vorausschau.json", {"stand": stamp(), "fehler": f"{type(e).__name__}: {e}"[:500]})
        print("FEHL umfeld_vorausschau", e, file=sys.stderr)
    res["quelle"] = "GIE AGSI+ (Speicherdaten seit 2018), Open-Meteo (Temperaturen), eigene Berechnung"
    return res


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


def reichweite_fuer(name, fluss, stock, kap, temps, tage, idx, ziel=None):
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
    if ziel:
        rest = stock - ziel["prozent"] / 100 * kap
        heute = NOW.date()
        stichtag = datetime.strptime(ziel["datum"], "%Y-%m-%d").date()
        out["ziel"] = {"prozent": ziel["prozent"], "datum": ziel["datum"], "tage_bis_stichtag": (stichtag - heute).days}
        if rest <= 0:
            out["ziel"]["tage_bis_marke"] = 0
        elif netto7 > 0.01:
            tage_m = round(rest * 1000 / netto7)
            out["ziel"]["tage_bis_marke"] = tage_m
            out["ziel"]["marke_ca_datum"] = (heute + timedelta(days=tage_m)).isoformat()
    return out


def reichweite():
    sp, we = read("gas_speicher.json", {}), read("wetter.json", {})
    if not sp.get("deutschland"):
        return {"stand": stamp(), "hinweis": "Keine Speicherdaten."}
    tage, idx = we.get("tage", []), we.get("heute_index", 7)
    de = sp["deutschland"]
    out = {"stand": stamp(), "annahmen": ("Reine Schätzung nur für die Gasspeicher, ohne Importe, LNG und Verbrauchsänderungen. Grundlage: mittlere Ein- und Ausspeicherung der letzten 7 Tage. "
                                           "Mit Wetter: Die Ausspeicherung folgt dem Heizbedarf (Heizgradtage, Basis 15 °C) der Temperaturvorhersage."),
           "deutschland": reichweite_fuer("Deutschland", de.get("fluss"), de["gas_twh"], de["kapazitaet_twh"], we.get("deutschland"), tage, idx,
                                         {"prozent": 30, "datum": "2027-02-01"}),
           "ziel_quelle": "Bundesnetzagentur, Seite „Aktuelle Lage der Gasversorgung“ (Füllstandsvorgabe 30 % zum 1. Februar 2027)",
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
        ("gaspreis.json", gaspreis), ("lng_tanks.json", lng_tanks), ("gas_umfeld.json", gas_umfeld), ("gas_stoerungen.json", gas_stoerungen), ("gas_vorausschau.json", gas_vorausschau),
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
