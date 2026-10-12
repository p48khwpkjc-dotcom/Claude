# Warum der Ausbruch scheitert, und was sonst trägt

Festgelegt vor dem ersten Lauf dieser Runde. Die Fragen kommen vom Nutzer:
Dreht der Preis nach dem Stop wieder? Wäre ein Stop am Tages- oder Vortagestief
besser? Ein Ziel am Tages- oder Vortageshoch? Nur montags handeln? Und als neue
Richtung: Krypto über Nacht halten und morgens verkaufen, oder umgekehrt
tagsüber halten.

## Instrumente und Daten

BTC, ETH, SOL, XRP — Binance, 1-Minuten-Kerzen, Oktober 2021 bis Oktober 2026.
Kosten wie überall: 0,05 % je Seite, 3 bp Slippage, 5 bp auf Stops.

## Das gesperrte Jahr

**Alles ab dem 12. Oktober 2025 ist für diese Runde gesperrt.** Diagnose,
Varianten und neue Strategien werden nur auf Oktober 2021 bis Oktober 2025
gerechnet. Diese Runde testet viele Varianten, und unter vielen ist die beste
auch dann gut, wenn nichts dahintersteckt. Das gesperrte Jahr ist die einzige
Zahl, die davon frei bleibt.

Ehrlicherweise dazugesagt: der erste ORB-Lauf (ORB_ERGEBNIS.md) hat dieses
Jahr schon gesehen, als Teil der fünf Jahre. Dort wurde aber nichts
ausgewählt; die neue Auswahl passiert nur auf den vier Jahren davor.

## Teil 1: Diagnose — warum verliert der Ausbruch?

Auf dem 15-Minuten- und dem 1-Minuten-Ausbruch, Stop an der Range, ohne Ziel:

1. **Dreht der Preis nach dem Stop?** Für jeden ausgestoppten Trade: erreicht
   der Kurs danach im selben Handelstag den Einstieg wieder, und erreicht er
   das Ziel, das ein 2R-Trade gehabt hätte? Verglichen mit dem Münzwurf, denn
   ein gewisser Anteil kommt auch rein zufällig zurück.
2. **Wie tief gehen spätere Gewinner zuerst ins Minus?** Verteilung des
   größten Rücksetzers (in R) der Trades, die am Ende im Plus schließen. Liegt
   die Masse knapp vor −1R, sitzt der Stop zu eng.
3. **Wie weit läuft der Ausbruch überhaupt?** Größter Gewinn und größter
   Rücksetzer bis 16:00 in R, Ausbruch gegen Münzwurf.
4. **Wann und an welchen Tagen?** Nach Wochentag, nach Uhrzeit des Signals,
   nach Breite der Range im Verhältnis zur üblichen Schwankung.

## Teil 2: Varianten des Ausbruchs

| Variante | Stop | Ziel |
|---|---|---|
| Basis | andere Range-Seite | 2R, 3R |
| Stop Tagestief | tiefster Kurs heute ab 00:00 New York bis zum Einstieg | 2R, 3R |
| Stop Vortagestief | Tief des Vortags (00:00–24:00 New York) | 2R, 3R |
| Ziel Tageshoch | andere Range-Seite | höchster Kurs heute vor dem Einstieg |
| Ziel Vortageshoch | andere Range-Seite | Hoch des Vortags |
| nur Montag … nur Freitag | wie Basis | wie Basis |

Für Shorts jeweils spiegelbildlich. Liegt ein Stop oder Ziel auf der falschen
Seite des Einstiegs, wird der Trade nicht genommen bzw. ohne Ziel bis 16:00
gehalten; wie oft das passiert, wird mitberichtet.

## Teil 3: Halten nach Tageszeit

| Strategie | Kauf | Verkauf |
|---|---|---|
| Über Nacht | 16:00 New York | 09:30 New York am nächsten Tag |
| Tagsüber | 09:30 New York | 16:00 New York |
| Asien / Europa / USA | Sitzungsbeginn | Sitzungsende (UTC 00–08, 08–13:30, 13:30–20) |
| Wochenende | Freitag 16:00 | Montag 09:30 |

Jeweils mit einem Kauf-und-Verkauf-Zyklus Kosten je Tag, verglichen mit
einfachem Halten über denselben Zeitraum, und nach Wochentag aufgeschlüsselt.

## Wie der Kandidat für das gesperrte Jahr bestimmt wird

Über alle Varianten der Teile 2 und 3, auf den vier Jahren:

1. Erwartungswert nach Kosten positiv, 95-%-Intervall über null.
2. In beiden Hälften der vier Jahre positiv.
3. Auf mindestens drei der vier Coins positiv.

Von den Varianten, die das erfüllen, geht **eine** auf das gesperrte Jahr:
die mit dem größten t-Wert, nicht die mit dem größten Erwartungswert. Erfüllt
keine die drei Bedingungen, ist das das Ergebnis, und das gesperrte Jahr
bleibt zu.

Mitgezählt und berichtet wird, wie viele Varianten insgesamt gerechnet wurden.
