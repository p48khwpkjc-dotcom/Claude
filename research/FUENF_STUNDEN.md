# 15 bis 25 Prozent im Monat bei höchstens fünf Stunden Haltedauer

Die Frage war, ob das geht, und ob ein gestaffelter Ausstieg dabei hilft:
bei 50 % des Weges zum Ziel der Stop auf Einstand, bei 75 % achtzig Prozent
der Position schließen und der Stop auf 50 %.

Beides ist gemessen. Beide Antworten sind negativ, und zwar aus zwei
verschiedenen Gründen, die sich gegenseitig verstärken.

## Die Zielgröße

| pro Monat | im Jahr |
|---|---|
| 15 % | 5,4× (+435 %) |
| 20 % | 8,9× (+792 %) |
| 25 % | 14,6× (+1.355 %) |

Mit fünf Stunden Haltedauer und einer Position gleichzeitig sind höchstens
rund 4,8 Trades am Tag möglich, also **100 bis 145 im Monat**. Für 20 %
braucht es damit 0,14 bis 0,20 % Gewinn je Trade.

## Die Falle: kurze Haltedauer erzwingt kurze Kerzen, und kurze Kerzen sind teuer

Fünf Stunden müssen in genug Kerzen passen, damit ein Trade überhaupt
arbeiten kann. Auf 1h sind das fünf Kerzen, auf 15m zwanzig. Also drängt die
Zeitvorgabe nach unten.

Nach unten steigen aber die Kosten, weil der ATR schrumpft, während die
Gebühr bleibt (BTCUSDT, Stop bei 2×ATR):

| Zeitrahmen | Median-ATR | Stopabstand | **Kosten je Trade** |
|---|---:|---:|---:|
| 15m | 0,28 % | 0,56 % | **0,32 R** |
| 1h | 0,74 % | 1,48 % | **0,12 R** |
| 4h | 1,54 % | 3,08 % | **0,06 R** |

Ein Trade auf 15m kostet **fünfeinhalbmal** so viel wie auf 4h. Die
Zeitvorgabe drückt also genau dorthin, wo das Handeln am teuersten ist.

## Was dabei herauskommt

Erwartungswert je Trade, Ziel 2R, ohne Ausstiegsmanagement, `train`,
28 Symbole:

| Strategie | 15m (5 h) | 1h (5 h) | 4h (96 h) |
|---|---:|---:|---:|
| vol_expansion | −0,146 | −0,027 | **+0,139** |
| keltner_trend | −0,153 | −0,033 | **+0,133** |
| donchian_breakout | −0,169 | −0,042 | **+0,142** |
| squeeze_breakout | −0,256 | −0,059 | +0,036 |
| fair_value_gap | −0,264 | −0,085 | −0,022 |
| opening_range | −0,346 | −0,113 | −0,008 |
| **random_entry** | **−0,162** | **−0,067** | +0,016 |

Unter der Fünf-Stunden-Grenze ist **jede** Strategie negativ, auf beiden
Zeitrahmen. Und 15m ist nicht besser als 1h, sondern deutlich schlechter —
genau um den Kostenunterschied.

Bemerkenswert ist die letzte Zeile: auf 15m liegt der Münzwurf bei −0,162 R
und die beste Strategie bei −0,146 R. Der Abstand zwischen "bestes Modell aus
17" und "Zufall" beträgt 0,016 R, während die Kosten 0,32 R betragen. Auf
diesem Zeitrahmen entscheidet nicht die Strategie, sondern die Gebühr.

## Das Ausstiegsschema

Vier Pläne, identische Einstiege, Stops und Ziele. 15m mit fünf Stunden,
Stichproben zwischen 24.586 und 145.889 Trades:

| Strategie | A nichts tun | B nur BE bei 50 % | **C das Schema** | D ohne BE |
|---|---:|---:|---:|---:|
| vol_expansion | **−0,146** | −0,149 | −0,163 | −0,161 |
| keltner_trend | **−0,153** | −0,157 | −0,162 | −0,160 |
| donchian_breakout | **−0,169** | −0,174 | −0,182 | −0,179 |
| squeeze_breakout | **−0,256** | −0,261 | −0,267 | −0,265 |
| opening_range | **−0,346** | −0,347 | −0,364 | −0,364 |

Auf beiden Zeitrahmen, in allen sechzehn Vergleichen: **nichts tun ist am
besten.** Das Schema landet jedes Mal darunter.

Der Break-Even-Stop bei 50 % ist der teuerste Teil. Er senkt sogar die
Trefferquote — auf 15m von 36,4 % auf 29,2 % bei `donchian_breakout` —, weil
er Trades bei jedem Rücksetzer über die Hälfte ausstoppt, auch die, die sich
erholt hätten. Plan D, derselbe Teilverkauf ohne den Break-Even-Stop, hat die
höchste Trefferquote aller vier Pläne (39,5 %) und verdient trotzdem weniger
als gar kein Management.

Das ist kein Widerspruch, sondern dieselbe Arithmetik wie beim Teilverkauf
allein: der obere Teil der Gewinnverteilung wird abgeschnitten, die Verluste
bleiben, und jeder zusätzliche Ausstieg zahlt Slippage.

## Was für 20 % im Monat nötig wäre

Bei 100 bis 145 Trades im Monat:

| Kante | Risiko je Trade für 20 %/Monat |
|---|---|
| +0,0366 R (Holdout, gemessen) | rund 5 % |
| +0,0537 R (1h ohne Zeitgrenze) | rund 3,5 % |
| +0,2015 R (4h train — im Holdout nicht bestätigt) | rund 1 % |

Fünf Prozent Risiko je Trade bei 62 % Verlierern heißt: eine Achterserie,
statistisch alle paar Wochen fällig, kostet rund ein Drittel des Kontos. Der
Kill-Switch bei 3 % Tagesverlust würde nach dem ersten Verlierer greifen.

Und die einzige Kante, bei der 1 % Risiko reichen würde, ist die, die im
Holdout von +0,2015 R auf +0,0366 R zusammengefallen ist — und die auf 4h
lebt, wo der Median-Trade zehn Stunden bis zum Ziel braucht.

## Die Antwort

Nein, nicht mit dem, was hier messbar ist. Nicht wegen einer fehlenden
Strategie, sondern weil sich zwei Bedingungen widersprechen: ein Trade
braucht Kerzen, um zu arbeiten, und je kleiner die Kerze, desto größer der
Anteil, den die Gebühr vom Risiko nimmt. Fünf Stunden lassen keinen
Zeitrahmen übrig, auf dem beides zugleich erfüllbar ist.

Was messbar positiv war, sah anders aus: 4h-Kerzen, Haltedauer in Tagen,
+0,14 bis +0,20 R je Trade im `train` — und selbst davon blieb im Holdout nur
+0,0366 R übrig, statistisch nicht von null zu unterscheiden. Das ist kein
Weg zu 20 % im Monat, sondern bestenfalls einer zu einem kleinen Vorteil, der
über viele Symbole und viele Monate gesammelt werden müsste.
