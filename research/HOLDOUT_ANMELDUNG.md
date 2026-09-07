# Anmeldung des Holdout-Laufs

Geschrieben und committet **vor** der Ausführung. Das Holdout-Segment war seit
Beginn dieser Untersuchung unberührt; es kann genau einmal benutzt werden. Wer
erst hinterher festlegt, was er getestet hat, hat kein Holdout, sondern ein
weiteres Testsegment.

## Was getestet wird

Genau eine Konfiguration, keine Varianten, keine Auswahl im Nachhinein:

| | |
|---|---|
| Strategie | `donchian_breakout` |
| Entscheidungsrahmen | 4h |
| Trendfilter | 1d |
| Kanal | 48 Kerzen (Vorgabewert) |
| Stop | 2,0 × ATR (Vorgabewert) |
| **Ziel** | **3,0 R** |
| Trailing | aus |
| Haltedauer | 96 h |
| Teilverkäufe | keine |
| Universum | dieselben 28 Symbole |
| Kosten | 0,05 % Taker je Seite, 3 bp Slippage, 5 bp auf Stops |
| Segment | `holdout`, ab 2026-01-24 |

Warum diese und keine andere: sie hat in
[TREFFERQUOTE.md](TREFFERQUOTE.md) den höchsten Erwartungswert des gesamten
Feldes, und sie erreicht ihn mit der größten Stichprobe der Spitzengruppe.
Nicht gewählt wurde die Einstellung mit der höchsten Trefferquote — die
verdient das Fünfzehntel.

## Die Referenz, an der sie gemessen wird

Auf `train` (2019 bis 2025-06-13), 2.754 Trades:

| Kennzahl | train |
|---|---:|
| Trefferquote | 41,18 % |
| Profitfaktor | 1,349 |
| Erwartungswert | +0,2015 R |

## Was vorher als Erwartung festgehalten wird

Das Holdout umfasst rund siebeneinhalb Monate gegen sechs Jahre train, also
ist mit grob 250 bis 400 Trades zu rechnen. Bei dieser Zahl hat ein
Profitfaktor breite Fehlerbalken — ein Wert zwischen etwa 1,1 und 1,6 wäre mit
der Train-Schätzung vereinbar, ohne dass irgendetwas gelernt wurde.

Als Bestätigung gilt: **Erwartungswert positiv und Profitfaktor über 1,15.**
Als Widerlegung: Profitfaktor unter 1,0.
Dazwischen liegt der Bereich, in dem die ehrliche Antwort "zu wenig Daten"
lautet, und dann wird auch das so berichtet.

Zusätzlich zählt die Breite: auf wie vielen der 28 Symbole ist das Ergebnis
positiv? Ein Profitfaktor, der aus zwei Symbolen kommt, ist kein Ergebnis.

## Was danach nicht mehr passiert

Nach diesem Lauf ist das Holdout verbraucht. Es wird kein zweiter Kandidat
nachgeschoben, keine Parametervariante nachgereicht und kein anderes Ziel-R
"zum Vergleich" nachgerechnet. Falls das Ergebnis enttäuscht, ist das das
Ergebnis. Weitere belastbare Zahlen brauchen dann neue Daten — spätere
Kursdaten, die es heute noch nicht gibt, oder ein anderes Marktsegment.
