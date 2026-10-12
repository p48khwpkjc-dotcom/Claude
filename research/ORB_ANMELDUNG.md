# New York Open Range Breakout: was getestet wird

Festgelegt vor dem ersten Lauf. Hier wird keine Strategie gesucht, sondern
eine vorgegebene geprüft, also gibt es nichts auszuwählen. Alle Varianten
werden berichtet, auch die schlechten.

## Die Regeln, wie vorgegeben

1. **Opening Range**: Hoch und Tief der ersten fünf Minuten ab der
   New-York-Eröffnung, 09:30 bis 09:35 Uhr New Yorker Zeit. Sommer- und
   Winterzeit werden über die Zeitzone `America/New_York` aufgelöst, nicht
   über einen festen UTC-Versatz.
2. **Signal**: die erste 1-Minuten-Kerze ab 09:35, deren **Schlusskurs** über
   dem Range-Hoch liegt, ist ein Long; die erste, die unter dem Range-Tief
   schließt, ein Short. Ein Trade pro Tag, das erste Signal zählt.
3. **Einstieg**: zur Eröffnung der nächsten Minute. Wer auf den Schlusskurs
   einer Kerze reagiert, kann frühestens danach handeln.
4. **Ausstieg**: Ende der regulären Sitzung, 16:00 Uhr New York — sofern
   vorher nicht Stop oder Ziel greift.

## Die Varianten

| Variante | Stop | Ziel |
|---|---|---|
| Halten bis Schluss | keiner | keines |
| Halten mit Stop | gegenüberliegende Range-Seite | keines |
| 1:1 bis 5:1 | gegenüberliegende Range-Seite | 1R, 1,5R, 2R, 3R, 4R, 5R |

Ein R ist der Abstand vom Einstieg zur gegenüberliegenden Seite der Range.
Das ist die übliche Definition für diese Strategie und gilt auch für die
Variante ohne Stop, damit alle Zeilen in derselben Einheit stehen.

## Instrumente und Kosten

| | Daten | Kosten je Seite |
|---|---|---|
| Bitcoin | Binance BTCUSDT, 1m, fünf Jahre | 0,05 % Gebühr + 3 bp Slippage, 5 bp auf Stops |
| Nasdaq (NQ) | sobald verfügbar | 0,0015 % Kommission + 0,5 bp Slippage |
| S&P 500 (ES) | sobald verfügbar | 0,0015 % Kommission + 0,5 bp Slippage |

Die Futures-Kosten entsprechen rund 4 bis 5 Dollar Kommission je Kontrakt und
Runde plus etwa einem Tick Slippage. Sie liegen damit um mehr als eine
Größenordnung unter den Krypto-Kosten — das wird für diese Strategie
wahrscheinlich der wichtigste Unterschied zwischen den Instrumenten.

Bitcoin handelt rund um die Uhr. Damit die Ergebnisse vergleichbar sind,
gelten dieselben New-Yorker Zeiten.

## Pessimistische Regeln, wie überall in diesem Projekt

- Berührt eine Kerze Stop und Ziel, gilt der Stop.
- Eröffnet eine Kerze jenseits des Stops, wird zur Eröffnung gefüllt, nicht
  am Stop.
- Jeder Fill zahlt Gebühr und Slippage.

## Kontrollen

- **Ohne Kosten**: trennt "keine Kante" von "Kante zu klein".
- **Münzwurf**: dieselben Tage, dieselbe Einstiegsminute, dieselbe Geometrie,
  aber die Richtung zufällig. Was der Münzwurf schafft, kommt aus der
  Geometrie und nicht aus dem Ausbruch.
- **Erste gegen zweite Hälfte** der Historie: hält das Ergebnis über die Zeit?

## Was als Ergebnis gilt

Eine Variante gilt als tragfähig, wenn der Erwartungswert nach Kosten positiv
ist, das 95-%-Intervall die Null nicht enthält, und sie in **beiden** Hälften
der Historie positiv ist. Bei sieben Varianten je Instrument wird außerdem
genannt, dass die beste von sieben auch zufällig gut aussehen kann.
