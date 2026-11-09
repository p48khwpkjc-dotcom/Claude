#!/usr/bin/env python3
"""Laedt Kurse fuer jeden Titel, der je im Universum war -- und friert sie ein.

Gebraucht werden nicht nur die heutigen Mitglieder, sondern alle, die zu
irgendeinem Stichtag dabei waren, auch uebernommene und abgestiegene. Fehlen
deren Kurse, faellt der Titel still aus dem Backtest, und der Survivorship-
Bias ist durch die Hintertuer zurueck. Deshalb wird jede Luecke protokolliert.

Laeuft im GitHub-Runner. Ergebnis:

    research/data/prices/close.csv.gz    adjustierte Schlusskurse
    research/data/prices/volume.csv.gz   Stueckvolumen
    research/data/prices/coverage.json   Quelle und Zeitraum je Symbol, Luecken

Wiederholbar: schon vorhandene Symbole werden nicht neu geladen.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from io import StringIO
from pathlib import Path

import httpx
import pandas as pd
import yaml

HIER = Path(__file__).resolve().parent
UNIVERSUM = HIER / "data" / "universe" / "membership.csv"
ZIEL = HIER / "data" / "prices"
KONFIG = HIER.parent / "config.yaml"
START = "2017-01-01"
# Zusaetzlich zum historischen Index: der Benchmark und die Live-Liste, damit
# die verzerrte Vergleichsvariante auf demselben Datensatz laeuft.
EXTRA = ["QQQ", "SPY"]


def benoetigte_symbole() -> list[str]:
    mitglieder = pd.read_csv(UNIVERSUM)
    symbole = set(mitglieder["symbol"].dropna().astype(str))
    live = yaml.safe_load(KONFIG.read_text())["universe"]["tickers"]
    symbole |= set(live) | set(EXTRA)
    return sorted(symbole)


def yfinance_holen(symbole: list[str], ende: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    import yfinance as yf

    closes, volumes = [], []
    for i in range(0, len(symbole), 40):
        block = symbole[i : i + 40]
        for versuch in range(3):
            try:
                raw = yf.download(
                    block, start=START, end=ende, auto_adjust=True,
                    progress=False, group_by="column", threads=True,
                )
                break
            except Exception as exc:  # noqa: BLE001 -- Rate-Limit u.a.
                print(f"  Block {i}: Versuch {versuch + 1} fehlgeschlagen: {exc}", file=sys.stderr)
                time.sleep(10 * (versuch + 1))
        else:
            continue
        if raw is None or raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            closes.append(raw["Close"])
            volumes.append(raw["Volume"])
        else:
            closes.append(raw[["Close"]].rename(columns={"Close": block[0]}))
            volumes.append(raw[["Volume"]].rename(columns={"Volume": block[0]}))
        print(f"  yfinance Block {i // 40 + 1}: {len(block)} Symbole")
        time.sleep(2)

    if not closes:
        return pd.DataFrame(), pd.DataFrame()
    close = pd.concat(closes, axis=1)
    volume = pd.concat(volumes, axis=1)
    for f in (close, volume):
        f.index = pd.to_datetime(f.index).tz_localize(None)
    close = close.loc[:, ~close.columns.duplicated()]
    volume = volume.loc[:, ~volume.columns.duplicated()]
    return close, volume


def stooq_holen(symbol: str, client: httpx.Client) -> tuple[pd.Series, pd.Series] | None:
    """Rueckfallebene fuer Symbole, die Yahoo nicht mehr fuehrt."""
    url = f"https://stooq.com/q/d/l/?s={symbol.lower().replace('.', '-')}.us&i=d"
    try:
        r = client.get(url)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    try:
        f = pd.read_csv(StringIO(r.text))
    except Exception:  # noqa: BLE001
        return None
    if "Date" not in f.columns or "Close" not in f.columns or f.empty:
        return None
    f["Date"] = pd.to_datetime(f["Date"])
    f = f.set_index("Date").sort_index()
    f = f[f.index >= pd.Timestamp(START)]
    if f.empty:
        return None
    vol = f["Volume"] if "Volume" in f.columns else pd.Series(index=f.index, dtype="float64")
    return f["Close"].astype("float64"), vol.astype("float64")


def main() -> int:
    if not UNIVERSUM.exists():
        print(f"{UNIVERSUM} fehlt -- erst das Universum bauen.", file=sys.stderr)
        return 2

    ZIEL.mkdir(parents=True, exist_ok=True)
    pfad_c, pfad_v, pfad_cov = ZIEL / "close.csv.gz", ZIEL / "volume.csv.gz", ZIEL / "coverage.json"
    benoetigt = benoetigte_symbole()

    if pfad_c.exists():
        close = pd.read_csv(pfad_c, index_col=0, parse_dates=True)
        volume = pd.read_csv(pfad_v, index_col=0, parse_dates=True)
        coverage = json.loads(pfad_cov.read_text())
    else:
        close, volume, coverage = pd.DataFrame(), pd.DataFrame(), {}

    offen = [s for s in benoetigt if s not in coverage]
    print(f"{len(benoetigt)} Symbole benoetigt, {len(offen)} noch offen")
    if not offen:
        return 0

    ende = date.today().isoformat()
    c_neu, v_neu = yfinance_holen(offen, ende)

    def eintragen(sym: str, c: pd.Series, v: pd.Series, quelle: str) -> None:
        nonlocal close, volume
        c = c.dropna()
        close = close.combine_first(c.to_frame(sym)) if not close.empty else c.to_frame(sym)
        volume = volume.combine_first(v.reindex(c.index).to_frame(sym)) if not volume.empty else v.reindex(c.index).to_frame(sym)
        coverage[sym] = {
            "quelle": quelle,
            "von": str(c.index[0].date()),
            "bis": str(c.index[-1].date()),
            "tage": int(len(c)),
        }

    fehlend = []
    for sym in offen:
        if sym in c_neu.columns and c_neu[sym].notna().sum() > 20:
            eintragen(sym, c_neu[sym], v_neu.get(sym, pd.Series(dtype="float64")), "yfinance")
        else:
            fehlend.append(sym)

    print(f"yfinance: {len(offen) - len(fehlend)} geladen, {len(fehlend)} ohne Daten -- versuche Stooq")
    with httpx.Client(timeout=30.0, follow_redirects=True,
                      headers={"User-Agent": "techrot-research/1.0"}) as client:
        for sym in fehlend:
            treffer = stooq_holen(sym, client)
            time.sleep(0.5)
            if treffer is not None and treffer[0].notna().sum() > 20:
                eintragen(sym, treffer[0], treffer[1], "stooq")
                print(f"  Stooq: {sym} {coverage[sym]['von']} bis {coverage[sym]['bis']}")
            else:
                coverage[sym] = {"quelle": None, "fehlt": True}
                print(f"  FEHLT: {sym}")

    close = close.sort_index()
    volume = volume.reindex(index=close.index, columns=close.columns)
    close.to_csv(pfad_c, float_format="%.8g", compression="gzip")
    volume.to_csv(pfad_v, float_format="%.8g", compression="gzip")
    pfad_cov.write_text(json.dumps(coverage, indent=1, sort_keys=True))

    n_fehlt = sum(1 for v in coverage.values() if v.get("fehlt"))
    print(f"\nFertig: {close.shape[1]} Symbole mit Kursen, {n_fehlt} ohne. "
          f"Zeitraum {close.index[0].date()} bis {close.index[-1].date()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
