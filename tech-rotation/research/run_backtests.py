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
tech_ohne_zins  wie tech, aber Cash bringt nichts -- zeigt, was die Verzinsung
                ausmacht

Cash verdient in allen Strategievarianten die Rendite von BIL (1-3-Monats-
T-Bills). Die Sharpe-Ratio ist die Ueberrendite gegenueber BIL je Einheit
Schwankung.

Robustheit: Fuer 21 uebernommene Titel fuehrt keine freie Quelle mehr Kurse.
Wie stark das Ergebnis davon abhaengt, wird gemessen statt geschaetzt: die
Variante tech laeuft wiederholt mit zufaellig entfernten Titeln, im selben
Umfang wie die echte Luecke.

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
ZIEHUNGEN = 20


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


def mit_rf(m: dict[str, float], equity: pd.Series, rf: pd.Series | None) -> dict[str, float]:
    """Ergaenzt die Sharpe-Ratio der Ueberrendite gegenueber dem Geldmarkt."""
    if rf is None or not m:
        return m
    r = equity.pct_change(fill_method=None).dropna()
    ueber = r - rf.reindex(r.index).fillna(0.0)
    vol = float(r.std(ddof=1))
    m = dict(m)
    m["sharpe_rf"] = float(ueber.mean() / vol * np.sqrt(252)) if vol > 0 else float("nan")
    return m


def kennzahlen(equity: pd.Series, rf: pd.Series | None = None) -> dict[str, object]:
    out: dict[str, object] = {"gesamt": mit_rf(performance_metrics(equity), equity, rf)}
    for name, (von, bis) in TEILPERIODEN.items():
        teil = equity.loc[von:bis] if bis else equity.loc[von:]
        out[name] = mit_rf(performance_metrics(teil), teil, rf) if len(teil) > 20 else {}
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
    # Geldmarktrendite: Tagesrendite des T-Bill-ETFs BIL (inkl. Ausschuettungen).
    rf = prices.close["BIL"].pct_change(fill_method=None).fillna(0.0)

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
    # Dieselbe Zahl nur fuer das Tech-Universum -- das ist die Luecke, die den
    # Hauptfall trifft, und der Massstab fuer das Robustheitsexperiment.
    tech_mm = tech_fehl = 0
    for tag in signaltage:
        alle = tech(tag)
        tech_mm += len(alle)
        tech_fehl += sum(1 for x in alle if x not in prices.close.columns or pd.isna(prices.close.at[tag, x]))
    print(f"   davon Tech: {tech_mm - tech_fehl}/{tech_mm} ({1 - tech_fehl / tech_mm:.1%})")
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
        "tech_ohne_zins": (basis, tech),
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
        zins = None if name == "tech_ohne_zins" else rf
        res = run_backtest(cfg, prices, universe_at=uni, cash_return=zins)
        kurven[name] = res.equity
        ergebnisse[name] = kennzahlen(res.equity, rf)
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
        print(f"   CAGR {g['cagr']:+.1%}  Vol {g['volatility']:.1%}  Sharpe(rf) {g['sharpe_rf']:.2f}  "
              f"MaxDD {g['max_drawdown']:.1%}")
        details[name] = res
        if name == "tech":
            kurven["qqq"] = res.benchmark
            ergebnisse["qqq"] = kennzahlen(res.benchmark, rf)

    kurven["gleichgewichtet"] = gleichgewichtet(
        prices, universum, signaltage, basis.execution.starting_cash
    )
    ergebnisse["gleichgewichtet"] = kennzahlen(kurven["gleichgewichtet"], rf)

    # ---- Rechenbeispiel: QQQ bei gleichem Risiko ---------------------------
    # Nachtraeglich auf die Schwankung der Tech-Variante skaliert, Rest im
    # Geldmarkt. Das ist KEINE handelbare Strategie (der Faktor ist erst im
    # Rueckblick bekannt), sondern die Frage: was haette dasselbe Risiko im
    # Index gebracht?
    r_qqq = kurven["qqq"].pct_change(fill_method=None).fillna(0.0)
    faktor = ergebnisse["tech"]["gesamt"]["volatility"] / ergebnisse["qqq"]["gesamt"]["volatility"]
    r_mix = faktor * r_qqq + (1 - faktor) * rf.reindex(r_qqq.index).fillna(0.0)
    kurven["qqq_gleiches_risiko"] = basis.execution.starting_cash * (1 + r_mix).cumprod()
    ergebnisse["qqq_gleiches_risiko"] = kennzahlen(kurven["qqq_gleiches_risiko"], rf)
    ergebnisse["qqq_gleiches_risiko"]["faktor"] = faktor
    print(f"\nQQQ bei gleichem Risiko: {faktor:.0%} QQQ, Rest Geldmarkt -> "
          f"CAGR {ergebnisse['qqq_gleiches_risiko']['gesamt']['cagr']:+.1%}")

    # ---- Robustheit gegen die Datenluecke ---------------------------------
    rng = np.random.default_rng(2026)
    anteil = tech_fehl / tech_mm if tech_mm else 0.0
    verfuegbar = [c for c in prices.close.columns if c not in ("QQQ", "SPY", "BIL")]
    stichproben = []
    for i in range(ZIEHUNGEN):
        weg = [c for c in verfuegbar if rng.random() < anteil]
        rest = PriceData(close=prices.close.drop(columns=weg), volume=prices.volume.drop(columns=weg))
        r = run_backtest(basis, rest, universe_at=tech, cash_return=rf)
        g = mit_rf(performance_metrics(r.equity), r.equity, rf)
        stichproben.append({"entfernt": len(weg), "cagr": g["cagr"], "sharpe_rf": g["sharpe_rf"],
                            "max_drawdown": g["max_drawdown"]})
        print(f"   Ziehung {i + 1:>2}/{ZIEHUNGEN}: {len(weg):>2} Titel entfernt, "
              f"CAGR {g['cagr']:+.1%}, Sharpe {g['sharpe_rf']:.2f}")
    st = pd.DataFrame(stichproben)
    robustheit = {
        "ziehungen": ZIEHUNGEN,
        "anteil_entfernt": anteil,
        "cagr": {"min": st.cagr.min(), "median": st.cagr.median(), "max": st.cagr.max(), "std": st.cagr.std()},
        "sharpe_rf": {"min": st.sharpe_rf.min(), "median": st.sharpe_rf.median(),
                      "max": st.sharpe_rf.max(), "std": st.sharpe_rf.std()},
        "einzeln": stichproben,
    }

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
            "tech_mitglieder_monate": tech_mm,
            "tech_ohne_kurs": tech_fehl,
            "tech_anteil_ohne_kurs": tech_fehl / tech_mm if tech_mm else None,
            "kursquellen": dict(Counter(v.get("quelle") or "fehlt" for v in quellen.values())),
        },
        "quelle_universum": {
            "artikel": "en.wikipedia.org/wiki/Nasdaq-100",
            "schnappschuesse": len(snap_index),
            "revisionen": {k: v.get("revid") for k, v in sorted(snap_index.items())},
        },
        "robustheit_datenluecke": robustheit,
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
