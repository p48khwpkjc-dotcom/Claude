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

## Automatisierung: TradingView → TradersPost → Paper-Konto

Ablauf: TradingView berechnet die Strategie auf seinen Servern und schickt bei jeder Order eine
Webhook-Nachricht an TradersPost. TradersPost legt die Order samt Stop und Ziel im Paper-/Demo-Konto
an. Dein Rechner muss dafür nicht laufen.

### Voraussetzungen

| | Warum |
|---|---|
| **TradingView-Bezahlplan** (Essential oder höher) | Webhooks gibt es im kostenlosen Plan nicht |
| **CME-Echtzeitdaten** in TradingView (Zusatzpaket) | Ohne das sind Futures-Kurse 10 Minuten verzögert, der Alarm käme 10 Minuten zu spät |
| **TradersPost-Konto** mit Paper-Broker (oder Tradovate-/NinjaTrader-Demo) | Führt die Orders aus |

### Einrichtung

1. **TradersPost:** Paper-Broker bzw. Demo-Konto verbinden → *Strategy* anlegen → *Webhook*
   anlegen → Strategie mit dem Paper-Konto abonnieren (Subscription) → **Webhook-URL kopieren**.
2. **TradingView:** Chart MNQ1!, 5 Minuten, Strategie drauf. In den Einstellungen unter
   *Automation* steht das Format standardmäßig auf **TradersPost**. Filter und Größe so einstellen,
   wie du testen willst.
3. **Alarm anlegen** (Uhr-Symbol → Bedingung: *1AM ORB Lab*, Auswahl
   *Order fills and alert() function calls*):
   - Nachricht: nur `{{strategy.order.alert_message}}`
   - Benachrichtigungen: **Webhook-URL** = URL aus TradersPost
   - Ablaufdatum: so lang wie möglich bzw. unbegrenzt
4. **Testen:** In TradersPost mit dem Test-Werkzeug eine Beispielnachricht schicken (siehe unten)
   und im Paper-Konto prüfen: Position offen, Stop **und** Ziel als Orders vorhanden. Danach die
   `exit`-Nachricht schicken und prüfen, dass Position **und** übrige Orders weg sind.

### Nachrichten, die die Strategie schickt

```json
{"ticker":"MNQ1!","action":"sell","orderType":"market","quantity":1,"takeProfit":{"limitPrice":21246.75},"stopLoss":{"type":"stop","stopPrice":21299.25}}
{"ticker":"MNQ1!","action":"exit"}
```

- **Einstieg:** Marktorder mit Bracket. Stop und Ziel liegen beim Broker, nicht nur im Chart.
- **Stop/Ziel getroffen:** keine Nachricht nötig, das erledigt die Bracket-Order.
- **Zeitausstieg 15:50 NY:** `exit`.
- **Tägliche Sicherheits-Glattstellung:** Ist die Strategie am Ende des Haltefensters schon flat,
  geht trotzdem ein `exit` raus. So kann das Konto nie über Nacht eine Position halten, falls
  Chart und Broker mal auseinanderlaufen. TradersPost meldet das an Tagen ohne Position als
  „nichts zu schließen“, das ist normal.

### Was „vollautomatisch“ nicht abdeckt (einmal pro Woche kurz prüfen)

- **Rollover:** MNQ wechselt quartalsweise den Kontrakt (nächster: Dezember 2026, rund eine Woche vor
  dem Verfall am 18.12.). Prüfe beim Test, ob TradersPost `MNQ1!` automatisch dem Frontmonat
  zuordnet. Wenn nicht: im Script unter *Symbol in alert message* den Kontrakt eintragen
  (z. B. `MNQZ2026`) und beim Rollover ändern.
- **Änderungen am Script oder an den Einstellungen** gelten erst nach **Löschen und Neuanlegen des
  Alarms**. Der Alarm arbeitet mit dem Stand zum Zeitpunkt seiner Erstellung.
- **Ablauf des Alarms:** je nach Plan läuft er nach einer Weile ab und muss erneuert werden.
- **Kontrolle:** Trades im Paper-Konto mit dem Strategy Tester in TradingView vergleichen.
  Abweichungen deuten auf Probleme mit dem Signal, der Verbindung oder dem Symbol hin.

Erst wenn das Paper-Konto über mehrere Wochen dasselbe zeigt wie der Strategy Tester, über echtes
Geld nachdenken.
