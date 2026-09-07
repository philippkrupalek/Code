"""Schreibt den Kontrollbericht als CSV und fasst ihn fuer die Konsole zusammen."""

import csv
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from finder import STATUS_FEHLT, STATUS_MEHRDEUTIG, STATUS_OK, STATUS_UNGEFAEHR

SPALTEN = [
    "mail_id", "bank", "dateityp", "erwartete_datei", "status",
    "gefundene_datei", "score", "quelle", "detail", "matrix_zeile",
]


def schreibe_csv(zeilen: list[dict], ordner: Path, monat) -> Path:
    ordner.mkdir(parents=True, exist_ok=True)
    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    ziel = ordner / f"kontrollbericht_{monat.jahr}-{monat.monat:02d}_{stempel}.csv"
    # utf-8-sig, damit Excel die Umlaute richtig anzeigt.
    with ziel.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SPALTEN, delimiter=";")
        writer.writeheader()
        writer.writerows(zeilen)
    return ziel


def zusammenfassung(zeilen: list[dict]) -> str:
    zaehler = Counter(z["status"] for z in zeilen)
    pro_mail = defaultdict(list)
    for z in zeilen:
        pro_mail[z["mail_id"]].append(z["status"])

    aus = ["", "Ergebnis pro Mailpaket:", ""]
    for mail_id, stati in pro_mail.items():
        ok = sum(1 for s in stati if s == STATUS_OK)
        gesamt = len(stati)
        problem = [s for s in stati if s not in (STATUS_OK, "MANUELL")]
        marker = "OK        " if not problem else "PRUEFEN   "
        aus.append(f"  {marker} {mail_id:<18} {ok}/{gesamt} gefunden")

    aus += ["", "Gesamt:"]
    for status in (STATUS_OK, STATUS_UNGEFAEHR, STATUS_MEHRDEUTIG, STATUS_FEHLT):
        if zaehler.get(status):
            aus.append(f"  {status:<14} {zaehler[status]}")
    for status, anzahl in zaehler.items():
        if status not in (STATUS_OK, STATUS_UNGEFAEHR, STATUS_MEHRDEUTIG, STATUS_FEHLT):
            aus.append(f"  {status:<14} {anzahl}")
    return "\n".join(aus)
