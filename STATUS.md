# Wo das Projekt steht

Kurznotiz für eine neue Sitzung. Wenn du diese Datei liest, weil du gerade neu
gestartet bist: alles Wichtige liegt im Repo, es geht nichts verloren.

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

## Was noch fehlt

**Der Backtest auf echten Kerzen.** Bisher scheiterte er nur daran, dass die
Umgebung keine Börse erreichen durfte.

## Nächster Schritt

Prüfen, ob der Datenzugang jetzt offen ist:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://data-api.binance.vision/api/v3/ping
```

`200` heißt offen. Dann:

```bash
pip install -r requirements.txt
python -m daytrader fetch --days 540      # dauert 10-20 Minuten
python -m daytrader backtest              # -> out/report.md
python -m daytrader costs                 # mit echtem ATR statt synthetischem
```

Kommt `000`, ist der Netzwerkzugang noch zu – dann steht in
[DATEN-HOLEN.md](DATEN-HOLEN.md), wie die Daten sonst hereinkommen.

## Worauf es beim Auswerten ankommt

Der Regime-Prüfstand hat das Feld vorsortiert. **donchian_breakout** und
**squeeze_breakout** halten ihre Verträge und schweigen dort, wo sie nicht
funktionieren (15 % bzw. 30 % Fehlsignale). **rsi_reversion** feuert zu 99,9 %
im falschen Regime, **ema_momentum** zu 85 %. Auf echten Daten sind also die
ersten beiden die Kandidaten – die anderen dienen als Kontrollgruppe.

Wichtig beim Lesen des Reports: Profitfaktor unter 1,2 überlebt keinen
Regimewechsel, und die Lücke zwischen In-Sample und Out-of-Sample ist die
Ehrlichkeitsprüfung. Halbiert sich eine Strategie außerhalb der Stichprobe,
wurde sie angepasst und nicht entdeckt.

Und der Befund, der alles andere überlagert: bei einem 1,2×ATR-Stop auf 5m-Kerzen
fressen Gebühren und Slippage rund 0,69 R pro Trade. Enge Intraday-Stops sind
meist unwirtschaftlich – siehe `daytrader costs`.
