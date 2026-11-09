#!/usr/bin/env python3
"""Ehrlicher Backtest der Tech-Rotation gegen ihre verzerrte Fassung und Benchmarks.

Alle Varianten laufen auf demselben eingefrorenen Datensatz und durch dieselbe
Engine wie der Live-Betrieb. Die Strategieparameter stammen unveraendert aus
``config.yaml`` -- sie wurden nie an Daten angepasst, und das bleibt so: wer
nach diesem Backtest an Parametern dreht, bis es besser aussieht, hat das
Ergebnis wertlos gemacht.

Varianten
---------
tech            HAUPTFALL. Universum = Nasdaq-100-Mitglieder der Sektoren
                Information Technology und Communication Services, jeweils
                zum Stichtag. Die ehrliche Fassung der Tech-Rotation.
ndx             Universum = gesamter Nasdaq-100 zum Stichtag. Keine einzige
                Klassifikationsentscheidung -- die Probe, ob das Ergebnis am
                Sektorfilter haengt.
verzerrt        Universum = die 36 Titel aus config.yaml, im Sept. 2026 gewaehlt
tech_teuer      wie tech, mit 25 bp Slippage und 5 bp Gebuehr statt 5 + 1
tech_monatsende wie tech, Umschichtung zum Monatsende statt -anfang. Haengt das
                Ergebnis am Termin, war es Timing-Glueck.
qqq             QQQ kaufen und halten
qqq_regeln      QQQ durch dieselben Regeln (Regime, Vol-Ziel, Bremse, Trend) --
                also alles ausser der Einzeltitelauswahl
gleichgewichtet alle Tech-Mitglieder zu gleichen Teilen, monatlich neu gewichtet

    python research/run_backtests.py
"""

from __future__ import annotations

import dataclasses
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "src"))

from techrot.backtest import (  # noqa: E402
    fill_inner_gaps,
    performance_metrics,
    rebalance_dates,
    run_backtest,
)
from techrot.config import Config, load_config  # noqa: E402
from techrot.data import PriceData  # noqa: E402

DATEN = HIER / "data"
ERGEBNIS = HIER / "results"
TEILPERIODEN = {"2019–2022": ("2019-01-01", "2022-12-31"), "2023–heute": ("2023-01-01", None)}


# --------------------------------------------------------------------------
# Laden
# --------------------------------------------------------------------------


def lade_kurse() -> PriceData:
    close = pd.read_csv(DATEN / "prices" / "close.csv.gz", index_col=0, parse_dates=True)
    volume = pd.read_csv(DATEN / "prices" / "volume.csv.gz", index_col=0, parse_dates=True)
    volume = volume.reindex(index=close.index, columns=close.columns)
    # Handelstage: nur Tage, an denen der Benchmark notiert. Einzelne Symbole
    # mit Kursen an Feiertagen (Auslandsnotiz) wuerden sonst Phantomtage einfuegen.
    tage = close["QQQ"].dropna().index
    return PriceData(close=close.loc[tage], volume=volume.loc[tage])


def lade_universum(nur_tech: bool) -> dict[str, list[str]]:
    m = pd.read_csv(DATEN / "universe" / "membership.csv", dtype=str)
    if nur_tech:
        m = m[m["tech"].str.lower() == "true"]
    return {monat: sorted(g["symbol"].dropna().unique()) for monat, g in m.groupby("month")}


def stichtagsfunktion(mitglieder: dict[str, list[str]]):
    def universum(tag: pd.Timestamp) -> list[str]:
        # Schnappschuss vom Ersten des Monats, 00:00 UTC. Ein Signal am ersten
        # Handelstag liegt nie davor. Beim Monatsende-Termin gilt ebenfalls
        # der Stand vom Ersten desselben Monats -- also aelter, nie juenger.
        return mitglieder.get(tag.strftime("%Y-%m"), [])
    return universum


def ersetze(cfg: Config, **pfade: object) -> Config:
    """``ersetze(cfg, **{"execution.slippage_bps": 25})`` -- verschachtelt."""
    for pfad, wert in pfade.items():
        teile = pfad.split(".")
        objekte = [cfg]
        for t in teile[:-1]:
            objekte.append(getattr(objekte[-1], t))
        neu = dataclasses.replace(objekte[-1], **{teile[-1]: wert})
        for obj, t in zip(reversed(objekte[:-1]), reversed(teile[:-1])):
            neu = dataclasses.replace(obj, **{t: neu})
        cfg = neu
    return cfg


# --------------------------------------------------------------------------
# Benchmarks ohne Strategie
# --------------------------------------------------------------------------


def gleichgewichtet(
    prices: PriceData, universum, signaltage: list[pd.Timestamp], start_cash: float
) -> pd.Series:
    """Alle Mitglieder mit Kurs zu gleichen Teilen; Umschichtung am Tag nach dem Signal."""
    close = fill_inner_gaps(prices.close)
    tage = close.index
    handelstage = [tage[tage.get_loc(s) + 1] for s in signaltage if tage.get_loc(s) + 1 < len(tage)]
    wert = start_cash
    teile = []
    for i, start in enumerate(handelstage):
        ende = handelstage[i + 1] if i + 1 < len(handelstage) else tage[-1]
        signal = signaltage[i]
        mitglieder = [s for s in universum(signal) if s in close.columns and pd.notna(close.at[signal, s])]
        fenster = close.loc[start:ende, mitglieder]
        # Endet eine Reihe im Monat, bleibt der Erloes als Cash stehen.
        fenster = fenster.ffill()
        basis = fenster.iloc[0]
        gueltig = basis.notna() & (basis > 0)
        relativ = fenster.loc[:, gueltig].div(basis[gueltig])
        pfad = relativ.mean(axis=1) * wert
        teile.append(pfad if i == 0 else pfad.iloc[1:])
        wert = float(pfad.iloc[-1])
    return pd.concat(teile)


# --------------------------------------------------------------------------
# Kennzahlen
# --------------------------------------------------------------------------


def jahresrenditen(equity: pd.Series) -> dict[str, float]:
    jahresende = equity.groupby(equity.index.year).last()
    vorher = pd.concat([pd.Series([equity.iloc[0]], index=[jahresende.index[0] - 1]), jahresende])
    r = jahresende / vorher.shift(1).loc[jahresende.index] - 1
    return {str(j): float(v) for j, v in r.items()}


def kennzahlen(equity: pd.Series) -> dict[str, object]:
    out: dict[str, object] = {"gesamt": performance_metrics(equity)}
    for name, (von, bis) in TEILPERIODEN.items():
        teil = equity.loc[von:bis] if bis else equity.loc[von:]
        out[name] = performance_metrics(teil) if len(teil) > 20 else {}
    out["jahre"] = jahresrenditen(equity)
    return out


def sauber(obj):
    """NaN/Inf zu None, numpy zu Python -- fuer gueltiges JSON."""
    if isinstance(obj, dict):
        return {str(k): sauber(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sauber(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj.date())
    return obj


# --------------------------------------------------------------------------
# Hauptlauf
# --------------------------------------------------------------------------


def main() -> int:
    ERGEBNIS.mkdir(parents=True, exist_ok=True)
    basis = load_config(HIER.parent / "config.yaml")
    prices = lade_kurse()
    tech = stichtagsfunktion(lade_universum(nur_tech=True))
    ndx = stichtagsfunktion(lade_universum(nur_tech=False))
    universum = tech  # Hauptfall: der gleichgewichtete Vergleich bezieht sich darauf

    # ---- Datenabdeckung zum Signaltag ------------------------------------
    signaltage = [
        d for d in rebalance_dates(prices.close.index, basis.backtest.rebalance)
        if d >= pd.Timestamp(basis.backtest.start)
    ]
    fehl_monate: Counter[str] = Counter()
    abdeckung = []
    for tag in signaltage:
        # Ueber den ganzen Index, nicht nur Tech: die strengere Zahl.
        alle = ndx(tag)
        mit = [s for s in alle if s in prices.close.columns and pd.notna(prices.close.at[tag, s])]
        for s in set(alle) - set(mit):
            fehl_monate[s] += 1
        abdeckung.append({"signal": tag, "mitglieder": len(alle), "mit_kurs": len(mit)})
    ab = pd.DataFrame(abdeckung)
    gesamt_mm = int(ab["mitglieder"].sum())
    fehl_mm = int((ab["mitglieder"] - ab["mit_kurs"]).sum())
    print(f"Abdeckung: {gesamt_mm - fehl_mm}/{gesamt_mm} Mitglieder-Monate mit Kurs "
          f"({1 - fehl_mm / gesamt_mm:.1%}); {len(fehl_monate)} Symbole betroffen")

    # ---- Varianten -------------------------------------------------------
    varianten = {
        "tech": (basis, tech),
        "ndx": (basis, ndx),
        "verzerrt": (basis, None),
        "tech_teuer": (
            ersetze(basis, **{"execution.slippage_bps": 25.0, "execution.commission_bps": 5.0}),
            tech,
        ),
        "tech_monatsende": (ersetze(basis, **{"backtest.rebalance": "month_end"}), tech),
        "qqq_regeln": (
            ersetze(
                basis,
                **{
                    "selection": dataclasses.replace(basis.selection, top_n=1, buffer_rank=1),
                    "risk.portfolio.max_position_weight": 1.0,
                    "risk.portfolio.min_names": 1,
                },
            ),
            lambda tag: ["QQQ"],
        ),
    }

    kurven: dict[str, pd.Series] = {}
    ergebnisse: dict[str, object] = {}
    details: dict[str, object] = {}
    for name, (cfg, uni) in varianten.items():
        print(f"\n== {name} ==")
        res = run_backtest(cfg, prices, universe_at=uni)
        kurven[name] = res.equity
        ergebnisse[name] = kennzahlen(res.equity)
        ergebnisse[name]["betrieb"] = {
            k: res.metrics.get(k)
            for k in ("avg_exposure", "avg_turnover", "total_costs", "n_trades", "n_rebalances", "n_delistings")
        }
        reb = res.rebalances
        if not reb.empty:
            ergebnisse[name]["betrieb"]["anteil_regime_aus"] = float((~reb["regime_ok"].astype(bool)).mean())
            ergebnisse[name]["betrieb"]["mittel_titel"] = float(reb["n_selected"].mean())
            ergebnisse[name]["betrieb"]["mittel_zugelassen"] = float(reb["n_eligible"].mean())
        g = ergebnisse[name]["gesamt"]
        print(f"   CAGR {g['cagr']:+.1%}  Vol {g['volatility']:.1%}  Sharpe {g['sharpe']:.2f}  "
              f"MaxDD {g['max_drawdown']:.1%}")
        details[name] = res
        if name == "tech":
            kurven["qqq"] = res.benchmark
            ergebnisse["qqq"] = kennzahlen(res.benchmark)

    kurven["gleichgewichtet"] = gleichgewichtet(
        prices, universum, signaltage, basis.execution.starting_cash
    )
    ergebnisse["gleichgewichtet"] = kennzahlen(kurven["gleichgewichtet"])

    # ---- Was hat die ehrliche Variante eigentlich gekauft? ----------------
    eh = details["tech"].rebalances
    auswahl = Counter(t for s in eh["selected"].dropna() for t in s.split(",") if t)
    nicht_in_live = {t: n for t, n in auswahl.items() if t not in basis.tickers}

    # ---- Schreiben ------------------------------------------------------
    gemeinsam = pd.DataFrame(kurven).dropna(how="all")
    gemeinsam.to_csv(ERGEBNIS / "equity.csv", float_format="%.2f")
    eh.to_csv(ERGEBNIS / "rebalances_tech.csv", index=False)
    details["tech"].trades.to_csv(ERGEBNIS / "trades_tech.csv", index=False)
    details["tech"].delistings.to_csv(ERGEBNIS / "delistings_tech.csv", index=False)
    details["ndx"].rebalances.to_csv(ERGEBNIS / "rebalances_ndx.csv", index=False)
    details["verzerrt"].rebalances.to_csv(ERGEBNIS / "rebalances_verzerrt.csv", index=False)

    quellen = json.loads((DATEN / "prices" / "coverage.json").read_text())
    snap_index = json.loads((HIER / "sources" / "nasdaq100" / "index.json").read_text())
    bericht = {
        "erstellt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "zeitraum": {"von": str(gemeinsam.index[0].date()), "bis": str(gemeinsam.index[-1].date())},
        "parameter": {
            "top_n": basis.selection.top_n,
            "buffer_rank": basis.selection.buffer_rank,
            "vol_target": basis.risk.portfolio.vol_target,
            "regime_sma": basis.risk.portfolio.regime_sma,
            "max_drawdown_brake": basis.risk.portfolio.max_drawdown_brake,
            "slippage_bps": basis.execution.slippage_bps,
            "commission_bps": basis.execution.commission_bps,
            "signal_weights": basis.ranking.normalized_weights(),
        },
        "varianten": ergebnisse,
        "abdeckung": {
            "mitglieder_monate": gesamt_mm,
            "ohne_kurs": fehl_mm,
            "anteil_ohne_kurs": fehl_mm / gesamt_mm if gesamt_mm else None,
            "fehlende_symbole": dict(fehl_monate.most_common()),
            "mittel_mitglieder": float(ab["mitglieder"].mean()),
            "kursquellen": dict(Counter(v.get("quelle") or "fehlt" for v in quellen.values())),
        },
        "quelle_universum": {
            "artikel": "en.wikipedia.org/wiki/Nasdaq-100",
            "schnappschuesse": len(snap_index),
            "revisionen": {k: v.get("revid") for k, v in sorted(snap_index.items())},
        },
        "auswahl_tech": dict(auswahl.most_common()),
        "auswahl_tech_nicht_in_live_liste": dict(sorted(nicht_in_live.items(), key=lambda x: -x[1])),
        "delistings_tech": details["tech"].delistings.to_dict(orient="records"),
    }
    (ERGEBNIS / "ergebnisse.json").write_text(
        json.dumps(sauber(bericht), indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nGeschrieben nach {ERGEBNIS}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
