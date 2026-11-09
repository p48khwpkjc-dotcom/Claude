#!/usr/bin/env python3
"""Schreibt die Tabellen, aus denen die Berichtsseite ihre Zahlen zieht.

Jede Zahl auf der Seite stammt aus einer dieser Dateien, und diese stammen
ausschliesslich aus results/ -- nichts wird hier neu gerechnet ausser
Umformungen (Prozent statt Anteil, Wochenwerte statt Tageswerte, Drawdown
aus der Equity-Kurve).

    python research/export_report.py  -> results/bericht/*.csv
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HIER = Path(__file__).resolve().parent
ERG = HIER / "results"
ZIEL = ERG / "bericht"

NAMEN = {
    "tech": "Ehrlich",
    "verzerrt": "Verzerrt",
    "ndx": "Ehrlich, ganzer Index",
    "tech_teuer": "Ehrlich, 5-fache Kosten",
    "tech_monatsende": "Ehrlich, Monatsende",
    "tech_ohne_zins": "Ehrlich, Cash ohne Zins",
    "qqq": "QQQ halten",
    "qqq_gleiches_risiko": "QQQ, gleiches Risiko",
    "qqq_regeln": "QQQ, gleiche Regeln",
    "gleichgewichtet": "Tech gleichgewichtet",
}
KURVEN = ["tech", "verzerrt", "qqq", "qqq_gleiches_risiko"]


def pct(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(100 * x, 1)


def main() -> int:
    ZIEL.mkdir(parents=True, exist_ok=True)
    e = json.loads((ERG / "ergebnisse.json").read_text())
    V = e["varianten"]

    # 1. Kennzahlen je Variante
    zeilen = []
    for key, name in NAMEN.items():
        g, b = V[key]["gesamt"], V[key].get("betrieb") or {}
        a, z = V[key]["2019–2022"], V[key]["2023–heute"]
        zeilen.append({
            "variante": key, "name": name,
            "cagr": pct(g["cagr"]), "vol": pct(g["volatility"]),
            "sharpe": round(g["sharpe_rf"], 2), "max_dd": pct(g["max_drawdown"]),
            "exposure": pct(b.get("avg_exposure")),
            "cagr_19_22": pct(a["cagr"]), "sharpe_19_22": round(a["sharpe_rf"], 2),
            "cagr_23_26": pct(z["cagr"]), "sharpe_23_26": round(z["sharpe_rf"], 2),
        })
    pd.DataFrame(zeilen).to_csv(ZIEL / "kennzahlen.csv", index=False)

    # 2. Kurven, woechentlich (Freitagsschluss), mit Drawdown
    q = pd.read_csv(ERG / "equity.csv", index_col=0, parse_dates=True)[KURVEN].dropna()
    w = q.resample("W-FRI").last().dropna()
    w = w / w.iloc[0] * 100  # Index: Start = 100
    out = pd.DataFrame({"datum": w.index.strftime("%Y-%m-%d")})
    for k in KURVEN:
        out[k] = w[k].round(2).to_numpy()
        out[f"dd_{k}"] = (100 * (w[k] / w[k].cummax() - 1)).round(1).to_numpy()
    out.to_csv(ZIEL / "kurven.csv", index=False)

    # 3. Jahresrenditen
    jahre = sorted(V["tech"]["jahre"])
    pd.DataFrame([
        {"jahr": int(j), **{k: pct(V[k]["jahre"][j]) for k in ("tech", "verzerrt", "qqq", "qqq_gleiches_risiko", "qqq_regeln")}}
        for j in jahre
    ]).to_csv(ZIEL / "jahre.csv", index=False)

    # 4. Robustheit gegen die Datenluecke
    r = e["robustheit_datenluecke"]
    pd.DataFrame([
        {"ziehung": i + 1, "entfernt": z["entfernt"], "cagr": pct(z["cagr"]), "sharpe": round(z["sharpe_rf"], 2)}
        for i, z in enumerate(r["einzeln"])
    ]).to_csv(ZIEL / "robustheit.csv", index=False)

    # 5. Fehlende Titel
    m = pd.read_csv(HIER / "data" / "universe" / "membership.csv", dtype=str)
    m = m[m.month >= "2019-01"]
    sektor = m.drop_duplicates("symbol").set_index("symbol")["sector"]
    tech = m[m.tech.str.lower() == "true"].groupby("symbol").size()
    fehl = e["abdeckung"]["fehlende_symbole"]
    pd.DataFrame([
        {"symbol": s, "monate": n, "tech_monate": int(tech.get(s, 0)), "sektor": sektor.get(s, "")}
        for s, n in sorted(fehl.items(), key=lambda x: -x[1])
    ]).to_csv(ZIEL / "luecken.csv", index=False)

    # 6. Paarvergleiche mit t-Wert der Mehrrendite
    tage = pd.read_csv(ERG / "equity.csv", index_col=0, parse_dates=True)
    ret = tage.pct_change().dropna()
    paare = [("tech", "qqq_gleiches_risiko"), ("tech", "qqq"), ("verzerrt", "tech"), ("tech", "qqq_regeln")]
    vgl = []
    for a, b in paare:
        akt = ret[a] - ret[b]
        jahre_n = len(akt) / 252
        mittel, te = akt.mean() * 252, akt.std() * np.sqrt(252)
        vgl.append({"paar": f"{a}|{b}", "a": NAMEN[a], "b": NAMEN[b],
                    "mehrrendite": pct(mittel), "tracking_error": pct(te),
                    "t": round(mittel / te * np.sqrt(jahre_n), 2)})
    pd.DataFrame(vgl).to_csv(ZIEL / "vergleiche.csv", index=False)

    # 7. Datenbasis in Zahlen
    ab = e["abdeckung"]
    val = (HIER / "data" / "universe" / "validation.txt").read_text().splitlines()
    zahl = lambda prefix: int(next(l for l in val if l.strip().startswith(prefix)).split(":")[1].split()[0])
    pd.DataFrame([
        # Monate, deren Indexstand der Backtest tatsaechlich verwendet (ab 2019).
        {"kennzahl": "monate", "wert": int(m.month.nunique())},
        {"kennzahl": "symbole", "wert": int(m.symbol.nunique())},
        {"kennzahl": "ereignisse", "wert": zahl("Gepruefte Ereignisse")},
        {"kennzahl": "uebereinstimmend", "wert": zahl("uebereinstimmend")},
        {"kennzahl": "verzug", "wert": zahl("1 Monat Redaktionsverzug")},
        {"kennzahl": "tech_mm", "wert": ab["tech_mitglieder_monate"]},
        {"kennzahl": "tech_ohne_kurs", "wert": ab["tech_ohne_kurs"]},
        {"kennzahl": "tech_luecke_pct", "wert": pct(ab["tech_anteil_ohne_kurs"])},
        {"kennzahl": "fehlende_symbole", "wert": len(fehl)},
        {"kennzahl": "ziehungen", "wert": r["ziehungen"]},
    ], dtype=object).to_csv(ZIEL / "datenbasis.csv", index=False)

    for f in sorted(ZIEL.glob("*.csv")):
        print(f"{f.name:<18} {len(pd.read_csv(f)):>4} Zeilen  {f.stat().st_size:>7} Bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
