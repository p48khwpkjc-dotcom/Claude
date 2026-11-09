#!/usr/bin/env python3
"""Prueft das rekonstruierte Universum gegen die Aenderungstabelle.

Die Monatsstaende und die Aenderungstabelle des Listenartikels sind zwei
unabhaengige Aufzeichnungen derselben Ereignisse. Fuer jede Aufnahme und
Entfernung ab 2019 wird geprueft, ob der erste Monatsstand danach sie zeigt.

Eine Abweichung, die einen Monat spaeter richtig steht, ist Redaktionsverzug
im Artikel: der Indexwechsel kommt im Backtest dann einen Monat spaeter an.
Das kostet Genauigkeit beim Zeitpunkt, bringt aber kein Zukunftswissen ein.

    python research/validate_universe.py   -> data/universe/validation.txt
"""

from __future__ import annotations

import glob
from pathlib import Path

import pandas as pd

HIER = Path(__file__).resolve().parent
UNI = HIER / "data" / "universe"


def main() -> int:
    kandidaten = [f for f in sorted(glob.glob(str(HIER / "sources/nasdaq100_liste/*_t*.csv")))
                  if len(pd.read_csv(f)) > 150 and "Reason" in "".join(pd.read_csv(f, nrows=0).columns)]
    if not kandidaten:
        print("Keine Aenderungstabelle gefunden.")
        return 1
    ch = pd.read_csv(kandidaten[-1], dtype=str)
    ch.columns = ["datum", "add_t", "add_s", "rem_t", "rem_s", "grund"][: len(ch.columns)]
    ch["datum"] = pd.to_datetime(ch["datum"], errors="coerce")
    ch = ch.dropna(subset=["datum"])

    aliase = dict(pd.read_csv(UNI / "aliases.csv", comment="#", dtype=str)[["listed", "symbol"]].values)

    def norm(t):
        t = str(t).strip() if pd.notna(t) else ""
        return aliase.get(t, t) if t and t not in ("nan", "—", "–") else None

    m = pd.read_csv(UNI / "membership.csv", dtype=str)
    mitglied = {mon: set(g.symbol) for mon, g in m.groupby("month")}
    monate = sorted(mitglied)

    zeilen, ok, verzug, abw = [], 0, 0, 0
    for _, r in ch[(ch.datum >= "2019-01-01")].sort_values("datum").iterrows():
        mon = (r.datum + pd.offsets.MonthBegin(1)).strftime("%Y-%m")
        if mon not in mitglied:
            continue
        for art, t in (("rein", norm(r.add_t)), ("raus", norm(r.rem_t))):
            if not t:
                continue
            soll = art == "rein"
            if (t in mitglied[mon]) == soll:
                ok += 1
                continue
            i = monate.index(mon)
            spaeter = monate[i + 1] if i + 1 < len(monate) else None
            if spaeter and (t in mitglied[spaeter]) == soll:
                verzug += 1
                urteil = "1 Monat Redaktionsverzug"
            else:
                abw += 1
                urteil = "ABWEICHUNG"
            zeilen.append(f"{r.datum.date()}  {art:<4} {t:<6} erwartet ab {mon}: {urteil}  ({r.grund})")

    n = ok + verzug + abw
    kopf = [
        f"Quelle: {Path(kandidaten[-1]).name}",
        f"Gepruefte Ereignisse ab 2019: {n}",
        f"  uebereinstimmend:          {ok} ({ok / n:.1%})",
        f"  1 Monat Redaktionsverzug:  {verzug}",
        f"  echte Abweichung:          {abw}",
        "",
    ]
    text = "\n".join(kopf + zeilen) + "\n"
    (UNI / "validation.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
