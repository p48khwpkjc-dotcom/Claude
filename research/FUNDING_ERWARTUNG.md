# Funding-Arbitrage: was ich vorher erwarte

Aufgeschrieben, bevor eine einzige historische Funding-Rate gemessen ist. Wie
bei der Strategiesuche gilt: eine Erwartung, die erst nach den Daten formuliert
wird, ist keine.

## Was der Trade ist

Spot kaufen, Perpetual in gleicher Höhe shorten. Die Preisbewegung hebt sich
auf — steigt BTC, gewinnt der Spot und verliert der Short im selben Maß. Was
bleibt, ist die Funding-Rate, die Binance alle acht Stunden zwischen Longs und
Shorts umlegt. Ist sie positiv, zahlen Longs an Shorts, und die Short-Seite
dieses Paares kassiert.

Es ist keine Wette auf die Richtung. Es ist die Vermietung von Bilanz an
Leute, die gehebelt long sein wollen.

## Die Arithmetik, die vor allem anderen kommt

Funding fällt dreimal täglich an, also 1.095-mal im Jahr.

| Funding je 8 h | pro Tag | **pro Jahr** |
|---|---:|---:|
| 0,003 % | 0,009 % | **3,3 %** |
| 0,010 % (Binance-Normalwert) | 0,030 % | **11,0 %** |
| 0,030 % | 0,090 % | **32,9 %** |
| 0,100 % (Bullenmarkt-Spitze) | 0,300 % | **109,5 %** |

Kosten: vier Fills für einen kompletten Zyklus — Spot rein, Perp rein, Spot
raus, Perp raus. Bei 0,05 % Gebühr und 3 bp Slippage je Fill sind das
**0,32 % der Position**. Beim Normalwert von 0,01 % je Periode dauert es also
**32 Perioden oder knapp elf Tage**, bis die Gebühren wieder drin sind.

*(Beim ersten Aufschreiben hatte ich 0,20 % und sieben Tage veranschlagt und
die Slippage vergessen. Der gebaute Rechner sagt 0,32 % — die Zahl hier ist
die korrigierte, und der Fehler stand in die für mich günstige Richtung.)*

Daraus folgt sofort die wichtigste Eigenschaft: das ist kein Trade, den man oft
macht. Wer wöchentlich ein- und aussteigt, verschenkt die Hälfte. Wer Monate
liegen lässt, zahlt die Gebühr einmal und kassiert 1.095 Mal.

## Meine Erwartung

**Über mehrere Jahre und die großen Perps gemittelt: 4 bis 12 % im Jahr
brutto**, bevor Kapitalkosten und Ausfallrisiken gegengerechnet sind.

Begründung: Funding ist im Mittel positiv, weil in Krypto strukturell mehr
Leute gehebelt long sein wollen als short. Aber es ist stark
zustandsabhängig — in Bullenphasen zweistellig annualisiert, in Bärenphasen
über Wochen negativ. Der Mittelwert über einen vollen Zyklus liegt deutlich
näher am Binance-Normalwert als an den Spitzen, die in Werbung zitiert werden.

Der aktuelle Messwert stützt die Vorsicht: BTC-Funding steht heute bei
**−0,0006 %**. Negativ. Wer heute einsteigt, zahlt.

**Mit einem Filter** (nur einsteigen, wenn Funding über einer Schwelle liegt,
aussteigen, wenn es darunter fällt) erwarte ich eine höhere Rate pro
investiertem Tag, aber weniger Tage im Markt — und mehr Ein- und Ausstiege,
also mehr Gebühren. Ob der Filter netto hilft, ist genau die Frage, die der
Backtest beantworten soll. Ich erwarte, dass er hilft, aber weniger als es
intuitiv scheint, weil die 0,20 % Wechselkosten rund sieben gute Tage
auffressen.

## Was ich *nicht* erwarte

Nichts in der Nähe von 15 bis 25 % im Monat. Wenn eine Rechnung dorthin kommt,
ist mit hoher Wahrscheinlichkeit einer dieser drei Fehler drin: die Gebühren
für beide Beine fehlen, die Phasen mit negativem Funding sind ausgeblendet,
oder die Rendite ist auf die Margin statt auf das eingesetzte Kapital
bezogen — der Spot muss schließlich auch bezahlt werden.

## Die Risiken, die keine Kennzahl zeigt

1. **Liquidation der Short-Seite.** Steigt der Kurs stark, verliert das
   Perp-Bein, während der Gewinn im Spot festliegt. Ohne genug freie Margin
   wird das Bein liquidiert und aus der marktneutralen Position wird eine
   nackte Long-Position — im schlechtesten Moment.
2. **Börsenrisiko.** Das Kapital liegt bei einer Gegenpartei. Diese Rendite
   ist eine Vergütung für genau dieses Risiko, und die Geschichte der Branche
   liefert genug Beispiele, warum sie bezahlt wird.
3. **Basisrisiko beim Ein- und Ausstieg.** Spot und Perp werden nicht zum
   selben Preis gefüllt. Die Differenz ist ein zusätzlicher, in keiner
   Funding-Tabelle sichtbarer Kostenposten.

Punkt 1 und 3 lassen sich modellieren, Punkt 2 nicht. Das gehört in jede Zahl,
die am Ende dabei herauskommt, als Fußnote hinein.
