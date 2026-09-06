# Suchprotokoll

Festgelegt **vor** dem ersten Suchlauf. Wer eine Auswahlregel erst formuliert,
nachdem er die Ergebnisse gesehen hat, hat keine Regel, sondern eine Ausrede.

## Warum es dieses Dokument gibt

Die Aufgabe lautete: so viele Strategien durchgehen, bis eine funktioniert. Bei
genügend Versuchen findet man immer eine — im letzten Durchgang lag von 72
Kombinationen genau eine über einem Profitfaktor von 1,0, und die zerfiel beim
Blick auf die Einzelsymbole. Eine breite Suche ist trotzdem legitim, aber nur
mit einem Netz darunter. Das Netz besteht aus drei Teilen: einem Segment, das
während der Suche nicht angefasst wird, einer Regel, die vorher feststeht, und
einer ehrlichen Zählung, wie oft überhaupt gewürfelt wurde.

## Datenaufteilung

Universum: 12 liquide USDT-Paare statt bisher 3. 900 Tage 1h- und 4h-Kerzen.

| Segment | Anteil | Zweck |
|---|---|---|
| **train** | erste 50 % | Auswahl. Hier darf beliebig oft geschaut werden. |
| **test** | mittlere 25 % | Bestätigung des auf train Ausgewählten. Einmal je Kandidat. |
| **holdout** | letzte 25 % | **Wird während der Suche nicht berührt.** Einmal, ganz am Ende, für genau einen Kandidaten. |

Sobald das Holdout-Segment für einen Kandidaten gelaufen ist, ist es verbraucht.
Ein zweiter Blick darauf — mit anderen Parametern, einer anderen Strategie, einer
anderen Haltedauer — macht es zu einem weiteren Testsegment und die Zahl
wertlos.

## Auswahlregel

Ein Kandidat kommt in die engere Wahl, wenn er **auf train** alle vier Hürden
nimmt:

1. **Mindestens 300 Trades.** Darunter ist der Profitfaktor Rauschen.
2. **Profitfaktor über 1,10.** Nicht 1,0: der Abstand ist der Puffer gegen
   Schätzfehler und gegen die Gebührenannahme.
3. **Auf mindestens 60 % der Symbole profitabel.** Eine Strategie, die ihr
   Ergebnis aus einem Symbol zieht, hat kein Signal gefunden, sondern eine
   Kursgeschichte.
4. **Erwartungswert über +0,05 R.** Das ist die Größenordnung, ab der die
   Taker-Gebühr von 0,15 R überhaupt schlagbar wäre.

Von den Überlebenden geht **einer** weiter, und zwar der mit dem höchsten
Profitfaktor auf train. Nicht der mit dem besten Testergebnis — sonst wäre die
Auswahl wieder auf dem Testsegment passiert.

Dieser eine wird auf **test** geprüft. Fällt er dort unter 1,0, ist das das
Ergebnis der Suche, und es wird berichtet. Es wird dann **nicht** der
Zweitplatzierte nachgeschoben; das wäre dieselbe Rosinenpickerei eine Ebene
tiefer.

Besteht er test, geht er einmal auf **holdout**.

## Was mitprotokolliert wird

- Die Gesamtzahl gerechneter Kombinationen. Ohne sie ist jeder Fund unbewertbar.
- Der Median über alle Kombinationen. Ein Bestwert ist nur gegen die Verteilung
  zu lesen, aus der er stammt.
- Für den Gewinner: Ergebnis je Symbol, nicht nur der Durchschnitt.

## Kostenannahme

0,05 % Taker je Seite, 3 bp Slippage, 5 bp auf Stops — wie in `config.yaml`.
Maker-Gebühren werden nicht unterstellt: Ausbruchsstrategien bekommen keine
Maker-Fills, und die Negativauslese dabei kann die Engine nicht abbilden
(siehe ZEITRAHMEN.md, Teil 4).
