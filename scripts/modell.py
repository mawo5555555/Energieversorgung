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


def ols(X, y):
    """Kleinste Quadrate für wenige Merkmale (Spalte 0 ist die Konstante). Gibt Koeffizienten und R² zurück."""
    k = len(X[0])
    A = [[sum(r[i] * r[j] for r in X) for j in range(k)] for i in range(k)]
    b = [sum(r[i] * yy for r, yy in zip(X, y)) for i in range(k)]
    for i in range(k):
        piv = max(range(i, k), key=lambda r: abs(A[r][i]))
        A[i], A[piv] = A[piv], A[i]
        b[i], b[piv] = b[piv], b[i]
        d = A[i][i]
        if abs(d) < 1e-12:
            raise ValueError("Merkmale nicht unabhängig")
        for j in range(i + 1, k):
            fct = A[j][i] / d
            for c in range(i, k):
                A[j][c] -= fct * A[i][c]
            b[j] -= fct * b[i]
    coef = [0.0] * k
    for i in range(k - 1, -1, -1):
        coef[i] = (b[i] - sum(A[i][j] * coef[j] for j in range(i + 1, k))) / A[i][i]
    my = sum(y) / len(y)
    ss_tot = sum((yy - my) ** 2 for yy in y)
    ss_res = sum((yy - sum(c * v for c, v in zip(coef, r))) ** 2 for r, yy in zip(X, y))
    return coef, (1 - ss_res / ss_tot) if ss_tot else 0.0


def verstromung_fit(gas_mwh, temp, wind, basis, eta):
    """Gas-Stromerzeugung (GWh Strom/Tag) ~ Heizgradtage + Wind + Strahlung, Heizperiode Okt-Mär."""
    X, y = [], []
    for t, mwh in gas_mwh.items():
        m = int(t[5:7])
        if (m >= 10 or m <= 3) and t in temp and t in wind:
            X.append([1.0, hdd(temp[t], basis), wind[t][0], wind[t][1]])
            y.append(mwh / 1000.0)
    if len(y) < 300:
        raise ValueError("zu wenig Daten für die Verstromung")
    coef, r2 = ols(X, y)
    return {"a": coef[0], "b_hdd": coef[1], "c_wind": coef[2], "d_rad": coef[3], "r2": r2, "n": len(y), "eta": eta}


def gas_fuer_strom(fv, T, wind, rad, basis):
    """Erdgas-Einsatz der Kraftwerke (GWh/Tag) aus Wetter."""
    el = max(0.0, fv["a"] + fv["b_hdd"] * hdd(T, basis) + fv["c_wind"] * wind + fv["d_rad"] * rad)
    return el / fv["eta"]


def fit_entnahme_mit_strom(hist, temp, gas_mwh, eta, basis=15.0):
    """Entnahme ~ Heizgradtage + Erdgas-Einsatz der Kraftwerke (beobachtet), Heizperiode, Füllstand 35-95 %."""
    X, y = [], []
    for t, r in hist.items():
        m = int(t[5:7])
        if (m >= 11 or m <= 3) and 35 <= r["full"] <= 95 and t in temp and t in gas_mwh:
            X.append([1.0, hdd(temp[t], basis), gas_mwh[t] / 1000.0 / eta])
            y.append(r["w"])
    if len(y) < 100:
        raise ValueError("zu wenig Daten")
    coef, r2 = ols(X, y)
    return {"a": coef[0], "b": coef[1], "e": coef[2], "r2": r2, "n": len(y)}


def ostern(jahr):
    a = jahr % 19
    b, c = divmod(jahr, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat, tag = divmod(h + l - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def kalender(d):
    """(Samstag, Sonntag, Feiertag) als 0/1; Feiertag 0,5 für den 24./31.12. und die Tage zwischen den Jahren."""
    sat, sun = (1.0 if d.weekday() == 5 else 0.0), (1.0 if d.weekday() == 6 else 0.0)
    o = ostern(d.year)
    fest = {date(d.year, 1, 1), date(d.year, 5, 1), date(d.year, 10, 3), date(d.year, 12, 25), date(d.year, 12, 26),
            o - timedelta(days=2), o + timedelta(days=1), o + timedelta(days=39), o + timedelta(days=50)}
    hol = 1.0 if d in fest else 0.0
    if hol == 0.0 and ((d.month == 12 and d.day in (24, 27, 28, 29, 30, 31)) or (d.month == 1 and d.day in (2, 3))):
        hol = 0.5
    return sat, sun, hol


def wols(X, y, w):
    """Gewichtete kleinste Quadrate: gibt Koeffizienten zurück und R² (ungewichtet)."""
    Xw = [[v * (wi ** 0.5) for v in r] for r, wi in zip(X, w)]
    yw = [yy * (wi ** 0.5) for yy, wi in zip(y, w)]
    coef, _ = ols(Xw, yw)
    my = sum(y) / len(y)
    ss_tot = sum((yy - my) ** 2 for yy in y)
    ss_res = sum((yy - sum(c * v for c, v in zip(coef, r))) ** 2 for r, yy in zip(X, y))
    return coef, (1 - ss_res / ss_tot) if ss_tot else 0.0


def mean_hdd_lag(temp_fn, d, basis):
    v = [hdd(temp_fn(d - timedelta(days=k)), basis) for k in (1, 2)]
    return sum(v) / 2.0


def fit_strom_voll(gas_mwh, temp, wind, kohle, preis, basis, eta):
    """Gas-Stromerzeugung (GWh Strom/Tag) ~ Kälte + Wind + Sonne + Kohlestrom + Strompreis + Kalender, Heizperiode Okt-Mär."""
    X, y = [], []
    for t, mwh in gas_mwh.items():
        m = int(t[5:7])
        if (m >= 10 or m <= 3) and t in temp and t in wind and (kohle is None or t in kohle) and (preis is None or t in preis):
            sat, sun, hol = kalender(s2d(t))
            row = [1.0, hdd(temp[t], basis), wind[t][0], wind[t][1], sat, sun, hol]
            if kohle is not None:
                row.append(kohle[t] / 1000.0)
            if preis is not None:
                row.append(preis[t])
            X.append(row)
            y.append(mwh / 1000.0)
    if len(y) < 300:
        raise ValueError("zu wenig Daten für die Verstromung")
    coef, r2 = ols(X, y)
    fv = {"a": coef[0], "b_hdd": coef[1], "c_wind": coef[2], "d_rad": coef[3], "sat": coef[4], "sun": coef[5], "hol": coef[6], "r2": r2, "n": len(y), "eta": eta,
          "k_kohle": None, "k_preis": None}
    i = 7
    if kohle is not None:
        fv["k_kohle"] = coef[i]
        i += 1
    if preis is not None:
        fv["k_preis"] = coef[i]
    return fv


def gas_strom_voll(fv, T, wind, rad, kohle_el, preis, d, basis):
    sat, sun, hol = kalender(d)
    el = fv["a"] + fv["b_hdd"] * hdd(T, basis) + fv["c_wind"] * wind + fv["d_rad"] * rad + fv["sat"] * sat + fv["sun"] * sun + fv["hol"] * hol
    if fv["k_kohle"] is not None and kohle_el is not None:
        el += fv["k_kohle"] * kohle_el
    if fv["k_preis"] is not None and preis is not None:
        el += fv["k_preis"] * preis
    return max(0.0, el) / fv["eta"]


def fit_entnahme_voll(hist, temp, wind, gas_mwh, ttf, eta, basis, jahr_jetzt):
    """Entnahme ~ Kälte + Kältenachwirkung + Wind + Gaskraftwerke + Kalender + Gaspreis, gewichtet nach Aktualität."""
    X, y, w = [], [], []
    for t, r in hist.items():
        m = int(t[5:7])
        if not ((m >= 11 or m <= 3) and 35 <= r["full"] <= 95 and t in temp and t in wind and t in gas_mwh):
            continue
        d = s2d(t)
        t1, t2 = d2s(d - timedelta(days=1)), d2s(d - timedelta(days=2))
        if t1 not in temp or t2 not in temp:
            continue
        sat, sun, hol = kalender(d)
        lag = (hdd(temp[t1], basis) + hdd(temp[t2], basis)) / 2.0
        row = [1.0, hdd(temp[t], basis), lag, wind[t][0], gas_mwh[t] / 1000.0 / eta, sat, sun, hol]
        if ttf is not None:
            vals = [ttf[d2s(d - timedelta(days=k))] for k in range(1, 31) if d2s(d - timedelta(days=k)) in ttf]
            if len(vals) < 20:
                continue
            row.append(sum(vals) / len(vals))
        X.append(row)
        y.append(r["w"])
        w.append(0.7 ** max(0, jahr_jetzt - d.year - (0 if m >= 11 else 1)))
    if len(y) < 150:
        raise ValueError("zu wenig Daten")
    coef, r2 = wols(X, y, w)
    out = {"a": coef[0], "b": coef[1], "lag": coef[2], "wind": coef[3], "e": coef[4], "sat": coef[5], "sun": coef[6], "hol": coef[7], "ttf": coef[8] if ttf is not None else None, "r2": r2, "n": len(y)}
    return out


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


def simuliere(start, stock, kap, i_tag, tmap, bis, fit, cap, basis=15.0, extra=0.0, extra_fn=None):
    """Tagesweise Simulation. tmap(datum) -> Temperatur. extra = zusätzlicher Entnahmebedarf je Tag (GWh), z. B. bei Importausfall.

    Fehlmenge = Bedarf, den die Speicher nicht liefern können (wegen Leistungsgrenze oder weil sie leer sind).
    """
    verlauf, ungedeckt, engpass = [], 0.0, 0
    erreicht = {}
    erster_engpass = None
    fehl_summe, fehl_tage, fehl_erster, fehl_spitze = 0.0, 0, None, 0.0
    d = start
    while d <= bis:
        f = stock / kap * 100
        bedarf = max(0.0, fit["a"] + fit["b"] * hdd(tmap(d), basis) + (extra_fn(d) if extra_fn else 0.0)) + extra
        c = cap(f)
        w = min(bedarf, c)
        if bedarf > c + 1e-9:
            engpass += 1
            if erster_engpass is None:
                erster_engpass = d2s(d)
            ungedeckt += (bedarf - c) / 1000.0
        zu = i_tag if f < 99.5 else 0.0
        verfuegbar = stock * 1000.0 + zu
        w_eff = min(w, verfuegbar)
        fehl = bedarf - w_eff
        if fehl > 1.0:
            fehl_summe += fehl / 1000.0
            fehl_tage += 1
            fehl_spitze = max(fehl_spitze, fehl)
            if fehl_erster is None:
                fehl_erster = d2s(d)
        stock = min(kap, max(0.0, stock + (zu - w_eff) / 1000.0))
        f2 = stock / kap * 100
        verlauf.append([d2s(d), round(f2, 1)])
        for marke in (30, 20, 10):
            if marke not in erreicht and f2 < marke:
                erreicht[marke] = d2s(d)
        if "leer" not in erreicht and stock <= 0.001:
            erreicht["leer"] = d2s(d)
        d += timedelta(days=1)
    return {"verlauf": verlauf, "erreicht": erreicht, "engpass_tage": engpass, "ungedeckt_twh": round(ungedeckt, 2), "erster_engpass": erster_engpass,
            "fehl_twh": round(fehl_summe, 2), "fehl_tage": fehl_tage, "fehl_erster": fehl_erster, "fehl_spitze_gwh": round(fehl_spitze)}


def wert_am(verlauf, tag):
    for t, v in verlauf:
        if t == tag:
            return v
    return None


def rueckrechnung(hist, temp, fit, cap, basis=15.0, extra_fn=None):
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
        sim = simuliere(start, r["twh"], r["kap"], i_tag, lambda d: temp.get(d2s(d), 5.0), date(y + 1, 3, 31), fit, cap, basis, 0.0, extra_fn)
        feb, mrz = d2s(date(y + 1, 2, 1)), d2s(date(y + 1, 3, 31))
        if feb in hist and mrz in hist:
            out.append({"winter": f"{y}/{str(y + 1)[2:]}", "start_prozent": round(r["full"], 1),
                        "ist_1_feb": round(hist[feb]["full"], 1), "modell_1_feb": wert_am(sim["verlauf"], feb),
                        "ist_31_maerz": round(hist[mrz]["full"], 1), "modell_31_maerz": wert_am(sim["verlauf"], mrz)})
    for o in out:
        o["fehler_1_feb"] = round(o["modell_1_feb"] - o["ist_1_feb"], 1)
        o["fehler_31_maerz"] = round(o["modell_31_maerz"] - o["ist_31_maerz"], 1)
    return out


def mindest_einspeicherung(start, stock, kap, tmap, bis, fit, cap, basis, metrik, ziel, i_max=4000.0, extra_fn=None):
    """Kleinste konstante Einspeicherung (GWh/Tag), bei der metrik(sim) >= ziel gilt. 0 = schon ohne Mehr erreicht, None = nicht erreichbar."""
    def ok(i):
        return metrik(simuliere(start, stock, kap, i, tmap, bis, fit, cap, basis, 0.0, extra_fn)) >= ziel
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


def umfeld_vorausschau(anlagen, nat_hist, nat_fit, temp, tmaps, start, bis, ziel_tag, basis=15.0):
    """Vorausschau je Speicher im Umfeld Brandenburgs (eigene Entnahme-Historie, eigene Höchstleistung) und zusammen.

    anlagen: Liste von {"name", "region", "hist"}. Ohne ausreichende eigene Historie wird die Entnahme über den Anteil
    am deutschen Verlauf geschätzt, ohne beobachtete Leistung bei niedrigem Füllstand gilt die Hälfte der Höchstleistung (Annahme).
    """
    res, summe = [], {}
    letzte_nat = sorted(nat_hist)[-30:]
    nat_w30 = sum(nat_hist[t]["w"] for t in letzte_nat) or 1.0
    for a in anlagen:
        h = a["hist"]
        tage = sorted(h)
        if not tage:
            continue
        last = tage[-1]
        r0 = h[last]
        kap, stock = r0["kap"], r0["twh"]
        if kap <= 0:
            continue
        l7 = [h[t]["i"] for t in tage[-7:]]
        i7 = sum(l7) / len(l7)
        hinweise = []
        try:
            fit = fit_entnahme(h, temp, basis)
            if fit["b"] <= 0:
                raise ValueError("kein Temperaturzusammenhang")
        except ValueError:
            anteil = (sum(h[t]["w"] for t in tage[-30:] if t in nat_hist) / nat_w30) if nat_w30 else 0.0
            fit = {"a": nat_fit["a"] * anteil, "b": nat_fit["b"] * anteil, "r2": None, "n": 0}
            hinweise.append("Entnahme über Anteil am deutschen Verlauf geschätzt")
        w_alle = [h[t]["w"] for t in tage]
        hoch_kand = [h[t]["w"] for t in tage if h[t]["full"] >= 30]
        hoch = sorted(hoch_kand)[int(0.995 * (len(hoch_kand) - 1))] if len(hoch_kand) >= 30 else max(w_alle)
        hoch = max(hoch, 1.0)
        tief = cap_tief(h)
        if tief is None:
            tief = 0.5 * hoch
            hinweise.append("Leistung bei niedrigem Füllstand nie beobachtet, Hälfte der Höchstleistung angenommen")
        tief = min(tief, hoch)
        eintrag = {"name": a["name"], "region": a.get("region", ""), "gastag": last, "fuellstand_prozent": round(r0["full"], 1), "gas_twh": round(stock, 2),
                   "kapazitaet_twh": round(kap, 2), "ausspeicherleistung_gemeldet_gwh": round(r0.get("wcap", 0) or 0),
                   "hoechste_entnahme_gwh": round(max(w_alle)), "leistung_hoch_gwh": round(hoch), "leistung_tief_gwh": round(tief),
                   "einspeicherung_7t_gwh": round(i7, 1), "hinweise": hinweise, "szenarien": {}}
        for name, tm in tmaps.items():
            eintrag["szenarien"][name] = {}
            for var in ("konstant", "faellt"):
                sim = simuliere(start, stock, kap, i7, tm, bis, fit, cap_fn(var, hoch, tief), basis)
                eintrag["szenarien"][name][var] = {"fuellstand_ziel_tag": wert_am(sim["verlauf"], ziel_tag), "fuellstand_ende": sim["verlauf"][-1][1],
                                                  "erreicht": sim["erreicht"], "erster_engpass": sim["erster_engpass"], "engpass_tage": sim["engpass_tage"]}
                bucket = summe.setdefault((name, var), {"kap": 0.0, "pfade": []})
                bucket["kap"] += kap
                bucket["pfade"].append((kap, sim["verlauf"]))
        res.append(eintrag)
    agg = {}
    for (name, var), b in summe.items():
        tage = [t for t, _ in b["pfade"][0][1]]
        verlauf = []
        for k, t in enumerate(tage):
            st = sum(kap * v[k][1] / 100.0 for kap, v in b["pfade"])
            verlauf.append([t, round(st / b["kap"] * 100, 1)])
        erreicht = {}
        for marke in (30, 20, 10):
            for t, v in verlauf:
                if v < marke:
                    erreicht[marke] = t
                    break
        agg.setdefault(name, {})[var] = {"verlauf": verlauf[::2], "fuellstand_ziel_tag": wert_am(verlauf, ziel_tag), "fuellstand_ende": verlauf[-1][1], "erreicht": erreicht}
    return {"anlagen": res, "gesamt": agg, "gesamt_kapazitaet_twh": round(sum(a["kapazitaet_twh"] for a in res), 2),
            "gesamt_gas_twh": round(sum(a["gas_twh"] for a in res), 2)}


def vorausschau(hist, temp, wetter, cfg, stand_tag, import_ref=None, strom=None):
    """Hauptfunktion: Szenarien mild/normal/kalt, je mit konstanter und fallender Ausspeicherleistung."""
    basis = cfg.get("heizgrenze_c", 15)
    fit = fit_entnahme(hist, temp, basis)
    fit_alt_r2 = fit["r2"]
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

    # Weitere Faktoren: Gaskraftwerke (Kälte, Wind, Sonne, Kohle, Strompreis), Kalender, Gaspreis, Kältenachwirkung, Aktualität
    verstr = {"aktiv": False, "grund": "keine Daten"}
    extra_fn_fuer = None
    wp10 = None
    modell2 = None
    try:
        if strom and strom.get("gas_mwh") and strom.get("wind"):
            eta = strom.get("eta", 0.5)
            kohle = strom.get("kohle") if strom.get("kohle") and len(strom["kohle"]) > 500 else None
            preis = strom.get("preis") if strom.get("preis") and len(strom["preis"]) > 500 else None
            ttf = strom.get("ttf") if strom.get("ttf") and len(strom["ttf"]) > 500 else None
            fv = fit_strom_voll(strom["gas_mwh"], temp, strom["wind"], kohle, preis, basis, eta)
            fit2 = fit_entnahme_voll(hist, temp, strom["wind"], strom["gas_mwh"], ttf, eta, basis, heute.year)
            ttf_geprueft = fit2["ttf"]
            ttf_verworfen = False
            if ttf is not None and fit2["ttf"] is not None and fit2["ttf"] >= 0:
                # Ein höherer Preis kann nicht mehr Entnahme verursachen: Scheinzusammenhang (Krisenjahre), Term verwerfen
                fit2 = fit_entnahme_voll(hist, temp, strom["wind"], strom["gas_mwh"], None, eta, basis, heute.year)
                ttf_verworfen = True
            wclim = klima({t: v[0] for t, v in strom["wind"].items()}, heute.year - 1)
            rclim = klima({t: v[1] for t, v in strom["wind"].items()}, heute.year - 1)
            fcw, fcr = {}, {}
            if wetter and wetter.get("wind"):
                for t, w_, r_ in zip(wetter["tage"], wetter["wind"], wetter.get("strahlung") or [None] * len(wetter["tage"])):
                    if w_ is not None and r_ is not None:
                        fcw[t], fcr[t] = w_, r_
            winter_w = sorted(v[0] for t, v in strom["wind"].items() if int(t[5:7]) >= 11 or int(t[5:7]) <= 3)
            winter_r = sorted(v[1] for t, v in strom["wind"].items() if int(t[5:7]) >= 11 or int(t[5:7]) <= 3)
            wp10 = winter_w[int(0.10 * (len(winter_w) - 1))]
            rp25 = winter_r[int(0.25 * (len(winter_r) - 1))]
            jahr_f = bis.year
            # Zukunftswerte der Eingänge: Kohlestrom, Strompreis und Gaspreis bleiben auf dem Stand der letzten Tage
            def letztes_mittel(reihe, n):
                ks = sorted(reihe)[-n:]
                return sum(reihe[k] for k in ks) / len(ks) if ks else None
            kohle_now = (letztes_mittel(kohle, 7) / 1000.0) if kohle else None
            preis_now = letztes_mittel(preis, 14) if preis else None
            ttf_now = letztes_mittel(ttf, 30) if ttf else None

            def wetter_tag(d):
                sd = d2s(d)
                if sd in fcw:
                    return fcw[sd], fcr[sd]
                return wclim.get(sd[5:], winter_w[len(winter_w) // 2]), rclim.get(sd[5:], winter_r[len(winter_r) // 2])

            # Nachführung des Kraftwerksgases an die letzten Tage (klingt über 3 Wochen ab)
            bias_gas = 0.0
            try:
                abw = []
                if wetter and wetter.get("wind"):
                    for t, tt, w_, r_ in zip(wetter["tage"], wetter["deutschland"], wetter["wind"], wetter.get("strahlung") or []):
                        if t in strom["gas_mwh"] and tt is not None and w_ is not None and r_ is not None and t < d2s(heute):
                            kn = kohle[t] / 1000.0 if (kohle and t in kohle) else kohle_now
                            pn = preis[t] if (preis and t in preis) else preis_now
                            abw.append(strom["gas_mwh"][t] / 1000.0 / eta - gas_strom_voll(fv, tt, w_, r_, kn, pn, s2d(t), basis))
                abw = abw[-7:]
                if len(abw) >= 3:
                    bias_gas = sum(abw) / len(abw)
            except Exception:  # noqa: BLE001
                bias_gas = 0.0

            def rest_fn(tmap, wfun=None, flaute=False):
                wfun = wfun or wetter_tag

                def fnc(d):
                    w_, r_ = wfun(d)
                    g_norm = gas_strom_voll(fv, tmap(d), w_, r_, kohle_now, preis_now, d, basis) + bias_gas * max(0.0, 1.0 - max(0, (d - heute).days) / 21.0)
                    zusatz = fit2["e"] * g_norm
                    if flaute and date(jahr_f, 1, 11) <= d <= date(jahr_f, 1, 24):
                        g_fl = gas_strom_voll(fv, tmap(d), min(w_, wp10), min(r_, rp25), kohle_now, preis_now, d, basis)
                        zusatz = fit2["e"] * g_norm + min(fit2["e"], 1.0) * (g_fl - g_norm)
                    sat, sun, hol = kalender(d)
                    z = fit2["lag"] * mean_hdd_lag(tmap, d, basis) + fit2["wind"] * w_ + fit2["sat"] * sat + fit2["sun"] * sun + fit2["hol"] * hol
                    if fit2["ttf"] is not None and ttf_now is not None:
                        z += fit2["ttf"] * ttf_now
                    return z + zusatz
                return fnc

            extra_fn_fuer = lambda tmap, flaute=False: rest_fn(tmap, None, flaute)  # noqa: E731
            nutzen = fit2["r2"] - fit["r2"]
            winter_tage = [t for t in strom["gas_mwh"] if int(t[5:7]) >= 11 or int(t[5:7]) <= 3]
            gw = sorted(strom["gas_mwh"][t] / 1000.0 / eta for t in winter_tage)
            tg = sorted(strom["gas_mwh"])
            mw14 = 0.0
            for i2 in range(0, len(tg) - 14):
                fen = tg[i2:i2 + 14]
                if all(int(t[5:7]) >= 11 or int(t[5:7]) <= 3 for t in fen):
                    mw14 = max(mw14, sum(strom["gas_mwh"][t] for t in fen) / 14 / 1000.0 / eta)
            aktiv = fit2["e"] > 0 and nutzen > 0.005 and fv["r2"] > 0.3
            verstr = {"aktiv": aktiv, "grund": None if aktiv else "kein ausreichender Zusammenhang in den Daten", "wirkungsgrad": eta,
                      "fit_strom": {"r2": round(fv["r2"], 2), "n": fv["n"], "wind_gwh_je_ms": round(fv["c_wind"], 2), "kaelte_gwh_je_grad": round(fv["b_hdd"], 2), "strahlung_gwh_je_mj": round(fv["d_rad"], 2),
                                    "kohle_gwh_je_gwh": round(fv["k_kohle"], 2) if fv["k_kohle"] is not None else None, "strompreis_gwh_je_euro": round(fv["k_preis"], 3) if fv["k_preis"] is not None else None},
                      "fit_entnahme": {"e": round(fit2["e"], 2), "r2_neu": round(fit2["r2"], 2), "r2_alt": round(fit["r2"], 2)},
                      "winter": {"mittel_gwh_gas": round(sum(gw) / len(gw)), "p95_gwh_gas": round(gw[int(0.95 * (len(gw) - 1))]), "max14_gwh_gas": round(mw14)}, "wind_p10_ms": round(wp10, 1)}
            letzter_tag = max(strom["gas_mwh"])
            verstr["aktuell"] = {"tag": letzter_tag, "gas_mw": round(strom["gas_mwh"][letzter_tag] / 24.0), "gas_gwh_tag": round(strom["gas_mwh"][letzter_tag] / 1000.0 / eta)}
            verstr["abweichung_letzte_tage_gwh"] = round(bias_gas)
            vor = []
            for k in range(0, 14):
                dd = heute + timedelta(days=k)
                w_, r_ = wetter_tag(dd)
                tt = wetter["deutschland"][wetter["tage"].index(d2s(dd))] if wetter and d2s(dd) in wetter.get("tage", []) else 5.0
                vor.append([d2s(dd), round(w_, 1), round(gas_strom_voll(fv, tt, w_, r_, kohle_now, preis_now, dd, basis) + bias_gas * max(0.0, 1.0 - k / 21.0))])
            verstr["vorschau"] = vor
            modell2 = {"ttf_geprueft": ttf_geprueft if ttf_verworfen else None, "fit": fit2, "fv": fv, "kohle_now": kohle_now, "preis_now": preis_now, "ttf_now": ttf_now, "rest_fn": rest_fn, "wetter_tag": wetter_tag, "wclim": wclim, "rclim": rclim,
                       "fcw": fcw, "strom": strom}
            if aktiv:
                fit = {"a": fit2["a"], "b": fit2["b"], "r2": fit2["r2"], "n": fit2["n"]}
            else:
                extra_fn_fuer = None
                modell2 = None
        else:
            verstr = {"aktiv": False, "grund": (strom or {}).get("fehler") or "keine Daten"}
    except Exception as e:  # noqa: BLE001
        verstr = {"aktiv": False, "grund": f"{type(e).__name__}: {e}"[:200]}
        extra_fn_fuer = None
        modell2 = None

    szen = {}
    tmaps = {}
    for name, off in (("mild", off_mild), ("normal", 0.0), ("kalt", off_kalt)):
        tmaps[name] = tmap_fuer(off)
        szen[name] = {"abweichung_c": round(off, 1)}
        for var in ("konstant", "faellt"):
            sim = simuliere(start_tag + timedelta(days=1), r0["twh"], r0["kap"], i_tag, tmap_fuer(off), bis, fit, cap_fn(var, hoch, tief), basis, 0.0, extra_fn_fuer(tmap_fuer(off)) if extra_fn_fuer else None)
            ziel_tag = cfg["ziel"]["datum"]
            szen[name][var] = {"verlauf": sim["verlauf"][::2], "fuellstand_ziel_tag": wert_am(sim["verlauf"], ziel_tag),
                               "fuellstand_ende": sim["verlauf"][-1][1], "erreicht": sim["erreicht"],
                               "engpass_tage": sim["engpass_tage"], "ungedeckt_twh": sim["ungedeckt_twh"],
                               "fehl_twh": sim["fehl_twh"], "fehl_tage": sim["fehl_tage"], "fehl_erster": sim["fehl_erster"], "fehl_spitze_gwh": sim["fehl_spitze_gwh"]}
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
    exr = None
    if verstr.get("aktiv") and modell2:
        f2, fv2, st = modell2["fit"], modell2["fv"], modell2["strom"]
        kohle_h = st.get("kohle") if st.get("kohle") and len(st["kohle"]) > 500 else None
        preis_h = st.get("preis") if st.get("preis") and len(st["preis"]) > 500 else None
        ttf_h = st.get("ttf") if st.get("ttf") and len(st["ttf"]) > 500 else None

        def exr(d):
            sd = d2s(d)
            w_ = st["wind"].get(sd)
            if not w_:
                return 0.0
            kn = kohle_h[sd] / 1000.0 if (kohle_h and sd in kohle_h) else modell2["kohle_now"]
            pn = preis_h[sd] if (preis_h and sd in preis_h) else modell2["preis_now"]
            g = gas_strom_voll(fv2, temp.get(sd, 5.0), w_[0], w_[1], kn, pn, d, basis)
            sat, sun, hol = kalender(d)
            lag = mean_hdd_lag(lambda dd: temp.get(d2s(dd), 5.0), d, basis)
            tt = None
            if ttf_h:
                vals = [ttf_h[d2s(d - timedelta(days=k))] for k in range(1, 31) if d2s(d - timedelta(days=k)) in ttf_h]
                tt = sum(vals) / len(vals) if vals else None
            z = f2["e"] * g + f2["lag"] * lag + f2["wind"] * w_[0] + f2["sat"] * sat + f2["sun"] * sun + f2["hol"] * hol
            if f2["ttf"] is not None and tt is not None:
                z += f2["ttf"] * tt
            return z
    rr = rueckrechnung(hist, temp, fit, cap_fn("konstant", hoch, tief), basis, exr)
    fehler = [abs(o["fehler_1_feb"]) for o in rr]
    # Empfindlichkeit: Was, wenn Importe teilweise wegfallen (zusätzlicher Entnahmebedarf je Tag)?
    start_sim = start_tag + timedelta(days=1)
    ziel_tag = cfg["ziel"]["datum"]
    pn = (import_ref or {}).get("pipeline_netto") or 0
    lg = (import_ref or {}).get("lng") or 0
    nor = (import_ref or {}).get("norwegen") or 0
    ges = pn + lg
    faelle = [("Importe 10 % niedriger", 0.10 * ges), ("Importe 20 % niedriger", 0.20 * ges)]
    if lg:
        faelle.append(("LNG fällt ganz aus", lg))
    if nor:
        faelle.append(("Norwegen fällt ganz aus", nor))
    empf = []
    if verstr.get("aktiv") and extra_fn_fuer:
        gn = extra_fn_fuer(tmaps["normal"], False)
        gf = extra_fn_fuer(tmaps["normal"], True)
        tage_fl = [date(bis.year, 1, 11) + timedelta(days=k) for k in range(14)]
        extra_mittel = sum(gf(x) - gn(x) for x in tage_fl) / 14
        verstr["flaute"] = {"zeitraum": "11. bis 24. Januar", "zusatz_gwh_tag": round(extra_mittel)}
        eintrag_f = {"fall": "Windflaute und trübes Wetter, 14 Tage im Januar (Gaskraftwerke laufen mehr)", "gwh_tag": round(extra_mittel)}
        for name in ("normal", "kalt"):
            sim = simuliere(start_sim, r0["twh"], r0["kap"], i_tag, tmaps[name], bis, fit, cap_fn("faellt", hoch, tief), basis, 0.0, extra_fn_fuer(tmaps[name], True))
            eintrag_f[name] = {"fuellstand_ziel_tag": wert_am(sim["verlauf"], ziel_tag), "fuellstand_ende": sim["verlauf"][-1][1], "erreicht": sim["erreicht"],
                               "fehl_twh": sim["fehl_twh"], "fehl_tage": sim["fehl_tage"], "fehl_erster": sim["fehl_erster"], "fehl_spitze_gwh": sim["fehl_spitze_gwh"]}
        empf.append(eintrag_f)
    for text, extra in faelle:
        eintrag = {"fall": text, "gwh_tag": round(extra)}
        for name in ("normal", "kalt"):
            sim = simuliere(start_sim, r0["twh"], r0["kap"], i_tag, tmaps[name], bis, fit, cap_fn("faellt", hoch, tief), basis, extra, extra_fn_fuer(tmaps[name]) if extra_fn_fuer else None)
            eintrag[name] = {"fuellstand_ziel_tag": wert_am(sim["verlauf"], ziel_tag), "fuellstand_ende": sim["verlauf"][-1][1], "erreicht": sim["erreicht"],
                             "fehl_twh": sim["fehl_twh"], "fehl_tage": sim["fehl_tage"], "fehl_erster": sim["fehl_erster"], "fehl_spitze_gwh": sim["fehl_spitze_gwh"]}
        empf.append(eintrag)
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
        a1 = mindest_einspeicherung(start_sim, r0["twh"], r0["kap"], tmaps[name], bis, fit, cf, basis, lambda x: x["verlauf"][-1][1], mind_ende, 4000.0, extra_fn_fuer(tmaps[name]) if extra_fn_fuer else None)
        a2 = mindest_einspeicherung(start_sim, r0["twh"], r0["kap"], tmaps[name], bis, fit, cf, basis,
                                    lambda x: wert_am(x["verlauf"], ziel_tag) if wert_am(x["verlauf"], ziel_tag) is not None else 0.0, ziel_p, 4000.0, extra_fn_fuer(tmaps[name]) if extra_fn_fuer else None)
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
    # Wetterläufe der Vorjahre als Szenarien (statt nur mild/normal/kalt)
    analog = None
    try:
        sim_start = start_tag + timedelta(days=1)
        runs = []
        for y in range(2018, heute.year):
            def datum_a(d, y=y):
                jj = y if d.month >= 7 else y + 1
                tag = 28 if (d.month == 2 and d.day == 29) else d.day
                return date(jj, d.month, tag)

            def tm_y(d, y=y):
                sd = d2s(d)
                if sd in fc:
                    return fc[sd]
                return temp.get(d2s(datum_a(d, y)), normal.get(sd[5:], 5.0))

            wf = None
            if modell2:
                def wf(d, y=y):
                    sd = d2s(d)
                    if sd in modell2["fcw"]:
                        return modell2["wetter_tag"](d)
                    w_a = modell2["strom"]["wind"].get(d2s(datum_a(d, y)))
                    return (w_a[0], w_a[1]) if w_a else modell2["wetter_tag"](d)
            ex = modell2["rest_fn"](tm_y, wf) if modell2 else None
            sim = simuliere(sim_start, r0["twh"], r0["kap"], i_tag, tm_y, bis, fit, cap_fn("konstant", hoch, tief), basis, 0.0, ex)
            runs.append({"winter": f"{y}/{str(y + 1)[2:]}", "ziel": wert_am(sim["verlauf"], cfg["ziel"]["datum"]), "ende": sim["verlauf"][-1][1],
                         "unter20": sim["erreicht"].get(20), "leer": sim["erreicht"].get("leer"), "verlauf": sim["verlauf"]})
        if runs:
            tage_a = [t for t, _ in runs[0]["verlauf"]]
            band_min, band_max, band_med = [], [], []
            for k, t in enumerate(tage_a):
                vals = sorted(r["verlauf"][k][1] for r in runs)
                if k % 2 == 0:
                    band_min.append([t, vals[0]])
                    band_max.append([t, vals[-1]])
                    band_med.append([t, vals[len(vals) // 2]])
            zi = sorted(r["ziel"] for r in runs if r["ziel"] is not None)
            en = sorted(r["ende"] for r in runs)
            u20 = sorted(r["unter20"] for r in runs if r["unter20"])
            analog = {"anzahl": len(runs), "winter": [{k: v for k, v in r.items() if k != "verlauf"} for r in runs],
                      "band": {"min": band_min, "max": band_max, "median": band_med},
                      "ziel": {"min": zi[0], "median": zi[len(zi) // 2], "max": zi[-1]}, "ende": {"min": en[0], "median": en[len(en) // 2], "max": en[-1]},
                      "unter20": {"frueh": u20[0] if u20 else None, "spaet": u20[-1] if u20 else None, "anzahl": len(u20)}}
    except Exception as e:  # noqa: BLE001
        analog = {"fehler": f"{type(e).__name__}: {e}"[:200]}
    # Übersicht der Faktoren im Modell
    fakt = []
    if modell2:
        f2, fv2 = modell2["fit"], modell2["fv"]
        eta2 = fv2["eta"]
        def z(x, nk=0):
            return f"{x:+.{nk}f}".replace(".", ",")
        fakt = [
            {"name": "Wochentag und Feiertage", "status": "eingerechnet", "wirkung": f"Gegenüber einem Werktag: Samstag {z(f2['sat'])}, Sonntag {z(f2['sun'])}, Feiertag {z(f2['hol'])} GWh/Tag Entnahme."},
            {"name": "Kältenachwirkung (Vortage)", "status": "eingerechnet", "wirkung": f"Zusätzlich je Heizgradtag der letzten zwei Tage {z(f2['lag'])} GWh/Tag (Gebäude speichern Wärme). Direkt je Heizgradtag {z(f2['b'])}."},
            {"name": "Wind (Auskühlung)", "status": "eingerechnet", "wirkung": f"Je +1 km/h Wind {z(f2['wind'], 1)} GWh/Tag Entnahme, zusätzlich zum Einfluss über die Gaskraftwerke."},
            {"name": "Gaskraftwerke (Kälte, Wind, Sonne)", "status": "eingerechnet", "wirkung": f"Erklärt mit den Kraftwerken {round(f2['r2'] * 100)} % der Schwankung der Entnahme (ohne {round(fit_alt_r2 * 100)} %)."},
        ]
        if fv2["k_kohle"] is not None:
            fakt.append({"name": "Kohle- und Kernkraft", "status": "eingerechnet" if abs(fv2["k_kohle"] * 10 / eta2) >= 5 else "geprüft, kaum Einfluss", "wirkung": f"Je 10 GWh weniger Kohlestrom am Tag etwa {z(-fv2['k_kohle'] * 10 / eta2)} GWh Gas für Strom. Kohlestrom wird auf dem Stand der letzten 7 Tage gehalten, ein Kraftwerksausfall ist nicht vorhergesagt."})
        if fv2["k_preis"] is not None:
            fakt.append({"name": "Strompreis", "status": "eingerechnet" if abs(fv2["k_preis"] * 10 / eta2) >= 5 else "geprüft, kaum Einfluss", "wirkung": f"Je +10 €/MWh Börsenstrompreis etwa {z(fv2['k_preis'] * 10 / eta2)} GWh Gas für Strom. Der Preis wird auf dem Stand der letzten 14 Tage gehalten."})
        if f2["ttf"] is not None:
            fakt.append({"name": "Gaspreis (Preiselastizität)", "status": "eingerechnet", "wirkung": f"Je +10 €/MWh im 30-Tage-Mittel {z(f2['ttf'] * 10)} GWh/Tag Entnahme. Der Preis wird auf dem heutigen Stand gehalten."})
        elif modell2.get("ttf_geprueft") is not None:
            fakt.append({"name": "Gaspreis (Preiselastizität)", "status": "geprüft, nicht eingerechnet", "wirkung": f"In den Daten seit 2018 ergibt sich ein unplausibler Zusammenhang (höherer Preis, mehr Entnahme: {z(modell2['ttf_geprueft'] * 10)} GWh/Tag je +10 €/MWh), das ist eine Scheinkorrelation mit den Krisenjahren. Ein dämpfender Preiseffekt auf den Verbrauch ist plausibel, aber aus diesen Daten nicht belegbar."})
        fakt.append({"name": "Konjunktur und Heizverhalten", "status": "eingerechnet", "wirkung": "Jüngere Winter zählen stärker (Gewicht 0,7 je Jahr zurück), damit das sparsamere Verhalten nach 2022 stärker durchschlägt."})
    if analog and analog.get("winter"):
        fakt.append({"name": "Wetterläufe der Vorjahre", "status": "eingerechnet", "wirkung": f"Die Wetterabläufe von {analog['anzahl']} Wintern seit 2018 werden ab Ende der Vorhersage durchgerechnet. Füllstand am 1. Februar: {round(analog['ziel']['min'])} bis {round(analog['ziel']['max'])} %."})
    kontext = {"fit": fit, "tmaps": tmaps, "start": start_sim, "bis": bis, "basis": basis}
    ergebnis = {
        "ausgangslage": {"gastag": stand_tag, "fuellstand_prozent": round(r0["full"], 1), "gas_twh": round(r0["twh"], 1), "kapazitaet_twh": round(r0["kap"], 1),
                         "einspeicherung_7t_gwh": round(i_tag, 1), "wetter_bis": fc_ende},
        "modell": {"a_gwh": round(fit["a"], 1), "b_gwh_je_grad": round(fit["b"], 1), "r2": round(fit["r2"], 2), "tage": fit["n"], "heizgrenze_c": basis,
                   "leistung_hoch_gwh": round(hoch), "leistung_tief_gwh": round(tief) if tief else None},
        "szenarien": szen,
        "vorjahre": vor, "vorjahr_verlauf": vorjahr_verlauf,
        "rueckrechnung": rr, "rueckrechnung_mittlerer_fehler_pp": round(sum(fehler) / len(fehler), 1) if fehler else None,
        "ziel": cfg["ziel"], "einspeicherung": einsp, "analog": analog, "faktoren_modell": fakt, "importausfall": empf, "verstromung": verstr, "importe_ref": {"pipeline_netto": pn, "lng": lg, "norwegen": nor},
        "ohne_importe": {"jahresverbrauch_twh": cfg["jahresverbrauch_twh"], "quelle": cfg.get("jahresverbrauch_quelle"), "verbrauch_tag_twh": round(verbrauch_tag, 2),
                         "tage": round(r0["twh"] / verbrauch_tag)},
    }
    return ergebnis, kontext
