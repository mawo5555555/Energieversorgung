/* Energie Brandenburg: liest die fertigen JSON-Dateien aus data/ und zeigt sie als Kacheln.
 * Die Dateien werden vom GitHub-Job (scripts/fetch_data.py) regelmäßig aktualisiert. */
(function () {
  "use strict";
  var nf = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });
  var nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
  var nf3 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  var nf2 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function when(iso) {
    var d = new Date(iso); if (isNaN(d)) return "unbekannt";
    return d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) + " Uhr";
  }
  function get(name) {
    return fetch("data/" + name + "?t=" + Date.now(), { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }
  function set(id, html) { var el = document.querySelector("#" + id + " .body"); if (el) el.innerHTML = html; }
  function hint(t, bad) { return '<p class="hint' + (bad ? " err" : "") + '">' + esc(t) + "</p>"; }
  function errNote(d) { return d && d.fehler ? hint("Letzter Abruf fehlgeschlagen (" + when(d.fehler_stand) + "): " + String(d.fehler).slice(0, 140), true) : ""; }
  function meta(d, extra) { return '<p class="meta">' + (d && d.stand ? "Stand " + when(d.stand) : "") + (extra ? " · " + extra : "") + "</p>"; }
  function noData(d, what) { return !d || (!d.stand && !d.fehler) ? hint(what + ": noch keine Daten vorhanden.") : null; }

  function spark(points, opts) {
    opts = opts || {};
    var v = points.filter(function (p) { return p[1] != null; });
    if (v.length < 2) return "";
    var min = opts.min != null ? opts.min : Math.min.apply(null, v.map(function (p) { return p[1]; }));
    var max = opts.max != null ? opts.max : Math.max.apply(null, v.map(function (p) { return p[1]; }));
    if (max - min < (opts.minSpan || 0.0001)) { var m = (max + min) / 2, s = (opts.minSpan || 1) / 2; min = m - s; max = m + s; }
    var n = v.length, d = v.map(function (p, i) { return (i ? "L" : "M") + (i / (n - 1) * 300).toFixed(1) + " " + (58 - (p[1] - min) / (max - min) * 54).toFixed(1); }).join(" ");
    var mid = opts.mid != null ? '<line class="mid" x1="0" x2="300" y1="' + (58 - (opts.mid - min) / (max - min) * 54).toFixed(1) + '" y2="' + (58 - (opts.mid - min) / (max - min) * 54).toFixed(1) + '"/>' : "";
    return '<svg class="spark" viewBox="0 0 300 62" preserveAspectRatio="none" role="img" aria-label="' + esc(opts.label || "Verlauf") + '">' + mid + '<path d="' + d + '"/></svg>';
  }
  function bars(items, unit, max) {
    max = max || Math.max.apply(null, items.map(function (i) { return i[1] || 0; })) || 1;
    return items.map(function (i) {
      return '<div class="row"><span>' + esc(i[0]) + '</span><div class="bar"><span style="width:' + Math.max(0, Math.min(100, (i[1] || 0) / max * 100)).toFixed(1) + '%"></span></div><span class="val">' +
        (i[1] == null ? "–" : nf.format(i[1]) + (unit ? " " + unit : "")) + "</span></div>";
    }).join("");
  }
  function gauge(pct, small, label) {
    var r = 44, c = 2 * Math.PI * r, f = Math.max(0, Math.min(100, pct)) / 100 * c;
    var col = pct < 30 ? "var(--red)" : pct < 60 ? "var(--orange)" : "var(--green)";
    return '<svg viewBox="0 0 100 100" role="img" aria-label="' + esc(label || "Füllstand") + '"><circle class="track" cx="50" cy="50" r="' + r + '" fill="none" stroke-width="10"/>' +
      '<circle class="arc" cx="50" cy="50" r="' + r + '" fill="none" stroke-width="10" stroke-linecap="round" style="stroke:' + col + '" stroke-dasharray="' + f.toFixed(1) + " " + c.toFixed(1) + '"/></svg>';
  }
  function lastVal(series) { for (var i = series.length - 1; i >= 0; i--) if (series[i][1] != null) return series[i]; return null; }

  function renderSpeicherDE(d) {
    var nd = noData(d, "Gasspeicher"); if (nd) return set("cSpeicherDE", nd);
    var h = errNote(d), de = d.deutschland;
    if (!de) h += hint(d.hinweis || "Keine Speicherdaten.");
    else h += '<div class="gauge"><div>' + gauge(de.fuellstand_prozent, false, "Füllstand Deutschland") + '</div><div><div class="big">' + nf.format(de.fuellstand_prozent) + ' <span class="unit">%</span></div>' +
      '<div class="num">Deutschland gesamt</div><p class="meta" style="margin-top:4px">' + nf.format(de.gas_twh) + " von " + nf.format(de.kapazitaet_twh) + " TWh</p></div></div>" +
      '<p class="meta">Einspeicherung ' + nf0.format(de.einspeicherung_gwh) + " GWh/Tag · Ausspeicherung " + nf0.format(de.ausspeicherung_gwh) + " GWh/Tag · Gastag " + esc(de.gastag) + "</p>" +
      spark(de.verlauf.map(function (p) { return [0, p[1]]; }), { label: "Füllstand Deutschland, 30 Tage", minSpan: 5 }) + '<p class="meta">Füllstand der letzten 30 Tage</p>';
    set("cSpeicherDE", h + meta(d, esc(d.quelle || "")));
  }
  function renderSpeicherBB(d) {
    var nd = noData(d, "Gasspeicher"); if (nd) return set("cSpeicherBB", nd);
    var h = errNote(d);
    if (!d.brandenburg || !d.brandenburg.length) h += hint("Keine Brandenburger Speicherdaten vorhanden.");
    else h += d.brandenburg.map(function (s) {
      return '<div class="gauge" style="margin:6px 0"><div>' + gauge(s.fuellstand_prozent, false, s.name) + '</div><div><div class="big">' + nf.format(s.fuellstand_prozent) + ' <span class="unit">%</span></div>' +
        '<div class="num"><strong>' + esc(s.name) + '</strong></div><p class="meta" style="margin-top:2px">' + nf2.format(s.gas_twh) + " von " + nf2.format(s.kapazitaet_twh) + " TWh · Gastag " + esc(s.gastag) + "</p></div></div>" +
        spark((s.verlauf || []).map(function (p) { return [0, p[1]]; }), { label: "Füllstand " + s.name, minSpan: 5 });
    }).join("") + '<p class="meta">In Brandenburg liegt laut GIE-Liste nur dieser Speicher. Weitere Anlagen sind dort nicht gemeldet.</p>';
    set("cSpeicherBB", h + meta(d, esc(d.quelle || "")));
  }

  function reichBlock(r) {
    if (!r) return hint("Keine Berechnung möglich.");
    var fuell = r.netto_7t_gwh <= 0, tage = r.tage_wetter != null ? r.tage_wetter : r.tage_aktuell;
    var h = '<div class="big">' + (fuell ? "füllt sich" : tage != null ? "ca. " + nf0.format(tage) + ' <span class="unit">Tage</span>' : "–") + "</div>" +
      '<p class="meta" style="margin-top:6px">' + (fuell ? "Im Mittel der letzten 7 Tage wird mehr eingespeichert als entnommen (netto +" + nf0.format(-r.netto_7t_gwh) + " GWh/Tag)." :
      "bis der Speicher leer wäre. Bei gleichbleibender Entnahme: " + (r.tage_aktuell != null ? "ca. " + nf0.format(r.tage_aktuell) + " Tage" : "–") + ", mit Wettervorhersage: " + (r.tage_wetter != null ? "ca. " + nf0.format(r.tage_wetter) + " Tage" : "nicht berechenbar") + ".") + "</p>" +
      '<p class="meta">Mittel der letzten 7 Tage: Ausspeicherung ' + nf0.format(r.ausspeicherung_7t_gwh) + " GWh/Tag, Einspeicherung " + nf0.format(r.einspeicherung_7t_gwh) + " GWh/Tag.</p>";
    if (r.ziel) {
      var z = r.ziel, dd = z.marke_ca_datum ? new Date(z.marke_ca_datum + "T12:00:00").toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" }) : null;
      h += '<p style="margin:10px 0 0"><strong>Füllstandsvorgabe ' + z.prozent + ' % zum 1. Februar 2027</strong> (noch ' + z.tage_bis_stichtag + " Tage): " +
        (z.tage_bis_marke === 0 ? "bereits unterschritten." : z.tage_bis_marke != null ? "Bei gleichbleibender Entnahme wäre die " + z.prozent + "-%-Marke etwa am " + dd + " erreicht" + (z.tage_bis_marke < z.tage_bis_stichtag ? ", also vor dem Stichtag." : ", also nach dem Stichtag.") : "Speicher füllen sich derzeit.") + "</p>" +
        '<p class="meta">Im Winter ist die Entnahme meist höher als im Mittel der letzten 7 Tage, die Marke würde dann früher erreicht.</p>';
    }
    if (r.projektion && r.projektion.length > 1) h += spark(r.projektion.map(function (p) { return [0, p[1]]; }), { label: "Voraussichtlicher Füllstand, 14 Tage", min: 0, max: 100 }) +
      '<p class="meta">Voraussichtlicher Füllstand in %, nächste ' + r.projektion.length + " Tage (bis " + esc(r.projektion[r.projektion.length - 1][0]) + "): " + nf.format(r.projektion[r.projektion.length - 1][1]) + " %</p>";
    return h;
  }
  function winterBlock(v) {
    function dat(x) { return new Date(x + "T12:00:00").toLocaleDateString("de-DE", { day: "numeric", month: "long" }); }
    var n = v.szenarien, nm = n.normal.konstant, kt = n.kalt.konstant, kf = n.kalt.faellt, ml = n.mild.konstant;
    function satz(x, name) {
      if (x.erreicht.leer) return "leer ca. " + dat(x.erreicht.leer);
      var s = "reichen bis Winterende (31. März), Rest ca. " + nf0.format(x.fuellstand_ende) + " %";
      if (x.erreicht["10"]) s += ", unter 10 % ab " + dat(x.erreicht["10"]);
      return s;
    }
    var kopf = nm.erreicht.leer ? "bis ca. " + dat(nm.erreicht.leer) : "bis Winterende";
    var h = '<div class="big">' + kopf + '</div><p style="margin:6px 0 0">im <strong>normalen Winter</strong>' + (nm.erreicht.leer ? "" : ", dann sind sie fast leer (ca. " + nf0.format(nm.fuellstand_ende) + " % am 31. März)") + ".</p>" +
      '<table style="margin-top:10px"><tr><th>Winter</th><th>Speicher</th></tr>' +
      '<tr><td><span style="color:var(--green)">■</span> mild</td><td>' + satz(ml) + "</td></tr>" +
      '<tr><td><span style="color:var(--blue)">■</span> normal</td><td>' + satz(nm) + "</td></tr>" +
      '<tr><td><span style="color:var(--red)">■</span> kalt</td><td>' + satz(kt) + (kf.engpass_tage > 0 ? ". Bei sinkender Ausspeicherleistung ab ca. " + dat(kf.erreicht["30"] || kt.erreicht["30"]) + " unter 30 %, an " + kf.engpass_tage + " Tagen reicht die Leistung nicht für den Bedarf" : "") + "</td></tr></table>" +
      '<p class="meta">Ausgangslage ' + nf.format(v.ausgangslage.fuellstand_prozent) + " % (" + nf.format(v.ausgangslage.gas_twh) + " TWh). Die Entnahme steigt mit der Kälte. Deshalb ist die Dauer deutlich kürzer als bei einer einfachen Rechnung mit der heutigen Entnahme. Typische Abweichung des Modells etwa " + nf0.format(v.rueckrechnung_mittlerer_fehler_pp || 8) + " Prozentpunkte. Verlauf, Szenarien und Annahmen: Kachel „Vorausschau bis Winterende“.</p>";
    return h;
  }
  function renderReich(d, v) {
    var nd = noData(d, "Reichweite");
    if (nd) { set("cReichDE", nd); set("cReichBB", nd); return; }
    if (!d.deutschland && !d.brandenburg) { set("cReichDE", hint(d.hinweis || "Keine Daten.")); set("cReichBB", hint(d.hinweis || "Keine Daten.")); return; }
    var ann = '<p class="hint">' + esc(d.annahmen || "") + " Das ist eine Schätzung, keine Prognose der Versorgungssicherheit.</p>";
    set("cReichDE", errNote(d) + (v && v.szenarien ? winterBlock(v) : reichBlock(d.deutschland) + ann) + meta(d, ""));
    set("cReichBB", errNote(d) + ((d.brandenburg || []).length ? d.brandenburg.map(function (r) { return "<h3>" + esc(r.name) + "</h3>" + reichBlock(r); }).join("") : hint("Keine Brandenburger Speicherdaten.")) + ann + meta(d, ""));
  }

  function renderEuropa(d) {
    var nd = noData(d, "Europa"); if (nd) return set("cEuropa", nd);
    if (!d.laender) return set("cEuropa", errNote(d) + hint(d.hinweis || "Keine Daten."));
    var l = d.laender.slice().sort(function (a, b) { return b.fuellstand_prozent - a.fuellstand_prozent; });
    var h = errNote(d) + l.map(function (c) {
      var de = c.code === "DE", col = c.fuellstand_prozent < 30 ? "var(--red)" : c.fuellstand_prozent < 60 ? "var(--orange)" : "var(--green)";
      return '<div class="row"><span style="' + (de ? "font-weight:700" : "") + '">' + esc(c.name) + '</span><div class="bar"><span style="width:' + Math.min(100, c.fuellstand_prozent) + "%;background:" + col + '"></span></div><span class="val" style="' + (de ? "font-weight:700;color:var(--label)" : "") + '">' + nf.format(c.fuellstand_prozent) + " %</span></div>";
    }).join("");
    set("cEuropa", h + '<p class="meta">Füllstand in % des nutzbaren Speichervolumens, letzter gemeldeter Gastag' + (l[0] ? " " + esc(l[0].gastag) : "") + (d.ohne_daten && d.ohne_daten.length ? ". Ohne Daten: " + esc(d.ohne_daten.join(", ")) : "") + "</p>" + meta(d, esc(d.quelle || "")));
  }
  function renderAnlagen(d) {
    var nd = noData(d, "Anlagen"); if (nd) return set("cAnlagen", nd);
    if (!d.anlagen) return set("cAnlagen", errNote(d) + hint(d.hinweis || "Keine Daten."));
    var rows = d.anlagen.slice(0, 15).map(function (a) {
      var col = a.fuellstand_prozent < 30 ? "var(--red)" : a.fuellstand_prozent < 60 ? "var(--orange)" : "var(--green)";
      return "<tr><td>" + esc(a.name) + '<div class="meta" style="margin:0">' + esc(a.firma) + '</div></td><td class="n">' + nf2.format(a.kapazitaet_twh) + '</td><td style="width:28%"><div class="bar" style="height:8px;background:var(--fill);border-radius:4px;overflow:hidden"><span style="display:block;height:100%;width:' + Math.min(100, a.fuellstand_prozent) + "%;background:" + col + '"></span></div></td><td class="n"><strong>' + nf.format(a.fuellstand_prozent) + " %</strong></td></tr>";
    }).join("");
    set("cAnlagen", errNote(d) + '<table><tr><th>Speicher</th><th class="n">Volumen TWh</th><th></th><th class="n">Füllstand</th></tr>' + rows + "</table>" +
      '<p class="meta">Die 15 größten von ' + d.anlagen.length + " Anlagen mit Daten, sortiert nach nutzbarem Speichervolumen.</p>" + meta(d, esc(d.quelle || "")));
  }

  function renderTtf(d, an) {
    var nd = noData(d, "Erdgaspreis"); if (nd) return set("cTtf", nd);
    if (d.preis == null) return set("cTtf", errNote(d) || hint("Kein Erdgaspreis verfügbar."));
    var up = d.aenderung_prozent >= 0, extra = "";
    if (an && !an.fehler && an.jahre) {
      var r = an.korrelation, txt = r == null ? "nicht berechenbar" : Math.abs(r) < 0.3 ? "kein klarer Zusammenhang" : (r < 0 ? "höhere Preise gingen mit weniger Einspeicherung einher" : "höhere Preise gingen mit mehr Einspeicherung einher");
      extra = '<h3 style="margin-top:12px">Preis und Einspeicherung</h3><p style="margin:0">Der Preis liegt bei ' + nf.format(an.ttf_aktuell) + " €/MWh, das ist höher als an " + an.perzentil_seit_2018 + " % der Tage seit 2018 (Median " + nf.format(an.ttf_median_seit_2018) + " €/MWh), in 30 Tagen " + (an.aenderung_30_tage_prozent >= 0 ? "+" : "") + nf.format(an.aenderung_30_tage_prozent) + " %.</p>" +
        '<table style="margin-top:6px"><tr><th>Sommer (Apr–Okt)</th><th class="n">Ø TTF €/MWh</th><th class="n">Ø Einspeicherung GWh/Tag</th></tr>' + an.jahre.map(function (y) { return "<tr><td>" + y.jahr + '</td><td class="n">' + nf0.format(y.ttf_mittel) + '</td><td class="n">' + nf0.format(y.einspeicherung_mittel_gwh) + "</td></tr>"; }).join("") + "</table>" +
        '<p class="meta">Zusammenhang über ' + an.anzahl_jahre + " Jahre: Korrelation " + (r == null ? "–" : nf2.format(r)) + " (" + txt + "). Bei so wenigen Jahren ist das nur ein Hinweis. Politische Vorgaben, Terminal-Kapazitäten und die Lage nach 2022 spielen mit hinein.</p>";
    }
    set("cTtf", errNote(d) + '<div class="big">' + nf2.format(d.preis) + ' <span class="unit">€/MWh</span></div><p style="margin:4px 0;color:var(--' + (up ? "bad" : "ok") + ')">' + (up ? "▲ " : "▼ ") + nf2.format(Math.abs(d.aenderung_prozent)) + " % zum Vortag</p>" +
      spark((d.verlauf || []).map(function (p) { return [0, p[1]]; }), { label: "TTF, 60 Tage" }) + '<p class="meta">Niederländischer Großhandelspreis (TTF), Leitpreis für Erdgas in Europa. Kursdatum ' + esc(d.datum) + ", verzögert</p>" + extra + meta(d, esc(d.quelle || "")));
  }
  function renderLngTanks(d) {
    var nd = noData(d, "LNG-Tanks"); if (nd) return set("cLngTanks", nd);
    if (!d.terminals && !d.deutschland) return set("cLngTanks", errNote(d) + hint(d.hinweis || "Keine Daten."));
    var de = d.deutschland, h = errNote(d);
    if (de) h += '<div class="big">' + (de.inhalt_gwh != null ? nf0.format(de.inhalt_gwh) : "–") + ' <span class="unit">GWh in den Tanks</span></div><p class="meta" style="margin-top:4px">Ausspeisung ins Gasnetz ' + (de.ausspeisung_gwh != null ? nf0.format(de.ausspeisung_gwh) : "–") + " GWh/Tag (alle Terminals zusammen)</p>";
    if (de && de.verlauf) { var vv = de.verlauf.filter(function (p) { return p[1] != null; }); if (vv.length > 1) h += spark(vv.map(function (p) { return [0, p[1]]; }), { label: "Tankfüllstand LNG, 10 Tage", minSpan: 5 }); }
    var rows = (d.terminals || []).map(function (t) {
      return "<tr><td>" + esc(t.name) + '<div class="meta" style="margin:0">' + esc(t.firma || "") + '</div></td><td class="n">' + (t.inhalt_gwh == null ? "–" : nf0.format(t.inhalt_gwh)) + '</td><td class="n">' + (t.ausspeisung_gwh == null ? "–" : nf0.format(t.ausspeisung_gwh)) + "</td></tr>";
    }).join("");
    set("cLngTanks", h + (rows ? '<table><tr><th>Terminal (schwimmende LNG-Terminals)</th><th class="n">Tankinhalt GWh</th><th class="n">Ausspeisung GWh/Tag</th></tr>' + rows + "</table>" : "") +
      '<p class="meta">Tankinhalt und Ausspeisung der LNG-Terminals, letzter gemeldeter Gastag' + (de && de.gastag ? " " + esc(de.gastag) : "") + ". Einen Prozent-Füllstand melden die Terminals nicht.</p>" + meta(d, esc(d.quelle || "")));
  }

  function renderVorausschau(d, pv) {
    var nd = noData(d, "Vorausschau"); if (nd) return set("cVorausschau", nd);
    var pvx = "";
    if (pv && pv.eintraege) {
      var es = pv.eintraege.slice(-8).reverse();
      pvx = '<h3 style="margin-top:14px">Wie sich die Prognose verändert hat</h3>' + (es.length < 2 ? '<p class="meta" style="margin-top:0">Die Prognose wird ab jetzt täglich festgehalten, hier erscheint dann der Verlauf.</p>' : '<table><tr><th>Stand</th><th class="n">Füllstand</th><th class="n">1.2. normal</th><th class="n">1.2. kalt</th><th class="n">31.3. normal</th></tr>' + es.map(function (e) { return "<tr><td>" + new Date(e.tag + "T12:00:00").toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" }) + '</td><td class="n">' + nf.format(e.fuellstand) + ' %</td><td class="n">' + nf0.format(e.normal_feb) + ' %</td><td class="n">' + nf0.format(e.kalt_feb) + ' %</td><td class="n">' + nf0.format(e.normal_ende) + " %</td></tr>"; }).join("") + "</table>") + '<p class="meta">Die Berechnung nutzt täglich den neuesten Speicherstand und die neueste Wettervorhersage und passt sich dadurch an.</p>';
    }
    if (!d.szenarien) return set("cVorausschau", errNote(d) + hint(d.hinweis || "Keine Daten."));
    var W = 340, H = 170, L = 28, T0 = 8, B = 22, pw = W - L - 8, ph = H - T0 - B;
    var t0 = new Date("2026-11-10T12:00:00").getTime(), t1 = new Date(d.ziel.datum.slice(0, 4) === "2027" ? "2027-03-31T12:00:00" : "2027-03-31T12:00:00").getTime();
    function X(s) { return L + (new Date(s + "T12:00:00").getTime() - t0) / (t1 - t0) * pw; }
    function Y(v) { return T0 + (100 - v) / 100 * ph; }
    var g = "";
    [0, 25, 50, 75, 100].forEach(function (v) { g += '<line x1="' + L + '" x2="' + (W - 8) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" stroke="var(--sep)" stroke-width="0.6"/><text x="' + (L - 4) + '" y="' + (Y(v) + 3) + '" text-anchor="end" font-size="8" fill="var(--muted)">' + v + "</text>"; });
    [["2026-12-01", "Dez"], ["2027-01-01", "Jan"], ["2027-02-01", "Feb"], ["2027-03-01", "Mär"]].forEach(function (m) { g += '<line x1="' + X(m[0]) + '" x2="' + X(m[0]) + '" y1="' + T0 + '" y2="' + (T0 + ph) + '" stroke="var(--sep)" stroke-width="0.5"/><text x="' + (X(m[0]) + 2) + '" y="' + (H - 8) + '" font-size="8" fill="var(--muted)">' + m[1] + "</text>"; });
    var zl = d.ziel;
    g += '<line x1="' + L + '" x2="' + (W - 8) + '" y1="' + Y(zl.prozent) + '" y2="' + Y(zl.prozent) + '" stroke="var(--red)" stroke-width="0.8" stroke-dasharray="2 3"/><text x="' + (W - 10) + '" y="' + (Y(zl.prozent) - 3) + '" text-anchor="end" font-size="8" fill="var(--red)">Vorgabe ' + zl.prozent + " % am 1.2.</text>";
    function line(v, col, w, dash) { return '<path d="' + v.map(function (p, i) { return (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1); }).join(" ") + '" fill="none" stroke="' + col + '" stroke-width="' + w + '" stroke-linejoin="round"' + (dash ? ' stroke-dasharray="3 2"' : "") + "/>"; }
    if (d.vorjahr_verlauf && d.vorjahr_verlauf.length) g += line(d.vorjahr_verlauf, "var(--muted)", 1, false);
    var farben = { mild: "var(--green)", normal: "var(--blue)", kalt: "var(--red)" }, namen = { mild: "Milder Winter", normal: "Normaler Winter", kalt: "Kalter Winter" };
    ["mild", "normal", "kalt"].forEach(function (n) { g += line(d.szenarien[n].konstant.verlauf, farben[n], 1.8, false) + line(d.szenarien[n].faellt.verlauf, farben[n], 1.2, true); });
    function dat(s) { return s ? new Date(s + "T12:00:00").toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" }) : "nicht erreicht"; }
    var rows = ["mild", "normal", "kalt"].map(function (n) {
      var s = d.szenarien[n], a = s.konstant, b = s.faellt;
      return '<tr><td><span style="color:' + farben[n] + '">■</span> ' + namen[n] + '<div class="meta" style="margin:0">' + (n === "normal" ? "Klima wie im Mittel seit 2018" : (s.abweichung_c > 0 ? "+" : "") + nf.format(s.abweichung_c) + " °C zum Mittel") + '</div></td><td class="n"><strong>' + nf0.format(a.fuellstand_ziel_tag) + " %</strong><div class=\"meta\" style=\"margin:0\">mit Leistungsabfall " + nf0.format(b.fuellstand_ziel_tag) + ' %</div></td><td class="n">' + nf0.format(a.fuellstand_ende) + " %</td><td class=\"n\">" + dat(a.erreicht[30]) + "</td><td class=\"n\">" + (b.engpass_tage > 0 ? b.engpass_tage + " Tage" : "–") + "</td></tr>";
    }).join("");
    var al = d.ausgangslage, m = d.modell, rr = (d.rueckrechnung || []).map(function (o) { return "<tr><td>" + esc(o.winter) + '</td><td class="n">' + nf0.format(o.ist_1_feb) + ' %</td><td class="n">' + nf0.format(o.modell_1_feb) + ' %</td><td class="n">' + (o.fehler_1_feb > 0 ? "+" : "") + nf0.format(o.fehler_1_feb) + "</td></tr>"; }).join("");
    var oi = d.ohne_importe;
    set("cVorausschau", errNote(d) +
      "<p style=\"margin:0 0 6px\">Ausgangslage " + esc(al.gastag) + ": <strong>" + nf.format(al.fuellstand_prozent) + " %</strong> (" + nf.format(al.gas_twh) + " TWh). Die Berechnung nutzt die Temperaturvorhersage bis " + esc(al.wetter_bis || "–") + ", danach das mittlere Klima seit 2018.</p>" +
      '<svg viewBox="0 0 ' + W + " " + H + '" style="width:100%;height:auto" role="img" aria-label="Voraussichtlicher Füllstand Deutschland bis 31. März">' + g + "</svg>" +
      '<p class="meta">Durchgezogen: Ausspeicherleistung bleibt auf dem höchsten beobachteten Niveau. Gestrichelt: Leistung sinkt bei niedrigem Füllstand (Annahme). Grau: tatsächlicher Verlauf im Vorjahr.</p>' +
      '<table><tr><th>Szenario</th><th class="n">Füllstand 1. Feb.</th><th class="n">31. März</th><th class="n">unter 30 % ab</th><th class="n">Engpass</th></tr>' + rows + "</table>" +
      (d.rueckrechnung_mittlerer_fehler_pp != null ? '<p style="margin:8px 0 0"><strong>Einordnung:</strong> Im normalen Winter liegt der Füllstand am 1. Februar nach dieser Rechnung bei ' + nf0.format(d.szenarien.normal.konstant.fuellstand_ziel_tag) + ' %. Berücksichtigt man die typische Abweichung der Rückrechnung von etwa ' + nf0.format(d.rueckrechnung_mittlerer_fehler_pp) + ' Prozentpunkten, ist ein Wert zwischen etwa ' + nf0.format(Math.max(0, d.szenarien.normal.konstant.fuellstand_ziel_tag - d.rueckrechnung_mittlerer_fehler_pp)) + ' und ' + nf0.format(d.szenarien.normal.konstant.fuellstand_ziel_tag + d.rueckrechnung_mittlerer_fehler_pp) + ' % plausibel, die Vorgabe liegt bei ' + d.ziel.prozent + ' %.</p>' : "") + '<p class="meta">Engpass: Tage, an denen der kältebedingte Entnahmebedarf die angenommene Ausspeicherleistung übersteigt. Dieses Gas müsste aus Importen oder anderen Quellen kommen.</p>' +
      '<h3 style="margin-top:14px">Ohne Importe</h3><p style="margin:0">Müssten die Speicher den <strong>gesamten</strong> Verbrauch decken (Durchschnitt ' + nf0.format(oi.jahresverbrauch_twh) + " TWh im Jahr, " + nf2.format(oi.verbrauch_tag_twh) + " TWh am Tag), reichte der Vorrat rechnerisch <strong>" + oi.tage + " Tage</strong>. Das ist eine andere Frage als oben bei der Reichweite, dort geht es nur um den Anteil, den die Speicher heute tatsächlich liefern. Im Winter liegt der Verbrauch über dem Jahresdurchschnitt, die echte Reichweite wäre dann kürzer. Quelle der Jahreszahl: " + esc(oi.quelle || "") + ".</p>" +
      '<h3 style="margin-top:14px">Wie gut ist das Modell?</h3><p class="meta" style="margin-top:0">Entnahme ≈ ' + nf0.format(m.a_gwh) + " + " + nf0.format(m.b_gwh_je_grad) + " GWh je Grad unter " + m.heizgrenze_c + " °C (aus " + m.tage + " Wintertagen seit 2018, Bestimmtheit " + nf2.format(m.r2) + "). Höchste beobachtete Entnahme " + nf0.format(m.leistung_hoch_gwh) + " GWh/Tag, bei 10 bis 20 % Füllstand nur " + (m.leistung_tief_gwh != null ? nf0.format(m.leistung_tief_gwh) : "–") + " GWh/Tag.</p>" +
      '<table><tr><th>Rückrechnung ab 12.11.</th><th class="n">tatsächlich 1.2.</th><th class="n">Modell</th><th class="n">Abweichung</th></tr>' + rr + "</table>" +
      '<p class="meta">Mittlere Abweichung ' + (d.rueckrechnung_mittlerer_fehler_pp != null ? nf.format(d.rueckrechnung_mittlerer_fehler_pp) : "–") + " Prozentpunkte mit den echten Temperaturen der jeweiligen Winter. Die Rückrechnung nutzt dieselben Daten wie die Schätzung und ist deshalb zu optimistisch, und sie prüft nicht die Unsicherheit der Wettervorhersage.</p>" +
      (pvx ? pvx : "") + '<p class="hint">Das ist ein Rechenbeispiel, keine Prognose der Versorgungssicherheit. Annahmen: Einspeicherung bleibt wie im Mittel der letzten 7 Tage; Importe und Verbrauch reagieren nicht auf niedrige Füllstände. Wie stark die Ausspeicherleistung bei niedrigem Füllstand sinkt, lässt sich aus den Daten nicht sicher bestimmen: Die gemeldete technische Leistung bleibt über alle Füllstände gleich, beobachtet wurden unter 20 % Füllstand nur wenige Tage. Die gestrichelte Variante ist deshalb eine Annahme. Die Szenarien Mild und Kalt entsprechen dem wärmsten und kältesten Winterdurchschnitt seit 2018. Einzelne Kältewellen können stärker wirken als ein kalter Durchschnitt.</p>' + meta(d, esc(d.quelle || "")));
  }

  function renderEinsp(d) {
    var nd = noData(d, "Einspeicherung"); if (nd) return set("cEinsp", nd);
    var e = d.einspeicherung;
    if (!e) return set("cEinsp", errNote(d) + hint("Die Berechnung wird gerade aktualisiert."));
    var hi = e.historie, n = e.szenarien, namen = { mild: "Milder Winter", normal: "Normaler Winter", kalt: "Kalter Winter" }, farben = { mild: "var(--green)", normal: "var(--blue)", kalt: "var(--red)" };
    function zelle(p) {
      if (!p || p.noetig_gwh == null) return "nicht erreichbar";
      if (p.noetig_gwh === 0) return "nicht nötig";
      return "<strong>" + nf0.format(p.noetig_gwh) + "</strong> GWh/Tag<div class=\"meta\" style=\"margin:0\">+" + nf0.format(p.zusatz_gwh) + (p.faktor ? " (" + nf.format(p.faktor) + "-fach)" : "") + "</div>";
    }
    var rows = ["mild", "normal", "kalt"].map(function (k) {
      return '<tr><td><span style="color:' + farben[k] + '">■</span> ' + namen[k] + '</td><td class="n">' + zelle(n[k].nicht_leer) + '</td><td class="n">' + zelle(n[k].vorgabe_1_feb) + "</td></tr>";
    }).join("");
    function urteil(p) {
      if (!p || p.noetig_gwh == null) return "wäre mit der angenommenen Rechnung nicht erreichbar";
      if (p.noetig_gwh === 0) return "ist ohne zusätzliche Einspeicherung erreicht";
      if (hi.hoechster_durchschnitt_winter_gwh != null && p.noetig_gwh <= hi.hoechster_durchschnitt_winter_gwh) return "läge im Rahmen dessen, was in einem Winter seit 2018 im Durchschnitt erreicht wurde";
      if (p.noetig_gwh <= hi.hoechster_durchschnitt_beliebig_gwh) return "läge nur auf dem Niveau der besten Sommer-Einspeicherung, im Winter wurde das im Durchschnitt noch nie erreicht";
      return "läge über allem, was seit 2018 im Durchschnitt über einen so langen Zeitraum erreicht wurde";
    }
    var nn = n.normal;
    function dat(s) { return new Date(s + "T12:00:00").toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" }); }
    var wr = (hi.winter || []).map(function (w) { return "<tr><td>" + esc(w.winter) + '</td><td class="n">' + (w.temp_c == null ? "–" : nf.format(w.temp_c)) + ' °C</td><td class="n">' + nf0.format(w.entnahme_gwh) + '</td><td class="n">' + nf0.format(w.einspeicherung_gwh) + '</td><td class="n">' + nf0.format(w.start) + " → " + nf0.format(w.ende) + " %</td></tr>"; }).join("");
    set("cEinsp", errNote(d) +
      '<p style="margin:0">Im Mittel der letzten 7 Tage werden <strong>' + nf0.format(e.jetzt_gwh) + " GWh/Tag</strong> eingespeichert. Wie viel müsste es bis 31. März im Durchschnitt sein, damit die Speicher nicht leerlaufen?</p>" +
      '<table style="margin-top:8px"><tr><th>Szenario</th><th class="n">am 31. März mindestens ' + nf0.format(e.mindest_ende_prozent) + ' % voll</th><th class="n">' + d.ziel.prozent + " % am 1. Februar (Vorgabe)</th></tr>" + rows + "</table>" +
      '<p style="margin:10px 0 0"><strong>Ist das realistisch?</strong> Im normalen Winter ' + urteil(nn.nicht_leer) + " (Ziel: nicht unter " + nf0.format(e.mindest_ende_prozent) + " %). Für die Vorgabe " + d.ziel.prozent + " % am 1. Februar " + urteil(nn.vorgabe_1_feb) + ".</p>" +
      '<ul class="plain"><li>Höchste Einspeicherung an einem Wintertag seit 2018: ' + nf0.format(hi.tagesmax_winter_gwh) + " GWh (95 % der Wintertage lagen unter " + nf0.format(hi.tages_p95_winter_gwh) + " GWh).</li>" +
      "<li>Höchster Winterdurchschnitt (12.11. bis 31.3.): " + nf0.format(hi.hoechster_durchschnitt_winter_gwh) + " GWh/Tag.</li>" +
      "<li>Höchster Durchschnitt über " + hi.laenge_tage + " Tage zu irgendeiner Jahreszeit: " + nf0.format(hi.hoechster_durchschnitt_beliebig_gwh) + " GWh/Tag (" + dat(hi.hoechster_durchschnitt_von) + " bis " + dat(hi.hoechster_durchschnitt_bis) + ").</li>" +
      (e.einspeicherleistung_gemeldet_gwh ? "<li>Von den Betreibern gemeldete technische Einspeicherleistung: " + nf0.format(e.einspeicherleistung_gemeldet_gwh) + " GWh/Tag. Das ist die Obergrenze der Anlagen, nicht der Gasmenge, die verfügbar ist.</li>" : "") +
      (e.importe_gwh ? "<li>Zum Vergleich: Netto-Importe über Pipelines und LNG zusammen derzeit etwa " + nf0.format(e.importe_gwh) + " GWh/Tag. Eine Mehr-Einspeicherung von " + nf0.format(nn.nicht_leer.zusatz_gwh || 0) + " GWh/Tag entspräche " + nf0.format(e.importe_gwh ? (nn.nicht_leer.zusatz_gwh || 0) / e.importe_gwh * 100 : 0) + " % davon.</li>" : "") + "</ul>" +
      '<h3 style="margin-top:14px">Die letzten Winter im Vergleich (12.11. bis 31.3.)</h3><table><tr><th>Winter</th><th class="n">Ø Temperatur</th><th class="n">Ø Entnahme GWh/Tag</th><th class="n">Ø Einspeicherung GWh/Tag</th><th class="n">Füllstand Start → Ende</th></tr>' + wr + "</table>" +
      '<p class="hint">Mehr Einspeicherung heißt mehr Gas im Land: aus zusätzlichen Importen und LNG oder aus geringerem Verbrauch. Jede eingesparte Gasmenge wirkt wie eine zusätzlich eingespeicherte. Die Rechnung nimmt eine gleichbleibende Einspeicherung an und gilt wie die Vorausschau mit einer Unsicherheit von etwa ' + nf0.format(d.rueckrechnung_mittlerer_fehler_pp || 8) + " Prozentpunkten. Ob die Mengen am Markt beschaffbar wären, hängt von Preisen, Terminal-Kapazitäten und Lieferverträgen ab und ist hier nicht berechnet.</p>" + meta(d, esc(d.quelle || "")));
  }

  function renderUmfeldVor(v, u) {
    var nd = noData(v, "Vorausschau Umfeld"); if (nd) return set("cUmfeldVor", nd);
    if (!v.anlagen) return set("cUmfeldVor", errNote(v) + hint(v.hinweis || "Keine Daten."));
    function dat(s) { return s ? new Date(s + "T12:00:00").toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" }) : "nicht bis 31.3."; }
    var farben = { mild: "var(--green)", normal: "var(--blue)", kalt: "var(--red)" }, namen = { mild: "Milder Winter", normal: "Normaler Winter", kalt: "Kalter Winter" };
    var W = 340, H = 150, L = 28, T0 = 8, B = 20, pw = W - L - 8, ph = H - T0 - B, t0 = new Date("2026-11-10T12:00:00").getTime(), t1 = new Date("2027-03-31T12:00:00").getTime();
    function X(s) { return L + (new Date(s + "T12:00:00").getTime() - t0) / (t1 - t0) * pw; } function Y(x) { return T0 + (100 - x) / 100 * ph; }
    var g = "";
    [0, 25, 50, 75, 100].forEach(function (x) { g += '<line x1="' + L + '" x2="' + (W - 8) + '" y1="' + Y(x) + '" y2="' + Y(x) + '" stroke="var(--sep)" stroke-width="0.6"/><text x="' + (L - 4) + '" y="' + (Y(x) + 3) + '" text-anchor="end" font-size="8" fill="var(--muted)">' + x + "</text>"; });
    [["2026-12-01", "Dez"], ["2027-01-01", "Jan"], ["2027-02-01", "Feb"], ["2027-03-01", "Mär"]].forEach(function (m) { g += '<text x="' + (X(m[0]) + 2) + '" y="' + (H - 6) + '" font-size="8" fill="var(--muted)">' + m[1] + "</text>"; });
    function line(a, col, w, dash) { return '<path d="' + a.map(function (p, i) { return (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1); }).join(" ") + '" fill="none" stroke="' + col + '" stroke-width="' + w + '" stroke-linejoin="round"' + (dash ? ' stroke-dasharray="3 2"' : "") + "/>"; }
    ["mild", "normal", "kalt"].forEach(function (k) { g += line(v.gesamt[k].konstant.verlauf, farben[k], 1.8, false) + line(v.gesamt[k].faellt.verlauf, farben[k], 1.2, true); });
    var rows = ["mild", "normal", "kalt"].map(function (k) {
      var a = v.gesamt[k].konstant, b = v.gesamt[k].faellt;
      return '<tr><td><span style="color:' + farben[k] + '">■</span> ' + namen[k] + '</td><td class="n">' + nf0.format(a.fuellstand_ziel_tag) + ' %<div class="meta" style="margin:0">mit Leistungsabfall ' + nf0.format(b.fuellstand_ziel_tag) + ' %</div></td><td class="n">' + nf0.format(a.fuellstand_ende) + ' %</td><td class="n">' + dat(a.erreicht["30"]) + '</td><td class="n">' + dat(a.erreicht["10"]) + "</td></tr>";
    }).join("");
    var fr = v.anlagen.map(function (a) {
      var n = a.szenarien.normal, kk = a.szenarien.kalt.faellt;
      return "<tr><td>" + esc(a.name) + '<div class="meta" style="margin:0">' + esc(a.region) + (a.hinweise && a.hinweise.length ? " · " + esc(a.hinweise.join("; ")) : "") + '</div></td><td class="n">' + nf0.format(a.fuellstand_prozent) + ' %</td><td class="n">' + nf0.format(a.hoechste_entnahme_gwh) + " / " + (a.ausspeicherleistung_gemeldet_gwh ? nf0.format(a.ausspeicherleistung_gemeldet_gwh) : "–") + '</td><td class="n">' + dat(n.konstant.erreicht["30"]) + '</td><td class="n">' + dat(n.konstant.erreicht["10"]) + '</td><td class="n">' + (kk.erster_engpass ? dat(kk.erster_engpass) : "kein Engpass") + "</td></tr>";
    }).join("");
    var gp = ((u && u.grenzpunkte) || []).map(function (p) {
      return "<tr><td>" + esc(p.name) + '</td><td class="n">' + p.tage.map(function (t) { return nf0.format(t[1]) + "/" + nf0.format(t[2]); }).join(" · ") + "</td></tr>";
    }).join("");
    set("cUmfeldVor", errNote(v) +
      '<p style="margin:0 0 6px">Die fünf Speicher im Umfeld Brandenburgs zusammen: heute <strong>' + nf.format(v.gesamt_gas_twh / v.gesamt_kapazitaet_twh * 100) + " %</strong> (" + nf.format(v.gesamt_gas_twh) + " von " + nf.format(v.gesamt_kapazitaet_twh) + " TWh). Jeder Speicher wird mit seiner eigenen Entnahme seit 2018 gerechnet.</p>" +
      '<svg viewBox="0 0 ' + W + " " + H + '" style="width:100%;height:auto" role="img" aria-label="Voraussichtlicher Füllstand im Umfeld Brandenburgs bis 31. März">' + g + "</svg>" +
      '<p class="meta">Durchgezogen: Leistung bleibt auf dem höchsten beobachteten Niveau. Gestrichelt: Leistung sinkt bei niedrigem Füllstand (Annahme).</p>' +
      '<table><tr><th>Szenario</th><th class="n">1. Februar</th><th class="n">31. März</th><th class="n">unter 30 % ab</th><th class="n">unter 10 % ab</th></tr>' + rows + "</table>" +
      '<h3 style="margin-top:14px">Die einzelnen Speicher im normalen Winter</h3><table><tr><th>Speicher</th><th class="n">heute</th><th class="n">Höchstentnahme / gemeldete Leistung (GWh/Tag)</th><th class="n">unter 30 % ab</th><th class="n">unter 10 % ab</th><th class="n">Engpass ab (kalt, Leistungsabfall)</th></tr>' + fr + "</table>" +
      '<p class="meta">„Engpass“ bedeutet: Der kältebedingte Entnahmebedarf des Speichers liegt über seiner angenommenen Ausspeicherleistung bei diesem Füllstand.</p>' +
      (gp ? '<h3 style="margin-top:14px">Gaszufluss aus Polen (Grenzpunkte in Brandenburg), letzte Tage</h3><table><tr><th>Punkt</th><th class="n">Einspeisung/Ausfuhr GWh/Tag</th></tr>' + gp + "</table>" : "") +
      '<p class="hint">Das ist die Sicht der Speicher. Der Gasbedarf und die Netzlage in Brandenburg selbst habe ich nicht als offene Daten gefunden, die Versorgung läuft über das Verbundnetz, auch aus Speichern in den Nachbarländern und über Pipelines. „Kritisch“ heißt hier nur: niedriger Füllstand oder Entnahmebedarf über der Höchstleistung, nicht dass die Versorgung vor Ort ausfällt. Die Unsicherheit ist größer als bei der Deutschland-Rechnung, weil einzelne Speicher stärker schwanken. Wo ein Speicher nie so niedrige Füllstände hatte, ist die Leistung bei niedrigem Füllstand angenommen (siehe Hinweis am Speicher).</p>' + meta(v, esc(v.quelle || "")));
  }

  function renderStoerungen(d) {
    var nd = noData(d, "Störungen"); if (nd) return set("cStoerungen", nd);
    if (!d.meldungen) return set("cStoerungen", errNote(d) + hint("Keine Daten."));
    function dat(s) { return s ? new Date(s + "T12:00:00").toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "2-digit" }) : "offen"; }
    var rows = d.meldungen.slice(0, 12).map(function (m) {
      return "<tr><td>" + esc(m.anlage || m.ereignis || "–") + '<div class="meta" style="margin:0">' + esc(m.betreiber || "") + (m.richtung ? " · " + esc(m.richtung) : "") + (m.ereignis ? " · " + esc(m.ereignis) : "") + '</div>' + (m.hinweis ? '<div class="meta" style="margin:0">' + esc(m.hinweis.slice(0, 110)) + (m.hinweis.length > 110 ? " …" : "") + "</div>" : "") + '</td><td>' + esc(m.art || "–") + '</td><td class="n">' + dat(m.von) + " – " + dat(m.bis) + '</td><td class="n">' + (m.nicht_verfuegbar_gwh == null ? "–" : nf0.format(m.nicht_verfuegbar_gwh)) + (m.technisch_gwh ? " von " + nf0.format(m.technisch_gwh) : "") + "</td></tr>";
    }).join("");
    set("cStoerungen", errNote(d) + '<div class="big">' + d.anzahl + ' <span class="unit">Meldungen (' + d.geplant + " geplant, " + d.ungeplant + ' ungeplant)</span></div><p class="meta" style="margin-top:4px">Einschränkungen der Transportkapazität im deutschen Gasnetz in den nächsten 180 Tagen, zusammen ' + nf0.format(d.summe_nicht_verfuegbar_gwh) + " GWh/Tag.</p>" +
      '<table><tr><th>Anlage</th><th>Art</th><th class="n">Zeitraum</th><th class="n">nicht verfügbar GWh/Tag</th></tr>' + rows + "</table>" +
      '<p class="hint">Das sind eingeschränkte Transportkapazitäten, keine ausgefallenen Gasmengen. Viele Meldungen sind langfristige Kapazitätsbeschränkungen oder laufen bis weit in die Zukunft. Ob sich eine Einschränkung auf die Gasflüsse auswirkt, zeigen die Meldungen nicht. Probleme im Schiffsverkehr zu LNG-Terminals und Wartungen im Ausland (z. B. Norwegen) sind hier nicht erfasst, dazu habe ich keine offene Datenquelle gefunden.</p>' + meta(d, esc(d.quelle || "")));
  }
  function renderVersorgung(v, u) {
    var nd = noData(v, "Versorgung"); if (nd) return set("cVersorgung", nd);
    if (!v.szenarien) return set("cVersorgung", errNote(v) + hint(v.hinweis || "Keine Daten."));
    function dat(s) { return s ? new Date(s + "T12:00:00").toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" }) : "–"; }
    var n = v.szenarien, nk = n.normal.konstant, nf_ = n.normal.faellt, kk = n.kalt.faellt;
    var ok = nk.fehl_twh === 0 && nf_.fehl_twh === 0;
    var kopf = ok ? (nk.fuellstand_ende < 10 ? "Im normalen Winter gerade noch" : "Im normalen Winter ja") : "Im normalen Winter nicht ganz";
    var namen = { mild: "Milder Winter", normal: "Normaler Winter", kalt: "Kalter Winter" }, farben = { mild: "var(--green)", normal: "var(--blue)", kalt: "var(--red)" };
    var rows = ["mild", "normal", "kalt"].map(function (k) {
      var a = n[k].konstant, b = n[k].faellt;
      function z(x) { return x.fehl_twh > 0 ? "<strong>" + nf.format(x.fehl_twh) + " TWh</strong><div class=\"meta\" style=\"margin:0\">ab " + dat(x.fehl_erster) + ", Spitze " + nf0.format(x.fehl_spitze_gwh) + " GWh/Tag</div>" : "keine"; }
      return '<tr><td><span style="color:' + farben[k] + '">■</span> ' + namen[k] + '</td><td class="n">' + z(a) + '</td><td class="n">' + z(b) + "</td></tr>";
    }).join("");
    var sens = (v.importausfall || []).map(function (e) {
      function z(x) { return x.fehl_twh > 0 ? nf.format(x.fehl_twh) + " TWh ab " + dat(x.fehl_erster) : "keine Fehlmenge"; }
      return "<tr><td>" + esc(e.fall) + '<div class="meta" style="margin:0">' + nf0.format(e.gwh_tag) + ' GWh/Tag weniger</div></td><td class="n">' + nf0.format(e.normal.fuellstand_ziel_tag) + ' %<div class="meta" style="margin:0">' + z(e.normal) + '</div></td><td class="n">' + nf0.format(e.kalt.fuellstand_ziel_tag) + ' %<div class="meta" style="margin:0">' + z(e.kalt) + "</div></td></tr>";
    }).join("");
    var reg = "";
    if (u && u.anlagen) {
      var l = u.anlagen.filter(function (a) { return a.szenarien.kalt.faellt.erster_engpass; }).map(function (a) { return esc(a.name) + " ab " + dat(a.szenarien.kalt.faellt.erster_engpass); });
      reg = '<li><strong>Brandenburger Umfeld:</strong> ' + (l.length ? "Im kalten Winter mit sinkender Leistung wird die Ausspeicherleistung bei " + l.join(", ") + " knapp. " : "Im kalten Winter kein Leistungsengpass bei den fünf Speichern. ") + "Im normalen Winter fällt der Füllstand dort " + (u.gesamt && u.gesamt.normal.konstant.erreicht["30"] ? "ab " + dat(u.gesamt.normal.konstant.erreicht["30"]) + " unter 30 %." : "nicht unter 30 %.") + "</li>";
    }
    var ziel = v.ziel;
    set("cVersorgung", errNote(v) + '<div class="big">' + kopf + "</div>" +
      '<p style="margin:6px 0 0">Reichen Speicher und die heutigen Importe, um den Bedarf zu decken? ' + (ok ? "Nach dieser Rechnung entsteht im normalen Winter keine Fehlmenge, das Gas wird aber knapp, wenn der Füllstand sinkt." : "Nach dieser Rechnung fehlen im normalen Winter " + nf.format(Math.max(nk.fehl_twh, nf_.fehl_twh)) + " TWh.") + " Unter Fehlmenge ist Gas gemeint, das die Speicher wegen Leistungsgrenze oder Leere nicht mehr liefern könnten und das aus zusätzlichen Importen oder Einsparungen kommen müsste.</p>" +
      '<table style="margin-top:10px"><tr><th>Szenario</th><th class="n">Fehlmenge (Leistung bleibt)</th><th class="n">Fehlmenge (Leistung sinkt, Annahme)</th></tr>' + rows + "</table>" +
      '<h3 style="margin-top:14px">Was, wenn Importe wegfallen?</h3><table><tr><th>Fall</th><th class="n">Normaler Winter: Füllstand 1. Feb.</th><th class="n">Kalter Winter: Füllstand 1. Feb.</th></tr>' + sens + "</table>" +
      '<p class="meta">Rechnung mit Leistungsabfall (Annahme). Der Ausfall gilt gleichmäßig bis 31. März. Zusätzlicher Bedarf wird aus den Speichern gedeckt, bis diese leer sind.</p>' +
      '<h3 style="margin-top:14px">Ab wann könnte es zu Einsparungen kommen?</h3><ul class="plain">' +
      "<li>Einen <strong>festen Füllstand</strong>, ab dem Einsparungen angeordnet werden, gibt es nicht. Entscheidend ist die Lage im Gesamtsystem.</li>" +
      "<li>Als Orientierung gilt die Füllstandsvorgabe der Bundesnetzagentur: <strong>" + ziel.prozent + " % am 1. Februar 2027</strong>. Fällt der Füllstand deutlich darunter, steigt das Risiko. Im normalen Winter rechnet diese Seite mit " + nf0.format(nk.fuellstand_ziel_tag) + " % (Spanne etwa ±" + nf0.format(v.rueckrechnung_mittlerer_fehler_pp || 8) + " Prozentpunkte).</li>" +
      "<li>Rechnerisch tritt die erste <strong>Fehlmenge</strong> im kalten Winter " + (kk.fehl_erster ? "ab etwa " + dat(kk.fehl_erster) + " (Spitze " + nf0.format(kk.fehl_spitze_gwh) + " GWh/Tag)" : "bis 31. März nicht") + " auf, im normalen Winter " + ((nf_.fehl_erster || nk.fehl_erster) ? "ab etwa " + dat(nf_.fehl_erster || nk.fehl_erster) : "nicht") + ".</li>" +
      reg +
      "<li>Nach dem Notfallplan Gas ruft das Wirtschaftsministerium die Stufen aus (Frühwarn-, Alarm-, Notfallstufe). In der Notfallstufe kann die Bundesnetzagentur als Bundeslastverteiler den Gasverbrauch lenken, geschützte Kunden wie Haushalte und Krankenhäuser werden bevorzugt. Laut Bundesnetzagentur galt zuletzt die Frühwarnstufe, bitte dort den aktuellen Stand prüfen.</li></ul>" +
      '<p class="hint">Das ist ein Rechenmodell, keine Warnung und keine Prognose der Behörden. Importe, Verbrauch und Politik reagieren in der Realität auf niedrige Füllstände, das ist hier nicht abgebildet. Regionale Schwellen für Einsparungen gibt es nicht, Brandenburg wird über das Verbundnetz versorgt.</p>' + meta(v, esc(v.quelle || "")));
  }
  function renderUmfeld(d) {
    var nd = noData(d, "Umfeld"); if (nd) return set("cUmfeld", nd);
    if (!d.anlagen) return set("cUmfeld", errNote(d) + hint(d.hinweis || "Keine Daten."));
    var su = d.summe, rows = d.anlagen.map(function (a) {
      var nutz = a.ausspeicherleistung_gwh > 0 ? a.ausspeicherung_gwh / a.ausspeicherleistung_gwh * 100 : null;
      var col = a.fuellstand_prozent < 30 ? "var(--red)" : a.fuellstand_prozent < 60 ? "var(--orange)" : "var(--green)";
      return "<tr><td>" + esc(a.name) + '<div class="meta" style="margin:0">' + esc(a.region) + '</div></td><td class="n"><strong>' + nf.format(a.fuellstand_prozent) + ' %</strong><div class="meta" style="margin:0">' + nf2.format(a.kapazitaet_twh) + ' TWh</div></td><td class="n">' + nf0.format(a.ausspeicherung_gwh) + ' / ' + (a.ausspeicherleistung_gwh > 0 ? nf0.format(a.ausspeicherleistung_gwh) : "–") + '<div class="meta" style="margin:0">' + (nutz == null ? "" : nf0.format(nutz) + " % genutzt") + "</div></td></tr>";
    }).join("");
    var h = errNote(d) + '<div class="big">' + (su.fuellstand_prozent == null ? "–" : nf.format(su.fuellstand_prozent)) + ' <span class="unit">% im Umfeld</span></div><p class="meta" style="margin-top:4px">' + nf.format(su.gas_twh) + " von " + nf.format(su.kapazitaet_twh) + " TWh in " + d.anlagen.length + " Speichern · Ausspeicherung 7-Tage-Mittel " + nf0.format(su.ausspeicherung_7t_gwh) + " GWh/Tag (technisch möglich " + nf0.format(su.ausspeicherleistung_gwh) + " GWh/Tag)</p>" +
      '<table><tr><th>Speicher</th><th class="n">Füllstand</th><th class="n">Ausspeicherung heute / möglich (GWh/Tag)</th></tr>' + rows + "</table>";
    if (d.projektion && d.projektion.length > 1) {
      var last = d.projektion[d.projektion.length - 1];
      h += spark(d.projektion.map(function (p) { return [0, p[1]]; }), { label: "Voraussichtlicher Füllstand im Umfeld, 14 Tage", min: 0, max: 100 }) +
        '<p class="meta">Voraussichtlicher Füllstand im Umfeld in 14 Tagen (' + esc(last[0]) + "): " + nf.format(last[1]) + " %. " + (d.engpass_tage > 0 ? "An " + d.engpass_tage + " von " + d.projektion.length + " Tagen würde der Heizbedarf die gemeldete Ausspeicherleistung übersteigen, die Entnahme wäre dann begrenzt." : "Die gemeldete Ausspeicherleistung wird in der Vorausschau nicht überschritten.") + "</p>";
    }
    set("cUmfeld", h + '<p class="hint">Die Speicher sind nach ihrer Lage in Brandenburg und Nachbarländern ausgewählt, der Netzanschluss ist nicht geprüft. Die Ausspeicherleistung ist der von den Betreibern gemeldete Wert. Ob und wie stark sie bei niedrigem Füllstand sinkt, hängt vom Speichertyp ab, das ist hier nicht berechnet.</p>' + meta(d, esc(d.quelle || "")));
  }

  var MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"], MSTART = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
  function renderHist(d) {
    var nd = noData(d, "Jahresvergleich"); if (nd) return set("cHist", nd);
    if (!d.jahre) return set("cHist", errNote(d) + hint(d.hinweis || "Keine Verlaufsdaten."));
    var W = 320, H = 150, L = 28, T = 8, B = 20, pw = W - L - 6, ph = H - T - B;
    function x(t) { return L + (t - 1) / 365 * pw; }
    function y(v) { return T + (100 - v) / 100 * ph; }
    var g = "";
    [0, 25, 50, 75, 100].forEach(function (v) { g += '<line x1="' + L + '" x2="' + (W - 6) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--sep)" stroke-width="0.6"/><text x="' + (L - 4) + '" y="' + (y(v) + 3) + '" text-anchor="end" font-size="8" fill="var(--muted)">' + v + "</text>"; });
    MSTART.forEach(function (t, i) { g += '<text x="' + x(t + 2) + '" y="' + (H - 6) + '" font-size="8" fill="var(--muted)">' + MONATE[i] + "</text>"; });
    var upper = [], lower = [];
    (d.band || []).forEach(function (b) { if (b[1] != null) { upper.push(x(b[0]).toFixed(1) + "," + y(b[2]).toFixed(1)); lower.unshift(x(b[0]).toFixed(1) + "," + y(b[1]).toFixed(1)); } });
    if (upper.length) g += '<polygon points="' + upper.concat(lower).join(" ") + '" fill="var(--blue)" opacity="0.16"/>';
    function line(arr, col, w, dash) { return arr && arr.length ? '<path d="' + arr.map(function (p, i) { return (i ? "L" : "M") + x(p[0]).toFixed(1) + " " + y(p[1]).toFixed(1); }).join(" ") + '" fill="none" stroke="' + col + '" stroke-width="' + w + '" stroke-linejoin="round"' + (dash ? ' stroke-dasharray="3 3"' : "") + "/>" : ""; }
    var avg = (d.band || []).filter(function (b) { return b[3] != null; }).map(function (b) { return [b[0], b[3]]; });
    var cur = String(d.aktuelles_jahr), prev = String(d.aktuelles_jahr - 1);
    g += line(avg, "var(--muted)", 1, true) + line(d.jahre[prev], "var(--orange)", 1.4) + line(d.jahre[cur], "var(--blue)", 2.2);
    var c = d.jahre[cur] || [], last = c.length ? c[c.length - 1] : null, a = last ? (d.band[last[0] - 1] || [])[3] : null;
    var txt = last && a != null ? "Aktuell " + nf.format(last[1]) + " % gegenüber dem Mittel der Vorjahre von " + nf.format(a) + " % (" + (last[1] >= a ? "+" : "") + nf.format(last[1] - a) + " Prozentpunkte)." : "";
    set("cHist", errNote(d) + '<svg viewBox="0 0 ' + W + " " + H + '" style="width:100%;height:auto" role="img" aria-label="Füllstand Deutschland im Jahresvergleich">' + g + "</svg>" +
      '<p class="meta"><span style="color:var(--blue)">■</span> ' + cur + ' · <span style="color:var(--orange)">■</span> ' + prev + ' · <span style="color:var(--muted)">- - -</span> Mittel ' + d.vorjahre[0] + "–" + d.vorjahre[d.vorjahre.length - 1] + " · helle Fläche: niedrigster bis höchster Wert dieser Jahre</p>" +
      (txt ? '<p style="margin:8px 0 0">' + esc(txt) + "</p>" : "") + meta(d, esc(d.quelle || "")));
  }

  var state = { scope: "de", wetter: null };
  function renderWetter(d) {
    state.wetter = d;
    var nd = noData(d, "Wetter"); if (nd) return set("cWetter", nd);
    var temps = state.scope === "bb" ? d.brandenburg : d.deutschland;
    if (!temps) return set("cWetter", errNote(d) + hint("Keine Wetterdaten."));
    var i0 = d.heute_index || 7, ort = state.scope === "bb" ? "Potsdam (Brandenburg)" : "Deutschland (Mittel aus 6 Großstädten)";
    var chips = d.tage.slice(i0, i0 + 7).map(function (t, k) {
      var dt = new Date(t + "T12:00:00"), v = temps[i0 + k];
      return '<div style="text-align:center;flex:1;min-width:0"><div class="meta" style="margin:0">' + (k ? dt.toLocaleDateString("de-DE", { weekday: "short" }) : "Heute") + '</div><div style="font-weight:600">' + (v == null ? "–" : nf0.format(v) + "°") + "</div></div>";
    }).join("");
    set("cWetter", errNote(d) + '<h3 style="margin-bottom:2px">' + esc(ort) + '</h3><div style="display:flex;gap:4px;margin:8px 0">' + chips + "</div>" +
      spark(temps.map(function (v) { return [0, v]; }), { label: "Tagesmitteltemperatur, 7 Tage zurück und 14 Tage voraus", mid: 15 }) +
      '<p class="meta">Tagesmittel der letzten 7 und der nächsten 14 Tage. Gestrichelt 15 °C: darunter wird geheizt, je kälter, desto mehr Gasverbrauch.</p>' + meta(d, esc(d.quelle || "")));
  }
  function applyScope(sc) {
    state.scope = sc;
    document.body.classList.toggle("scope-bb", sc === "bb"); document.body.classList.toggle("scope-de", sc === "de");
    document.querySelectorAll(".seg button").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.ansicht === sc ? "true" : "false"); });
    try { localStorage.setItem("energie.ansicht", sc); } catch (e) {}
    if (state.wetter) renderWetter(state.wetter);
  }

  function renderPipe(d) {
    var nd = noData(d, "Pipelines"); if (nd) return set("cPipe", nd);
    if (!d.gruppen || !d.gruppen.length || d.gruppen[0].netto === undefined) return set("cPipe", errNote(d) + hint("Die Pipeline-Daten werden gerade neu berechnet."));
    var g = d.gruppen.slice().sort(function (a, b) { return (b.einspeisung || 0) - (a.einspeisung || 0); });
    var rows = g.map(function (x) {
      return "<tr><td>" + esc(x.name) + '</td><td class="n">' + (x.einspeisung == null ? "–" : nf0.format(x.einspeisung)) + '</td><td class="n">' + (x.ausfuhr == null ? "–" : nf0.format(x.ausfuhr)) + '</td><td class="n"><strong>' + (x.netto == null ? "–" : nf0.format(x.netto)) + "</strong></td></tr>";
    }).join("");
    set("cPipe", errNote(d) + '<div class="big">' + nf0.format(d.summe_netto) + ' <span class="unit">GWh/Tag netto</span></div><p class="meta" style="margin-top:4px">Einspeisung nach Deutschland insgesamt ' + nf0.format(d.summe_einspeisung) + " GWh/Tag, davon läuft ein Teil wieder hinaus.</p>" +
      spark((d.verlauf || []).map(function (p) { return [0, p[1]]; }), { label: "Netto-Importe, 10 Tage", minSpan: 100 }) +
      '<table><tr><th>Herkunft</th><th class="n">Einspeisung</th><th class="n">Ausfuhr</th><th class="n">Netto</th></tr>' + rows + "</table>" +
      '<p class="meta">Angaben in GWh pro Tag für den ' + esc(d.tag) + " (neuester Tag, für den alle Länder gemeldet haben). Netto = Einspeisung minus Ausfuhr an denselben Punkten. Wo beides fast gleich hoch ist (z. B. Niederlande, Belgien, Tschechien), fließt das Gas vermutlich überwiegend durch Deutschland hindurch.</p>" + meta(d, esc(d.quelle || "")));
  }
  function renderLngEin(d) {
    var nd = noData(d, "LNG"); if (nd) return set("cLng", nd);
    if (!d.terminals || !d.terminals.length || d.terminals[0].einspeisung === undefined) return set("cLng", errNote(d) + hint("Die LNG-Daten werden gerade neu berechnet."));
    var items = d.terminals.map(function (t) { return [t.name, t.einspeisung]; }).sort(function (a, b) { return (b[1] || 0) - (a[1] || 0); });
    set("cLng", errNote(d) + '<div class="big">' + nf0.format(d.summe) + ' <span class="unit">GWh/Tag gesamt</span></div>' + bars(items, "GWh/d") +
      '<p class="meta">Einspeisung der deutschen LNG-Terminals ins Gasnetz am ' + esc(d.tag) + "</p>" + meta(d, esc(d.quelle || "")));
  }

  function renderPreis(d) {
    var nd = noData(d, "Strompreis"); if (nd) return set("cPreis", nd);
    var p = d.preis_eur_mwh;
    set("cPreis", errNote(d) + (p == null ? hint("Kein Preis verfügbar.") : '<div class="big">' + nf2.format(p) + ' <span class="unit">€/MWh</span></div>' + spark(d.preis_verlauf || [], { label: "Strompreis, 48 Stunden" }) + '<p class="meta">Day-Ahead-Preis Deutschland/Luxemburg, letzte 48 Stunden</p>') + meta(d, "SMARD.de, CC BY 4.0"));
  }
  function renderMix(d) {
    var nd = noData(d, "Stromerzeugung"); if (nd) return set("cMix", nd);
    var m = d.erzeugung_mw || {}, items = Object.keys(m).map(function (k) { return [k, m[k]]; }).filter(function (i) { return i[0] !== "Pumpspeicher"; }).sort(function (a, b) { return b[1] - a[1]; });
    var sum = items.reduce(function (a, i) { return a + i[1]; }, 0), ee = ["Wind offshore", "Wind onshore", "Photovoltaik", "Wasserkraft", "Sonstige Erneuerbare"];
    var eeSum = items.reduce(function (a, i) { return a + (ee.indexOf(i[0]) >= 0 ? i[1] : 0); }, 0);
    set("cMix", errNote(d) + '<div class="big">' + (sum ? nf0.format(eeSum / sum * 100) : "–") + ' <span class="unit">% erneuerbar an der Erzeugung</span></div>' +
      bars(items, "MW") + '<p class="meta">Erzeugung gesamt ' + nf0.format(sum) + " MW" + (d.verbrauch_mw != null ? " · Verbrauch (Netzlast) " + nf0.format(d.verbrauch_mw) + " MW" : "") + " · Deutschland, nicht Brandenburg</p>" +
      meta(d, d.daten_stand_ms ? "Messwerte von " + when(d.daten_stand_ms) : ""));
  }

  function renderFreq(d) {
    var nd = noData(d, "Netzfrequenz"); if (nd) return set("cFreq", nd);
    if (d.hz == null) return set("cFreq", errNote(d) || hint("Keine Frequenz verfügbar."));
    var dev = Math.abs(d.hz - 50), cls = dev < 0.05 ? "" : dev < 0.2 ? "warn" : "bad", txt = dev < 0.05 ? "im Normalbereich" : dev < 0.2 ? "leicht abweichend" : "deutliche Abweichung";
    set("cFreq", errNote(d) + '<div class="big">' + nf3.format(d.hz) + ' <span class="unit">Hz</span> <span class="pill ' + cls + '">' + txt + "</span></div>" +
      spark(d.verlauf || [], { label: "Netzfrequenz, 24 Stunden", mid: 50, min: 49.9, max: 50.1 }) +
      '<p class="meta">Sollwert 50,000 Hz, Normalbereich ±0,05 Hz. Gestrichelt: 50 Hz. Verlauf der letzten 24 Stunden.</p>' +
      meta(d, "Quelle: " + esc(d.quelle || "") + ". Der Wert ist eine Momentaufnahme beim letzten Abruf, nicht live."));
  }

  function renderKraft(d) {
    var nd = noData(d, "Kraftstoff"); if (nd) return set("cKraft", nd);
    if (!d.preise) return set("cKraft", errNote(d) + hint(d.hinweis || "Keine Preise."));
    var n = { diesel: "Diesel", e5: "Super E5", e10: "Super E10" }, rows = Object.keys(d.preise).map(function (k) {
      var p = d.preise[k]; return "<tr><td>" + n[k] + '</td><td class="n">' + nf2.format(p.min) + '</td><td class="n"><strong>' + nf2.format(p.median) + '</strong></td><td class="n">' + nf2.format(p.max) + '</td><td class="n">' + p.anzahl + "</td></tr>";
    }).join("");
    set("cKraft", errNote(d) + '<table><tr><th>Sorte</th><th class="n">günstigste €/l</th><th class="n">mittlere €/l</th><th class="n">teuerste €/l</th><th class="n">Tankstellen</th></tr>' + rows + "</table>" +
      '<p class="meta">Nur geöffnete Tankstellen in Brandenburg (' + d.stationen + " erfasst).</p>" + meta(d, esc(d.quelle || "")));
  }

  function renderOel(d) {
    var nd = noData(d, "Rohöl"); if (nd) return set("cOel", nd);
    if (d.brent_usd == null) return set("cOel", errNote(d) || hint("Kein Rohölpreis verfügbar."));
    var up = d.aenderung_prozent >= 0;
    set("cOel", errNote(d) + '<div class="big">' + nf2.format(d.brent_usd) + ' <span class="unit">US-Dollar je Barrel</span></div><p style="margin:4px 0;color:var(--' + (up ? "bad" : "ok") + ')">' +
      (up ? "▲ " : "▼ ") + nf2.format(Math.abs(d.aenderung_prozent)) + ' % zum Vortag</p>' + spark((d.verlauf || []).map(function (p) { return [0, p[1]]; }), { label: "Brent, 60 Tage" }) +
      '<p class="meta">Kursdatum ' + esc(d.datum) + ", verzögert</p>" + meta(d, esc(d.quelle || "")));
  }

  function load() {
    Promise.all(["meta.json", "gas_speicher.json", "gas_lng.json", "gas_pipeline.json", "strom.json", "frequenz.json", "kraftstoff.json", "rohoel.json", "reichweite.json", "gas_historie.json", "wetter.json", "gas_europa.json", "gas_anlagen.json", "gaspreis.json", "lng_tanks.json", "gas_umfeld.json", "gas_vorausschau.json", "gas_umfeld_vorausschau.json", "gas_stoerungen.json", "gas_preisanalyse.json", "prognose_verlauf.json"].map(get)).then(function (r) {
      document.getElementById("stand").textContent = r[0] && r[0].letzter_lauf ? "Letzter Datenabruf: " + when(r[0].letzter_lauf) : "Noch kein Datenabruf.";
      [function () { renderSpeicherDE(r[1]); }, function () { renderSpeicherBB(r[1]); },
        function () { renderLngEin(r[2]); }, function () { renderPipe(r[3]); },
        function () { renderPreis(r[4]); }, function () { renderMix(r[4]); }, function () { renderFreq(r[5]); }, function () { renderKraft(r[6]); },
        function () { renderOel(r[7]); }, function () { renderReich(r[8], r[16]); }, function () { renderHist(r[9]); }, function () { renderWetter(r[10]); }, function () { renderEuropa(r[11]); }, function () { renderAnlagen(r[12]); }, function () { renderTtf(r[13], r[19]); }, function () { renderLngTanks(r[14]); }, function () { renderUmfeld(r[15]); }, function () { renderVorausschau(r[16], r[20]); }, function () { renderEinsp(r[16]); }, function () { renderUmfeldVor(r[17], r[15]); }, function () { renderStoerungen(r[18]); }, function () { renderVersorgung(r[16], r[17]); }
      ].forEach(function (f) { try { f(); } catch (e) { if (window.console) console.error(e); } });
    });
  }
  document.querySelectorAll(".seg button").forEach(function (b) { b.addEventListener("click", function () { applyScope(b.dataset.ansicht); }); });
  var sc = "de"; try { sc = localStorage.getItem("energie.ansicht") || "de"; } catch (e) {}
  applyScope(sc === "bb" ? "bb" : "de");
  var links = [].slice.call(document.querySelectorAll(".tabbar a"));
  function spy() {
    var y = window.scrollY + 130, cur = null;
    links.forEach(function (a) {
      var t = document.querySelector(a.getAttribute("href")); if (!t || t.offsetParent === null) return;
      if (t.getBoundingClientRect().top + window.scrollY <= y) cur = a;
    });
    links.forEach(function (a) { if (a === cur) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current"); });
  }
  window.addEventListener("scroll", spy, { passive: true });
  load();
  setInterval(load, 60000);
})();
