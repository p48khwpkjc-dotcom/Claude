# Höhere Zeitrahmen und die Frage der Haltedauer

[ERGEBNIS.md](ERGEBNIS.md) endete mit drei offenen Richtungen. Die erste — ein
längerer Zeitrahmen, wo derselbe Trade einen Bruchteil kostet — ist hiermit
durchgerechnet: 15m, 30m und 1h als Entscheidungsrahmen, 4h als Trendfilter,
900 Tage Historie (20. März 2024 bis 6. September 2026), dieselben sechs
Strategien, dieselbe Engine.

Vorgabe war zunächst, keinen Trade länger als drei Stunden zu halten. Diese
Vorgabe erwies sich als der bestimmende Faktor — sie steht deshalb im Zentrum
des zweiten Teils.

## Teil 1: Der Zeitrahmen tut, was die Kostenrechnung verspricht

Der ATR wächst mit der Kerze, die Gebühr bleibt gleich. Damit fällt der Preis
eines Trades, gemessen in Risikoeinheiten (BTCUSDT, Stop bei 2×ATR):

| Zeitrahmen | Median-ATR | Stop-Abstand | Kosten pro Trade |
|---|---:|---:|---:|
| 5m | 0,13 % | 0,26 % | 0,69 R |
| 15m | 0,28 % | 0,57 % | 0,32 R |
| 30m | 0,42 % | 0,85 % | 0,21 R |
| 1h | 0,62 % | 1,24 % | 0,15 R |

Von 5m auf 1h wird ein Trade also viereinhalbmal billiger. Der Backtest folgt
dem, Profitfaktor außerhalb der Stichprobe, bester Wert je Zeitrahmen:

| Zeitrahmen | bester PF | schlechtester PF | bester Erwartungswert |
|---|---:|---:|---:|
| 5m | 0,50 | 0,37 | −0,41 R |
| 15m | 0,70 | 0,54 | −0,20 R |
| 30m | 0,80 | 0,57 | −0,09 R |
| 1h | 0,80 | 0,64 | −0,07 R |

Jede Zeile ist besser als die davor, und die Verbesserung entspricht der
Ersparnis. Über 1,0 kommt trotzdem nichts.

## Teil 2: Die drei Stunden waren das Problem

Der Verdacht kam aus der Ausstiegsstatistik. Bei drei Stunden Höchsthaltedauer
enden die Trades so:

| Zeitrahmen | Zeit-Stopp | Stop-Loss | **Ziel** | Trailing |
|---|---:|---:|---:|---:|
| 15m | 24,7 % | 38,5 % | **19,7 %** | 17,1 % |
| 30m | 45,6 % | 32,0 % | **14,1 %** | 8,3 % |
| 1h | 65,6 % | 21,5 % | **9,5 %** | 3,4 % |

Auf 1h-Kerzen läuft also fast jeder zweite bis dritte Trade nicht in Stop oder
Ziel, sondern in die Uhr. Drei Stunden sind dort drei Kerzen. Das ist kein Test
des Zeitrahmens mehr, das ist ein Test der Vorgabe.

### Wie lange ein Trade wirklich braucht

Derselbe Lauf ohne wirksame Zeitgrenze (240 Stunden), damit die Verteilung nicht
abgeschnitten ist. Haltedauer bis zum Ziel, nur für Trades, die es erreichen:

| Strategie | 15m | 30m | 1h |
|---|---:|---:|---:|
| donchian_breakout | 2,0 h | 5,0 h | 10,0 h |
| squeeze_breakout | 1,0 h | 2,2 h | 6,0 h |
| rsi_reversion | 2,2 h | 5,0 h | 8,5 h |
| vwap_reversion | 3,2 h | 5,5 h | 9,5 h |
| ema_momentum | 1,0 h | 2,5 h | 6,0 h |
| opening_range | 0,5 h | 1,0 h | 2,0 h |

*(Median. Die Zeit bis zum Ziel skaliert mit der Kerzengröße — was auf 5m in
einer Stunde passiert, braucht auf 1h zwölf.)*

### Die eigentliche Antwort: Wahrscheinlichkeit statt Median

Der Median oben zählt nur die Gewinner. Interessant ist der Anteil **aller**
Trades, die innerhalb von H Stunden ins Ziel laufen:

| Zeitrahmen | 3 h | 6 h | 8 h | 12 h | 24 h | 48 h | Obergrenze |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15m | 20,1 % | 24,3 % | 25,5 % | 26,4 % | 27,3 % | 27,5 % | **27,5 %** |
| 30m | 15,7 % | 21,1 % | 23,3 % | 25,9 % | 28,6 % | 29,0 % | **29,0 %** |
| 1h | 9,8 % | 14,5 % | 17,1 % | 21,8 % | 27,5 % | 29,2 % | **29,3 %** |

Zwei Dinge stehen darin.

**Erstens: es gibt eine harte Decke bei rund 29 %.** Egal wie lange man hält,
mehr als knapp drei von zehn Trades erreichen ihr Ziel nie — der Rest wird
vorher ausgestoppt oder vom Trailing eingesammelt. „Lange genug halten" macht
aus einem Trade keinen Gewinner; es entscheidet nur, ob die knapp 30 %, die
ohnehin ankommen, auch ankommen dürfen.

**Zweitens: wo die Kurve flach wird, hängt am Zeitrahmen.** Um rund 90 % des
Erreichbaren mitzunehmen, braucht es:

- **15m → etwa 8 Stunden** (25,5 % von 27,5 %)
- **30m → etwa 12 Stunden** (25,9 % von 29,0 %)
- **1h → etwa 24 Stunden** (27,5 % von 29,3 %)

Das sind jeweils **24 bis 32 Kerzen**. Die Faustregel lautet also nicht „drei
Stunden", sondern „rund dreißig Kerzen" — und die Uhr richtet sich danach, wie
groß eine Kerze ist.

Bei drei Stunden bekommt 15m noch 73 % des Erreichbaren, 30m nur 54 % und 1h
gerade 33 %. Genau in dieser Reihenfolge hat die Vorgabe die höheren Zeitrahmen
bestraft.

### Was längeres Halten am Ergebnis ändert

Bester Profitfaktor außerhalb der Stichprobe, je Zeitrahmen und Zeitgrenze:

| Zeitrahmen | 3 h | 6 h | 12 h | 24 h |
|---|---:|---:|---:|---:|
| 15m | 0,70 | 0,70 | 0,71 | 0,73 |
| 30m | 0,80 | 0,84 | 0,82 | 0,85 |
| 1h | 0,80 | 0,96 | 1,12 | 1,14 |

Auf 15m ist die Zeitgrenze fast wirkungslos — dort passt der Trade ohnehin
hinein. Auf 1h ist sie der wichtigste einzelne Parameter im ganzen Test.

## Teil 3: Auf 1h existiert eine Kante — sie ist nur kleiner als die Gebühr

Der Kontrolllauf mit Gebühren und Slippage auf null trennt „keine Kante" von
„Kante zu klein". Profitfaktor in beiden Hälften:

| Zeitrahmen | Strategien, die in **beiden** Hälften über 1,0 liegen |
|---|---|
| 5m | 0 von 6 |
| 15m | 1 von 6 |
| 30m | 1 von 6 |
| **1h** | **5 von 6** |

Auf 1h liegen `donchian_breakout` (1,07 / 1,14), `ema_momentum` (1,09 / 1,10),
`opening_range` (1,10 / 1,17), `squeeze_breakout` (1,20 / 1,29) und
`vwap_reversion` (1,11 / 1,14) in Stichprobe *und* außerhalb über eins, mit
ähnlichen Werten in beiden Hälften. Das ist etwas anderes als auf 5m, wo dieselbe
Rechnung einen Münzwurf ergab und die Rangfolge zwischen den Hälften kippte.

Die Größe dieser Kante: **+0,03 bis +0,08 R pro Trade.** Die Kosten auf 1h bei
2×ATR: **0,15 R.** Damit ist die Rechnung entschieden, und zwar knapp.

## Teil 4: Der Grenzfall — Maker-Gebühren

Wenn die Kante real und nur zu klein ist, muss die Gebühr unter sie fallen.
Derselbe Lauf mit 0,02 % Maker statt 0,05 % Taker, Slippage 1 bp statt 3, auf 1h
mit 24 Stunden Haltedauer:

| Strategie | PF in-sample | PF out-of-sample | Trades (out) |
|---|---:|---:|---:|
| vwap_reversion | 1,14 | 1,33 | 104 |
| donchian_breakout | 1,06 | 1,07 | 633 |
| squeeze_breakout | 1,02 | 1,03 | 530 |
| ema_momentum | 1,04 | 0,85 | 177 |
| opening_range | 0,91 | 0,95 | 519 |
| rsi_reversion | 0,68 | 0,78 | 344 |

Drei Strategien stehen in beiden Hälften über eins. `donchian_breakout` und
`squeeze_breakout` tun das mit ordentlichen Stichproben und beinahe identischen
Werten drinnen wie draußen — das sieht nicht nach Zufall aus.

**Nur: diese Zahlen sind nicht handelbar.** Eine Maker-Order ist eine Limit-Order,
die im Buch liegt und darauf wartet, dass jemand sie nimmt. Ein Kanalausbruch
kauft aber genau dann, wenn der Kurs durch das Niveau *hindurchgeht* — eine
Limit-Order dort füllt bevorzugt in den Fällen, in denen der Ausbruch scheitert
und der Kurs zurückkommt. Die Engine kann diese Negativauslese nicht abbilden;
sie unterstellt, dass jede Order zum Wunschpreis fällt. Der Lauf ist damit eine
Obergrenze, kein Plan: *selbst* unter der günstigsten denkbaren Kostenannahme
kommt eine Ausbruchsstrategie auf 1,03 bis 1,07.

## Was das alles zusammen bedeutet

Ich habe in diesem Durchgang 72 Kombinationen gerechnet (3 Zeitrahmen × 4
Haltedauern × 6 Strategien). Davon lagen außerhalb der Stichprobe **zwei** über
einem Profitfaktor von 1,0, und nur **eine** davon auch innerhalb — mit 1,01, an
der Kippe. Der Median über alle 72 Zellen liegt bei 0,70.

Das ist wichtig für die Bewertung der einen guten Zelle (`vwap_reversion`, 1h,
24h Haltedauer, PF 1,14): Bei 72 Versuchen ist eine Zelle über 1,1 keine
Entdeckung, sondern die Erwartung. Der Blick auf die Einzelsymbole bestätigt es —
in der Stichprobe verliert dieselbe Strategie auf BTC (0,78) und ETH (0,69) und
gewinnt nur auf SOL (1,55). Bei 36 Trades je Symbol ist das Rauschen.

Drei belastbare Ergebnisse bleiben:

1. **Der Zeitrahmen wirkt, und zwar genau so stark wie vorhergesagt.** Von 5m auf
   1h wird ein Trade viereinhalbmal billiger, und der Erwartungswert verbessert
   sich von −0,41 R auf −0,07 R.
2. **Die Haltedauer muss zum Zeitrahmen passen, nicht zur Uhr.** Rund dreißig
   Kerzen, also 8 h auf 15m, 12 h auf 30m, 24 h auf 1h. Drei Stunden auf 1h
   verschenken zwei Drittel der erreichbaren Ziele.
3. **Auf 1h existiert eine kleine, in beiden Hälften stabile Rohkante von +0,03
   bis +0,08 R** — und die Taker-Gebühr von 0,15 R pro Trade ist größer als sie.

Der Abstand ist damit zum ersten Mal beziffert statt nur behauptet: es fehlen
etwa 0,1 R pro Trade. Das ist kein Parameterproblem. Entweder die Gebühr sinkt
unter die Kante — realistisch nur mit Limit-Einstiegen, die eine Ausbruchsstrategie
nicht bekommt — oder die Kante muss wachsen, und dafür braucht es ein Signal,
das nicht aus Preis und Volumen derselben Kerzen stammt.

## Nachvollziehen

```bash
python -m daytrader fetch --interval 1h --days 900
python -m daytrader -c mein_1h.yaml costs
python -m daytrader -c mein_1h.yaml backtest
```

Die Konfigurationen unterscheiden sich von `config.yaml` nur in `interval`,
`htf_interval` (4h), `history_days` (900), `max_hold_hours` und `cooldown_bars`
(auf etwa eine Stunde Wanduhr skaliert: 4 / 2 / 1 Kerzen bei 15m / 30m / 1h).
