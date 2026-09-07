"""Sucht Dateien im Bankenversand-Ordner. Liest ausschliesslich, schreibt nie."""

import difflib
import fnmatch
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

STATUS_OK = "OK"
STATUS_FEHLT = "FEHLT"
STATUS_MEHRDEUTIG = "MEHRDEUTIG"
STATUS_UNGEFAEHR = "UNGEFAEHR"
STATUS_MANUELL = "MANUELL"
STATUS_KEIN_ORDNER = "KEIN_BANKORDNER"

UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})

# Schreibweisen, die im Haus synonym verwendet werden.
SYNONYME = [
    (r"\bvolksbank\b", "vb"),
    (r"\boesterreichische\b", ""),
    (r"\be gen\b", ""),
    (r"\beg\b", ""),
    (r"\bag\b", ""),
]


def normalisiere(text: str) -> str:
    """Kleinschreibung, Umlaute aufgeloest, Sonderzeichen zu Leerzeichen."""
    text = unicodedata.normalize("NFC", str(text)).lower().translate(UMLAUTE)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    for muster, ersatz in SYNONYME:
        text = re.sub(muster, ersatz, text)
    return re.sub(r"\s+", " ", text).strip()


def aehnlichkeit(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalisiere(a), normalisiere(b)).ratio()


@dataclass
class Treffer:
    status: str
    pfad: Path | None = None
    kandidaten: list = None
    score: float = 0.0
    detail: str = ""


def finde_monatsordner(root: Path, muster: str, werte: dict) -> Path | None:
    relativ = muster
    for platzhalter, wert in werte.items():
        relativ = relativ.replace(platzhalter, wert)
    kandidat = root / Path(relativ.replace("\\", "/"))
    if kandidat.is_dir():
        return kandidat

    # Fallback: Monatsordner unscharf suchen, falls die Benennung abweicht.
    jahr_ordner = root / werte["{JJJJ}"]
    if not jahr_ordner.is_dir():
        return None
    ziel = normalisiere(Path(relativ).name)
    for unter in sorted(p for p in jahr_ordner.iterdir() if p.is_dir()):
        if normalisiere(unter.name) == ziel or werte["{MM}"] in unter.name:
            return unter
    return None


def finde_bankordner(monatsordner: Path, bank: str, schwelle: float) -> Path | None:
    if not monatsordner.is_dir():
        return None
    ordner = [p for p in monatsordner.iterdir() if p.is_dir()]
    ziel = normalisiere(bank)
    for p in ordner:
        if normalisiere(p.name) == ziel:
            return p
    bester, bester_score = None, 0.0
    for p in ordner:
        score = aehnlichkeit(bank, p.name)
        if score > bester_score:
            bester, bester_score = p, score
    return bester if bester_score >= schwelle else None


def _dateien(ordner: Path) -> list[Path]:
    try:
        return [p for p in ordner.iterdir() if p.is_file() and not p.name.startswith("~$")]
    except OSError:
        return []


def suche_datei(muster: str, ordner: list[Path], schwelle: float) -> Treffer:
    """Sucht ordnerweise nach Prioritaet: erst Bankordner, dann Monatsordner.

    Der erste Ordner mit einem brauchbaren Treffer gewinnt. Dadurch gilt eine
    Datei, die absichtlich an zwei Stellen liegt (z. B. die Management Summary),
    nicht als mehrdeutig.
    """
    vorhanden = [o for o in ordner if o and o.is_dir()]
    if not vorhanden:
        return Treffer(STATUS_FEHLT, detail="Ordner nicht erreichbar")

    bester_fehltreffer = Treffer(STATUS_FEHLT, detail="nichts Passendes gefunden")

    for o in vorhanden:
        treffer = _suche_in_ordner(muster, _dateien(o), schwelle)
        if treffer.status != STATUS_FEHLT:
            return treffer
        if treffer.score > bester_fehltreffer.score:
            bester_fehltreffer = treffer

    return bester_fehltreffer


def _suche_in_ordner(muster: str, alle: list[Path], schwelle: float) -> Treffer:
    if not alle:
        return Treffer(STATUS_FEHLT, detail="Ordner leer")

    ziel = normalisiere(muster)

    exakt = [p for p in alle if normalisiere(p.name) == ziel]
    if len(exakt) == 1:
        return Treffer(STATUS_OK, pfad=exakt[0], score=1.0)
    if len(exakt) > 1:
        return Treffer(STATUS_MEHRDEUTIG, kandidaten=exakt,
                       detail="mehrere gleichnamige Dateien im selben Ordner")

    if "*" in muster or "?" in muster:
        wild = [p for p in alle if fnmatch.fnmatch(normalisiere(p.name), ziel)]
        if len(wild) == 1:
            return Treffer(STATUS_OK, pfad=wild[0], score=1.0)
        if len(wild) > 1:
            return Treffer(STATUS_MEHRDEUTIG, kandidaten=wild, detail="mehrere Wildcard-Treffer")

    bewertet = sorted(((aehnlichkeit(muster, p.name), p) for p in alle), reverse=True,
                      key=lambda t: t[0])
    score, pfad = bewertet[0]
    if score >= schwelle:
        gleichauf = [p for s, p in bewertet if s >= schwelle]
        if len(gleichauf) > 1 and abs(bewertet[0][0] - bewertet[1][0]) < 0.02:
            return Treffer(STATUS_MEHRDEUTIG, kandidaten=gleichauf[:5], score=score,
                           detail="mehrere aehnliche Treffer")
        return Treffer(STATUS_UNGEFAEHR, pfad=pfad, score=score,
                       detail="Name weicht ab, bitte pruefen")

    return Treffer(STATUS_FEHLT, score=score,
                   detail=f"bester Kandidat: {pfad.name} ({score:.0%})")
