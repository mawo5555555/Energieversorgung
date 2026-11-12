# Energie Brandenburg

Web-App mit Gasspeichern, LNG- und Pipeline-Importen, Strom, Netzfrequenz, Kraftstoffpreisen, Rohöl, Wetter und einer Vorausschau zur Gasspeicher-Reichweite.

## So funktioniert es

- `index.html`, `app.js`, `style.css`: die Seite (reines HTML/JS, keine Abhängigkeiten). Sie liest nur `data/*.json`.
- `scripts/fetch_data.py`: holt die Daten aus den Quellen und schreibt `data/*.json`. Fällt eine Quelle aus, bleibt der letzte gute Stand und es wird ein Fehler vermerkt.
- `.github/workflows/daten.yml`: startet das Skript alle 15 Minuten (GitHub kann das verzögern) und speichert Änderungen im Repository.
- `config/`: Messpunkte (ENTSOG), Brandenburger Speicher (EIC-Codes), Suchzentren für Tankstellen.

## Einrichtung

1. GitHub Pages einschalten (Settings → Pages → Branch `main`, Ordner `/`).
2. Unter Settings → Secrets and variables → Actions diese Secrets anlegen:
   - `GIE_API_KEY` (kostenlos auf https://agsi.gie.eu/account), für Gasspeicher und LNG
   - `TANKERKOENIG_API_KEY` (kostenlos auf https://creativecommons.tankerkoenig.de), für Kraftstoffpreise
3. Unter Actions den Workflow „Daten abrufen“ einmal manuell starten (Run workflow).

Ohne die Schlüssel laufen Strom, Netzfrequenz, Pipelines und LNG trotzdem; die anderen Kacheln zeigen einen Hinweis.

## Quellen und Lizenzen

- Gasspeicher: GIE AGSI+ (Quellenangabe Pflicht)
- Pipelines und LNG-Einspeisung: ENTSOG Transparency Platform
- Strom: Bundesnetzagentur | SMARD.de, CC BY 4.0
- Netzfrequenz: netzfrequenz.info (inoffiziell, nur Momentwert)
- Kraftstoff: Tankerkönig.de, CC BY 4.0
- Rohöl: stooq.com (verzögert)

Alle Angaben ohne Gewähr.
