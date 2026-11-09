#!/usr/bin/env python3
"""Baut aus den Wikipedia-Schnappschuessen das Point-in-time-Universum.

Eingang:  research/sources/nasdaq100/  (vom Runner geholt, je Monat ein Stand)
Ausgang:  research/data/universe/membership.csv
          Spalten: month, listed, symbol
          ``listed`` ist der Ticker so, wie er damals im Artikel stand;
          ``symbol`` ist das Symbol, unter dem es heute Kurse gibt (FB -> META).

Jede Umbenennung steht in ``aliases.csv`` und ist damit pruefbar. Geraten
wird nichts: ein Ticker ohne Eintrag bleibt, wie er ist, und faellt
spaetestens beim Kursabruf als fehlend auf.

    python research/build_universe.py
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

import pandas as pd

HIER = Path(__file__).resolve().parent
QUELLE = HIER / "sources" / "nasdaq100"
# Ab Sommer 2026 steht die Liste in einem eigenen Artikel.
LISTE = HIER / "sources" / "nasdaq100_liste"
ZIEL = HIER / "data" / "universe"
TICKER_SPALTE = re.compile(r"^(ticker|symbol|ticker symbol)\b", re.I)
# Nur GICS-Sektoren. Ab Ende 2025 listet der Artikel ICB -- eine andere
# Taxonomie; beide zu mischen hiesse, Titel je nach Monat anders einzuordnen.
SEKTOR_SPALTE = re.compile(r"^gics\s*sector$", re.I)
TECH_SEKTOREN = {"Information Technology", "Communication Services"}
ERSTER_PFLICHTMONAT = "2019-01"
# Aeltere Fassungen: "* [[Apple Inc.]] (AAPL)" in einer columns-list.
WIKI_POSTEN = re.compile(r"^\*.*\(\s*(?:NASDAQ:\s*)?([A-Z][A-Z0-9.]{0,6})\s*\)\s*$", re.M)
GUELTIG = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def tickerspalte(t: pd.DataFrame) -> str | None:
    for c in t.columns:
        if TICKER_SPALTE.search(str(c).strip()):
            return c
    return None


def bereinigen(roh: str) -> str | None:
    s = str(roh).strip().upper()
    s = re.sub(r"\[.*?\]", "", s)          # Fussnoten [1]
    s = s.split(":")[-1].strip()           # "NASDAQ: AAPL"
    s = s.replace(" ", " ").split()[0] if s else s
    return s if s and GUELTIG.match(s) else None


def sektorspalte(t: pd.DataFrame) -> str | None:
    for c in t.columns:
        if SEKTOR_SPALTE.search(re.sub(r"\[.*?\]", "", str(c)).strip()):
            return c
    return None


def aus_tabellen(ordner: Path, eintrag: dict) -> tuple[list[tuple[str, str | None]], str] | None:
    """Ticker und Sektor aus der passenden Tabelle eines Monatsstands."""
    kandidaten = []
    for tab in eintrag.get("tabellen", []):
        t = pd.read_csv(ordner / tab["datei"], dtype=str)
        spalte = tickerspalte(t)
        if spalte is None:
            continue
        sektor = sektorspalte(t)
        paare = []
        for _, zeile in t.iterrows():
            tk = bereinigen(zeile[spalte]) if pd.notna(zeile[spalte]) else None
            if tk:
                paare.append((tk, str(zeile[sektor]).strip() if sektor and pd.notna(zeile[sektor]) else None))
        if len(paare) >= 80:
            kandidaten.append((abs(len(paare) - 101), tab["datei"], paare))
    if not kandidaten:
        return None
    kandidaten.sort(key=lambda k: k[0])
    return kandidaten[0][2], kandidaten[0][1]


def aus_wikitext(ordner: Path, eintrag: dict) -> tuple[list[tuple[str, str | None]], str] | None:
    """Ticker aus dem Components-Abschnitt aelterer Fassungen (ohne Sektor)."""
    if "wikitext" not in eintrag:
        return None
    text = gzip.decompress((ordner / eintrag["wikitext"]).read_bytes()).decode("utf-8")
    a = text.find("==Components==")
    if a < 0:
        return None
    b = text.find("\n==", a + 5)
    abschnitt = text[a : b if b > 0 else None]
    ticker = [m.group(1) for m in WIKI_POSTEN.finditer(abschnitt)]
    if len(ticker) < 80:
        return None
    return [(t, None) for t in ticker], eintrag["wikitext"]


def sektoren_ergaenzen(m: pd.DataFrame) -> pd.DataFrame:
    """Fuellt fehlende GICS-Sektoren auf, mit Herkunftsangabe je Zeile.

    1. Gelistet im selben Monat -- unveraendert.
    2. Sonst der Eintrag desselben Symbols aus dem zeitlich naechsten Monat.
       Der Sektor eines Unternehmens ist keine Information ueber seine
       spaetere Kursentwicklung; Survivorship-Bias entsteht dadurch nicht.
    3. Sonst die Handklassifikation in sectors_manual.csv.
    """
    m = m.copy()
    m["_t"] = pd.PeriodIndex(m["month"], freq="M").astype("int64")
    gelistet = m.dropna(subset=["sector"])[["symbol", "_t", "sector"]]
    for i in m.index[m["sector"].isna()]:
        kand = gelistet[gelistet["symbol"] == m.at[i, "symbol"]]
        if len(kand):
            naechster = kand.iloc[(kand["_t"] - m.at[i, "_t"]).abs().argmin()]
            m.at[i, "sector"] = naechster["sector"]
            m.at[i, "sector_source"] = "naechster_monat"

    hand_pfad = ZIEL / "sectors_manual.csv"
    if hand_pfad.exists():
        hand = pd.read_csv(hand_pfad, dtype=str, comment="#")
        karte = dict(zip(hand["symbol"].str.strip(), hand["sector"].str.strip()))
        offen = m["sector"].isna() & m["symbol"].isin(karte)
        m.loc[offen, "sector"] = m.loc[offen, "symbol"].map(karte)
        m.loc[offen, "sector_source"] = "handklassifikation"
    return m.drop(columns="_t")


def lade_aliase() -> dict[str, str]:
    pfad = ZIEL / "aliases.csv"
    if not pfad.exists():
        return {}
    a = pd.read_csv(pfad, dtype=str, comment="#")
    return dict(zip(a["listed"].str.strip(), a["symbol"].str.strip()))


def main() -> int:
    index = json.loads((QUELLE / "index.json").read_text())
    liste = json.loads((LISTE / "index.json").read_text()) if (LISTE / "index.json").exists() else {}
    aliase = lade_aliase()
    zeilen, herkunft, probleme, hinweise = [], [], [], []

    for monat in sorted(set(index) | set(liste)):
        treffer, art, eintrag = None, None, None
        # Reihenfolge: Tabelle im Hauptartikel, Wikitext-Liste im Hauptartikel,
        # Tabelle im ausgelagerten Listenartikel.
        for ordner, quelle, versuch, name in (
            (QUELLE, index, aus_tabellen, "tabelle"),
            (QUELLE, index, aus_wikitext, "wikitext"),
            (LISTE, liste, aus_tabellen, "listenartikel"),
        ):
            if monat in quelle:
                treffer = versuch(ordner, quelle[monat])
                if treffer:
                    art, eintrag = name, quelle[monat]
                    break
        if not treffer:
            # Vor 2019 nur Vorlauf -- der Backtest beginnt im Januar 2019. Fehlt
            # dort ein Monat, ist das ein Hinweis; ab 2019 ist es ein Fehler.
            if monat >= ERSTER_PFLICHTMONAT:
                probleme.append(f"{monat}: keine Bestandteilliste gefunden")
            else:
                hinweise.append(monat)
            continue
        paare, datei = treffer
        herkunft.append({"month": monat, "quelle": art, "revid": eintrag["revid"],
                         "stand": eintrag["zeit"], "datei": datei})
        gesehen = set()
        for t, sektor in paare:
            if t in gesehen:
                continue
            gesehen.add(t)
            zeilen.append({"month": monat, "listed": t, "symbol": aliase.get(t, t), "sector": sektor})

    if not zeilen:
        print("Keine Mitglieder extrahiert.", file=sys.stderr)
        return 1

    m = pd.DataFrame(zeilen)
    m["sector_source"] = m["sector"].notna().map({True: "gelistet", False: None})
    m = sektoren_ergaenzen(m)
    m["tech"] = m["sector"].isin(TECH_SEKTOREN)

    ZIEL.mkdir(parents=True, exist_ok=True)
    m.to_csv(ZIEL / "membership.csv", index=False)
    pd.DataFrame(herkunft).to_csv(ZIEL / "provenance.csv", index=False)
    print("Quellen:", pd.DataFrame(herkunft)["quelle"].value_counts().to_dict())

    # ---- Pruefung --------------------------------------------------------
    anzahl = m.groupby("month").size()
    print(f"{anzahl.index[0]} bis {anzahl.index[-1]}: {len(anzahl)} Monate, "
          f"{m['symbol'].nunique()} verschiedene Symbole")
    print(f"Mitglieder je Monat: min {anzahl.min()}, max {anzahl.max()}, Median {anzahl.median():.0f}")
    auffaellig = anzahl[(anzahl < 98) | (anzahl > 106)]
    if len(auffaellig):
        print("Auffaellige Monate (erwartet 100-104):")
        for mon, n in auffaellig.items():
            print(f"  {mon}: {n}")

    vorher = None
    print("\nWechsel von Monat zu Monat:")
    for mon, g in m.groupby("month"):
        jetzt = set(g["symbol"])
        if vorher is not None and jetzt != vorher:
            rein, raus = sorted(jetzt - vorher), sorted(vorher - jetzt)
            print(f"  {mon}: +{len(rein)} {' '.join(rein)} | -{len(raus)} {' '.join(raus)}")
        vorher = jetzt
    ohne = sorted(m.loc[m["sector"].isna(), "symbol"].unique())
    print(f"\nSektorherkunft: {m['sector_source'].value_counts(dropna=False).to_dict()}")
    if ohne:
        print(f"Ohne Sektor ({len(ohne)}): {' '.join(ohne)}")
        probleme.append(f"{len(ohne)} Symbole ohne Sektor -- sectors_manual.csv ergaenzen")
    tech_je_monat = m[m["tech"]].groupby("month").size()
    print(f"Tech-Mitglieder (IT + Kommunikation) je Monat: "
          f"min {tech_je_monat.min()}, max {tech_je_monat.max()}, Median {tech_je_monat.median():.0f}")
    if hinweise:
        print(f"\nVorlauf ohne lesbare Liste (nicht gebraucht): {hinweise[0]} bis {hinweise[-1]}")
    for p in probleme:
        print("PROBLEM:", p, file=sys.stderr)
    return 1 if probleme else 0


if __name__ == "__main__":
    raise SystemExit(main())
