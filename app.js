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
  function renderReich(d) {
    var nd = noData(d, "Reichweite");
    if (nd) { set("cReichDE", nd); set("cReichBB", nd); return; }
    if (!d.deutschland && !d.brandenburg) { set("cReichDE", hint(d.hinweis || "Keine Daten.")); set("cReichBB", hint(d.hinweis || "Keine Daten.")); return; }
    var ann = '<p class="hint">' + esc(d.annahmen || "") + " Das ist eine Schätzung, keine Prognose der Versorgungssicherheit.</p>";
    set("cReichDE", errNote(d) + reichBlock(d.deutschland) + ann + meta(d, ""));
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

  function renderTtf(d) {
    var nd = noData(d, "Erdgaspreis"); if (nd) return set("cTtf", nd);
    if (d.preis == null) return set("cTtf", errNote(d) || hint("Kein Erdgaspreis verfügbar."));
    var up = d.aenderung_prozent >= 0;
    set("cTtf", errNote(d) + '<div class="big">' + nf2.format(d.preis) + ' <span class="unit">€/MWh</span></div><p style="margin:4px 0;color:var(--' + (up ? "bad" : "ok") + ')">' + (up ? "▲ " : "▼ ") + nf2.format(Math.abs(d.aenderung_prozent)) + " % zum Vortag</p>" +
      spark((d.verlauf || []).map(function (p) { return [0, p[1]]; }), { label: "TTF, 60 Tage" }) + '<p class="meta">Niederländischer Großhandelspreis (TTF), Leitpreis für Erdgas in Europa. Kursdatum ' + esc(d.datum) + ", verzögert</p>" + meta(d, esc(d.quelle || "")));
  }
  function renderLngTanks(d) {
    var nd = noData(d, "LNG-Tanks"); if (nd) return set("cLngTanks", nd);
    if (!d.terminals && !d.deutschland) return set("cLngTanks", errNote(d) + hint(d.hinweis || "Keine Daten."));
    var de = d.deutschland, h = errNote(d);
    if (de && de.fuellstand_prozent != null) h += '<div class="gauge"><div>' + gauge(de.fuellstand_prozent, false, "Tankfüllstand LNG Deutschland") + '</div><div><div class="big">' + nf.format(de.fuellstand_prozent) + ' <span class="unit">%</span></div><div class="num">LNG-Tanks in Deutschland</div>' +
      '<p class="meta" style="margin-top:4px">' + (de.inhalt_gwh != null ? nf0.format(de.inhalt_gwh) + " GWh gelagert" : "") + (de.ausspeisung_gwh != null ? " · Ausspeisung ins Netz " + nf0.format(de.ausspeisung_gwh) + " GWh/Tag" : "") + "</p></div></div>";
    if (de && de.verlauf) h += spark(de.verlauf.map(function (p) { return [0, p[1]]; }), { label: "Tankfüllstand LNG, 10 Tage", minSpan: 5 });
    h += (d.terminals || []).map(function (t) {
      var col = t.fuellstand_prozent == null ? "var(--muted)" : t.fuellstand_prozent < 30 ? "var(--red)" : t.fuellstand_prozent < 60 ? "var(--orange)" : "var(--green)";
      return '<div class="row"><span>' + esc(t.name) + '</span><div class="bar"><span style="width:' + Math.min(100, t.fuellstand_prozent || 0) + "%;background:" + col + '"></span></div><span class="val">' + (t.fuellstand_prozent == null ? "–" : nf.format(t.fuellstand_prozent) + " %") + "</span></div>";
    }).join("");
    set("cLngTanks", h + '<p class="meta">Tankfüllstand der LNG-Terminals und Ausspeisung ins Gasnetz, letzter gemeldeter Gastag' + (de && de.gastag ? " " + esc(de.gastag) : "") + "</p>" + meta(d, esc(d.quelle || "")));
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
    Promise.all(["meta.json", "gas_speicher.json", "gas_lng.json", "gas_pipeline.json", "strom.json", "frequenz.json", "kraftstoff.json", "rohoel.json", "reichweite.json", "gas_historie.json", "wetter.json", "gas_europa.json", "gas_anlagen.json", "gaspreis.json", "lng_tanks.json", "gas_umfeld.json"].map(get)).then(function (r) {
      document.getElementById("stand").textContent = r[0] && r[0].letzter_lauf ? "Letzter Datenabruf: " + when(r[0].letzter_lauf) : "Noch kein Datenabruf.";
      [function () { renderSpeicherDE(r[1]); }, function () { renderSpeicherBB(r[1]); },
        function () { renderLngEin(r[2]); }, function () { renderPipe(r[3]); },
        function () { renderPreis(r[4]); }, function () { renderMix(r[4]); }, function () { renderFreq(r[5]); }, function () { renderKraft(r[6]); },
        function () { renderOel(r[7]); }, function () { renderReich(r[8]); }, function () { renderHist(r[9]); }, function () { renderWetter(r[10]); }, function () { renderEuropa(r[11]); }, function () { renderAnlagen(r[12]); }, function () { renderTtf(r[13]); }, function () { renderLngTanks(r[14]); }, function () { renderUmfeld(r[15]); }
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
