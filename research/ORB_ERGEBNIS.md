# New York Open Range Breakout: Ergebnisse

Geprüft nach [ORB_ANMELDUNG.md](ORB_ANMELDUNG.md): Hoch und Tief der ersten
fünf Minuten ab 09:30 New York, Einstieg auf der Minute nach dem ersten
Schlusskurs außerhalb der Range, Ausstieg zum Sitzungsende um 16:00 oder
vorher an Stop oder Ziel. Ein R ist der Abstand vom Einstieg zur
gegenüberliegenden Seite der Range.

## Bitcoin

Binance BTCUSDT, 2.635.119 Minuten vom 8. Oktober 2021 bis 12. Oktober 2026.
Kosten 0,05 % je Seite, 3 bp Slippage, 5 bp auf Stops.

### Wie angemeldet: jeder Tag, mit Kosten

| Variante | Trades | Treffer | Erwartungswert | 95-%-Intervall | ohne Kosten | Münzwurf |
|---|---:|---:|---:|---|---:|---:|
| halten, kein Stop | 1.829 | 41,3 % | **−0,452 R** | −0,67 bis −0,23 | +0,326 | −0,568 |
| halten mit Stop | 1.829 | 20,0 % | **−0,501 R** | −0,63 bis −0,38 | +0,164 | −0,481 |
| 1:1 | 1.829 | 43,7 % | **−0,568 R** | −0,62 bis −0,51 | +0,034 | −0,564 |
| 1,5:1 | 1.829 | 36,9 % | **−0,558 R** | −0,62 bis −0,49 | +0,029 | −0,546 |
| 2:1 | 1.829 | 30,6 % | **−0,590 R** | −0,66 bis −0,52 | +0,047 | −0,537 |
| 3:1 | 1.829 | 24,8 % | **−0,589 R** | −0,67 bis −0,51 | +0,022 | −0,555 |
| 4:1 | 1.829 | 22,7 % | **−0,556 R** | −0,65 bis −0,46 | +0,068 | −0,542 |
| 5:1 | 1.829 | 21,8 % | **−0,517 R** | −0,62 bis −0,42 | +0,095 | −0,511 |

Jede Variante verliert, jedes Jahr von 2021 bis 2026, und bei jeder schließt
das Intervall die Null auf der Verlustseite aus. Nach Kosten liegt der
Ausbruch auf dem Niveau des Münzwurfs.

### Warum: die Range ist zu schmal für die Gebühr

Die ersten fünf Minuten spannen im Median **0,286 % des Kurses**. Ein Trade
kostet mit Ein- und Ausstieg rund 0,1 % plus Slippage — das sind
**0,37 R je Trade**, bevor der Kurs sich bewegt hat. Ohne Kosten sind alle
acht Varianten positiv; die Gebühr ist größer als jeder von ihnen.

### Nachträglich, und als nachträglich gekennzeichnet: nur Werktage

Ein New York Open findet nur montags bis freitags statt. Der Lauf oben hat
Bitcoin auch an Wochenenden gehandelt, weil die Anmeldung das nicht ausschloss.
Die Einschränkung auf Werktage ist inhaltlich naheliegend, wurde aber erst
nach dem Blick auf die Zahlen geprüft, und das gehört dazu.

Ohne Kosten, Werktage, 1.305 Trades:

| Variante | Erwartungswert | t | 1. Hälfte (2021–2024) | 2. Hälfte (2024–2026) |
|---|---:|---:|---:|---:|
| halten mit Stop | +0,340 R | 3,79 | +0,553 (t 3,66) | +0,127 (t 1,31) |
| 2:1 | +0,123 R | 3,11 | +0,226 (t 3,96) | +0,021 (t 0,39) |
| 5:1 | +0,204 R | 3,40 | +0,306 (t 3,45) | +0,103 (t 1,26) |

An Werktagen hatte der Ausbruch einen messbaren Rohvorteil — aber fast nur in
der ersten Hälfte. Seit Frühjahr 2024 ist er bei keiner Variante mehr von null
zu unterscheiden. Eine mögliche Erklärung ist der Start der Spot-Bitcoin-ETFs
im Januar 2024, der den Handel zur New-Yorker Eröffnung verändert hat; belegt
ist das hier nicht.

Mit Kosten, Werktage:

| Variante | Spot Taker | Futures Taker 0,04 % + 1 bp | Maker 0,02 % + 1 bp |
|---|---:|---:|---:|
| halten mit Stop | −0,126 | +0,047 [−0,12, +0,22] | +0,155 [−0,01, +0,32] |
| 2:1 | −0,309 | −0,155 | −0,048 |
| 5:1 | −0,217 | −0,076 | +0,031 |

Selbst auf Maker-Niveau ist keine Variante sicher positiv, und Maker-Gebühren
bekommt ein Ausbruchseinstieg in der Praxis nicht.

### Urteil Bitcoin

Nicht tragfähig. Nach den angemeldeten Regeln verliert jede Variante deutlich
und in jedem Jahr. Der Rohvorteil, der an Werktagen bestand, ist in der
zweiten Hälfte der Historie verschwunden, und er war nie größer als die
Gebühr eines Privatkontos.

## Nasdaq 100 und S&P 500

Noch offen — die Daten fehlen. Für diese Strategie sind sie der interessantere
Teil: Futures kosten je Runde rund 0,02 R statt 0,37 R, also genau den Posten,
an dem Bitcoin scheitert.
