# Ergebnis: Diagnose, Varianten, Halten nach Tageszeit

Gerechnet nach [SESSION_ANMELDUNG.md](SESSION_ANMELDUNG.md) auf BTC, ETH, SOL
und XRP, Oktober 2021 bis Oktober 2025. **Das gesperrte Jahr ab dem
12. Oktober 2025 wurde nicht geöffnet**, weil kein Kandidat die Regel
bestanden hat.

Kosten wie überall: 0,05 % je Seite, 3 bp Slippage, 5 bp auf Stops.

## Der Ausbruch auf allen vier Coins

1m-, 5m- und 15m-Signale, Ziele von 1:1 bis 5:1 in halben Schritten, jeder Tag
und nur Werktage (Fünf-Jahres-Lauf, wie zuerst bei Bitcoin): **216 Zellen,
keine mit Erwartungswert über null nach Kosten.** Bestes Ergebnis je Coin:

| | 1m | 5m | 15m | 15m, nur Werktage |
|---|---:|---:|---:|---:|
| BTC | −0,52 R | −0,45 R | −0,21 R | −0,008 R |
| ETH | −0,36 R | −0,31 R | −0,15 R | −0,024 R |
| SOL | −0,28 R | −0,23 R | −0,07 R | −0,006 R |
| XRP | −0,42 R | −0,35 R | −0,23 R | −0,123 R |

Je größer die Signalkerze, desto breiter die Range und desto kleiner der
Kostenanteil (BTC: 0,37 R bei 1m, 0,20 R bei 15m). An null kommt nur der
15-Minuten-Ausbruch an Werktagen heran, nicht darüber.

## Warum er scheitert

Bitcoin, Diagnose neben dem Münzwurf (gleicher Tag, gleiche Minute, gleicher
Abstand, zufällige Richtung):

**Der Kurs dreht nach dem Stop oft zurück — aber nicht wegen des Ausbruchs.**
Beim 1m-Ausbruch werden 77 % der Trades ausgestoppt; 68 % davon sind noch am
selben Tag zurück am Einstieg (Median 32 Minuten), 32 % laufen sogar bis zum
2R-Ziel. Beim Münzwurf: 70 % und 34 %. Die Range ist enger als die normale
Schwankung, Stop und Einstieg liegen rund 0,3 % auseinander.

**Der Stop sitzt zu eng.** Von den Trades, die bis 16:00 gehalten im Gewinn
schließen, fallen beim 1m-Ausbruch 54 % vorher unter −1R. Bei 15m sind es 23 %.

**Die Richtung des Ausbruchs trägt keine Information.** Bis 16:00 erreichen
+1R / +2R / +3R: Ausbruch 71 % / 51 % / 38 %, Münzwurf 73 % / 53 % / 38 %.

**Wochenenden und schmale Ranges sind am teuersten**, weil die Kosten im
Verhältnis zur Range dort am größten sind: Samstag −1,67 R, Sonntag −1,16 R
(1m); schmalstes Viertel −1,08 R, breitestes −0,08 R.

## Die Varianten

30 Varianten, gepoolt über die vier Coins. Keine besteht die Regel. Was man
daraus lernt:

| Variante (Stop / Ziel) | 1m | 15m |
|---|---:|---:|
| Range / 2R (Basis) | −0,41 R | −0,18 R |
| **Tagestief / 2R** | **−0,11 R** | **−0,09 R** |
| Tagestief / 3R | −0,11 R | −0,08 R |
| Vortagestief / 2R | −0,15 R | −0,17 R |
| Range / Tageshoch | −0,38 R | −0,20 R |
| Range / Vortageshoch | −0,40 R | −0,21 R |

Ein weiterer Stop hilft deutlich, genau wie die Diagnose vorhersagte. Ziele an
Tages- oder Vortageshochs helfen nicht. Positiv wird nichts.

Wochentage (15m, Range-Stop, 2R): Donnerstag −0,002 R, Freitag −0,016 R,
Montag −0,033 R; Samstag und Sonntag um −0,45 R. Der Donnerstag lag in der
ersten Hälfte bei +0,19 R und in der zweiten bei −0,19 R — kein stabiler
Effekt, sondern ein guter Zeitabschnitt.

## Halten nach Tageszeit

Gepoolt über die vier Coins, Prozent je Durchgang, ein kompletter Kauf und
Verkauf je Durchgang:

| Fenster | brutto | netto (0,16 %) | t netto | BTC | ETH | SOL | XRP |
|---|---:|---:|---:|---:|---:|---:|---:|
| über Nacht 16:00→09:30 NY | +0,098 | −0,062 | −1,5 | +0,11 | +0,13 | +0,26 | −0,11 |
| tagsüber 09:30→16:00 NY | +0,018 | −0,142 | −4,0 | −0,03 | −0,06 | −0,11 | +0,27 |
| Asien 00–08 UTC | +0,006 | −0,154 | −5,6 | −0,01 | +0,01 | +0,14 | −0,12 |
| Europa 08–13:30 UTC | +0,061 | −0,099 | −4,5 | +0,06 | +0,05 | +0,07 | +0,06 |
| USA 13:30–20 UTC | +0,007 | −0,153 | −4,3 | −0,03 | −0,06 | −0,11 | +0,23 |
| spät 20–24 UTC | +0,042 | −0,119 | −5,6 | +0,06 | +0,07 | +0,04 | −0,01 |
| Wochenende Fr→Mo | +0,127 | −0,033 | −0,2 | +0,18 | −0,06 | +0,43 | −0,04 |

(Coin-Spalten brutto.) Bei Bitcoin, Ethereum und Solana kam der Gewinn brutto
überwiegend nachts — bei XRP umgekehrt tagsüber. Die Europa-Sitzung ist der
einzige Abschnitt, der auf allen vier Coins brutto positiv ist. Beides ist
kleiner als die Kosten eines täglichen Kaufs und Verkaufs.

Mit den niedrigsten realistischen Kosten (Maker-Gebühren, 0,04 % für die
ganze Runde): über Nacht +0,058 % (t 1,4), Europa +0,021 % (t 1,0). Auch dann
statistisch nicht von null zu unterscheiden.

## Urteil dieser Runde

37 Varianten gerechnet (30 Ausbruch, 7 Haltefenster), dazu 216 Zellen des
Ausbruchsrasters. Keine besteht die Regel; das gesperrte Jahr bleibt zu und
steht für eine künftige, neu angemeldete Hypothese weiter zur Verfügung.

Was messbar existiert, ist brutto: ein leichter Vorteil des 15-Minuten-
Ausbruchs an Werktagen, die Nacht bei BTC/ETH/SOL, die Europa-Sitzung. Alles
davon ist kleiner als die Kosten eines Privatkontos. Die Hebel, die noch offen
sind, liegen deshalb bei den Kosten, nicht bei weiteren Regeln: Futures mit
CME-Kosten (NQ/ES, siehe STATUS.md) oder Ausführung mit Maker-Gebühren.
