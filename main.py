"""Bankenversand-Assistent, Stufe 1: Vollstaendigkeitspruefung.

Liest die Versandmatrix, sucht die Dateien im Bankenversand-Ordner und schreibt
einen Kontrollbericht. Es wird ausschliesslich gelesen, nie geschrieben oder
kopiert und nichts versendet.

Aufruf:
    python src/main.py --monat 07 --jahr 2026
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import finder
from finder import (STATUS_KEIN_ORDNER, STATUS_MANUELL, finde_bankordner,
                    finde_monatsordner, suche_datei)
from matrix import Berichtsmonat, lade_matrix
from report import schreibe_csv, zusammenfassung


def lade_config(pfad: Path) -> dict:
    with pfad.open(encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    p = argparse.ArgumentParser(description="Bankenversand-Assistent Stufe 1")
    p.add_argument("--monat", type=int, required=True, help="Berichtsmonat, z. B. 7")
    p.add_argument("--jahr", type=int, required=True, help="Berichtsjahr, z. B. 2026")
    p.add_argument("--config", default="config.json")
    p.add_argument("--root", help="Ueberschreibt bankenversand_root, gut zum Testen")
    args = p.parse_args()

    if not 1 <= args.monat <= 12:
        print("Monat muss zwischen 1 und 12 liegen.")
        return 2

    basis = Path(args.config).resolve().parent
    cfg = lade_config(Path(args.config))
    monat = Berichtsmonat(args.monat, args.jahr)
    schwelle = float(cfg.get("match_schwelle", 0.85))
    root = Path(args.root or cfg["bankenversand_root"])

    print(f"\nBankenversand-Assistent, Stufe 1 (nur lesen)")
    print(f"Berichtsmonat : {monat}")
    print(f"Wurzelordner  : {root}")

    if not root.is_dir():
        print("\nWurzelordner nicht erreichbar. Ist das K-Laufwerk verbunden?")
        return 1

    matrix_pfad = basis / cfg["versandmatrix"]
    if not matrix_pfad.is_file():
        print(f"\nVersandmatrix nicht gefunden: {matrix_pfad}")
        return 1

    zeilen = lade_matrix(str(matrix_pfad), cfg["matrix_blatt"], monat)
    print(f"Matrixzeilen  : {len(zeilen)}")

    monatsordner = finde_monatsordner(root, cfg["monatsordner_muster"], monat.werte)
    if monatsordner is None:
        print(f"\nKein Monatsordner fuer {monat} gefunden.")
        return 1
    print(f"Monatsordner  : {monatsordner}\n")

    bankordner_cache: dict[str, Path | None] = {}
    ergebnis = []

    for z in zeilen:
        if not z.ist_anhang:
            ergebnis.append(_zeile(z, STATUS_MANUELL, detail="kein Anhang, Link versenden"))
            continue
        if z.offene_platzhalter:
            offen = ", ".join(z.offene_platzhalter)
            ergebnis.append(_zeile(z, STATUS_MANUELL,
                                   detail=f"Platzhalter nicht aufloesbar: {offen}"))
            continue

        if z.bank not in bankordner_cache:
            bankordner_cache[z.bank] = finde_bankordner(monatsordner, z.bank, schwelle)
        bankordner = bankordner_cache[z.bank]

        if bankordner is None:
            ergebnis.append(_zeile(z, STATUS_KEIN_ORDNER,
                                   detail=f"kein Ordner fuer '{z.bank}' im Monatsordner"))
            continue

        # Zentrale Dateien wie die Management Summary liegen auch im Monatsordner.
        treffer = suche_datei(z.muster, [bankordner, monatsordner], schwelle)
        ergebnis.append(_zeile(z, treffer.status, treffer))

    bericht = schreibe_csv(ergebnis, basis / cfg.get("output_ordner", "output"), monat)
    print(zusammenfassung(ergebnis))
    print(f"\nKontrollbericht: {bericht}\n")
    return 0


def _zeile(z, status, treffer=None, detail="") -> dict:
    kandidaten = ""
    if treffer is not None and getattr(treffer, "kandidaten", None):
        kandidaten = " | ".join(p.name for p in treffer.kandidaten)
    return {
        "mail_id": z.mail_id,
        "bank": z.bank,
        "dateityp": z.dateityp,
        "erwartete_datei": z.muster,
        "status": status,
        "gefundene_datei": (treffer.pfad.name if treffer and treffer.pfad else kandidaten),
        "score": f"{treffer.score:.2f}" if treffer and treffer.score else "",
        "quelle": z.quelle,
        "detail": detail or (treffer.detail if treffer else ""),
        "matrix_zeile": z.zeile_nr,
    }


if __name__ == "__main__":
    sys.exit(main())
