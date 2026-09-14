"""Bankenversand-Assistent, Stufe 3: Mailpakete schnueren."""

import argparse
import csv
import json
import shutil
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from finder import (STATUS_FEHLT, STATUS_MEHRDEUTIG, finde_bankordner,
                    finde_monatsordner, suche_datei)
from matrix import Berichtsmonat, lade_matrix

STATUS_BEREIT = "vorbereitet"
STATUS_UNVOLLSTAENDIG = "unvollstaendig"

SPALTEN = ["mail_id", "bank", "empfaengergruppe", "status", "anhaenge",
           "fehlend", "manuell", "ordner"]


def betreff(vorlage: str, bank: str, monat) -> str:
    return (vorlage.replace("{BANK}", bank)
                   .replace("{MONAT}", monat.werte["{MONAT}"])
                   .replace("{JJJJ}", monat.werte["{JJJJ}"])
                   .replace("{MM}", monat.werte["{MM}"]))


def main() -> int:
    p = argparse.ArgumentParser(description="Bankenversand-Assistent Stufe 3")
    p.add_argument("--monat", type=int, required=True)
    p.add_argument("--jahr", type=int, required=True)
    p.add_argument("--config", default="config.json")
    p.add_argument("--root")
    p.add_argument("--ziel", help="Ueberschreibt den Ordner fuer die Mailpakete")
    p.add_argument("--schreiben", action="store_true")
    args = p.parse_args()

    basis = Path(args.config).resolve().parent
    with Path(args.config).open(encoding="utf-8") as f:
        cfg = json.load(f)
    monat = Berichtsmonat(args.monat, args.jahr)
    schwelle = float(cfg.get("match_schwelle", 0.85))
    root = Path(args.root or cfg["bankenversand_root"])
    vorlage = cfg.get("betreff_vorlage", "UIA Vertriebscontrolling {MONAT} {JJJJ} - {BANK}")

    modus = "SCHREIBEN" if args.schreiben else "PROBELAUF (nichts wird angelegt)"
    print(f"\nBankenversand-Assistent, Stufe 3 - {modus}")
    print(f"Berichtsmonat : {monat}")

    if not root.is_dir():
        print("\nBankenversand-Wurzel nicht erreichbar.")
        return 1

    monatsordner = finde_monatsordner(root, cfg["monatsordner_muster"], monat.werte)
    if monatsordner is None:
        print(f"\nKein Monatsordner fuer {monat} gefunden.")
        return 1

    zielwurzel = Path(args.ziel) if args.ziel else monatsordner / "03_Mailvorbereitung"
    print(f"Monatsordner  : {monatsordner}")
    print(f"Mailpakete    : {zielwurzel}\n")

    zeilen = lade_matrix(str(basis / cfg["versandmatrix"]), cfg["matrix_blatt"], monat)

    pakete: OrderedDict = OrderedDict()
    for z in zeilen:
        pakete.setdefault(z.mail_id, []).append(z)

    bankordner_cache: dict = {}
    status_zeilen = []
    bereit = unvollstaendig = 0

    for mail_id, eintraege in pakete.items():
        bank = eintraege[0].bank
        verteiler = eintraege[0].empfaengergruppe

        if bank not in bankordner_cache:
            bankordner_cache[bank] = finde_bankordner(monatsordner, bank, schwelle)
        bankordner = bankordner_cache[bank]

        anhaenge, fehlend, manuell = [], [], []

        for z in eintraege:
            if not z.ist_anhang:
                manuell.append({"dateityp": z.dateityp, "hinweis": "kein Anhang, Link versenden"})
                continue
            if z.offene_platzhalter:
                manuell.append({"dateityp": z.dateityp,
                                "hinweis": f"Platzhalter offen: {', '.join(z.offene_platzhalter)}"})
                continue
            if bankordner is None:
                fehlend.append({"dateityp": z.dateityp, "erwartet": z.muster,
                                "grund": "kein Bankordner"})
                continue

            treffer = suche_datei(z.muster, [bankordner, monatsordner], schwelle)
            if treffer.status in (STATUS_FEHLT, STATUS_MEHRDEUTIG) or treffer.pfad is None:
                fehlend.append({"dateityp": z.dateityp, "erwartet": z.muster,
                                "grund": treffer.detail or treffer.status})
                continue
            anhaenge.append({"dateityp": z.dateityp, "datei": treffer.pfad.name,
                             "quelle": str(treffer.pfad)})

        status = STATUS_BEREIT if not fehlend else STATUS_UNVOLLSTAENDIG
        if fehlend:
            unvollstaendig += 1
        else:
            bereit += 1

        paketordner = zielwurzel / mail_id
        metadaten = {
            "mail_id": mail_id,
            "bank": bank,
            "empfaengergruppe": verteiler,
            "berichtsmonat": f"{monat.werte['{MM}']}-{monat.werte['{JJJJ}']}",
            "betreff": betreff(vorlage, bank, monat),
            "status": status,
            "erstellt": datetime.now().isoformat(timespec="seconds"),
            "anhaenge": [a["datei"] for a in anhaenge],
            "fehlend": fehlend,
            "manuell": manuell,
        }

        if args.schreiben:
            paketordner.mkdir(parents=True, exist_ok=True)
            for a in anhaenge:
                ziel = paketordner / a["datei"]
                if not ziel.exists():
                    shutil.copy2(a["quelle"], ziel)
            with (paketordner / "mail_metadata.json").open("w", encoding="utf-8") as f:
                json.dump(metadaten, f, ensure_ascii=False, indent=2)

        marker = "OK      " if status == STATUS_BEREIT else "PRUEFEN "
        print(f"  {marker} {mail_id:<18} {len(anhaenge)} Anhaenge"
              + (f", {len(fehlend)} fehlen" if fehlend else "")
              + (f", {len(manuell)} manuell" if manuell else ""))

        status_zeilen.append({
            "mail_id": mail_id, "bank": bank, "empfaengergruppe": verteiler,
            "status": status, "anhaenge": len(anhaenge), "fehlend": len(fehlend),
            "manuell": len(manuell), "ordner": str(paketordner),
        })

    ausgabe = basis / cfg.get("output_ordner", "output")
    ausgabe.mkdir(parents=True, exist_ok=True)
    statusdatei = ausgabe / f"versandstatus_{monat.jahr}-{monat.monat:02d}.csv"
    with statusdatei.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SPALTEN, delimiter=";")
        writer.writeheader()
        writer.writerows(status_zeilen)

    print(f"\n  {'versandbereit':<18} {bereit}")
    print(f"  {'unvollstaendig':<18} {unvollstaendig}")
    if not args.schreiben:
        print("\nProbelauf. Zum Anlegen der Ordner --schreiben anhaengen.")
    print(f"\nStatusdatei: {statusdatei}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
