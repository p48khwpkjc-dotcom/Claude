#!/usr/bin/env python3
"""Baut aus den Wikipedia-Schnappschuessen das Point-in-time-Universum.

Eingang:  research/sources/nasdaq100/  (vom Runner geholt, je Monat ein Stand)
Ausgang:  research/data/universe/membership.csv
          Spalten: month, listed, symbol
          ``listed`` ist der Ticker so, wie er damals im Artikel stand;
          ``symbol`` ist das Symbol, unter dem es heute Kurse gibt (FB -> META).

Jede Umbenennung steht in ``aliases.csv`` und ist damit pruefbar. Geraten
wird nichts: ein Ticker ohne Eintrag bleibt, wie er ist, und faellt
spaetestens beim Kursabruf als fehlend auf.

    python research/build_universe.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

HIER = Path(__file__).resolve().parent
QUELLE = HIER / "sources" / "nasdaq100"
ZIEL = HIER / "data" / "universe"
TICKER_SPALTE = re.compile(r"^(ticker|symbol|ticker symbol)\b", re.I)
GUELTIG = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def tickerspalte(t: pd.DataFrame) -> str | None:
    for c in t.columns:
        if TICKER_SPALTE.search(str(c).strip()):
            return c
    return None


def bereinigen(roh: str) -> str | None:
    s = str(roh).strip().upper()
    s = re.sub(r"\[.*?\]", "", s)          # Fussnoten [1]
    s = s.split(":")[-1].strip()           # "NASDAQ: AAPL"
    s = s.replace(" ", " ").split()[0] if s else s
    return s if s and GUELTIG.match(s) else None


def lade_aliase() -> dict[str, str]:
    pfad = ZIEL / "aliases.csv"
    if not pfad.exists():
        return {}
    a = pd.read_csv(pfad, dtype=str, comment="#")
    return dict(zip(a["listed"].str.strip(), a["symbol"].str.strip()))


def main() -> int:
    index = json.loads((QUELLE / "index.json").read_text())
    aliase = lade_aliase()
    zeilen = []
    probleme = []

    for monat in sorted(index):
        eintrag = index[monat]
        kandidaten = []
        for tab in eintrag.get("tabellen", []):
            t = pd.read_csv(QUELLE / tab["datei"], dtype=str)
            spalte = tickerspalte(t)
            if spalte is None:
                continue
            ticker = [x for x in (bereinigen(v) for v in t[spalte].dropna()) if x]
            if len(ticker) >= 80:
                kandidaten.append((len(ticker), tab["datei"], ticker))
        if not kandidaten:
            probleme.append(f"{monat}: keine Bestandteiltabelle gefunden")
            continue
        # Bei mehreren passenden Tabellen die naechste an 100 Eintraegen.
        kandidaten.sort(key=lambda k: abs(k[0] - 101))
        _, datei, ticker = kandidaten[0]
        for t in dict.fromkeys(ticker):
            zeilen.append({"month": monat, "listed": t, "symbol": aliase.get(t, t)})

    if not zeilen:
        print("Keine Mitglieder extrahiert.", file=sys.stderr)
        return 1

    m = pd.DataFrame(zeilen)
    ZIEL.mkdir(parents=True, exist_ok=True)
    m.to_csv(ZIEL / "membership.csv", index=False)

    # ---- Pruefung --------------------------------------------------------
    anzahl = m.groupby("month").size()
    print(f"{anzahl.index[0]} bis {anzahl.index[-1]}: {len(anzahl)} Monate, "
          f"{m['symbol'].nunique()} verschiedene Symbole")
    print(f"Mitglieder je Monat: min {anzahl.min()}, max {anzahl.max()}, Median {anzahl.median():.0f}")
    auffaellig = anzahl[(anzahl < 98) | (anzahl > 106)]
    if len(auffaellig):
        print("Auffaellige Monate (erwartet 100-104):")
        for mon, n in auffaellig.items():
            print(f"  {mon}: {n}")

    vorher = None
    print("\nWechsel von Monat zu Monat:")
    for mon, g in m.groupby("month"):
        jetzt = set(g["symbol"])
        if vorher is not None and jetzt != vorher:
            rein, raus = sorted(jetzt - vorher), sorted(vorher - jetzt)
            print(f"  {mon}: +{len(rein)} {' '.join(rein)} | -{len(raus)} {' '.join(raus)}")
        vorher = jetzt
    for p in probleme:
        print("PROBLEM:", p, file=sys.stderr)
    return 1 if probleme else 0


if __name__ == "__main__":
    raise SystemExit(main())
