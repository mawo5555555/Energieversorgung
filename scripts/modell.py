"""Vorausschau der deutschen Gasspeicher bis zum Winterende.

Grundidee: Die Entnahme aus den Speichern hängt von der Kälte ab (Heizgradtage). Der Zusammenhang wird aus den
Winterdaten seit 2018 geschätzt. Die Entnahme ist nach oben begrenzt (Ausspeicherleistung), und diese Grenze kann bei
niedrigem Füllstand sinken. Dafür gibt es zwei Varianten:
  konstant   Grenze bleibt auf dem höchsten beobachteten Niveau
  faellt     Grenze sinkt linear von 40 % Füllstand bis 10 % auf den Wert, der bei 10-20 % Füllstand höchstens beobachtet wurde
Die zweite Variante ist eine Annahme, die sich an Beobachtungen anlehnt, aber nicht aus ihnen bewiesen werden kann.
Reine Standardbibliothek.
"""
from datetime import date, datetime, timedelta


def d2s(d):
    return d.isoformat()


def s2d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def hdd(t, basis):
    return max(0.0, basis - t)


def fit_entnahme(hist, temp, basis=15.0):
    """Entnahme (GWh/Tag) ~ a + b * Heizgradtage, Heizperiode (Nov-Mär), Füllstand 35-95 %."""
    xs, ys = [], []
    for t, r in hist.items():
        m = int(t[5:7])
        if (m >= 11 or m <= 3) and 35 <= r["full"] <= 95 and t in temp:
            xs.append(hdd(temp[t], basis))
            ys.append(r["w"])
    n = len(xs)
    if n < 100:
        raise ValueError("zu wenig Daten für die Schätzung")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    return {"a": a, "b": b, "r2": 1 - ss_res / ss_tot, "n": n}


def cap_hoch(hist):
    w = sorted(r["w"] for r in hist.values() if r["full"] >= 30)
    return w[int(0.995 * (len(w) - 1))]


def cap_tief(hist):
    w = []
    for t, r in hist.items():
        m = int(t[5:7])
        if 10 <= r["full"] < 20 and (m >= 10 or m <= 3):
            w.append(r["w"])
    return max(w) if w else None


def cap_fn(variante, hoch, tief):
    def cap(f):
        if variante == "konstant" or tief is None:
            return hoch
        if f >= 40:
            return hoch
        if f >= 10:
            return tief + (hoch - tief) * (f - 10) / 30.0
        return tief * max(0.0, f) / 10.0
    return cap


def klima(temp, jahr_bis):
    """Normale Tagestemperatur je Kalendertag (±3 Tage geglättet) aus den Jahren bis jahr_bis."""
    by = {}
    for t, v in temp.items():
        by.setdefault(t[5:], []).append((int(t[:4]), v))
    normal = {}
    for md in by:
        vals = []
        for off in range(-3, 4):
            ref = datetime.strptime("2000-" + md, "%Y-%m-%d").date() + timedelta(days=off)
            key = f"{ref.month:02d}-{ref.day:02d}"
            vals += [v for (y, v) in by.get(key, []) if y <= jahr_bis]
        if vals:
            normal[md] = sum(vals) / len(vals)
    return normal


def winter_abweichungen(temp):
    """Mitteltemperatur je Winter (Nov-Mär); liefert (Mittel, kältester, wärmster) für die Szenarien."""
    saison = {}
    for t, v in temp.items():
        y, m = int(t[:4]), int(t[5:7])
        if m >= 11:
            saison.setdefault(y, []).append(v)
        elif m <= 3:
            saison.setdefault(y - 1, []).append(v)
    mittel = {y: sum(v) / len(v) for y, v in saison.items() if len(v) > 120}
    alle = sum(mittel.values()) / len(mittel)
    return alle, min(mittel.values()) - alle, max(mittel.values()) - alle, mittel


def simuliere(start, stock, kap, i_tag, tmap, bis, fit, cap, basis=15.0):
    """Tagesweise Simulation. tmap(datum) -> Temperatur. Gibt Verlauf und Kennzahlen zurück."""
    verlauf, ungedeckt, engpass = [], 0.0, 0
    erreicht = {}
    d = start
    while d <= bis:
        f = stock / kap * 100
        bedarf = max(0.0, fit["a"] + fit["b"] * hdd(tmap(d), basis))
        c = cap(f)
        w = min(bedarf, c)
        if bedarf > c + 1e-9:
            engpass += 1
            ungedeckt += (bedarf - c) / 1000.0
        zu = i_tag if f < 99.5 else 0.0
        stock = min(kap, max(0.0, stock + (zu - w) / 1000.0))
        f2 = stock / kap * 100
        verlauf.append([d2s(d), round(f2, 1)])
        for marke in (30, 20, 10):
            if marke not in erreicht and f2 < marke:
                erreicht[marke] = d2s(d)
        if "leer" not in erreicht and stock <= 0.001:
            erreicht["leer"] = d2s(d)
        d += timedelta(days=1)
    return {"verlauf": verlauf, "erreicht": erreicht, "engpass_tage": engpass, "ungedeckt_twh": round(ungedeckt, 2)}


def wert_am(verlauf, tag):
    for t, v in verlauf:
        if t == tag:
            return v
    return None


def rueckrechnung(hist, temp, fit, cap, basis=15.0):
    """Prüft das Modell an vergangenen Wintern: Start 12.11. mit tatsächlicher Lage, echte Temperaturen, Ergebnis am 1.2. und 31.3."""
    out = []
    for y in range(2018, 2026):
        start = date(y, 11, 12)
        t0 = d2s(start - timedelta(days=1))
        if t0 not in hist:
            continue
        r = hist[t0]
        letzte = [hist[d2s(start - timedelta(days=k))]["i"] for k in range(1, 8) if d2s(start - timedelta(days=k)) in hist]
        i_tag = sum(letzte) / len(letzte) if letzte else 0.0
        sim = simuliere(start, r["twh"], r["kap"], i_tag, lambda d: temp.get(d2s(d), 5.0), date(y + 1, 3, 31), fit, cap, basis)
        feb, mrz = d2s(date(y + 1, 2, 1)), d2s(date(y + 1, 3, 31))
        if feb in hist and mrz in hist:
            out.append({"winter": f"{y}/{str(y + 1)[2:]}", "start_prozent": round(r["full"], 1),
                        "ist_1_feb": round(hist[feb]["full"], 1), "modell_1_feb": wert_am(sim["verlauf"], feb),
                        "ist_31_maerz": round(hist[mrz]["full"], 1), "modell_31_maerz": wert_am(sim["verlauf"], mrz)})
    for o in out:
        o["fehler_1_feb"] = round(o["modell_1_feb"] - o["ist_1_feb"], 1)
        o["fehler_31_maerz"] = round(o["modell_31_maerz"] - o["ist_31_maerz"], 1)
    return out


def mindest_einspeicherung(start, stock, kap, tmap, bis, fit, cap, basis, metrik, ziel, i_max=4000.0):
    """Kleinste konstante Einspeicherung (GWh/Tag), bei der metrik(sim) >= ziel gilt. 0 = schon ohne Mehr erreicht, None = nicht erreichbar."""
    def ok(i):
        return metrik(simuliere(start, stock, kap, i, tmap, bis, fit, cap, basis)) >= ziel
    if ok(0.0):
        return 0.0
    if not ok(i_max):
        return None
    lo, hi = 0.0, i_max
    for _ in range(30):
        mid = (lo + hi) / 2
        if ok(mid):
            hi = mid
        else:
            lo = mid
    return hi


def einspeicher_historie(hist, temp, laenge):
    """Winter 12.11.-31.3. je Jahr: Temperatur, mittlere Entnahme und Einspeicherung; dazu Rekorde der Einspeicherung."""
    winter = []
    for y in range(2018, 2026):
        tage = [d2s(date(y, 11, 12) + timedelta(days=k)) for k in range((date(y + 1, 3, 31) - date(y, 11, 12)).days + 1)]
        tage = [t for t in tage if t in hist]
        if len(tage) < 120:
            continue
        ts = [temp[t] for t in tage if t in temp]
        winter.append({"winter": f"{y}/{str(y + 1)[2:]}", "temp_c": round(sum(ts) / len(ts), 1) if ts else None,
                       "entnahme_gwh": round(sum(hist[t]["w"] for t in tage) / len(tage)), "einspeicherung_gwh": round(sum(hist[t]["i"] for t in tage) / len(tage)),
                       "start": round(hist[tage[0]]["full"], 1), "ende": round(hist[tage[-1]]["full"], 1)})
    alle = sorted(hist)
    werte = [hist[t]["i"] for t in alle]
    pre = [0.0]
    for v in werte:
        pre.append(pre[-1] + v)
    best, best_i = 0.0, 0
    for i in range(0, len(werte) - laenge + 1):
        m = (pre[i + laenge] - pre[i]) / laenge
        if m > best:
            best, best_i = m, i
    wtage = [t for t in alle if int(t[5:7]) >= 11 or int(t[5:7]) <= 3]
    wi = sorted(hist[t]["i"] for t in wtage)
    return {"winter": winter, "tagesmax_winter_gwh": round(wi[-1]), "tages_p95_winter_gwh": round(wi[int(0.95 * (len(wi) - 1))]),
            "hoechster_durchschnitt_winter_gwh": max((w["einspeicherung_gwh"] for w in winter), default=None),
            "hoechster_durchschnitt_beliebig_gwh": round(best), "hoechster_durchschnitt_von": alle[best_i], "hoechster_durchschnitt_bis": alle[best_i + laenge - 1],
            "laenge_tage": laenge}


def vorausschau(hist, temp, wetter, cfg, stand_tag, import_ref=None):
    """Hauptfunktion: Szenarien mild/normal/kalt, je mit konstanter und fallender Ausspeicherleistung."""
    basis = cfg.get("heizgrenze_c", 15)
    fit = fit_entnahme(hist, temp, basis)
    hoch, tief = cap_hoch(hist), cap_tief(hist)
    if tief is not None:
        tief = min(tief, hoch)
    start_tag = s2d(stand_tag)
    r0 = hist[stand_tag]
    letzte = [hist[d2s(start_tag - timedelta(days=k))] for k in range(0, 7) if d2s(start_tag - timedelta(days=k)) in hist]
    i_tag = sum(x["i"] for x in letzte) / len(letzte)
    heute = datetime.utcnow().date()
    normal = klima(temp, heute.year - 1)
    mittel, off_kalt, off_mild, _ = winter_abweichungen(temp)
    fc = {}
    if wetter and wetter.get("deutschland"):
        for t, v in zip(wetter["tage"], wetter["deutschland"]):
            if v is not None:
                fc[t] = v
    fc_ende = max(fc) if fc else None
    bis = s2d(cfg["horizont"])

    def tmap_fuer(offset):
        def f(d):
            s = d2s(d)
            if s in fc:
                return fc[s]
            return normal.get(s[5:], 5.0) + (offset if (fc_ende is None or s > fc_ende) else 0.0)
        return f

    szen = {}
    tmaps = {}
    for name, off in (("mild", off_mild), ("normal", 0.0), ("kalt", off_kalt)):
        tmaps[name] = tmap_fuer(off)
        szen[name] = {"abweichung_c": round(off, 1)}
        for var in ("konstant", "faellt"):
            sim = simuliere(start_tag + timedelta(days=1), r0["twh"], r0["kap"], i_tag, tmap_fuer(off), bis, fit, cap_fn(var, hoch, tief), basis)
            ziel_tag = cfg["ziel"]["datum"]
            szen[name][var] = {"verlauf": sim["verlauf"][::2], "fuellstand_ziel_tag": wert_am(sim["verlauf"], ziel_tag),
                               "fuellstand_ende": sim["verlauf"][-1][1], "erreicht": sim["erreicht"],
                               "engpass_tage": sim["engpass_tage"], "ungedeckt_twh": sim["ungedeckt_twh"]}
    # Vorjahre tatsächlich
    vor = []
    for y in range(2018, heute.year):
        a, b, c = d2s(date(y, 11, 12)), d2s(date(y + 1, 2, 1)), d2s(date(y + 1, 3, 31))
        if a in hist and b in hist and c in hist:
            vor.append({"winter": f"{y}/{str(y + 1)[2:]}", "start": round(hist[a]["full"], 1), "feb": round(hist[b]["full"], 1), "maerz": round(hist[c]["full"], 1)})
    vorjahr_verlauf = []
    y0 = heute.year - 1 if heute.month >= 7 else heute.year - 2
    for k in range(0, 160, 2):
        d = date(y0, 11, 11) + timedelta(days=k)
        if d2s(d) in hist:
            vorjahr_verlauf.append([d2s(date(d.year + 1, d.month, d.day)), round(hist[d2s(d)]["full"], 1)])
    rr = rueckrechnung(hist, temp, fit, cap_fn("konstant", hoch, tief), basis)
    fehler = [abs(o["fehler_1_feb"]) for o in rr]
    # Wie viel mehr Einspeicherung wäre nötig?
    start_sim = start_tag + timedelta(days=1)
    laenge = (bis - start_sim).days + 1
    ziel_tag = cfg["ziel"]["datum"]
    ziel_p = float(cfg["ziel"]["prozent"])
    mind_ende = float(cfg.get("mindest_ende_prozent", 10))
    ref_netto = (import_ref or {}).get("pipeline_netto"), (import_ref or {}).get("lng")
    bedarf = {}
    for name in ("mild", "normal", "kalt"):
        cf = cap_fn("konstant", hoch, tief)
        a1 = mindest_einspeicherung(start_sim, r0["twh"], r0["kap"], tmaps[name], bis, fit, cf, basis, lambda x: x["verlauf"][-1][1], mind_ende)
        a2 = mindest_einspeicherung(start_sim, r0["twh"], r0["kap"], tmaps[name], bis, fit, cf, basis,
                                    lambda x: wert_am(x["verlauf"], ziel_tag) if wert_am(x["verlauf"], ziel_tag) is not None else 0.0, ziel_p)
        def paket(x):
            if x is None:
                return {"noetig_gwh": None}
            return {"noetig_gwh": round(x), "zusatz_gwh": round(max(0.0, x - i_tag)), "faktor": round(x / i_tag, 1) if i_tag > 1 else None}
        bedarf[name] = {"nicht_leer": paket(a1), "vorgabe_1_feb": paket(a2)}
    his = einspeicher_historie(hist, temp, laenge)
    quote = None
    if ref_netto[0] is not None and ref_netto[1] is not None:
        quote = round(ref_netto[0] + ref_netto[1])
    einsp = {"jetzt_gwh": round(i_tag), "mindest_ende_prozent": mind_ende, "szenarien": bedarf, "historie": his,
             "einspeicherleistung_gemeldet_gwh": round(r0.get("icap", 0)) if r0.get("icap") else None, "importe_gwh": quote}
    verbrauch_tag = cfg["jahresverbrauch_twh"] / 365.0
    return {
        "ausgangslage": {"gastag": stand_tag, "fuellstand_prozent": round(r0["full"], 1), "gas_twh": round(r0["twh"], 1), "kapazitaet_twh": round(r0["kap"], 1),
                         "einspeicherung_7t_gwh": round(i_tag, 1), "wetter_bis": fc_ende},
        "modell": {"a_gwh": round(fit["a"], 1), "b_gwh_je_grad": round(fit["b"], 1), "r2": round(fit["r2"], 2), "tage": fit["n"], "heizgrenze_c": basis,
                   "leistung_hoch_gwh": round(hoch), "leistung_tief_gwh": round(tief) if tief else None},
        "szenarien": szen,
        "vorjahre": vor, "vorjahr_verlauf": vorjahr_verlauf,
        "rueckrechnung": rr, "rueckrechnung_mittlerer_fehler_pp": round(sum(fehler) / len(fehler), 1) if fehler else None,
        "ziel": cfg["ziel"], "einspeicherung": einsp,
        "ohne_importe": {"jahresverbrauch_twh": cfg["jahresverbrauch_twh"], "quelle": cfg.get("jahresverbrauch_quelle"), "verbrauch_tag_twh": round(verbrauch_tag, 2),
                         "tage": round(r0["twh"] / verbrauch_tag)},
    }
