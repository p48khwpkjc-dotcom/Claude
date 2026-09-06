# Day-Trading Bot (Krypto)

Backtest- und Signal-Framework für Intraday-Krypto. Entscheidungen auf 5m-Kerzen,
Trendfilter auf 1h, Risiko- und Kostenrechnung vor jeder Strategie.

Stand: fertig gerechnet, und das Ergebnis ist negativ. Auf 466.557 echten 5m-Kerzen
(BTC, ETH, SOL, 18 Monate) verdient keine der sechs Strategien Geld — auch nicht mit
Gebühren und Slippage auf null. Der Befund und was daraus folgt: **[ERGEBNIS.md](ERGEBNIS.md)**.

## Schnellstart

```bash
pip install -r requirements.txt

python -m daytrader selftest              # läuft ohne Netz, auf synthetischen Daten
python -m daytrader costs                 # was Gebühren pro Risikoeinheit kosten
python -m daytrader regimes               # Strategieprüfung ohne Börsendaten
python -m daytrader fetch                 # Kerzen von Binance in den lokalen Cache
python -m daytrader backtest              # Strategievergleich -> out/report.md
```

`fetch` braucht Zugang zu `data-api.binance.vision` – öffentlich, ohne API-Key und
ohne Konto. In abgeschotteten Umgebungen (CI, gesperrte Container) läuft alles
andere mit `--source synthetic` weiter.

Kommt die Umgebung an keine Börse heran, transportiert `export`/`verify` die Kerzen
über das Repository dorthin: Schritt für Schritt in **[DATEN-HOLEN.md](DATEN-HOLEN.md)**.

Aktueller Projektstand und nächster Schritt: **[STATUS.md](STATUS.md)**.

## Das Wichtigste zuerst: die Kostenrechnung

Bevor irgendeine Strategie sinnvoll bewertet werden kann, muss man wissen, was ein
Trade kostet. `python -m daytrader costs` rechnet das aus:

| Stop | Abstand | Kosten pro Trade | Trefferquote für Break-even bei 2R |
|---|---|---|---|
| 1,0 × ATR | 0,13 % | 1,38 R | 79 % |
| 2,0 × ATR | 0,26 % | 0,69 R | 56 % |
| 5,0 × ATR | 0,65 % | 0,28 R | 43 % |

(BTCUSDT, gemessen am echten 5m-ATR von 0,13 % des Kurses. Eine frühere Fassung
dieser Tabelle rechnete mit synthetischen Kerzen und einem doppelt so großen ATR —
die Kosten sind also doppelt so hoch wie zunächst angenommen.)

Bei einem engen 5m-Stop sind Gebühren und Slippage größer als der Stop selbst: bei
1,0 × ATR kostet ein Trade 1,38 R, also mehr, als er riskiert. Der Break-even bei 1R
läge dort bei einer Trefferquote von 100 %. Ein „diszipliniert enger" Stop ist dann vor allem eine teure Art,
die Börse zu bezahlen. Das ist der Grund, warum die meisten Intraday-Systeme
scheitern, und es entscheidet, welche Stop-Abstände überhaupt testenswert sind.

## Der Regime-Prüfstand

`python -m daytrader regimes` testet jede Strategie gegen Marktzustände, die per
Konstruktion trenden oder mean-revertieren. Das braucht keine Börsendaten und
beantwortet eine Frage, die vor dem Backtest kommt: *Ist die Strategie in sich
schlüssig?* Eine Trendfolge, die auf einer nachweislich trendenden Serie verliert,
ist kaputt – daran ändern echte Kerzen nichts.

Jede Strategie hinterlegt im Code, was sie über sich behauptet
(`expects_edge_in`, `expects_no_edge_in`). Der Prüfstand hält sie daran fest.

Der Durchgang hat zwei populäre Indikatoren als strukturell fehlkalibriert entlarvt:

| Strategie | Signale im falschen Regime | Urteil |
|---|---|---|
| rsi_reversion | 99,9 % | feuert fast ausschließlich dort, wo sie verliert |
| ema_momentum | 85,2 % | dito |
| vwap_reversion | 78,6 % | Trendfilter zu schwach |
| opening_range | 46,6 % | gemischt |
| squeeze_breakout | 29,7 % | gut gezielt |
| donchian_breakout | 15,4 % | gut gezielt |

Der Grund ist messbar: **RSI liegt in einer trendenden Serie zu 33 % der Zeit unter
30, in einer seitwärts laufenden zu 0,06 %.** Wer überverkauften RSI kauft, kauft
also praktisch nur in Abwärtstrends – das Gegenteil von Mean Reversion.
Bei EMA-Kreuzungen ist es spiegelbildlich: 1.678 Kreuzungen in der Seitwärtsserie
gegen 85 in der Trendserie.

Kursniveau-basierte Auslöser (Kanalbrüche, Abstand zu einem adaptiven Band) folgen
dem Regime. Oszillatoren und Kreuzungen tun das nicht.

Was der Prüfstand allerdings **nicht** leistet: eine Vorauswahl nach Rendite. Auf
echten Kerzen liegt das hier verworfene `rsi_reversion` im Mittelfeld und das hier
gelobte `squeeze_breakout` am unteren Ende (siehe [ERGEBNIS.md](ERGEBNIS.md)). Er
misst innere Schlüssigkeit, und die sagt über den Ertrag nichts vorher.

## Aufbau

```
daytrader/
  config.py            Getypte Konfiguration aus config.yaml
  core/
    types.py           Signal, Position, Trade, Ergebnisobjekte
    indicators.py      Kausale Indikatoren (EMA, ATR, RSI, VWAP, Opening Range)
    timeframe.py       Resampling und Mehr-Zeitrahmen-Alignment
  data/
    binance.py         Öffentliche Kerzen, kein API-Key
    synthetic.py       Deterministischer Generator für Tests ohne Netz
    loader.py          Parquet-Cache, inkrementelles Update, Validierung
  strategies/
    vwap_reversion.py    Mean Reversion zum Session-VWAP
    rsi_reversion.py     Reine RSI-Reversion (Kontrollgruppe)
    opening_range.py     Ausbruch aus der ersten UTC-Stunde
    ema_momentum.py      EMA-Kreuzung mit 1h-Trendfilter
    donchian_breakout.py Kanalausbruch (Kontrollgruppe Trendfolge)
    squeeze_breakout.py  Bollinger-Kompression, Volatilitätsausbruch
  risk/manager.py      Positionsgröße, Kill-Switch, Cooldown, Tageslimits
  backtest/
    engine.py          Bar-für-Bar-Simulation mit Fills, Gebühren, Slippage
    costs.py           Kosten pro Risikoeinheit, Break-even-Trefferquoten
    regimes.py         Prüfstand gegen konstruierte Marktzustände
    metrics.py         Profitfaktor, Erwartungswert in R, Drawdown, Sharpe
    runner.py          Walk-Forward-Matrix und Report
```

## Wogegen die Engine sich wehrt

Ein Backtest, der schmeichelt, ist wertlos. Vier Regeln sind fest eingebaut:

1. Ein Signal auf Kerze *i* wird zur **Eröffnung von Kerze i+1** gefüllt, nie zum
   Schlusskurs der Kerze, die das Signal erzeugt hat.
2. Enthält eine Kerze Stop **und** Ziel, gilt der **Stop** als zuerst getroffen.
   Ohne Tickdaten kann man es nicht wissen, und die pessimistische Lesart ist die
   einzige, die nicht lügt.
3. Ein Trailing-Stop wird erst nachgezogen, wenn die Kerze abgearbeitet ist – er
   kann die nächste Kerze schützen, niemals die, die ihn erzeugt hat.
4. Jeder Fill zahlt Gebühr und Slippage gegen sich. Stops zahlen mehr, und ein Gap
   durch den Stop füllt zur Eröffnung, nicht auf dem Wunschniveau.

`tests/test_no_lookahead.py` backtestet jede Strategie zweimal – einmal auf der
vollen Historie, einmal auf einer abgeschnittenen Kopie – und besteht nur, wenn
jeder vorher geschlossene Trade identisch herauskommt.

```bash
python -m pytest tests/ -q      # 72 Tests
```

## Risiko-Regeln

Aus `config.yaml`, nicht aus dem Strategiecode. Eine Strategie sagt „long, Stop
hier"; über Größe und darüber, ob der Trade überhaupt stattfindet, entscheidet
ausschließlich der Risk-Layer.

- 0,5 % Risiko pro Trade, Größe aus dem Stop-Abstand
- Hebel 1,0 – die Position übersteigt nie das Eigenkapital
- Kill-Switch bei 3 % Tagesverlust: **schließt offene Positionen** und sperrt den
  Rest des UTC-Tages
- Cooldown nach drei Verlusten in Folge
- maximal 5 Trades pro Tag, eine Position gleichzeitig
- Zwangsschluss nach 4 Stunden – Krypto hat keinen Handelsschluss

## Nächste Schritte

1. `fetch` auf einer Maschine mit Börsenzugang, dann `backtest` auf echten Kerzen.
   Erst diese Zahlen entscheiden, welche Strategie weiterverfolgt wird. Der
   Regime-Prüfstand hat das Feld vorsortiert – `donchian_breakout` und
   `squeeze_breakout` sind die beiden Kandidaten, die ihre Verträge halten und
   dort schweigen, wo sie nicht funktionieren.
2. Live-Loop gegen Binance- oder Bybit-Testnet, mit Logging und Heartbeat.
3. Deployment (systemd oder Docker) auf einen kleinen VPS.

Vor echtem Geld: mehrere Wochen Paper-Betrieb, und die Paper-Statistik muss zum
Backtest passen. Tut sie das nicht, stimmt eine der beiden Zahlen nicht.
