# Ergebnis der Strategiesuche

Durchgeführt nach [SUCHPROTOKOLL.md](SUCHPROTOKOLL.md). 14 Strategien, zwei
Zeitrahmen, drei Haltedauern, 12 Symbole, 84 Kombinationen. Das Holdout-Segment
ist zum Zeitpunkt dieser Notiz **nicht geöffnet**.

## Der erste Durchgang war ungültig

Im Suchgitter stand 4h als Entscheidungsrahmen *und* als Trendfilter. Eine
4h-Serie auf 4h zu resamplen ändert nichts, also bekam jede Strategie, die den
Filter benutzt, statt eines höheren Zeitrahmens die vorige Kerze. Kein
Lookahead — `align_to` verschiebt weiterhin um eine volle Periode — aber die
Strategien taten nicht, was ihr Code behauptet.

Aufgefallen ist es, weil `ema_momentum` mit einem Profitfaktor von 1,47 weit vor
dem Feld lag und auf `test` mit 0,75 zurückkam. Nach der Reparatur (4h gepaart
mit 1d) fällt sie aus den Überlebenden heraus. Die vier übrigen Spitzenkandidaten
ändern sich um keine Stelle, weil sie `with_htf_trend` gar nicht verwenden — das
ist die Gegenprobe, dass die Reparatur genau das getroffen hat, was kaputt war.

## Die vorregistrierte Regel ist gescheitert

Sie lautete: nimm den höchsten Profitfaktor auf `train`, bestätige ihn einmal auf
`test`, schiebe bei Misserfolg **nicht** den Zweiten nach.

Im ungültigen Durchgang griff sie `ema_momentum` (1,47 → 0,75). Damit ist sie
gescheitert, und der Zweitplatzierte wurde nicht nachgeschoben.

Der Grund für das Scheitern ist allgemeiner als dieser eine Fall: **der höchste
Wert im Feld ist der überangepassteste.** Eine Regel, die auf die Spitze zeigt,
zeigt zuverlässig auf den Ausreißer. Das ist keine Panne der Regel, das ist ihre
Bauart.

## Was stattdessen übrig bleibt

Nach der Reparatur nehmen 13 von 84 Kombinationen die Train-Hürden. Der Übertrag
auf `test`:

| | train | test |
|---|---:|---:|
| Median Profitfaktor | 1,146 | **1,223** |
| über 1,0 | 13 von 13 | **11 von 13** |
| Rangkorrelation train → test | | **+0,481** |

Je Strategiefamilie auf 4h, gemittelt über die drei Haltedauern:

| Familie | train | test | Symbole profitabel (test) |
|---|---:|---:|---|
| donchian_breakout | 1,15 | **1,72** | 10–12 von 12 |
| keltner_trend | 1,25 | **1,32** | 8 von 12 |
| squeeze_breakout | 1,15 | **1,22** | 8–9 von 12 |
| vol_expansion | 1,16 | **1,19** | 6–8 von 12 |

Beide Ausreißer nach unten sind `donchian_breakout` auf **1h** (0,91). Das passt
zum Kostenbefund aus [../ZEITRAHMEN.md](../ZEITRAHMEN.md): auf 1h kostet ein
Trade 0,15 R, auf 4h ein Vielfaches weniger, und genau dort kippt das Vorzeichen.

Vier voneinander unabhängige Auslöser — Kanalbruch, Bandpersistenz,
Bollinger-Kompression, Range-Ausdehnung — liegen auf 4h in beiden Segmenten über
eins. Das ist etwas anderes als eine Zelle, die zufällig passt.

## Der Preis, den die Diagnose gekostet hat

Um zu messen, ob ein Train-Rang überhaupt etwas vorhersagt, habe ich **alle**
Überlebenden auf `test` laufen lassen. Das war die Frage wert — die Antwort
(Set überträgt sich, Spitze nicht) ist der eigentliche Ertrag dieses Durchgangs.

Es hat aber einen Preis: `test` ist als unabhängige Bestätigung verbraucht. Ich
kenne jetzt das Testergebnis jeder Kombination, also ist jede Auswahl, die ich
ab hier treffe, mit Testwissen kontaminiert — auch die nach Protokoll fällige
(`keltner_trend`, 4h, 48 h, dessen 1,26 ich bereits gesehen habe).

**Sauber ist nur noch das Holdout.** Es ist ein Einwegschuss: nach dem ersten
Blick ist die Zahl keine Out-of-Sample-Zahl mehr.

## Offene Entscheidung

Wofür das Holdout ausgegeben wird, ist nicht mehr aus dem Protokoll ableitbar,
weil das Protokoll den Fall „Regel gescheitert, Set trägt trotzdem" nicht
vorgesehen hat. Zur Wahl stehen:

1. **`keltner_trend`, 4h, 48 h** — der Kandidat nach ursprünglicher Regel.
2. **Gleichgewichtet über die vier 4h-Familien bei 48 h** — die Hypothese, die
   die Diagnose tatsächlich stützt: Breite statt Spitze.
3. **Noch nicht ausgeben** und zuerst mehr Historie oder mehr Symbole holen.

Empfehlung ist 2. Wenn die Lehre dieses Durchgangs lautet, dass die Rangfolge
nicht überträgt, das Set aber schon, dann ist das Set die Hypothese, die geprüft
gehört — und nicht wieder deren Spitze.

## Zweiter Durchgang: breiter, tiefer, und diesmal hält der Kandidat

Nach der Holdout-Entscheidung wurde die Grundlage verbreitert statt das Holdout
ausgegeben: 28 statt 12 Symbole, Historie bis Juli 2019 statt März 2024,
400.581 4h-Kerzen. Die Splits laufen jetzt über feste Kalenderdaten
(train bis 2025-06-13, test bis 2026-01-24, holdout danach), damit mehr
Historie die Holdout-Grenze nicht nach hinten schiebt.

Zwei Fehler kamen dabei heraus, beide echt:

- **`synthetic.py` war nicht deterministisch.** Der Seed stammte aus Pythons
  `hash(symbol)`, der pro Prozess zufällig ist. Der als deterministisch
  dokumentierte Generator lieferte bei jedem Lauf andere Kerzen, und selektive
  Strategien fielen mal durch den Test und mal nicht. Jetzt `crc32`.
- **Ein Stop kann unter null rutschen.** Bei einem billigen Coin erreicht
  `Kurs − 3×ATR` die Null, und `Signal` weist das zurück — der Lauf stürzte ab.
  Zwölf von vierzehn Strategien bilden Stop oder Ziel durch Subtraktion, also
  war das kein Einzelfall, sondern wartete nur auf das erste billige Symbol.
  `base.entry()` prüft die Geometrie jetzt an einer Stelle.

### Die Überlebenden

13 von 84 Kombinationen nehmen die Hürden, alle auf 4h, und jede Familie über
**alle drei** Haltedauern — keine Messerkante:

| Familie | Trades | PF | E[R] | Symbole profitabel |
|---|---:|---:|---:|---|
| donchian_breakout (48h) | 3.078 | 1,278 | +0,123 | 24 von 28 |
| vol_expansion (96h) | 2.441 | 1,284 | +0,133 | 23 von 28 |
| keltner_trend (48h) | 3.120 | 1,187 | +0,077 | 22 von 28 |
| ema_momentum (48h) | 1.396 | 1,221 | +0,103 | 20 von 28 |
| momentum_persistence (192h) | 768 | 1,321 | +0,144 | 19 von 28 |

### Die Bestätigung

Kandidat nach Regel ist `momentum_persistence`, 4h, 192 h. Diese Kombination
war im ersten Durchgang **nicht** unter den Überlebenden, ist also nie auf
`test` gelaufen — die Bestätigung ist für sie sauber, anders als für die
übrigen vier Familien.

| | train | test |
|---|---:|---:|
| Profitfaktor | 1,321 | **1,275** |
| Erwartungswert | +0,144 R | **+0,127 R** |
| Trades | 768 | 114 |
| Symbole profitabel | 19 von 28 | 10 von 18 |

Zum ersten Mal in dieser Untersuchung übersteht ein vorregistriert ausgewählter
Kandidat die Bestätigung, und zwar mit fast unverändertem Profitfaktor.

### Was der Gewinner tatsächlich ist

Nicht das, was der Projektname verspricht. Die Fenster sind in Kerzen gezählt,
also ändern sie ihre Bedeutung mit dem Zeitrahmen. Auf 4h bedeuten die
Vorgabewerte:

| Parameter | in Kerzen | auf 4h |
|---|---:|---|
| lookback | 168 | **28 Tage** |
| skip | 12 | 2 Tage |
| Haltedauer | — | bis zu **8 Tage** |
| cooldown | 24 | 4 Tage |

Das ist Ein-Monats-Momentum mit Kurzfrist-Auslassung, gehalten über gut eine
Woche — dieselbe Struktur wie die Tech-Rotation im Nachbarbranch, und die
Anomalie mit den meisten veröffentlichten Belegen. Es ist **kein**
Intraday-Signal.

Der Zusammenhang mit allem Vorherigen ist damit geschlossen: Intraday scheitert,
weil die Gebühr pro Trade größer ist als die Kante (ERGEBNIS.md, ZEITRAHMEN.md).
Diese Strategie handelt rund vier- bis fünfmal je Symbol und Jahr — sie zahlt die
Gebühr so selten, dass sie kaum ins Gewicht fällt. Sichtbar auch daran, dass
dieselbe Strategie auf 1h nicht funktioniert (PF 0,93 bis 1,03) und dass das
Ergebnis mit der Haltedauer steigt: 1,04 bei zwei Tagen, 1,22 bei vier, 1,32
bei acht.

### Was noch offen ist

- **114 Trades auf `test` sind dünn.** Ein Profitfaktor von 1,275 hat bei dieser
  Zahl breite Fehlerbalken. Die 768 Trades auf train sind das belastbarere Maß.
- **Die Haltedauer ist noch nicht ausgereizt.** 1,04 → 1,22 → 1,32 über 2, 4 und
  8 Tage heißt, dass die Grenze bei 8 Tagen weiter bindet. Das zu verfolgen
  hieße aber, weitere Zellen zu rechnen — und jede zusätzliche Zelle verwässert
  genau die Aussagekraft, die dieser Aufbau schützen soll.
- **Das Holdout ist unberührt.** Es bleibt der einzige saubere Datensatz.

## Was in keinem Fall folgt

`donchian_breakout` auf 4h hat mit 1,72 das beste Testergebnis. Es zu wählen,
*weil* es das beste Testergebnis hat, wäre exakt der Fehler, den dieser ganze
Aufbau verhindern soll, eine Ebene höher.
