"""Minimaler xlsx-Leser ohne externe Bibliotheken.

Eine .xlsx ist ein ZIP mit XML darin. Das reicht Python mit Bordmitteln, damit
weder pip noch eine virtuelle Umgebung noetig sind. Es wird nur gelesen, nie
geschrieben, und nur Zellwerte, keine Formatierung.
"""

import re
import zipfile
from xml.etree import ElementTree

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL_DOC = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_REL_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"

ZELL_RE = re.compile(r"([A-Z]+)(\d+)")


def _spalten_index(ref: str) -> int:
    """A1 -> 0, B1 -> 1, AA1 -> 26."""
    treffer = ZELL_RE.match(ref)
    if not treffer:
        return 0
    index = 0
    for zeichen in treffer.group(1):
        index = index * 26 + (ord(zeichen) - ord("A") + 1)
    return index - 1


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    wurzel = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
    texte = []
    for si in wurzel.findall(f"{NS_MAIN}si"):
        # Ein Eintrag kann in mehrere <t> zerfallen, wenn Teile anders formatiert sind.
        texte.append("".join(t.text or "" for t in si.iter(f"{NS_MAIN}t")))
    return texte


def _blattpfad(z: zipfile.ZipFile, blattname: str) -> str:
    workbook = ElementTree.fromstring(z.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))

    ziele = {r.get("Id"): r.get("Target") for r in rels.findall(f"{NS_REL_PKG}Relationship")}
    namen = []
    for blatt in workbook.iter(f"{NS_MAIN}sheet"):
        namen.append(blatt.get("name"))
        if blatt.get("name") == blattname:
            ziel = ziele.get(blatt.get(f"{NS_REL_DOC}id"), "")
            ziel = ziel.lstrip("/")
            return ziel if ziel.startswith("xl/") else f"xl/{ziel}"
    raise ValueError(f"Blatt '{blattname}' nicht gefunden. Vorhanden: {namen}")


def lies_blatt(pfad: str, blattname: str) -> list[list[str]]:
    """Gibt das Blatt als Liste von Zeilen zurueck, jede Zeile eine Liste von Strings."""
    with zipfile.ZipFile(pfad) as z:
        strings = _shared_strings(z)
        wurzel = ElementTree.fromstring(z.read(_blattpfad(z, blattname)))

    zeilen: list[list[str]] = []
    for zeile in wurzel.iter(f"{NS_MAIN}row"):
        werte: list[str] = []
        for zelle in zeile.findall(f"{NS_MAIN}c"):
            index = _spalten_index(zelle.get("r", ""))
            while len(werte) <= index:
                werte.append("")

            typ = zelle.get("t")
            if typ == "inlineStr":
                inhalt = "".join(t.text or "" for t in zelle.iter(f"{NS_MAIN}t"))
            else:
                v = zelle.find(f"{NS_MAIN}v")
                inhalt = v.text if v is not None and v.text is not None else ""
                if typ == "s" and inhalt:
                    inhalt = strings[int(inhalt)]
            werte[index] = inhalt
        zeilen.append(werte)
    return zeilen
