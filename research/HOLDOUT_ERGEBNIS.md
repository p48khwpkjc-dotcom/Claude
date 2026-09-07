# Das Holdout-Ergebnis

Ausgeführt nach [HOLDOUT_ANMELDUNG.md](HOLDOUT_ANMELDUNG.md), einmal, auf Daten
ab dem 24. Januar 2026, die während der gesamten Untersuchung nicht angefasst
wurden. Das Segment ist damit verbraucht.

## Die Zahl

| Kennzahl | train (2019–2025) | **holdout (ab 2026-01-24)** |
|---|---:|---:|
| Trades | 2.754 | **634** |
| Trefferquote | 41,18 % | **38,49 %** |
| Profitfaktor | 1,349 | **1,059** |
| Erwartungswert | +0,2015 R | **+0,0366 R** |
| Symbole profitabel | 23 von 28 | **15 von 28** |

Vom Erwartungswert sind **82 Prozent verschwunden**. Die Breite ist von 82 % der
Symbole auf 54 % gefallen — knapp über dem Münzwurf.

## Was davon statistisch übrig bleibt

Die 634 Trades streuen mit einer Standardabweichung von 1,49 R:

| | |
|---|---|
| Standardfehler | 0,0592 R |
| t-Wert | **0,62** |
| 95-%-Intervall | **−0,079 bis +0,153 R** |

Das Intervall enthält die Null. Der gemessene Vorteil ist von "kein Vorteil"
nicht zu unterscheiden.

Um einen Effekt dieser Größe von null zu trennen, bräuchte man rund **6.364
Trades** — das Zehnfache dessen, was das Holdout hergibt. Und das Holdout ist
nicht klein, weil ich zu wenig geholt hätte: es sind siebeneinhalb Monate über
28 Symbole. Der Effekt ist klein, nicht die Stichprobe.

Die zweite Zahl ist die unbequemere: der Train-Erwartungswert von +0,2015 R
liegt **2,8 Standardfehler** über dem Holdout-Mittel. Das ist zu viel für
Zufall. Die Train-Schätzung war nicht nur verrauscht, sie war überhöht — das
ist die Signatur einer Überanpassung, auch wenn die Anpassung nie absichtlich
stattgefunden hat.

## Das vorher festgelegte Urteil

Angemeldet war: Bestätigung bei positivem Erwartungswert **und** Profitfaktor
über 1,15; Widerlegung bei Profitfaktor unter 1,0; dazwischen lautet die
ehrliche Antwort "zu wenig Daten".

Der Profitfaktor liegt bei **1,059**. Also weder das eine noch das andere,
sondern genau der mittlere Fall — und der wird jetzt so berichtet, wie es
vorher festgelegt wurde, statt in die günstigere Richtung gedeutet zu werden.

Er liegt zudem unter dem angemeldeten Band von 1,1 bis 1,6, das mit der
Train-Schätzung vereinbar gewesen wäre. Das Ergebnis ist also schwächer als
selbst die pessimistische Vorabrechnung.

## Was das praktisch heißt

Nach sieben Monaten ungesehener Daten hat die beste Konfiguration aus der
gesamten Untersuchung weder verlässlich verdient noch klar verloren. Die beste
Schätzung ihres wahren Erwartungswerts liegt irgendwo zwischen −0,08 R und
+0,15 R je Trade. Auf dieser Grundlage Geld zu riskieren, hieße, auf die obere
Hälfte eines Intervalls zu setzen, dessen untere Hälfte den Verlust enthält.

Es heißt auch nicht, dass die Strategie wertlos ist. Es heißt, dass die
vorhandenen Daten die Frage nicht beantworten können.

## Was jetzt nicht passiert

Kein zweiter Kandidat, keine Parametervariante, kein anderes Ziel-R "zum
Vergleich". Das Holdout ist verbraucht; jede weitere Zahl daraus wäre eine
Testzahl, keine Out-of-Sample-Zahl.

Belastbarere Aussagen brauchen Daten, die es heute noch nicht gibt: Kurse aus
der Zukunft, ein anderer Markt, oder ein Effekt, der groß genug ist, um sich
in weniger als sechstausend Trades zu zeigen. Von diesen dreien ist der letzte
der einzige, an dem sich arbeiten lässt — und die Kostenrechnung aus
[../ERGEBNIS.md](../ERGEBNIS.md) sagt, wo die Grenze dafür liegt.
