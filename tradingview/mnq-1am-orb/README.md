# MNQ 1AM Range Breakout · Regime Lab (Pine Script v6)

Automatisierbare TradingView-Strategie für **MNQ1! im 5-Minuten-Chart** mit fünf testbaren
Regime-Filtern und einer eingebauten Vergleichstabelle.

Datei: [`mnq_1am_range_breakout.pine`](mnq_1am_range_breakout.pine)

## Regeln (wie im Prompt)

| | |
|---|---|
| **Range** | Hoch/Tief der 15 Minuten von 01:00–01:15 New York (drei 5m-Kerzen: 01:00, 01:05, 01:10) |
| **Long** | Eine 5m-Kerze schließt mit dem **Body** über dem Range-Hoch → Kauf zum Schlusskurs |
| **Short** | Eine 5m-Kerze schließt mit dem **Body** unter dem Range-Tief → Verkauf zum Schlusskurs |
| **Stop** | Gegenüberliegende Seite der Range (optional + Puffer in Ticks) |
| **Ziel** | 0,5 R (R = Einstieg − Stop) |

Zusätzliche Einstellungen, die der Prompt offen lässt (alle im Menü änderbar):

- **Einstiegsfenster** 01:15–10:00 NY, **Haltefenster** bis 15:50 NY (danach wird glattgestellt)
- **1 Trade pro Tag** (erster Ausbruch). Bei mehr Trades/Tag braucht ein neuer Trade in dieselbe
  Richtung erst einen Schluss zurück in der Range.
- **Bestätigung**: `Close` (Schluss jenseits der Range, Standard) oder `Full body`
  (Open **und** Close jenseits der Range – strenger)
- **Positionsgröße**: feste Kontrakte oder fester $-Risikobetrag
- **Kosten**: 0,75 $ pro Kontrakt und Seite, 1 Tick Slippage (in den Strategie-Eigenschaften anpassbar)

## Die 5 Regime-Filter

Alle Filter nutzen nur **abgeschlossene** Daten (Vortag bzw. letzte abgeschlossene Stunde) –
kein Repainting, kein Blick in die Zukunft. Jeder Filter lässt sich **invertieren**.

| # | Filter | Logik (Standard) | Hypothese | Invertiert = |
|---|---|---|---|---|
| F1 | **Daily-EMA-Trend** | Long nur, wenn Vortages-Schluss > EMA 50 (Daily), Short nur darunter | Ausbrüche in Trendrichtung halten eher 0,5 R | nur Gegentrend |
| F2 | **ATR-Perzentil** (Volatilitätsregime) | Daily ATR(14) liegt im 20.–80. Perzentil der letzten 100 Tage | Extreme Vola (zu ruhig / zu wild) erzeugt Fehlausbrüche | nur Extremregime |
| F3 | **Range-Breite vs. ATR** | Range-Höhe = 3–12 % der Daily ATR | Zu enge Range = Rauschen, zu weite = schlechtes Chance-Risiko | nur Ausreißer-Ranges |
| F4 | **ADX-Trendstärke** | ADX(14) auf 60 min ≥ 20 | Ausbrüche funktionieren in Trendphasen, nicht in Chop | nur Chop |
| F5 | **VIX-Niveau** (Risikostimmung) | VIX-Schluss des Vortags ≤ 25 | Ruhiges Risk-on-Umfeld = sauberere Ausbrüche | nur Stress-Phasen |

Die Kalibrierungswerte (ATR-Perzentil, Range-Breite in % ATR, ADX, VIX) stehen im **Today-Panel**
oben rechts und im **Data Window**, damit du die Schwellen realistisch setzen kannst.

## So testest du, welcher Filter am besten ist

1. Chart **MNQ1!**, **5 Minuten**, Script über den Pine-Editor hinzufügen.
2. In den Strategie-Eigenschaften **Bar Magnifier** einschalten (falls dein Plan es hat) – genauere
   Fills, wenn Stop und Ziel in derselben Kerze liegen. Optional im Chart **B-ADJ** (back-adjusted)
   aktivieren, damit Rollover-Lücken die Daily-Filter nicht verzerren.
3. **Vergleichstabelle unten rechts** lesen: Die Strategie läuft intern **11-mal parallel** –
   Baseline, F1–F5 und F1–F5 invertiert – mit identischen Regeln. Spalten: Trades, Win %, Net R,
   Avg R, Profit-Faktor, Max-Drawdown (alles in R, ohne Gebühren). Die beste Zeile ist grün markiert.
4. **Worauf achten**
   - Bei 0,5 R liegt die **Break-even-Trefferquote bei 66,7 %** (steht in der Fußzeile). Ein Filter
     hilft nur, wenn er die Win-Rate klar darüber hebt bzw. **Avg R** erhöht.
   - **Normal vs. invertiert** vergleichen: Ein echter Regime-Effekt zeigt sich, wenn die normale
     Variante deutlich besser ist als die invertierte. Sind beide ähnlich, filtert der Filter nur
     zufällig Trades weg.
   - **Genug Trades**: Unter ~50 Trades ist ein Unterschied meist Zufall.
5. Den Favoriten als **Filter A** wählen → der **Strategy Tester** zeigt dann die echten Ergebnisse
   mit Gebühren, Slippage und Kontrakten. Mit **Filter B** kannst du zwei Filter kombinieren (UND).
6. **Out-of-Sample**: Unter *Backtest window* Schwellen auf z. B. 2024 optimieren, dann ab 2025
   prüfen, ob der Vorteil hält. Für mehr Historie den **Deep Backtesting**-Modus nutzen.

Hinweis: Die Vergleichstabelle simuliert Ein- und Ausstiege zum Schlusskurs (wie die Strategie mit
„Fill orders on bar close“) und nutzt dieselbe Annahme wie der TradingView Broker-Emulator, wenn
Stop und Ziel in einer Kerze liegen. Kleine Abweichungen zum Strategy Tester (Slippage, Gebühren,
Bar Magnifier) sind normal.

## Automatisierung (Webhook)

Jede Order bringt eine fertige JSON-Nachricht mit:

```json
{"symbol":"MNQ1!","action":"buy","qty":1,"entry":21234.50,"stop":21210.25,"target":21246.75,"time":"2026-11-09 01:20"}
{"symbol":"MNQ1!","action":"exit","qty":1,"time":"2026-11-09 01:45"}
```

1. Alert erstellen → Bedingung: diese Strategie → **Nachricht:** `{{strategy.order.alert_message}}`
2. Webhook-URL deines Brückendienstes eintragen (z. B. TradersPost, PickMyTrade, eigener Server).
3. Unter *Automation* das **Broker-Symbol** setzen (z. B. `MNQZ2026`), falls dein Dienst kein
   `MNQ1!` versteht, und das JSON-Format bei Bedarf an deinen Dienst anpassen.
4. Entweder die Bracket-Order (stop/target im Einstieg) **oder** die separaten `exit`-Nachrichten
   nutzen – nicht beides gleichzeitig ausführen lassen, sonst drohen doppelte Ausstiege.

Erst im **Paper-Trading** laufen lassen, bevor echtes Geld dranhängt.
