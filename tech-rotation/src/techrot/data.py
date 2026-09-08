"""Datenschicht: Kursbeschaffung, Cache und Qualitaetspruefung.

Der Provider ist austauschbar, damit die Strategie nicht an eine Quelle
gebunden ist. Alle Provider liefern dieselbe Struktur: zwei DataFrames mit
DatetimeIndex (tz-naiv, aufsteigend) und Tickern als Spalten.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from .config import Config, DataConfig


class DataError(RuntimeError):
    """Kursdaten konnten nicht beschafft oder nicht validiert werden."""


@dataclass(frozen=True)
class PriceData:
    """Adjustierte Schlusskurse und Volumen fuer ein Tickeruniversum."""

    close: pd.DataFrame
    volume: pd.DataFrame

    def __post_init__(self) -> None:
        if not self.close.index.equals(self.volume.index):
            raise DataError("close und volume haben unterschiedliche Datumsindizes")

    @property
    def last_date(self) -> pd.Timestamp:
        return self.close.index[-1]

    def up_to(self, asof: pd.Timestamp) -> PriceData:
        """Schneidet das Panel auf alles bis einschliesslich asof zu.

        Der Kern des Lookahead-Schutzes: Ranking und Risikopruefung sehen nur
        dieses Fenster, nie spaetere Kurse.
        """
        mask = self.close.index <= asof
        return PriceData(close=self.close.loc[mask], volume=self.volume.loc[mask])

    def dollar_volume(self, window: int) -> pd.Series:
        """Durchschnittliches Handelsvolumen in USD ueber window Tage."""
        notional = self.close * self.volume
        return notional.tail(window).mean()


class PriceProvider(Protocol):
    name: str

    def fetch(
        self, tickers: list[str], start: datetime, end: datetime
    ) -> tuple[pd.DataFrame, pd.DataFrame]: ...


def _normalize(frame: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Vereinheitlicht Index und Spalten eines Roh-Frames."""
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    for ticker in tickers:
        if ticker not in frame.columns:
            # np.nan, nicht pd.NA: pd.NA laesst sich nicht nach float64 casten
            # und wuerde den ganzen Lauf abbrechen, statt den fehlenden Ticker
            # der Qualitaetspruefung zu ueberlassen.
            frame[ticker] = np.nan
    return frame[tickers].astype("float64")


class YFinanceProvider:
    """Yahoo Finance. Kostenlos, kein API-Key, taegliche Bars."""

    name = "yfinance"

    def fetch(
        self, tickers: list[str], start: datetime, end: datetime
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        import yfinance as yf

        raw = yf.download(
            tickers,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
            group_by="column",
            threads=True,
        )
        if raw is None or raw.empty:
            raise DataError(
                "yfinance lieferte keine Daten. Netzwerk, Ticker-Symbole oder "
                "Rate-Limit pruefen."
            )

        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"]
            volume = raw["Volume"]
        else:
            # Einzelticker: flache Spalten
            close = raw[["Close"]].rename(columns={"Close": tickers[0]})
            volume = raw[["Volume"]].rename(columns={"Volume": tickers[0]})

        return _normalize(close, tickers), _normalize(volume, tickers)


class StooqProvider:
    """Stooq-CSV. Fallback ohne API-Key; liefert kein verlaessliches Volumen
    fuer alle Symbole, deckt aber US-Aktien taeglich ab."""

    name = "stooq"

    def __init__(self, transport: object | None = None) -> None:
        # Nur Tests reichen hier einen Transport herein.
        self._transport = transport

    def fetch(
        self, tickers: list[str], start: datetime, end: datetime
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        import httpx

        closes: dict[str, pd.Series] = {}
        volumes: dict[str, pd.Series] = {}
        with httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            transport=self._transport,  # type: ignore[arg-type]
        ) as client:
            for ticker in tickers:
                url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d"
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    raise DataError(f"Stooq-Abruf fuer {ticker} fehlgeschlagen: {exc}") from exc

                frame = pd.read_csv(StringIO(resp.text))
                # Stooq antwortet auf ein unbekanntes Symbol mit Klartext
                # statt CSV -- so einen Ticker still ueberspringen.
                if "Date" not in frame.columns or "Close" not in frame.columns:
                    continue
                frame["Date"] = pd.to_datetime(frame["Date"])
                frame = frame.set_index("Date").sort_index()
                closes[ticker] = frame["Close"]
                if "Volume" in frame.columns:
                    volumes[ticker] = frame["Volume"]

        if not closes:
            raise DataError("Stooq lieferte fuer kein Symbol Daten")

        close = pd.DataFrame(closes)
        # Ein Symbol ohne Volumenspalte bekommt NaN und faellt damit ueber die
        # Liquiditaetspruefung heraus, statt still mit 0 durchzurutschen.
        volume = pd.DataFrame(volumes, index=close.index) if volumes else pd.DataFrame(
            index=close.index
        )
        window = (close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end))
        return _normalize(close[window], tickers), _normalize(volume[window], tickers)


class LocalCsvProvider:
    """Liest close.csv und volume.csv aus data/local.

    Fuer Backtests auf eigenen Daten, fuer Umgebungen ohne Netzzugang und
    fuer reproduzierbare Tests.
    """

    name = "local_csv"

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def fetch(
        self, tickers: list[str], start: datetime, end: datetime
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        close_path = self.directory / "close.csv"
        volume_path = self.directory / "volume.csv"
        if not close_path.exists():
            raise DataError(f"Lokale Kursdatei fehlt: {close_path}")

        close = pd.read_csv(close_path, index_col=0, parse_dates=True)
        if volume_path.exists():
            volume = pd.read_csv(volume_path, index_col=0, parse_dates=True)
        else:
            volume = pd.DataFrame(1e12, index=close.index, columns=close.columns)

        present = [t for t in tickers if t in close.columns]
        if not present:
            raise DataError(f"Keiner der Ticker ist in {close_path} enthalten")

        window = (close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end))
        return (
            _normalize(close[window], present),
            _normalize(volume.reindex(close.index)[window], present),
        )


def build_provider(cfg: Config) -> PriceProvider:
    match cfg.data.provider:
        case "yfinance":
            return YFinanceProvider()
        case "stooq":
            return StooqProvider()
        case "local_csv":
            return LocalCsvProvider(cfg.path("data/local"))
        case other:
            raise DataError(f"Unbekannter Datenprovider: {other}")


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------


def _cache_is_fresh(meta_path: Path, ttl_hours: float, tickers: list[str]) -> bool:
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if sorted(meta.get("tickers", [])) != sorted(tickers):
        return False
    age_hours = (time.time() - float(meta.get("fetched_at", 0))) / 3600
    return age_hours < ttl_hours


def load_prices(cfg: Config, *, use_cache: bool = True, refresh: bool = False) -> PriceData:
    """Beschafft Kurse fuer Universum plus Benchmark, mit Cache."""
    tickers = list(cfg.tickers)
    if cfg.benchmark and cfg.benchmark not in tickers:
        tickers.append(cfg.benchmark)

    cache_dir = cfg.path(cfg.data.cache_dir)
    close_path = cache_dir / "close.csv"
    volume_path = cache_dir / "volume.csv"
    meta_path = cache_dir / "meta.json"

    if (
        use_cache
        and not refresh
        and close_path.exists()
        and volume_path.exists()
        and _cache_is_fresh(meta_path, cfg.data.cache_ttl_hours, tickers)
    ):
        close = pd.read_csv(close_path, index_col=0, parse_dates=True)
        volume = pd.read_csv(volume_path, index_col=0, parse_dates=True)
        return PriceData(close=close, volume=volume)

    # Zeitzonenfrei in UTC: die Kurspanels sind tz-naiv, ein tz-bewusster
    # Zeitstempel liesse jeden Vergleich mit dem Index scheitern.
    end = datetime.now(timezone.utc).replace(tzinfo=None)
    start = end - timedelta(days=int(cfg.data.history_years * 365.25) + 10)
    provider = build_provider(cfg)
    close, volume = provider.fetch(tickers, start, end)

    if use_cache:
        cache_dir.mkdir(parents=True, exist_ok=True)
        close.to_csv(close_path)
        volume.to_csv(volume_path)
        meta_path.write_text(
            json.dumps(
                {
                    "fetched_at": time.time(),
                    "provider": provider.name,
                    "tickers": tickers,
                    "rows": int(len(close)),
                    "last_date": str(close.index[-1].date()) if len(close) else None,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return PriceData(close=close, volume=volume)


# --------------------------------------------------------------------------
# Qualitaetspruefung
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DataQuality:
    """Pro-Ticker-Befund der Datenpruefung."""

    ticker: str
    ok: bool
    reason: str
    history_days: int
    staleness_days: int
    missing_ratio: float


def check_data_quality(
    prices: PriceData, tickers: list[str], data_cfg: DataConfig, asof: pd.Timestamp
) -> dict[str, DataQuality]:
    """Prueft je Ticker Historienlaenge, Aktualitaet und Luecken."""
    results: dict[str, DataQuality] = {}
    for ticker in tickers:
        if ticker not in prices.close.columns:
            results[ticker] = DataQuality(ticker, False, "keine Kursreihe vorhanden", 0, 999, 1.0)
            continue

        series = prices.close[ticker]
        valid = series.dropna()
        history = len(valid)

        if history == 0:
            results[ticker] = DataQuality(ticker, False, "Kursreihe ist leer", 0, 999, 1.0)
            continue

        staleness = int((asof - valid.index[-1]).days)
        # Luecken nur innerhalb der tatsaechlichen Historie zaehlen: ein Ticker
        # mit spaeterem IPO soll nicht als "lueckenhaft" gelten.
        window = series.loc[valid.index[0] :]
        missing_ratio = float(window.isna().mean()) if len(window) else 1.0

        reasons = []
        if history < data_cfg.min_history_days:
            reasons.append(f"nur {history} von {data_cfg.min_history_days} Tagen Historie")
        if staleness > data_cfg.max_staleness_days:
            reasons.append(f"letzter Kurs {staleness} Tage alt")
        if missing_ratio > data_cfg.max_missing_ratio:
            reasons.append(f"{missing_ratio:.1%} Luecken")

        results[ticker] = DataQuality(
            ticker=ticker,
            ok=not reasons,
            reason="; ".join(reasons) if reasons else "ok",
            history_days=history,
            staleness_days=staleness,
            missing_ratio=missing_ratio,
        )
    return results
