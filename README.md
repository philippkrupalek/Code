# Bankenversand-Assistent — Stufe 1

Prüft, ob für einen Berichtsmonat alle Dateien aus der Versandmatrix im
Bankenversand-Ordner liegen, und schreibt einen Kontrollbericht.

**Diese Stufe liest ausschließlich.** Es wird nichts kopiert, nichts überschrieben,
nichts verschickt. Der einzige Schreibvorgang geht in den lokalen `output/`-Ordner.

## Einrichten

**Keine Installation nötig.** Das Skript kommt mit der Standard-Bibliothek aus —
kein `pip`, keine virtuelle Umgebung, keine externen Pakete. Es braucht nur eine
vorhandene Python-Installation ab 3.9.

Die `.xlsx` wird direkt gelesen: eine Excel-Datei ist ein ZIP mit XML darin, und
das kann Python von Haus aus. Alternativ funktioniert auch eine `.csv` — dann in
`config.json` einfach den Dateinamen umstellen.

Ordnerstruktur:

```
bankenversand-assistent/
├── config.json
├── versandmatrix.xlsx
├── src/
│   ├── main.py
│   ├── matrix.py
│   ├── xlsx_reader.py
│   ├── finder.py
│   └── report.py
└── output/            (wird automatisch angelegt)
```

## Verwenden

```
python src/main.py --monat 7 --jahr 2026
```

Zum Testen ohne K-Laufwerk:

```
python src/main.py --monat 7 --jahr 2026 --root C:\Temp\Testbankenversand
```

## Status im Kontrollbericht

| Status | Bedeutung |
|---|---|
| `OK` | Genau eine Datei mit passendem Namen gefunden |
| `UNGEFAEHR` | Datei gefunden, Name weicht ab — Spalte `score` und `gefundene_datei` prüfen |
| `MEHRDEUTIG` | Mehrere Kandidaten, das Skript rät nicht — Kandidaten stehen in `gefundene_datei` |
| `FEHLT` | Nichts Passendes gefunden; der beste Kandidat steht in `detail` |
| `KEIN_BANKORDNER` | Für die Bank gibt es im Monatsordner keinen Ordner |
| `MANUELL` | Zeile ohne prüfbare Datei (Download-Link, offener Platzhalter) |

Beim ersten Lauf werden viele Zeilen nicht `OK` sein. Das ist so gewollt: daran
siehst du, wo die Dateimuster in der Matrix von der Realität abweichen. Korrigiert
wird dann in der **Matrix**, nicht im Code.

## Matching

Der Vergleich läuft normalisiert: Kleinschreibung, Umlaute aufgelöst,
Sonderzeichen zu Leerzeichen, `Volksbank` und `VB` gleichwertig. Dadurch matcht
`Sparplanreporting Juli 2026 VB Tirol.xlsx` auch auf das Muster mit Unterstrich.

Die Schwelle für unscharfe Treffer steht in `config.json` unter `match_schwelle`
(Standard 0.85). Zu niedrig führt zu falschen Zuordnungen, zu hoch zu unnötigen
`FEHLT`-Meldungen.

## Platzhalter

| Platzhalter | Beispiel Juli 2026 |
|---|---|
| `{MM}` | `07` |
| `{JJJJ}` | `2026` |
| `{MONAT}` | `Juli` |
| `{STICHTAG}` | `20260731` |

Der Berichtsmonat wird als Eingabe übergeben, nicht aus dem Tableau-Workbooknamen
abgeleitet. Damit hängt der Assistent nicht an Marvins `getSuffix()`.

`{WORKBOOK_DATUM}` in der Wien-NH-Zeile wird bewusst nicht aufgelöst — solange
unklar ist, was da angehängt wird, landet die Zeile auf `MANUELL`.

## Nächste Stufen

2. Marvin-Logs auswerten, PDFs prüfen und in die Bankordner kopieren
3. Mailpakete unter `03_Mailvorbereitung` schnüren, inklusive `mail_metadata.json`
4. Ausgabe-Adapter: Outlook-Entwürfe oder Teams-Ablage
