"""Liest die Versandmatrix und loest die Platzhalter fuer einen Berichtsmonat auf.

Kommt ohne externe Bibliotheken aus. Neben .xlsx wird auch .csv gelesen, falls
die Matrix lieber als CSV gepflegt wird.
"""

import calendar
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from xlsx_reader import lies_blatt

MONATSNAMEN = {
    1: "Jänner", 2: "Februar", 3: "März", 4: "April", 5: "Mai", 6: "Juni",
    7: "Juli", 8: "August", 9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}

PLATZHALTER_RE = re.compile(r"\{[A-Z_]+\}")


@dataclass
class Berichtsmonat:
    """Alle aus Monat und Jahr abgeleiteten Werte an einer Stelle."""

    monat: int
    jahr: int

    @property
    def werte(self) -> dict:
        letzter_tag = calendar.monthrange(self.jahr, self.monat)[1]
        return {
            "{MM}": f"{self.monat:02d}",
            "{JJJJ}": str(self.jahr),
            "{MONAT}": MONATSNAMEN[self.monat],
            "{STICHTAG}": f"{self.jahr}{self.monat:02d}{letzter_tag:02d}",
        }

    def aufloesen(self, text: str) -> str:
        for platzhalter, wert in self.werte.items():
            text = text.replace(platzhalter, wert)
        return text

    def __str__(self) -> str:
        return f"{MONATSNAMEN[self.monat]} {self.jahr} ({self.monat:02d}-{self.jahr})"


@dataclass
class MatrixZeile:
    zeile_nr: int
    mail_id: str
    bank: str
    bank_key: str
    empfaengergruppe: str
    dateityp: str
    muster_roh: str
    muster: str = ""
    pflicht: bool = True
    quelle: str = ""
    hinweis: str = ""
    offene_platzhalter: list = field(default_factory=list)

    @property
    def ist_anhang(self) -> bool:
        """Zeilen ohne echte Datei, z. B. der Download-Link fuer Wien NH."""
        return not self.muster_roh.strip().startswith("--")


def _rohzeilen(pfad: str, blatt: str) -> list[list[str]]:
    if Path(pfad).suffix.lower() == ".csv":
        with open(pfad, encoding="utf-8-sig", newline="") as f:
            probe = f.read(4096)
            f.seek(0)
            try:
                dialekt = csv.Sniffer().sniff(probe, delimiters=";,\t")
            except csv.Error:
                dialekt = csv.excel
                dialekt.delimiter = ";"
            return [list(z) for z in csv.reader(f, dialekt)]
    return lies_blatt(pfad, blatt)


def _feld(zeile: list[str], index: int) -> str:
    return zeile[index].strip() if index < len(zeile) and zeile[index] else ""


def lade_matrix(pfad: str, blatt: str, monat: Berichtsmonat) -> list[MatrixZeile]:
    roh = _rohzeilen(pfad, blatt)
    if not roh:
        raise ValueError(f"Keine Zeilen in {pfad} gefunden.")

    zeilen: list[MatrixZeile] = []
    for nr, werte in enumerate(roh[1:], start=2):  # Zeile 1 ist die Kopfzeile
        if not _feld(werte, 0):
            continue
        muster_roh = _feld(werte, 5)
        aufgeloest = monat.aufloesen(muster_roh)
        zeilen.append(
            MatrixZeile(
                zeile_nr=nr,
                mail_id=_feld(werte, 0),
                bank=_feld(werte, 1),
                bank_key=_feld(werte, 2),
                empfaengergruppe=_feld(werte, 3),
                dateityp=_feld(werte, 4),
                muster_roh=muster_roh,
                muster=aufgeloest,
                pflicht=_feld(werte, 6).lower() in ("ja", "j", "x", "true"),
                quelle=_feld(werte, 7),
                hinweis=_feld(werte, 8),
                offene_platzhalter=PLATZHALTER_RE.findall(aufgeloest),
            )
        )
    return zeilen
