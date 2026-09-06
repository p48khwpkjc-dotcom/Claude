# Der Backtest auf echten Kerzen

Das war der letzte offene Punkt: alles bisher Gebaute lief auf synthetischen oder
konstruierten Daten. Am 6. September 2026 war der Zugang zu
`data-api.binance.vision` offen, und die Rechnung ließ sich zu Ende führen.

**Datengrundlage:** 155.519 5m-Kerzen je Symbol, BTCUSDT, ETHUSDT und SOLUSDT,
15. März 2025 bis 6. September 2026. 466.557 Kerzen insgesamt. Auswahl auf den
ersten 60 %, der Rest bleibt zurückgehalten.

## Das Ergebnis

Keine der sechs Strategien verdient Geld. Nicht in der Stichprobe, nicht außerhalb.

Außerhalb der Stichprobe, über die drei Symbole gemittelt:

| Strategie | Trades | Trefferquote | Profitfaktor | Erwartungswert | Rendite |
|---|---:|---:|---:|---:|---:|
| vwap_reversion | 2.140 | 25,98 % | 0,50 | −0,63 R | −68,5 % |
| rsi_reversion | 1.730 | 45,65 % | 0,48 | −0,41 R | −57,5 % |
| donchian_breakout | 3.196 | 23,35 % | 0,47 | −0,53 R | −83,2 % |
| squeeze_breakout | 2.739 | 26,71 % | 0,42 | −0,67 R | −77,1 % |
| ema_momentum | 1.243 | 27,55 % | 0,39 | −0,65 R | −49,8 % |
| opening_range | 667 | 30,71 % | 0,37 | −0,79 R | −29,7 % |

Ein Profitfaktor von 0,37 bis 0,50 heißt: pro Dollar, den diese Systeme gewinnen,
verlieren sie zwei bis drei. Die Rangfolge ist dabei nebensächlich — sie sortiert
Verluste.

## Woran es liegt

Naheliegend wäre, die Kosten verantwortlich zu machen. Der Gegentest entscheidet
das: derselbe Lauf, Gebühren und Slippage auf null.

| Strategie | Profitfaktor (in) | Profitfaktor (out) | Erwartungswert (out) |
|---|---:|---:|---:|
| ema_momentum | 1,06 | 0,99 | +0,02 R |
| donchian_breakout | 1,03 | 0,96 | −0,01 R |
| squeeze_breakout | 0,99 | 1,01 | +0,02 R |
| opening_range | 0,97 | 1,05 | +0,03 R |
| vwap_reversion | 0,96 | 1,02 | +0,09 R |
| rsi_reversion | 0,89 | 0,92 | −0,03 R |

Ohne jede Reibung landet alles zwischen 0,89 und 1,06. Das ist ein Münzwurf.
Und die Reihenfolge dreht sich zwischen den beiden Hälften: `ema_momentum` führt
in der Stichprobe und fällt außerhalb auf Platz vier, `opening_range` ist drinnen
Vorletzter und draußen Erster. Wenn die Rangfolge kippt, sobald man die Daten
wechselt, misst sie kein Signal.

Die Kosten sind also nicht der Dieb einer vorhandenen Kante. Es gibt keine Kante,
und die Kosten verwandeln den Münzwurf in einen sicheren Verlust.

## Der Gegentest mit weiten Stops

Wenn Kosten pro Risikoeinheit das Problem sind, muss ein weiterer Stop helfen —
er verteilt dieselbe Gebühr über mehr Risiko. Derselbe Lauf mit 5×ATR statt
1,0 bis 2,0×ATR, Kosten unverändert:

| Strategie | Erwartungswert vorher | mit 5×ATR | Differenz |
|---|---:|---:|---:|
| vwap_reversion | −0,63 R | −0,15 R | +0,48 |
| rsi_reversion | −0,41 R | −0,16 R | +0,25 |
| opening_range | −0,79 R | −0,18 R | +0,61 |
| donchian_breakout | −0,53 R | −0,24 R | +0,29 |
| squeeze_breakout | −0,67 R | −0,24 R | +0,43 |
| ema_momentum | −0,65 R | −0,25 R | +0,40 |

Die Ersparnis tritt genau so ein, wie die Kostenrechnung sie vorhergesagt hat.
Sie reicht nur nirgends bis über null, weil darunter nichts liegt, das sie
freilegen könnte.

## Korrektur an der früheren Kostenschätzung

Die Zahlen im README stammten aus synthetischen Kerzen und waren zu freundlich.
Der echte 5m-ATR von BTCUSDT liegt bei 0,13 % des Kurses, halb so groß wie
angenommen. Damit verdoppeln sich die Kosten pro Risikoeinheit:

| Stop | Abstand | Kosten (geschätzt) | Kosten (gemessen) |
|---|---:|---:|---:|
| 1,0 × ATR | 0,13 % | 0,69 R | **1,38 R** |
| 2,0 × ATR | 0,26 % | 0,35 R | **0,69 R** |
| 5,0 × ATR | 0,65 % | 0,14 R | **0,28 R** |

Bei 1,0×ATR kostet ein Trade mehr, als er riskiert. Der Break-even bei 1R läge
bei einer Trefferquote von 100 % — die Zeile ist nicht schwierig, sie ist
unmöglich.

## Was der Regime-Prüfstand nicht geleistet hat

Der Prüfstand hatte `donchian_breakout` und `squeeze_breakout` als die sauber
zielenden Kandidaten ausgewiesen und `rsi_reversion` mit 99,9 % Fehlsignalen
verworfen. Auf echten Daten liegt `rsi_reversion` im Mittelfeld und
`squeeze_breakout` am unteren Ende. Der Prüfstand misst also innere
Schlüssigkeit, und die sagt über die Rendite nichts vorher. Als Filter gegen
kaputte Logik bleibt er nützlich; als Vorauswahl war er es nicht.

## Was daraus folgt

Bei 0,05 % Taker-Gebühr je Seite ist 5m-Krypto-Intraday mit diesem Strategietyp
nicht wirtschaftlich. Drei Wege führen aus dieser Rechnung heraus, alle drei
verlassen die bisherige Anlage:

1. **Längerer Zeitrahmen.** Auf 1h- oder 4h-Kerzen ist der ATR ein Vielfaches,
   die Gebühr bleibt gleich. Dieselbe Strategie kostet dort einen Bruchteil.
2. **Andere Gebührenstruktur.** Maker-Orders statt Taker, oder ein Konto mit
   Volumenrabatt. Das ändert die Größenordnung, nicht das Vorzeichen — ohne
   Kante bringt auch das nichts.
3. **Eine andere Signalquelle.** Preis und Volumen auf 5m sind offenbar
   ausgereizt; die sechs getesteten Formen greifen alle darauf zu. Orderbuch,
   Finanzierungsraten oder Cross-Asset-Signale wären etwas anderes, kein
   weiterer Indikator auf denselben Kerzen.

Was nicht folgt: an den Parametern drehen, bis eine Kurve nach oben zeigt. Bei
sechs Strategien, drei Symbolen und einem Profitfaktor um 1,0 im kostenfreien
Lauf findet man diese Kurve garantiert, und sie bedeutet nichts.

## Nachvollziehen

```bash
pip install -r requirements.txt
python -m daytrader fetch --days 540    # ~4 Minuten bei offenem Zugang
python -m daytrader backtest            # -> out/report.md
python -m daytrader costs               # die Kostentabelle oben
```

`out/` ist bewusst nicht im Repo — die Berichte sind aus den Kerzen jederzeit
reproduzierbar, und `trades.csv` allein wiegt 7 MB.
