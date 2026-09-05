# Tech-Rotation

Monatliches Rebalancing in die momentumstaerksten US-Tech-Aktien. Vier Bausteine:
Datenbeschaffung, Ranking, Risikopruefung, Ausfuehrung. Jeder ist einzeln
testbar, alle laufen im Backtest und im Livebetrieb ueber denselben Code.

> **Kein Anlagerat.** Das hier ist ein Werkzeug, keine Empfehlung. Momentum-
> Strategien haben lange Durststrecken und heftige Trendwenden. Der Backtest
> zeigt, was in der Vergangenheit passiert waere, nicht was passieren wird.
> Standardmaessig handelt nichts mit echtem Geld -- siehe [Sicherungen](#sicherungen).

## Wie die Strategie arbeitet

**1. Daten.** Taegliche adjustierte Schlusskurse und Volumen fuer das
konfigurierte Universum plus Benchmark. Quelle ist standardmaessig Yahoo
(`yfinance`, kein API-Key). Alternativen: `stooq`, `local_csv`. Jeder Lauf
prueft je Ticker Historienlaenge, Aktualitaet und Datenluecken; wer durchfaellt,
kommt nicht ins Ranking und verzerrt auch den Querschnitt der anderen nicht.

**2. Ranking.** Der Score ist eine gewichtete Summe querschnittlicher z-Scores:

| Signal | Fenster | Gewicht |
| --- | --- | ---: |
| `mom_12_1` | Rendite t-252 bis t-21 | 40 % |
| `mom_6_1` | Rendite t-126 bis t-21 | 30 % |
| `mom_3_0` | Rendite t-63 bis heute | 15 % |
| `risk_adj_mom` | `mom_12_1` geteilt durch Volatilitaet | 15 % |

Der letzte Monat bleibt bei den langen Fenstern aussen vor, weil kurzfristiges
Momentum zur Umkehr neigt. z-Scores werden bei ±3 gekappt, damit ein einzelner
Ausreisser nicht die ganze Rangliste kippt.

**3. Risiko.** Zwei Ebenen.

*Je Titel* (wer darf ueberhaupt gekauft werden):
Mindestliquiditaet 50 Mio USD Tagesumsatz, Volatilitaetsobergrenze, positives
absolutes 12-1-Momentum, Kurs ueber der SMA200.

*Je Portfolio* (wie viel Kapital darf investiert sein):
Regime-Filter (faellt der Benchmark unter seine SMA200, geht alles in Cash),
Volatilitaets-Targeting auf 18 % p.a., Drawdown-Bremse ab 20 % Rueckgang,
Positionslimit 20 %, Mindestanzahl Titel, Turnover-Deckel 60 % je Rebalancing.

**4. Ausfuehrung.** Aus der Differenz zwischen Bestand und Zielgewichten
entstehen Marktorders -- Verkaeufe zuerst, damit die Liquiditaet fuer die Kaeufe
da ist. Orders unter 250 USD entfallen. Bestandsschutz haelt einen gehaltenen
Titel, solange er unter Rang 12 liegt; das druckt den Turnover deutlich, ohne
das Signal zu verwaessern.

## Installation

```bash
cd tech-rotation
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Benutzung

```bash
techrot check-data                 # Datenqualitaet je Ticker
techrot rank                       # aktuelle Rangliste
techrot backtest --out out/        # historische Simulation
techrot rebalance                  # Trockenlauf: was wuerde passieren
techrot rebalance --execute        # Orders senden (Papier, siehe unten)
techrot status                     # Depot, Cash, Drawdown
```

`--config <pfad>` waehlt eine andere Konfiguration, `--refresh` umgeht den
Kurscache, `--force` rebalanciert ausserhalb des Monatstermins.

### Ohne Netzzugang ausprobieren

```bash
python scripts/make_demo.py
techrot --config demo/config.yaml backtest
techrot --config demo/config.yaml rebalance --execute
```

Das erzeugt synthetische Kurse und eine passende Konfiguration. Die
Kennzahlen daraus sind bedeutungslos -- die Kurven sind glatt konstruiert, damit
die Mechanik pruefbar ist. Es geht um die Kette, nicht um die Rendite.

## Automatisierung

`.github/workflows/tech-rotation.yml` laeuft an jedem US-Handelstag um 13:00 UTC,
also vor der Eroeffnung. Der Job entscheidet nicht selbst, wann rebalanciert
wird: `techrot rebalance` handelt nur, wenn seit dem letzten Lauf ein
Kalendermonat vergangen ist. Ein ausgefallener Lauf holt den Termin am naechsten
Handelstag nach, statt den Monat zu ueberspringen.

Der Zustand (`data/state.json`) wird nach jedem Handel zurueck in den Branch
committet -- so ueberlebt das Depot zwischen zwei Laeufen, obwohl der Runner
zustandslos ist. `data/orders.jsonl` ist das Auditprotokoll: jede Order, jeder
Fill, jeder Fehler mit Zeitstempel.

Drei Dinge sind zu beachten:

- GitHub startet Cron-Workflows **nur vom Default-Branch**. Solange die Datei
  auf einem Feature-Branch liegt, funktioniert nur der manuelle Start ueber
  *Run workflow*.
- Broker-Zugangsdaten kommen aus den Repository-Secrets `ALPACA_API_KEY_ID`
  und `ALPACA_API_SECRET_KEY`.
- Der Workflow braucht `contents: write`, um den Zustand zu committen.

**Lokal statt GitHub** -- ein Cron-Eintrag reicht:

```cron
0 9 * * 1-5 cd /pfad/zu/tech-rotation && .venv/bin/techrot rebalance --execute >> logs/rebalance.log 2>&1
```

## Broker

| Broker | `execution.broker` | Was passiert |
| --- | --- | --- |
| Papier | `paper` | Fills werden lokal simuliert, mit Slippage und Kommission. Standard. |
| Alpaca | `alpaca` | Echte Marktorders ueber die Alpaca-REST-API. |

Der Paper-Broker rechnet Slippage immer gegen den Auftraggeber: Kaeufe fuellen
ueber, Verkaeufe unter dem Referenzkurs. Das Papierergebnis ist damit eher zu
pessimistisch als zu optimistisch.

Alpaca zielt standardmaessig auf den **Paper-Endpunkt** (`paper-api.alpaca.markets`).

### Sicherungen

Echter Handel verlangt drei unabhaengige Schritte -- eine vergessene Zeile
allein loest nichts aus:

1. `execution.broker: alpaca` in `config.yaml`
2. `execution.mode: live` in `config.yaml`
3. Umgebungsvariable `TECHROT_ALLOW_LIVE=I_UNDERSTAND`

Fehlt einer davon, verweigert `AlpacaBroker` den Start. Zusaetzlich ist
`techrot rebalance` ohne `--execute` immer ein reiner Trockenlauf, und die
Kombination `broker: paper` mit `mode: live` lehnt schon die
Konfigurationspruefung ab.

## Konfiguration

Alles steckt in `config.yaml`; die Datei ist durchkommentiert. Die Parameter mit
der groessten Wirkung:

| Parameter | Standard | Wirkung |
| --- | --- | --- |
| `selection.top_n` | 8 | Wie viele Titel gehalten werden |
| `selection.buffer_rank` | 12 | Bestandsschutz: Turnover runter, Traegheit rauf |
| `risk.portfolio.vol_target` | 0.18 | Zielvolatilitaet des Portfolios p.a. |
| `risk.portfolio.regime_sma` | 200 | Ab wann der Markt als Baisse gilt (0 = aus) |
| `risk.portfolio.max_turnover_per_rebalance` | 0.60 | Deckel gegen Umschichtungsorgien |
| `ranking.weights` | s.o. | Gewichtung der Momentum-Horizonte |

Die Konfiguration wird beim Laden vollstaendig validiert: Tippfehler in
Schluesselnamen, ein `top_n` groesser als das Universum, ein Positionslimit, das
die Zielexposure nicht tragen kann, oder eine zu kurze Historie fuer den
laengsten Lookback brechen den Lauf ab, statt still etwas anderes zu tun.

Das Universum ist bewusst eine statische, versionierte Liste. Wer es
nachzieht, sollte die Aenderung committen -- sonst wird jeder Backtest
rueckwirkend mit den heutigen Gewinnern gerechnet (Survivorship-Bias).

## Tests

```bash
python -m pytest -q          # 82 Tests
```

Die Fixtures sind analytisch konstruiert (exponentieller Trend mal Sinuswelle),
nicht zufaellig -- damit sind Momentum-Reihenfolge und Volatilitaet exakt
vorhersagbar und die Tests haben keine Flake-Quelle.

Abgedeckt sind unter anderem: die Renditemessung auf bekannten Kursreihen, jeder
einzelne Risikofilter, die Turnover-Bremse, das Positionslimit, Zustands-
Persistenz, Ausfuehrung samt Journal, das Weiterlaufen nach einer abgelehnten
Order und der Lookahead-Schutz.

Der letzte Punkt ist der wichtigste: `test_kein_lookahead` prueft, dass ein Plan
zum Stichtag identisch ausfaellt, egal ob spaetere Kurse im Panel stehen oder
nicht. Fiele der Test, waere jede Backtest-Zahl wertlos.

## Aufbau

```
config.yaml              Alle Parameter
src/techrot/
  config.py              Laden und Validieren
  data.py                Provider, Cache, Qualitaetspruefung
  ranking.py             Momentum-Kennzahlen und Score
  risk.py                Eignungsfilter und Exposure-Entscheidung
  portfolio.py           Auswahl, Gewichte, Turnover, Orders
  brokers.py             Paper- und Alpaca-Anbindung
  execution.py           Der Lauf: Plan bauen, Plan ausfuehren
  backtest.py            Monatliche Simulation
  report.py              Konsolen- und Markdown-Ausgabe
  cli.py                 Kommandozeile
scripts/make_demo.py     Synthetisches Setup ohne Netz
tests/                   82 Tests
```

`plan_rebalance` ist frei von Seiteneffekten und liefert einen vollstaendig
begruendeten Plan; erst `execute_plan` schickt Orders los. Deshalb ist der
Trockenlauf eine echte Vorschau und nicht bloss eine Schaetzung -- er durchlaeuft
exakt dieselbe Logik.

## Bekannte Grenzen

- **Nur Long, nur US-Aktien.** Keine Shorts, keine Hebel, keine Optionen.
- **Tagesschluss-Daten.** Signale entstehen aus dem Vortagesschluss, Orders sind
  Marktorders zur Eroeffnung. Der Backtest bildet das mit einem Handelstag
  Versatz ab, kennt aber keine Eroeffnungskurse -- er rechnet mit dem
  Schlusskurs des Folgetages.
- **Keine Steuern.** Kosten sind nur Slippage und Kommission. Bei monatlicher
  Rotation ist die Steuerlast in einem Privatdepot ein realer Renditefaktor.
- **Keine Corporate Actions ausser Splits/Dividenden**, die ueber die
  adjustierten Kurse bereits eingerechnet sind. Uebernahmen und Delistings
  fallen ueber die Datenqualitaetspruefung heraus, werden aber nicht sauber
  abgewickelt.
- **Statisches Universum.** Neue Titel kommen nur durch eine Aenderung an
  `config.yaml` hinzu.
