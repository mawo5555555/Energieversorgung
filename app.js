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

  var state = { scope: "bb", wetter: null };
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
    try { localStorage.setItem("energie.scope", sc); } catch (e) {}
    if (state.wetter) renderWetter(state.wetter);
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

  function load() {
    Promise.all(["meta.json", "gas_speicher.json", "gas_lng.json", "gas_pipeline.json", "strom.json", "frequenz.json", "kraftstoff.json", "rohoel.json", "reichweite.json", "gas_historie.json", "wetter.json"].map(get)).then(function (r) {
      document.getElementById("stand").textContent = r[0] && r[0].letzter_lauf ? "Letzter Datenabruf: " + when(r[0].letzter_lauf) : "Noch kein Datenabruf.";
      [function () { renderSpeicherDE(r[1]); }, function () { renderSpeicherBB(r[1]); },
        function () { renderGruppen("cLng", r[2], "terminals", "LNG"); }, function () { renderGruppen("cPipe", r[3], "gruppen", "Pipelines"); },
        function () { renderPreis(r[4]); }, function () { renderMix(r[4]); }, function () { renderFreq(r[5]); }, function () { renderKraft(r[6]); },
        function () { renderOel(r[7]); }, function () { renderReich(r[8]); }, function () { renderHist(r[9]); }, function () { renderWetter(r[10]); }
      ].forEach(function (f) { try { f(); } catch (e) { if (window.console) console.error(e); } });
    });
  }
  document.querySelectorAll(".seg button").forEach(function (b) { b.addEventListener("click", function () { applyScope(b.dataset.ansicht); }); });
  var sc = "bb"; try { sc = localStorage.getItem("energie.scope") || "bb"; } catch (e) {}
  applyScope(sc === "de" ? "de" : "bb");
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
