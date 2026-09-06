# Wo das Projekt steht

Kurznotiz für eine neue Sitzung. Wenn du diese Datei liest, weil du gerade neu
gestartet bist: alles Wichtige liegt im Repo, es geht nichts verloren.

## Der Stand in einem Satz

Der Backtest auf echten Kerzen ist gelaufen, und er ist negativ: keine der sechs
Strategien verdient Geld, auch nicht ohne Gebühren. Die Einzelheiten stehen in
**[ERGEBNIS.md](ERGEBNIS.md)**.

## Fertig und getestet

- **Datenlayer** – Binance-Kerzen ohne API-Key, Parquet-Cache, harte Validierung
- **Backtest-Engine** – Fill auf der nächsten Kerzeneröffnung, Stop schlägt Ziel,
  Trailing erst nach der Kerze, Gebühren und Slippage auf jedem Fill
- **Risk-Layer** – 0,5 % Risiko pro Trade, Kill-Switch bei 3 % Tagesverlust,
  Cooldown, Tageslimit, 4 Stunden maximale Haltedauer
- **Sechs Strategien** – vwap_reversion, rsi_reversion, opening_range,
  ema_momentum, donchian_breakout, squeeze_breakout
- **Kostenrechnung** (`daytrader costs`) – Gebühren pro Risikoeinheit
- **Regime-Prüfstand** (`daytrader regimes`) – Strategieprüfung ohne Börsendaten
- **Datentransport** (`daytrader export` / `verify`) – Kerzen über das Repo
- 94 Tests, alle grün: `python -m pytest tests/ -q`
- **Backtest auf 466.557 echten 5m-Kerzen** – BTC, ETH, SOL, 18 Monate

## Was der Backtest ergeben hat

Profitfaktor 0,37 bis 0,50 über alle sechs Strategien, in und außerhalb der
Stichprobe. Setzt man Gebühren und Slippage auf null, landet alles zwischen 0,89
und 1,06 — ein Münzwurf. Es gibt also keine Kante, die von Kosten aufgefressen
würde; es gibt keine Kante.

Nebenbefund: die frühere Kostenschätzung war um den Faktor zwei zu freundlich.
Der echte 5m-ATR von BTC liegt bei 0,13 % des Kurses, nicht 0,26 %. Ein 1,2×ATR-
Stop kostet damit nicht 0,69 R, sondern 1,38 R — mehr, als der Trade riskiert.

## Der Netzwerkzugang ist offen

`data-api.binance.vision` antwortet aus dieser Umgebung mit `200`. Der Umweg aus
[DATEN-HOLEN.md](DATEN-HOLEN.md) — Kerzen auf dem eigenen Rechner holen und übers
Repo transportieren — wird nicht mehr gebraucht. Die Anleitung bleibt trotzdem
stehen, für den Fall, dass sich die Policy wieder ändert.

Prüfen lässt sich das jederzeit:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://data-api.binance.vision/api/v3/ping
```

`200` heißt offen, `000` heißt zu.

Der Abruf dauert bei offenem Zugang rund vier Minuten, nicht die früher
geschätzten zwanzig:

```bash
python -m daytrader fetch --days 540
python -m daytrader backtest              # -> out/report.md
python -m daytrader costs
```

## Nächster Schritt

Hier ist eine Entscheidung fällig, keine Programmieraufgabe. Der 5m-Intraday-
Ansatz auf Preis und Volumen ist durchgerechnet und trägt nicht. Drei Richtungen
stehen offen, jede verlässt die bisherige Anlage — ERGEBNIS.md wägt sie ab:

1. Längerer Zeitrahmen (1h/4h), wo derselbe Trade einen Bruchteil kostet
2. Andere Gebührenstruktur (Maker statt Taker) — hilft nur mit einer Kante
3. Eine andere Signalquelle: Orderbuch, Finanzierungsraten, Cross-Asset

Was **nicht** ansteht: an Parametern drehen, bis eine Kurve nach oben zeigt. Bei
sechs Strategien und einem kostenfreien Profitfaktor um 1,0 findet man diese
Kurve garantiert, und sie bedeutet nichts.

Der Live-Loop gegen die Testnet-API ist weiterhin nicht gebaut — und solange
keine Strategie im Backtest trägt, gibt es dafür auch keinen Anlass.
