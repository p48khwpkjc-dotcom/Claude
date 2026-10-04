#!/usr/bin/env python3
"""Baut die interaktive Ansicht aus dem JSON-Export eines Laufs.

    python scripts/build_view.py [--daten data/ranking.json] [--ziel web/querschnitt.html]

Die Vorlage ``web/querschnitt.template.html`` enthaelt die Platzhaltermarke
``/*__DATEN__*/`` in einem ``<script type="application/json">``. Hier wird sie
durch den Lauf ersetzt. Damit haengt die Seite an keinem Netzaufruf: sie
rendert vollstaendig aus sich selbst, auch offline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
MARKE = "/*__DATEN__*/"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--daten", default=str(WURZEL / "data" / "ranking.json"))
    p.add_argument("--vorlage", default=str(WURZEL / "web" / "querschnitt.template.html"))
    p.add_argument("--ziel", default=str(WURZEL / "web" / "querschnitt.html"))
    args = p.parse_args(argv)

    daten_pfad = Path(args.daten)
    if not daten_pfad.exists():
        print(
            f"FEHLER: {daten_pfad} fehlt. Erst einen Lauf machen:\n"
            f"  techrot rebalance --json data/ranking.json",
            file=sys.stderr,
        )
        return 2

    rohdaten = daten_pfad.read_text(encoding="utf-8")
    lauf = json.loads(rohdaten)  # bricht frueh ab, wenn die Datei kaputt ist

    vorlage = Path(args.vorlage).read_text(encoding="utf-8")
    if MARKE not in vorlage:
        print(f"FEHLER: Marke {MARKE} nicht in {args.vorlage} gefunden.", file=sys.stderr)
        return 2

    # Kompakt und ohne den Platzhalterkommentar. `</script>` kann in gueltigem
    # JSON aus diesem Export nicht vorkommen, trotzdem maskiert: ein Ticker mit
    # dieser Zeichenfolge wuerde das Script sonst mitten im Datenblock beenden.
    nutzlast = json.dumps(lauf, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    Path(args.ziel).write_text(vorlage.replace(MARKE, nutzlast), encoding="utf-8")

    print(
        f"{args.ziel} gebaut: {len(lauf['tickers'])} Titel, "
        f"Signalstand {lauf['signal_date']}, "
        f"{sum(1 for t in lauf['tickers'] if t['eligible'])} zugelassen"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
