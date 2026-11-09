# Ehrlicher Backtest der Tech-Rotation

Die 36 Titel in `config.yaml` wurden im September 2026 ausgewählt — also mit
dem Wissen, welche Tech-Werte es bis dahin geschafft haben. Ein Backtest auf
dieser Liste ist **survivorship-verzerrt**: er kann nur Gewinner wählen, weil
die Verlierer gar nicht auf der Liste stehen. Er sieht systematisch zu gut aus.

Dieser Ordner enthält die ehrliche Fassung: an jedem Stichtag darf die Strategie
nur aus Titeln wählen, die damals im Nasdaq-100 waren — einschließlich der
später übernommenen, abgestiegenen und vergessenen.

## Ablauf

| Schritt | Skript | Wo | Ergebnis |
|---|---|---|---|
| 1 | `fetch_snapshots.py` | GitHub-Runner | `sources/` — Wikipedia-Artikel am Ersten jedes Monats |
| 2 | `build_universe.py` | lokal | `data/universe/membership.csv` |
| 3 | `validate_universe.py` | lokal | `data/universe/validation.txt` |
| 4 | `fetch_prices.py` | GitHub-Runner | `data/prices/` — eingefrorene Kurse |
| 5 | `run_backtests.py` | lokal | `results/` |

Schritte 1 und 4 brauchen Netz und laufen im Workflow
`.github/workflows/tech-rotation-research.yml`. Ihr Ergebnis wird als
**eingefrorener Datensatz** committet: jeder spätere Lauf rechnet auf exakt
denselben Zahlen, und niemand kann die Daten nachträglich so ziehen, dass das
Ergebnis besser aussieht.

## Universum

**Quelle:** die Versionsgeschichte des Wikipedia-Artikels „Nasdaq-100" (ab
Mitte 2026 „List of NASDAQ-100 companies"), jeweils die letzte Fassung vor dem
Ersten des Monats, 00:00 UTC. Jede verwendete Revisionsnummer steht in
`data/universe/provenance.csv`.

**Warum das ehrlich ist:** Der Artikelstand am Stichtag ist, was man an diesem
Tag wissen konnte. Der Signaltag der Strategie ist der erste Handelstag des
Monats und liegt damit nie vor dem Schnappschuss.

**Geprüft:** gegen die Änderungstabelle des Listenartikels, eine unabhängige
Aufzeichnung derselben Ereignisse. Siehe `data/universe/validation.txt`.
Abweichungen um einen Monat sind Redaktionsverzug im Artikel — der Wechsel
kommt im Backtest dann einen Monat später an. Das kostet Genauigkeit beim
Zeitpunkt, bringt aber kein Zukunftswissen ein.

**Umbenennungen** (FB → META, Symantec → Gen Digital …) stehen in
`aliases.csv`. Übernommene Titel bekommen ausdrücklich keinen Eintrag: ihre
Kurse werden unter dem alten Symbol gesucht, und fehlen sie, steht das in der
Abdeckungsstatistik.

**Tech-Filter:** GICS-Sektor Information Technology oder Communication
Services, wie im jeweiligen Monat gelistet. Fehlt die Angabe, gilt der Eintrag
desselben Titels aus dem zeitlich nächsten Monat, sonst `sectors_manual.csv`.
Der Sektor eines Unternehmens ist keine Information über seine spätere
Kursentwicklung; Survivorship-Bias entsteht dadurch nicht.

## Engine

Der Backtest ruft dieselben Funktionen auf wie der Live-Betrieb. Zwei
Ergänzungen machen ihn survivorship-fest (`src/techrot/backtest.py`):

- `universe_at`: das Universum wird an jedem Signaltag neu bestimmt.
- Endet die Kursreihe eines gehaltenen Titels (Übernahme, Delisting), wird er
  am ersten Tag danach zum letzten Kurs in Cash umgewandelt. Ohne diesen
  Schritt bewertete das Depot ihn mit null — ein fiktiver Totalverlust.

## Regeln für die Auswertung

Die Strategieparameter stammen unverändert aus `config.yaml`. Sie wurden nie an
Daten angepasst. **Wer nach diesem Backtest Parameter verstellt, bis das
Ergebnis besser aussieht, hat es wertlos gemacht** — der Backtest misst dann
nur noch, wie gut man sich an die Vergangenheit anpassen kann.

## Grenzen

- **Datenlücken:** Für manche übernommenen Titel liefert keine freie Quelle
  mehr Kurse. Sie fallen aus dem wählbaren Universum. Umfang und Namen stehen
  in `results/ergebnisse.json` unter `abdeckung`.
- **Gestaltungsrückschau:** Die Strategie selbst — Momentum auf Tech — wurde
  2026 entworfen, mit dem Wissen, dass Momentum und Tech in diesem Zeitraum
  funktioniert haben. Kein Backtest kann das herausrechnen.
- **Kosten:** 5 bp Slippage und 1 bp Gebühr im Standardfall; die Variante
  `tech_teuer` rechnet mit dem Fünffachen.
- **Steuern** sind nicht berücksichtigt.
