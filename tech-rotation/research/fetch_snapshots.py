#!/usr/bin/env python3
"""Holt den Wikipedia-Artikel "Nasdaq-100" so, wie er am Ersten jedes Monats aussah.

Das ist die Quelle fuer das Point-in-time-Universum: was man an einem Stichtag
ueber die Indexzusammensetzung wissen konnte, ohne Kenntnis spaeterer
Ereignisse. Die Versionsgeschichte des Artikels liefert genau das.

Laeuft im GitHub-Runner (die Entwicklungsumgebung erreicht Wikipedia nicht).
Gespeichert werden je Monat alle Tabellen mit mindestens 20 Zeilen als CSV,
dazu die Revisionsnummer -- damit ist jeder Schnappschuss zitierbar und
nachpruefbar. Hat ein Monat keine solche Tabelle (aeltere Artikelfassungen
listen Bestandteile teils als Fliesstext), wird stattdessen der Wikitext
gesichert.

    python research/fetch_snapshots.py [--von 2017-12] [--bis 2026-11]
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from datetime import date
from io import StringIO
from pathlib import Path

import httpx
import pandas as pd

API = "https://en.wikipedia.org/w/api.php"
TITEL = "Nasdaq-100"
ZIEL = Path(__file__).resolve().parent / "sources" / "nasdaq100"
# Wikimedia verlangt einen User-Agent mit Kontaktangabe (URL oder E-Mail),
# sonst antwortet die API mit 403 "Please respect our robot policy". Als
# Kontakt dient das Repository, keine personenbezogene Adresse.
KOPF = {
    "User-Agent": (
        "techrot-research/1.0 "
        "(https://github.com/p48khwpkjc-dotcom/Claude; point-in-time index study) "
        f"httpx/{httpx.__version__}"
    )
}


def monate(von: str, bis: str) -> list[date]:
    j, m = map(int, von.split("-"))
    ende_j, ende_m = map(int, bis.split("-"))
    out = []
    while (j, m) <= (ende_j, ende_m):
        out.append(date(j, m, 1))
        m += 1
        if m == 13:
            j, m = j + 1, 1
    return out


def revision_am(client: httpx.Client, stichtag: date) -> tuple[int, str] | None:
    """Letzte Revision vor Mitternacht UTC des Stichtags."""
    r = client.get(
        API,
        params={
            "action": "query",
            "prop": "revisions",
            "titles": TITEL,
            "redirects": 1,
            "rvlimit": 1,
            "rvstart": f"{stichtag.isoformat()}T00:00:00Z",
            "rvdir": "older",
            "rvprop": "ids|timestamp",
            "format": "json",
            "formatversion": 2,
        },
    )
    r.raise_for_status()
    seiten = r.json().get("query", {}).get("pages", [])
    if not seiten or "revisions" not in seiten[0]:
        return None
    rev = seiten[0]["revisions"][0]
    return int(rev["revid"]), rev["timestamp"]


def html_der_revision(client: httpx.Client, revid: int) -> str:
    r = client.get(
        API,
        params={
            "action": "parse",
            "oldid": revid,
            "prop": "text",
            "format": "json",
            "formatversion": 2,
        },
    )
    r.raise_for_status()
    return r.json()["parse"]["text"]


def wikitext_der_revision(client: httpx.Client, revid: int) -> str:
    r = client.get(
        API,
        params={
            "action": "query",
            "prop": "revisions",
            "revids": revid,
            "rvprop": "content",
            "rvslots": "main",
            "format": "json",
            "formatversion": 2,
        },
    )
    r.raise_for_status()
    seite = r.json()["query"]["pages"][0]
    return seite["revisions"][0]["slots"]["main"]["content"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--von", default="2017-12")
    p.add_argument("--bis", default=date.today().strftime("%Y-%m"))
    args = p.parse_args(argv)

    ZIEL.mkdir(parents=True, exist_ok=True)
    index_pfad = ZIEL / "index.json"
    index = json.loads(index_pfad.read_text()) if index_pfad.exists() else {}

    fehler = 0
    abgelehnt_in_folge = 0
    with httpx.Client(headers=KOPF, timeout=60.0, follow_redirects=True) as client:
        for stichtag in monate(args.von, args.bis):
            if abgelehnt_in_folge >= 3:
                # Drei 403 hintereinander: die Gegenseite lehnt grundsaetzlich
                # ab. Weiterzufragen waere genau das, was die Richtlinie verbietet.
                print("Abbruch: drei Ablehnungen in Folge (403).", file=sys.stderr)
                fehler += 1
                break
            schluessel = stichtag.strftime("%Y-%m")
            if schluessel in index and index[schluessel].get("ok"):
                continue  # schon vorhanden -- Lauf ist wiederholbar

            try:
                treffer = revision_am(client, stichtag)
                if treffer is None:
                    print(f"{schluessel}: keine Revision gefunden", file=sys.stderr)
                    fehler += 1
                    continue
                revid, zeit = treffer
                time.sleep(0.4)

                html = html_der_revision(client, revid)
                time.sleep(0.4)
                try:
                    tabellen = pd.read_html(StringIO(html))
                except ValueError:
                    tabellen = []

                gesichert = []
                for i, t in enumerate(tabellen):
                    if len(t) < 20:
                        continue
                    # Mehrstufige Kopfzeilen flachklopfen, damit die CSV lesbar bleibt.
                    if isinstance(t.columns, pd.MultiIndex):
                        t.columns = [" / ".join(str(x) for x in c if "Unnamed" not in str(x)) for c in t.columns]
                    datei = ZIEL / f"{schluessel}_r{revid}_t{i}.csv"
                    t.to_csv(datei, index=False)
                    gesichert.append({"datei": datei.name, "zeilen": len(t), "spalten": [str(c) for c in t.columns]})

                eintrag = {"ok": True, "revid": revid, "zeit": zeit, "tabellen": gesichert}
                if not any(g["zeilen"] >= 80 for g in gesichert):
                    # Keine Tabelle in Indexgroesse: Wikitext als Rueckfallebene sichern.
                    text = wikitext_der_revision(client, revid)
                    time.sleep(0.4)
                    wt = ZIEL / f"{schluessel}_r{revid}.wiki.gz"
                    wt.write_bytes(gzip.compress(text.encode("utf-8")))
                    eintrag["wikitext"] = wt.name

                index[schluessel] = eintrag
                groesste = max((g["zeilen"] for g in gesichert), default=0)
                print(f"{schluessel}: Revision {revid} vom {zeit}, {len(gesichert)} Tabellen, groesste {groesste} Zeilen"
                      + (" -- Wikitext gesichert" if "wikitext" in eintrag else ""))
            except httpx.HTTPStatusError as exc:
                print(f"{schluessel}: HTTP {exc.response.status_code}: {exc.response.text[:160]}",
                      file=sys.stderr)
                fehler += 1
                abgelehnt_in_folge = abgelehnt_in_folge + 1 if exc.response.status_code == 403 else 0
                time.sleep(3)
                continue
            except httpx.HTTPError as exc:
                print(f"{schluessel}: Netzfehler {exc}", file=sys.stderr)
                fehler += 1
                time.sleep(3)
                continue
            abgelehnt_in_folge = 0

            # Zwischenstand sichern: ein Abbruch kostet so keine fertigen Monate.
            index_pfad.write_text(json.dumps(index, indent=1, sort_keys=True))

    print(f"\n{sum(1 for v in index.values() if v.get('ok'))} Monate gesichert, {fehler} Fehler")
    return 1 if fehler else 0


if __name__ == "__main__":
    raise SystemExit(main())
