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
  function set(id, html) { document.querySelector("#" + id + " .body").innerHTML = html; }
  function hint(t, bad) { return '<p class="hint' + (bad ? " err" : "") + '">' + esc(t) + "</p>"; }
  function errNote(d) { return d && d.fehler ? hint("Letzter Abruf fehlgeschlagen (" + when(d.fehler_stand) + "): " + d.fehler, true) : ""; }
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
  function lastVal(series) { for (var i = series.length - 1; i >= 0; i--) if (series[i][1] != null) return series[i]; return null; }

  function renderSpeicher(d) {
    var nd = noData(d, "Gasspeicher"); if (nd) return set("cSpeicher", nd);
    var h = errNote(d), de = d.deutschland;
    if (!de) h += hint(d.hinweis || "Keine Speicherdaten.");
    else {
      h += '<div class="grid"><div><div class="big">' + nf.format(de.fuellstand_prozent) + ' <span class="unit">% Deutschland</span></div>' +
        '<div class="row" style="grid-template-columns:1fr"><div class="bar"><span style="width:' + Math.min(100, de.fuellstand_prozent) + '%"></span></div></div>' +
        '<p class="meta">' + nf.format(de.gas_twh) + " von " + nf.format(de.kapazitaet_twh) + " TWh · Einspeicherung " + nf0.format(de.einspeicherung_gwh) + " GWh/Tag · Ausspeicherung " + nf0.format(de.ausspeicherung_gwh) + " GWh/Tag · Gastag " + esc(de.gastag) + "</p></div>" +
        "<div>" + spark(de.verlauf.map(function (p) { return [0, p[1]]; }), { label: "Füllstand Deutschland, 30 Tage", minSpan: 5 }) + '<p class="meta">Füllstand der letzten 30 Tage</p></div></div>';
    }
    h += "<h3 style=\"margin-top:14px\">Speicher in Brandenburg</h3>";
    if (!d.brandenburg || !d.brandenburg.length) h += hint("Die Brandenburger Speicheranlagen sind noch nicht festgelegt (config/brandenburg-speicher.json).");
    else h += bars(d.brandenburg.map(function (s) { return [s.name, s.fuellstand_prozent]; }), "%", 100);
    set("cSpeicher", h + meta(d, esc(d.quelle || "")));
  }

  function renderGruppen(id, d, key, titelLeer) {
    var nd = noData(d, titelLeer); if (nd) return set(id, nd);
    var g = d[key] || {}, items = [], tag = null, summe = 0, any = false;
    Object.keys(g).forEach(function (n) {
      var lv = lastVal(g[n]); items.push([n, lv ? lv[1] : null, lv ? lv[0] : null]);
      if (lv) { any = true; summe += lv[1]; if (!tag || lv[0] > tag) tag = lv[0]; }
    });
    items.sort(function (a, b) { return (b[1] || 0) - (a[1] || 0); });
    var h = errNote(d);
    if (!any) h += hint("Keine Daten gemeldet.");
    else h += '<div class="big">' + nf0.format(summe) + ' <span class="unit">GWh/Tag gesamt</span></div>' + bars(items, "GWh/d");
    var leer = items.filter(function (i) { return i[1] == null; }).map(function (i) { return i[0]; });
    set(id, h + (leer.length ? '<p class="meta">Keine Daten gemeldet: ' + esc(leer.join(", ")) + "</p>" : "") + meta(d, (tag ? "letzter Tag mit Daten " + esc(tag) : "") + " · " + esc(d.quelle || "")));
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

  function renderSchwedt(d) {
    if (!d) return set("cSchwedt", hint("Keine Daten."));
    var h = (d.pruefen ? hint(d.hinweis) : "") + '<ul class="plain">' + (d.eckdaten || []).map(function (e) { return "<li><strong>" + esc(e.label) + ":</strong> " + esc(e.wert) + "</li>"; }).join("") + "</ul>" +
      '<p class="meta">Für Auslastung und Kraftstoffversorgung gibt es keine offene Live-Schnittstelle. Hilfreiche Quellen:</p><ul class="plain">' +
      (d.quellen || []).map(function (q) { return '<li><a href="' + esc(q.url) + '" rel="noopener">' + esc(q.titel) + "</a></li>"; }).join("") + "</ul>";
    set("cSchwedt", h);
  }

  function load() {
    Promise.all(["meta.json", "gas_speicher.json", "gas_lng.json", "gas_pipeline.json", "strom.json", "frequenz.json", "kraftstoff.json", "rohoel.json", "schwedt.json"].map(get)).then(function (r) {
      document.getElementById("stand").textContent = r[0] && r[0].letzter_lauf ? "Letzter Datenabruf: " + when(r[0].letzter_lauf) : "Noch kein Datenabruf.";
      renderSpeicher(r[1]);
      renderGruppen("cLng", r[2], "terminals", "LNG");
      renderGruppen("cPipe", r[3], "gruppen", "Pipelines");
      renderPreis(r[4]); renderMix(r[4]); renderFreq(r[5]); renderKraft(r[6]); renderOel(r[7]); renderSchwedt(r[8]);
    });
  }
  load();
  setInterval(load, 60000);
})();
