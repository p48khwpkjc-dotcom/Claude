# Trefferquote und Chance-Risiko-Verhältnis

Die Aufgabe lautete: so lange Strategien durchgehen, bis eine 70 % Trefferquote
bei 2:1 bis 3:1 liefert, und dabei das Internet nach allem absuchen, was das
verspricht — TJR, ICT, Smart Money Concepts.

Das Ergebnis ist keine gefundene Strategie, sondern eine vermessene Kurve. Die
beiden Größen lassen sich nicht unabhängig einstellen, und die Messung sagt,
wie teuer jeder Prozentpunkt Trefferquote ist.

## Der Aufbau

17 Strategien, darunter drei nach den veröffentlichten ICT/SMC-Definitionen neu
gebaut. Ziel-R von 0,25 bis 3,0. Trailing aus, damit ein Treffer genau eine
Sache bedeutet. 28 Symbole, sieben Jahre, Segment `train`. Stichproben bis
64.270 Trades. Kosten wie überall: 0,05 % Taker je Seite, 3 bp Slippage.

Dazu ein Nullmodell, `random_entry`: ein Münzwurf mit demselben Stop und
demselben Ziel. Es beantwortet die Frage, die bei jeder Trefferquote zuerst zu
stellen ist — wie viel davon hätte auch ein Würfel geschafft?

## Die Kurve

Trefferquote in Prozent, auf 4h:

| Strategie | 0,25R | 0,5R | 0,75R | 1R | 1,5R | 2R | 2,5R | 3R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| vol_expansion | 82,2 | **70,6** | 61,4 | 54,6 | 47,6 | 44,5 | 42,5 | 42,2 |
| keltner_trend | 82,3 | **70,1** | 61,0 | 54,1 | 46,6 | 43,7 | 42,4 | 41,5 |
| donchian_breakout | 82,0 | **70,0** | 61,3 | 54,8 | 46,9 | 43,4 | 41,8 | 41,2 |
| squeeze_breakout | 81,6 | 69,7 | 60,7 | 53,3 | 43,4 | 38,2 | 35,3 | 33,5 |
| momentum_persistence | 78,9 | 63,4 | 55,1 | 50,3 | 47,2 | 46,8 | 46,5 | 46,3 |
| opening_range | 77,2 | 67,8 | 59,1 | 52,2 | 42,5 | 36,0 | 31,8 | 29,4 |
| failed_breakout | 77,4 | 64,4 | 54,4 | 47,2 | 38,3 | 34,5 | 32,7 | 32,0 |
| fair_value_gap | 76,6 | 65,4 | 57,0 | 50,6 | 41,8 | 36,7 | 33,6 | 31,8 |
| order_block | 70,0 | 62,0 | 54,3 | 47,0 | 38,6 | 34,0 | 30,8 | 28,8 |

**70 % ist erreichbar.** Sechs Strategien schneiden die Linie. Alle bei 0,5R
oder darunter, keine bei 2R oder darüber.

## Was an der 70-Prozent-Stelle verdient wird

Derselbe Lauf, Erwartungswert in R:

| Strategie | 0,25R | 0,5R | 1R | 2R | 3R |
|---|---:|---:|---:|---:|---:|
| donchian_breakout | −0,014 | **+0,013** | +0,058 | +0,142 | **+0,202** |
| vol_expansion | −0,012 | **+0,022** | +0,049 | +0,139 | **+0,186** |
| keltner_trend | −0,010 | **+0,016** | +0,047 | +0,133 | **+0,170** |
| momentum_persistence | −0,031 | −0,039 | −0,017 | +0,089 | +0,116 |
| squeeze_breakout | −0,029 | −0,006 | +0,015 | +0,036 | +0,049 |

Die Spalte mit 70 % Trefferquote (0,5R) und die Spalte mit dem höchsten Gewinn
(3R) sind verschiedene Spalten, und zwar die beiden Enden der Tabelle.
`donchian_breakout` verdient bei 70 % Trefferquote **+0,013 R**, bei 41 %
Trefferquote **+0,202 R** — das **Fünfzehnfache**.

Wer die Trefferquote maximiert, minimiert den Gewinn. Das ist hier keine
Redewendung, sondern die gemessene Form derselben Tabelle.

Und die Strategien, die 70 % erst bei 0,25R erreichen, verdienen dort gar
nichts mehr: `order_block` −0,182 R, `fair_value_gap` −0,097 R,
`opening_range` −0,096 R. Hohe Quote, sicherer Verlust.

## Warum 70 % bei 2:1 nicht am Rand des Erreichbaren liegt

Bei 2R muss der Kurs den doppelten Stopabstand zurücklegen, bevor er den
einfachen erreicht. Der Münzwurf `random_entry` schafft das in **41,0 %** der
Fälle — das ist der Anteil, der allein aus der Geometrie kommt.

Die beste gemessene Strategie liegt bei 46,8 %. Ihr tatsächlicher
Informationsgehalt ist also **rund sechs Prozentpunkte**. Für 70 % bräuchte
man **29**. Der Zielwert liegt nicht knapp außerhalb der Reichweite, sondern
um eine Größenordnung daneben.

## Was Teilverkäufe daran ändern

Nichts Gutes. Drei Ausstiegspolitiken bei identischen Einstiegen:

- **A** ohne Teilverkauf
- **B** die Hälfte raus bei 75 % des Weges zum Ziel, Stop bleibt
- **C** dasselbe, danach Stop auf Einstand

Sechzehn Kombinationen aus Strategie und Ziel, **kein einziger Ausnahmefall**:

| Strategie (2R) | Treffer A → B | Erwartungswert A → B |
|---|---|---|
| donchian_breakout | 43,5 % → 46,8 % | +0,142 → +0,120 R |
| vol_expansion | 44,5 % → 47,8 % | +0,139 → +0,123 R |
| squeeze_breakout | 38,2 % → 43,1 % | +0,036 → +0,029 R |
| fair_value_gap | 36,7 % → 41,2 % | −0,022 → −0,034 R |
| random_entry | 41,0 % → 43,6 % | +0,016 → +0,004 R |

Der Münzwurf zeigt den Mechanismus am klarsten: **drei Viertel des Gewinns**
gegen 2,6 Prozentpunkte Trefferquote eingetauscht. Es wird nichts besser
vorhergesagt — der obere Teil der Gewinnverteilung wird abgeschnitten, während
die Verluste bleiben, wie sie waren.

Politik C ist durchweg noch etwas schlechter als B: der Stop auf Einstand
stoppt Trades aus, die sich erholt hätten.

Der Test `test_breakeven_after_partial_turns_that_loser_into_a_profit` hält den
Mechanismus in einer Zeile fest: derselbe Kursverlauf ergibt ohne Teilverkauf
−0,25 R, mit Teilverkauf und Stop auf Einstand **+0,75 R** — und wird dann als
Gewinner gezählt. So entstehen die Quoten, die in Kursen gezeigt werden.

## Was die Recherche ergab

TJR lehrt eine Neuverpackung von ICT und Smart Money Concepts: Liquidity
Sweeps, Order Blocks, Fair Value Gaps, Market Structure, mit Fokus auf den
London- und New-York-Open.

| Quelle | Angegebene Trefferquote |
|---|---|
| Marketing und Community | 65–75 % bei RR über 1:2,5 |
| Ein Backtest über 2.600 Trades | 61 %, PF 2,17 |
| **Unabhängige mechanische Backtests** | **38–48 %** |
| **Diese Messung (2R, 4h, 28 Symbole)** | **34–37 %** |

Meine Zahlen liegen am unteren Rand des unabhängigen Korridors, was zu
erwarten ist: hier werden Gebühren und Slippage mitgerechnet.

Wo 70 % wirklich vorkommt, ist es immer dieselbe Konstruktion:

- **Mean Reversion mit engem Ziel und weitem Stop** — 70 bis 85 % ist dort
  normal. Ein Münzwurf mit Ziel 0,3R gewinnt 76,9 %.
- **Grid und Martingale** — hohe kurzfristige Quote bei nicht-null
  Wahrscheinlichkeit eines kontoauslöschenden Drawdowns, formal das
  Gambler's-Ruin-Problem.
- **Optionsverkauf** — hohe Quote durch Zeitwertverfall, bezahlt im Tail.

## Die brauchbare Antwort

Wenn das Ziel Geld ist und nicht die Quote, steht das Optimum in derselben
Tabelle, nur am anderen Ende: **`donchian_breakout` auf 4h mit 3R-Ziel** —
41,2 % Trefferquote, **+0,202 R** je Trade, 2.754 Trades. Oder `vol_expansion`
mit +0,186 R.

Das fühlt sich schlechter an, weil sechs von zehn Trades verlieren. Es
verdient das Fünfzehnfache.
