"""Hand candles from a machine with exchange access to one without.

The container this bot was developed in cannot reach any exchange: the network
policy blocks them. GitHub is reachable, so the repository itself becomes the
transport. This module writes the candles into a committed folder together
with a manifest, so the receiving side can prove it got exactly what was sent
rather than trusting that a large binary survived the round trip.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

MANIFEST = "manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(frames: dict[str, pd.DataFrame], interval: str, out_dir: Path,
          source: str = "data-api.binance.vision") -> Path:
    """Write one parquet per symbol plus a manifest describing all of them."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for symbol, df in frames.items():
        path = out_dir / f"{symbol.upper()}_{interval}.parquet"
        df.to_parquet(path, compression="zstd")
        entries.append({
            "symbol": symbol.upper(),
            "interval": interval,
            "file": path.name,
            "rows": int(len(df)),
            "first_bar": df.index[0].isoformat(),
            "last_bar": df.index[-1].isoformat(),
            "first_close": float(df["close"].iloc[0]),
            "last_close": float(df["close"].iloc[-1]),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
        log.info("%s -> %s (%d rows, %.1f MB)", symbol, path.name,
                 len(df), path.stat().st_size / 1e6)

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "interval": interval,
        "datasets": entries,
    }
    manifest_path = out_dir / MANIFEST
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


def verify(out_dir: Path) -> tuple[bool, list[str]]:
    """Check every file against the manifest. Returns (ok, messages)."""
    out_dir = Path(out_dir)
    manifest_path = out_dir / MANIFEST
    if not manifest_path.exists():
        return False, [f"no {MANIFEST} in {out_dir}"]

    manifest = json.loads(manifest_path.read_text())
    messages, ok = [], True

    for entry in manifest["datasets"]:
        path = out_dir / entry["file"]
        if not path.exists():
            messages.append(f"MISSING  {entry['file']}")
            ok = False
            continue

        actual = sha256(path)
        if actual != entry["sha256"]:
            messages.append(f"CORRUPT  {entry['file']} -- checksum does not match the manifest")
            ok = False
            continue

        df = pd.read_parquet(path)
        if len(df) != entry["rows"]:
            messages.append(f"CORRUPT  {entry['file']} -- {len(df)} rows, manifest says {entry['rows']}")
            ok = False
            continue

        span_days = (pd.Timestamp(entry["last_bar"]) - pd.Timestamp(entry["first_bar"])).days
        messages.append(
            f"OK       {entry['symbol']:<10} {entry['rows']:>7,} bars  "
            f"{entry['first_bar'][:10]} .. {entry['last_bar'][:10]}  ({span_days} days)"
        )
    return ok, messages


def install(out_dir: Path, cache_dir: Path) -> list[str]:
    """Copy verified exported candles into the working cache."""
    out_dir, cache_dir = Path(out_dir), Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((out_dir / MANIFEST).read_text())

    installed = []
    for entry in manifest["datasets"]:
        target = cache_dir / entry["file"]
        target.write_bytes((out_dir / entry["file"]).read_bytes())
        installed.append(f"{entry['symbol']} -> {target}")
    return installed
