# Wo das Projekt steht

Kurznotiz für eine neue Sitzung. Wenn du diese Datei liest, weil du gerade neu
gestartet bist: alles Wichtige liegt im Repo, es geht nichts verloren.

## Der Stand in einem Satz

Auf 5m verdient keine Strategie Geld und es gibt auch keine Kante
(**[ERGEBNIS.md](ERGEBNIS.md)**). Auf 1h gibt es eine — klein, aber in beiden
Hälften stabil — und sie ist um rund 0,1 R pro Trade kleiner als die Taker-Gebühr
(**[ZEITRAHMEN.md](ZEITRAHMEN.md)**).

## Fertig und getestet

- **Datenlayer** – Binance-Kerzen ohne API-Key, Parquet-Cache, harte Validierung
- **Backtest-Engine** – Fill auf der nächsten Kerzeneröffnung, Stop schlägt Ziel,
  Trailing erst nach der Kerze, Gebühren und Slippage auf jedem Fill
- **Risk-Layer** – 0,5 % Risiko pro Trade, Kill-Switch bei 3 % Tagesverlust,
  Cooldown, Tageslimit, 4 Stunden maximale Haltedauer
- **Sechs Strategien** – vwap_reversion, rsi_reversion, opening_range,
  ema_momentum, donchian_breakout, squeeze_breakout
- **Kostenrechnung** (`daytrader costs`) – Gebühren pro Risikoeinheit
- **Regime-Prüfstand** (`daytrader regimes`) – Strategieprüfung ohne Börsendaten
- **Datentransport** (`daytrader export` / `verify`) – Kerzen über das Repo
- 94 Tests, alle grün: `python -m pytest tests/ -q`
- **Backtest auf 466.557 echten 5m-Kerzen** – BTC, ETH, SOL, 18 Monate

## Was der Backtest ergeben hat

Profitfaktor 0,37 bis 0,50 über alle sechs Strategien, in und außerhalb der
Stichprobe. Setzt man Gebühren und Slippage auf null, landet alles zwischen 0,89
und 1,06 — ein Münzwurf. Es gibt also keine Kante, die von Kosten aufgefressen
würde; es gibt keine Kante.

Nebenbefund: die frühere Kostenschätzung war um den Faktor zwei zu freundlich.
Der echte 5m-ATR von BTC liegt bei 0,13 % des Kurses, nicht 0,26 %. Ein 1,2×ATR-
Stop kostet damit nicht 0,69 R, sondern 1,38 R — mehr, als der Trade riskiert.

## Der Netzwerkzugang ist offen

`data-api.binance.vision` antwortet aus dieser Umgebung mit `200`. Der Umweg aus
[DATEN-HOLEN.md](DATEN-HOLEN.md) — Kerzen auf dem eigenen Rechner holen und übers
Repo transportieren — wird nicht mehr gebraucht. Die Anleitung bleibt trotzdem
stehen, für den Fall, dass sich die Policy wieder ändert.

Prüfen lässt sich das jederzeit:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://data-api.binance.vision/api/v3/ping
```

`200` heißt offen, `000` heißt zu.

Der Abruf dauert bei offenem Zugang rund vier Minuten, nicht die früher
geschätzten zwanzig:

```bash
python -m daytrader fetch --days 540
python -m daytrader backtest              # -> out/report.md
python -m daytrader costs
```

## Was der Zeitrahmen-Durchgang ergeben hat

Richtung 1 aus ERGEBNIS.md ist abgearbeitet: 15m, 30m und 1h gerechnet, 900 Tage,
72 Kombinationen aus Zeitrahmen, Haltedauer und Strategie. Drei Ergebnisse:

- **Der Zeitrahmen wirkt wie vorhergesagt.** Von 5m auf 1h wird ein Trade
  viereinhalbmal billiger (0,69 R → 0,15 R bei 2×ATR), der Erwartungswert steigt
  von −0,41 R auf −0,07 R.
- **Die Haltedauer muss zur Kerze passen, nicht zur Uhr.** Rund dreißig Kerzen:
  8 h auf 15m, 12 h auf 30m, 24 h auf 1h. Drei Stunden auf 1h schneiden zwei
  Drittel der erreichbaren Ziele ab. Die Obergrenze liegt ohnehin bei knapp 29 %
  der Trades — mehr erreicht ihr Ziel nie, egal wie lange man hält.
- **Auf 1h liegen 5 von 6 Strategien ohne Kosten in beiden Hälften über 1,0.**
  Die Rohkante beträgt +0,03 bis +0,08 R, die Gebühr 0,15 R. Es fehlen also rund
  0,1 R pro Trade.

Die Konfigurationen liegen in `configs/` und sind lauffähig:

```bash
python -m daytrader fetch --interval 1h --days 900
python -m daytrader -c configs/1h.yaml backtest
```

## Zur Frage nach 70 % Trefferquote bei 2:1

Vermessen statt gesucht: **[research/TREFFERQUOTE.md](research/TREFFERQUOTE.md)**.

70 % Trefferquote ist erreichbar — sechs Strategien schneiden die Linie, alle
bei einem Ziel von 0,5R oder darunter, keine bei 2R. Die beiden Größen lassen
sich nicht unabhängig einstellen.

Bei `donchian_breakout`: 70 % Treffer bei 0,5R bringen **+0,013 R** je Trade,
41 % Treffer bei 3R bringen **+0,202 R**. Wer die Quote maximiert, minimiert
den Gewinn, um das Fünfzehnfache.

Der Münzwurf `random_entry` erreicht bei 2R schon 41,0 % — das ist der Anteil,
der aus der Geometrie kommt. Die beste Strategie liegt bei 46,8 %, trägt also
rund sechs Punkte Information. Für 70 % bräuchte es 29.

Teilverkäufe verschieben das nicht, sie kosten: in 16 von 16 Kombinationen
steigt die Trefferquote und fällt der Erwartungswert.

## Das Holdout ist ausgegeben

**[research/HOLDOUT_ERGEBNIS.md](research/HOLDOUT_ERGEBNIS.md)** — einmal
gelaufen, vorher angemeldet, Segment jetzt verbraucht.

`donchian_breakout` auf 4h mit 3R-Ziel, 634 Trades ab dem 24. Januar 2026:
Profitfaktor **1,059**, Erwartungswert **+0,0366 R**, 15 von 28 Symbolen
profitabel. Auf train waren es 1,349 und +0,2015 R bei 23 von 28.

Statistisch ist davon nichts übrig: t = 0,62, das 95-%-Intervall reicht von
−0,079 bis +0,153 R und enthält die Null. Für einen Nachweis bräuchte es rund
6.364 Trades statt 634. Der Train-Wert liegt 2,8 Standardfehler darüber — die
Schätzung war überhöht, nicht bloß verrauscht.

Nach der vorab festgelegten Regel (Bestätigung ab PF 1,15, Widerlegung unter
1,0) ist das der mittlere Fall: **zu wenig Daten**. So wird es berichtet.

## Nächster Schritt

Der Abstand ist jetzt beziffert statt behauptet, und das macht die Entscheidung
schärfer. Zwei Wege bleiben:

1. **Die Gebühr unter die Kante drücken.** Mit 0,02 % Maker statt 0,05 % Taker
   stehen `donchian_breakout` (1,06 / 1,07) und `squeeze_breakout` (1,02 / 1,03)
   in beiden Hälften über eins. Nur bekommt eine Ausbruchsstrategie keine
   Maker-Fills — die Limit-Order füllt bevorzugt, wenn der Ausbruch scheitert.
   Diesen Effekt kann die Engine nicht abbilden, der Lauf ist eine Obergrenze.
   Wer hier weitermacht, muss zuerst die Negativauslese modellieren.
2. **Die Kante wachsen lassen.** Dafür braucht es ein Signal, das nicht aus Preis
   und Volumen derselben Kerzen stammt: Orderbuch, Finanzierungsraten,
   Cross-Asset.

Was **nicht** ansteht: an Parametern drehen, bis eine Kurve nach oben zeigt. Von
72 gerechneten Kombinationen lagen zwei außerhalb der Stichprobe über 1,0 und nur
eine davon auch innerhalb, mit 1,01. Der Median liegt bei 0,70. Bei so vielen
Versuchen ist die beste Zelle die Erwartung, keine Entdeckung.

Der Live-Loop gegen die Testnet-API ist weiterhin nicht gebaut — und solange
keine Strategie im Backtest trägt, gibt es dafür auch keinen Anlass.
