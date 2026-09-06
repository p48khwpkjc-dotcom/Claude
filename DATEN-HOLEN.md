# Echte Börsendaten in den Bot bekommen

Der Container, in dem ich arbeite, kommt an keine Börse heran – die Netzwerk-Policy
der Umgebung blockiert Binance, Bybit, Kraken, Coinbase und alle anderen. GitHub
erreiche ich dagegen. Also wird das Repository selbst zum Transportweg: du holst
die Kerzen auf deinem Rechner, pushst sie, ich ziehe sie und rechne.

Rechenzeit auf deiner Seite: einmalig etwa zwanzig Minuten, davon fünfzehn Warten.

---

## Voraussetzungen

**Python 3.11 oder neuer.** Prüfen:

```
python3 --version      # macOS / Linux
py --version           # Windows
```

Kommt eine Fehlermeldung oder eine Version unter 3.11, hier installieren:
<https://www.python.org/downloads/>. Unter Windows beim Installer **„Add Python to
PATH" ankreuzen**, sonst findet die Kommandozeile ihn nicht.

**Git.** Prüfen mit `git --version`, sonst von <https://git-scm.com/downloads>.

---

## Schritt 1 – Repo holen

```
git clone https://github.com/p48khwpkjc-dotcom/Claude.git
cd Claude
git checkout claude/day-trading-bot-necw1e
```

## Schritt 2 – Abhängigkeiten installieren

macOS / Linux:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Meckert PowerShell über die Ausführungsrichtlinie, einmalig:
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

## Schritt 3 – Erst klein testen

Bevor du eine Viertelstunde auf 540 Tage wartest, prüfe mit 90 Tagen, ob der Weg
überhaupt offen ist:

```
python -m daytrader export --days 90
```

Läuft das durch, siehst du so etwas:

```
fetching BTCUSDT 5m, 90 days ...
wrote 3 dataset(s), 4.8 MB total
manifest: data/exchange/manifest.json
```

Bricht es mit einem Netzwerkfehler ab, spring zu **„Wenn Binance bei dir blockiert
ist"** weiter unten.

## Schritt 4 – Vollen Datensatz holen

```
python -m daytrader export --days 540
```

Das dauert je nach Leitung zehn bis zwanzig Minuten – der Bot lädt in
1000-Kerzen-Paketen und hält sich absichtlich an das Rate-Limit. Ergebnis sind rund
30 MB in `data/exchange/`, plus eine `manifest.json` mit Zeilenzahl, Zeitraum und
SHA256-Prüfsumme je Datei.

## Schritt 5 – Prüfen und hochladen

```
python -m daytrader verify
```

Erwartet:

```
OK       BTCUSDT    155,520 bars  2025-03-15 .. 2026-09-06  (540 days)
OK       ETHUSDT    155,520 bars  2025-03-15 .. 2026-09-06  (540 days)
OK       SOLUSDT    155,520 bars  2025-03-15 .. 2026-09-06  (540 days)

all checksums match
```

Dann hochladen:

```
git add data/exchange
git commit -m "Add exchange candles for backtesting"
git push
```

Fragt Git nach Zugangsdaten: dein GitHub-Benutzername, und als Passwort ein
Personal Access Token (nicht dein Kontopasswort). Token erstellen unter
<https://github.com/settings/tokens> mit dem Haken bei `repo`.

## Schritt 6 – Mir Bescheid sagen

Schreib mir einfach „Daten sind oben". Ich ziehe sie, prüfe die Checksummen gegen
das Manifest und rechne dann das durch, was bisher nicht ging:

- Strategievergleich auf echten Kerzen, in- und out-of-sample
- die Kostenrechnung mit dem tatsächlichen ATR statt einem synthetischen
- ob `donchian_breakout` und `squeeze_breakout` ihre Vorauswahl bestätigen

---

## Wenn Binance bei dir blockiert ist

`data-api.binance.vision` ist ein reiner Datenserver ohne Konto und ohne
Registrierung, aus Deutschland normalerweise erreichbar. Falls doch nicht, testest
du das so:

```
curl -s -o /dev/null -w "%{http_code}\n" https://data-api.binance.vision/api/v3/ping
```

`200` heißt offen. Kommt `000` oder ein Timeout, sag mir Bescheid – dann baue ich
dir einen Adapter für Kraken oder Bybit, die aus anderen Netzen oft durchkommen.
Das sind etwa dreißig Zeilen, der Rest des Bots bleibt unverändert.

---

## Alternative Wege

**Die Netzwerk-Policy der Umgebung ändern.** Sauberste Lösung auf Dauer: Wenn du
eine neue Claude-Umgebung mit einer Policy anlegst, die `data-api.binance.vision`
erlaubt, hole ich die Daten selbst und du musst gar nichts tun. Wie Umgebungen und
ihre Netzwerkregeln funktionieren, steht hier:
<https://code.claude.com/docs/en/claude-code-on-the-web>

**Fertige CSV-Dateien.** Hast du schon Kerzendaten von woanders – TradingView-Export,
ein Datenanbieter, ein alter Download – schick sie mir. Ich brauche pro Zeile
Zeitstempel, Open, High, Low, Close, Volumen. Der Loader prüft die Daten ohnehin auf
unmögliche OHLC-Werte, doppelte Zeitstempel und Lücken, bevor irgendetwas gerechnet
wird.

---

## Wenn etwas klemmt

| Meldung | Ursache |
|---|---|
| `python: command not found` | Unter Windows `py` statt `python3`, oder PATH-Haken beim Installer vergessen |
| `No module named daytrader` | Du stehst nicht im Ordner `Claude`, oder das venv ist nicht aktiviert |
| `could not reach Binance market data` | Netzwerk oder Geo-Sperre – siehe Abschnitt oben |
| `file is 100.00 MB; this exceeds GitHub's limit` | Zu viele Tage auf einmal; nimm `--days 365` |
| `verification failed` | Datei beim Übertragen beschädigt: `data/exchange` löschen und Schritt 4 wiederholen |

Bei allem anderen: schick mir die Fehlermeldung im Wortlaut, dann sehe ich es mir an.
