"""Bankenversand-Assistent, Stufe 2: Marvin-PDFs pruefen und einsammeln."""

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from finder import finde_bankordner, finde_monatsordner, normalisiere
from matrix import Berichtsmonat, lade_matrix

SPALTEN = ["bank", "pdf", "log_status", "pdf_status", "aktion",
           "in_matrix", "ziel", "detail"]


def sammle_logs(logs_root: Path, suffix: str) -> list[dict]:
    """Zuordnung ueber das Feld 'report', nicht ueber den Log-Dateinamen."""
    gefunden = []
    for log_datei in sorted(logs_root.rglob("*.log.json")):
        try:
            with log_datei.open(encoding="utf-8") as f:
                daten = json.load(f)
        except (OSError, json.JSONDecodeError) as fehler:
            gefunden.append({"log": log_datei, "daten": None, "fehler": str(fehler)})
            continue
        if str(daten.get("report", "")).lower().endswith(suffix.lower()):
            gefunden.append({"log": log_datei, "daten": daten, "fehler": None})
    return gefunden


def pruefe_log(daten: dict) -> tuple[bool, str]:
    if daten.get("status") != "SUCCESSFUL":
        return False, f"Log-Status {daten.get('status')}"
    if daten.get("errors", 0) != 0:
        return False, f"{daten.get('errors')} Fehler im Log"
    seiten = daten.get("pages", [])
    schlecht = [s for s in seiten if s.get("status") != "SUCCESSFUL"]
    if schlecht:
        return False, f"{len(schlecht)} von {len(seiten)} Seiten fehlerhaft"
    return True, f"{len(seiten)} Seiten"


def pruefe_pdf(pfad: Path) -> tuple[bool, str]:
    if not pfad.is_file():
        return False, "PDF nicht vorhanden"
    groesse = pfad.stat().st_size
    if groesse == 0:
        return False, "PDF ist leer"
    if groesse < 10000:
        return False, f"PDF verdaechtig klein ({groesse} Bytes)"
    return True, f"{groesse // 1024} KB"


def schreibe_bericht(zeilen, ordner: Path, monat) -> Path:
    ordner.mkdir(parents=True, exist_ok=True)
    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    ziel = ordner / f"pdf_uebernahme_{monat.jahr}-{monat.monat:02d}_{stempel}.csv"
    with ziel.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SPALTEN, delimiter=";")
        writer.writeheader()
        writer.writerows(zeilen)
    return ziel


def main() -> int:
    p = argparse.ArgumentParser(description="Bankenversand-Assistent Stufe 2")
    p.add_argument("--monat", type=int, required=True)
    p.add_argument("--jahr", type=int, required=True)
    p.add_argument("--config", default="config.json")
    p.add_argument("--root")
    p.add_argument("--logs", help="Logs-Ordner des Tableau-Skripts")
    p.add_argument("--schreiben", action="store_true")
    p.add_argument("--ueberschreiben", action="store_true")
    args = p.parse_args()

    basis = Path(args.config).resolve().parent
    with Path(args.config).open(encoding="utf-8") as f:
        cfg = json.load(f)
    monat = Berichtsmonat(args.monat, args.jahr)
    schwelle = float(cfg.get("match_schwelle", 0.85))
    root = Path(args.root or cfg["bankenversand_root"])
    logs_root = Path(args.logs or cfg.get("marvin_logs", ""))

    modus = "SCHREIBEN" if args.schreiben else "PROBELAUF (nichts wird kopiert)"
    print(f"\nBankenversand-Assistent, Stufe 2 - {modus}")
    print(f"Berichtsmonat : {monat}")
    print(f"Logs          : {logs_root}")

    if not logs_root.is_dir():
        print("\nLogs-Ordner nicht erreichbar. Pfad mit --logs angeben.")
        return 1
    if not root.is_dir():
        print("\nBankenversand-Wurzel nicht erreichbar.")
        return 1

    monatsordner = finde_monatsordner(root, cfg["monatsordner_muster"], monat.werte)
    if monatsordner is None:
        print(f"\nKein Monatsordner fuer {monat} gefunden.")
        return 1
    print(f"Monatsordner  : {monatsordner}")

    suffix = f"__{monat.werte['{MM}']}-{monat.werte['{JJJJ}']}.pdf"
    logs = sammle_logs(logs_root, suffix)
    print(f"Passende Logs : {len(logs)} (Suffix {suffix})\n")
    if not logs:
        print("Keine Logs zu diesem Berichtsmonat gefunden. Stimmt der Monat?")
        return 1

    matrix_pfad = basis / cfg["versandmatrix"]
    gefragt = set()
    if matrix_pfad.is_file():
        for z in lade_matrix(str(matrix_pfad), cfg["matrix_blatt"], monat):
            gefragt.add(normalisiere(z.muster))

    cache: dict = {}
    ergebnis = []
    kopiert = ueberspringen = fehlerhaft = 0

    for eintrag in logs:
        log_datei, daten = eintrag["log"], eintrag["daten"]
        if daten is None:
            ergebnis.append({"bank": "", "pdf": log_datei.name, "log_status": "LESEFEHLER",
                             "pdf_status": "", "aktion": "UEBERSPRUNGEN", "in_matrix": "",
                             "ziel": "", "detail": eintrag["fehler"]})
            fehlerhaft += 1
            continue

        pdf = Path(daten["report"])
        bank = pdf.parent.name
        log_ok, log_detail = pruefe_log(daten)
        pdf_ok, pdf_detail = pruefe_pdf(pdf)

        zeile = {"bank": bank, "pdf": pdf.name,
                 "log_status": "OK" if log_ok else log_detail,
                 "pdf_status": "OK" if pdf_ok else pdf_detail,
                 "aktion": "", "in_matrix": "Ja" if normalisiere(pdf.name) in gefragt else "nein",
                 "ziel": "", "detail": ""}

        if not (log_ok and pdf_ok):
            zeile["aktion"] = "UEBERSPRUNGEN"
            zeile["detail"] = "Report nicht sauber, bitte in Marvin neu erzeugen"
            fehlerhaft += 1
            ergebnis.append(zeile)
            continue

        if bank not in cache:
            cache[bank] = finde_bankordner(monatsordner, bank, schwelle)
        ziel_ordner = cache[bank]

        if ziel_ordner is None:
            zeile["aktion"] = "KEIN_ZIELORDNER"
            zeile["detail"] = f"kein Ordner fuer '{bank}' im Monatsordner"
            fehlerhaft += 1
            ergebnis.append(zeile)
            continue

        ziel = ziel_ordner / pdf.name
        zeile["ziel"] = str(ziel)

        if ziel.exists() and not args.ueberschreiben:
            zeile["aktion"] = "SCHON_VORHANDEN"
            zeile["detail"] = "unveraendert gelassen, --ueberschreiben zum Ersetzen"
            ueberspringen += 1
            ergebnis.append(zeile)
            continue

        if args.schreiben:
            try:
                shutil.copy2(pdf, ziel)
                zeile["aktion"] = "KOPIERT"
                zeile["detail"] = pdf_detail
                kopiert += 1
            except OSError as fehler:
                zeile["aktion"] = "KOPIERFEHLER"
                zeile["detail"] = str(fehler)
                fehlerhaft += 1
        else:
            zeile["aktion"] = "WUERDE_KOPIEREN"
            zeile["detail"] = pdf_detail
            kopiert += 1
        ergebnis.append(zeile)

    bericht = schreibe_bericht(ergebnis, basis / cfg.get("output_ordner", "output"), monat)

    print("Ergebnis:")
    label = "kopiert" if args.schreiben else "waeren zu kopieren"
    print(f"  {label:<22} {kopiert}")
    print(f"  {'schon vorhanden':<22} {ueberspringen}")
    print(f"  {'problematisch':<22} {fehlerhaft}")
    nicht_gefragt = sum(1 for z in ergebnis if z["in_matrix"] == "nein")
    if nicht_gefragt:
        print(f"  {'nicht in der Matrix':<22} {nicht_gefragt}")
    if not args.schreiben:
        print("\nProbelauf. Zum tatsaechlichen Kopieren --schreiben anhaengen.")
    print(f"\nBericht: {bericht}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
