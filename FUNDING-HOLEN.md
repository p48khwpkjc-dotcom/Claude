# Funding-Raten in den Bot bekommen

Die Netzwerk-Policy dieser Umgebung lässt genau einen Binance-Host durch:
`data-api.binance.vision`, und der liefert nur Spot-Daten. Der Futures-Host
`fapi.binance.com` und das Archiv `data.binance.vision` werden beide auf
Proxy-Ebene mit 403 abgewiesen, ebenso Bybit, OKX, Hyperliquid und CoinGecko.

Also derselbe Weg wie schon bei den Kerzen: du holst die Raten auf deinem
Rechner, pushst sie, ich rechne. Aufwand bei dir: ein paar Minuten, davon das
meiste Warten.

Prüfen, ob du überhaupt durchkommst:

```
curl -s -o /dev/null -w "%{http_code}\n" "https://fapi.binance.com/fapi/v1/ping"
```

`200` heißt gut. `451` heißt, dass Binance dein Land sperrt — dann brauchst du
eine andere Quelle, und der Abschnitt ganz unten sagt, welches Format der Bot
sonst noch frisst.

---

## Schritt 1 – Repo holen

```
git clone https://github.com/p48khwpkjc-dotcom/Claude.git
cd Claude
git checkout claude/status-md-lesen-vylgn6
pip install -r requirements.txt
```

## Schritt 2 – Raten herunterladen

```
python scripts/fetch_funding.py
```

Das Skript zieht die Funding-Historie für die konfigurierten Symbole, so weit
zurück, wie Binance sie hergibt (bei BTC und ETH bis 2019), und legt je Symbol
eine CSV unter `data/exchange/funding/` ab. Kein API-Key, kein Konto.

Einzelne Symbole oder ein kürzerer Zeitraum:

```
python scripts/fetch_funding.py --symbols BTCUSDT,ETHUSDT --days 1500
```

## Schritt 3 – Prüfen

```
python scripts/fetch_funding.py --verify
```

Zeigt je Symbol, wie viele Perioden geladen wurden, den Zeitraum, den
Mittelwert der Rate und was der annualisiert bedeutet. Wenn hier steht

```
BTCUSDT   8,412 Perioden  2019-09-10 .. 2026-09-08   Mittel 0.0094 %   = 10.3 % p.a.
```

dann ist alles da, was der Backtest braucht.

## Schritt 4 – Pushen

```
git add data/exchange/funding
git commit -m "Funding-Raten von Binance"
git push
```

`data/exchange/` ist bewusst **nicht** in `.gitignore` — das ist der
Transportweg. Die Dateien sind klein: rund 8.400 Zeilen je Symbol und Jahrzehnt,
also wenige hundert Kilobyte insgesamt.

Danach sagst du mir Bescheid, ich ziehe den Branch und rechne.

---

## Wenn Binance bei dir gesperrt ist

Der Bot liest jede CSV, die zwei Spalten hat:

| Spalte | Inhalt |
|---|---|
| `fundingTime` oder `time` | Zeitstempel — Millisekunden seit 1970 oder ISO-8601 |
| `fundingRate` oder `funding_rate` | Rate je Periode als Dezimalzahl, `0.0001` = 0,01 % |

Dateiname: `data/exchange/funding/<SYMBOL>_funding.csv`.

Damit funktioniert auch jede andere Quelle — Bybit, OKX, ein
Coinglass-Export, oder was auch immer du erreichst. Wichtig ist nur, dass die
Rate **je Periode** angegeben ist und nicht schon annualisiert. Wer eine
annualisierte Zahl einliest, misst um den Faktor 1.095 daneben, und der
Backtest hat keine Möglichkeit, das zu merken.

## Was danach passiert

Meine Erwartung steht in [research/FUNDING_ERWARTUNG.md](research/FUNDING_ERWARTUNG.md),
geschrieben bevor eine einzige historische Rate gemessen war: **4 bis 12 % im
Jahr brutto**, und ausdrücklich nichts in der Nähe von 15 bis 25 % im Monat.
Danach berichte ich, was die Daten sagen — auch wenn es weniger ist.
