# Day-Trading Bot (Krypto)

Backtest- und Signal-Framework für Intraday-Krypto. Entscheidungen auf 5m-Kerzen,
Trendfilter auf 1h, Risiko- und Kostenrechnung vor jeder Strategie.

Stand: Datenlayer, Backtest-Engine, drei Strategiekandidaten und der Risk-Layer
sind fertig und getestet. Der Live-Loop gegen die Testnet-API ist noch nicht gebaut.

## Schnellstart

```bash
pip install -r requirements.txt

python -m daytrader selftest              # läuft ohne Netz, auf synthetischen Daten
python -m daytrader costs                 # was Gebühren pro Risikoeinheit kosten
python -m daytrader fetch                 # Kerzen von Binance in den lokalen Cache
python -m daytrader backtest              # Strategievergleich -> out/report.md
```

`fetch` braucht Zugang zu `data-api.binance.vision` – öffentlich, ohne API-Key und
ohne Konto. In abgeschotteten Umgebungen (CI, gesperrte Container) läuft alles
andere mit `--source synthetic` weiter.

## Das Wichtigste zuerst: die Kostenrechnung

Bevor irgendeine Strategie sinnvoll bewertet werden kann, muss man wissen, was ein
Trade kostet. `python -m daytrader costs` rechnet das aus:

| Stop | Abstand | Kosten pro Trade | Trefferquote für Break-even bei 2R |
|---|---|---|---|
| 1,0 × ATR | 0,26 % | 0,69 R | 56 % |
| 2,0 × ATR | 0,52 % | 0,35 R | 45 % |
| 5,0 × ATR | 1,30 % | 0,14 R | 38 % |

Bei einem engen 5m-Stop sind Gebühren und Slippage in derselben Größenordnung wie
der Stop selbst. Ein „diszipliniert enger" Stop ist dann vor allem eine teure Art,
die Börse zu bezahlen. Das ist der Grund, warum die meisten Intraday-Systeme
scheitern, und es entscheidet, welche Stop-Abstände überhaupt testenswert sind.

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
    vwap_reversion.py  Mean Reversion zum Session-VWAP
    opening_range.py   Ausbruch aus der ersten UTC-Stunde
    ema_momentum.py    EMA-Kreuzung mit 1h-Trendfilter
  risk/manager.py      Positionsgröße, Kill-Switch, Cooldown, Tageslimits
  backtest/
    engine.py          Bar-für-Bar-Simulation mit Fills, Gebühren, Slippage
    costs.py           Kosten pro Risikoeinheit, Break-even-Trefferquoten
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
   Erst diese Zahlen entscheiden, welche der drei Strategien weiterverfolgt wird.
2. Live-Loop gegen Binance- oder Bybit-Testnet, mit Logging und Heartbeat.
3. Deployment (systemd oder Docker) auf einen kleinen VPS.

Vor echtem Geld: mehrere Wochen Paper-Betrieb, und die Paper-Statistik muss zum
Backtest passen. Tut sie das nicht, stimmt eine der beiden Zahlen nicht.
