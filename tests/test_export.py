"""The repository is the transport for candles. It has to be a reliable one."""

import json
from pathlib import Path

import pandas as pd
import pytest

from daytrader.data import export
from daytrader.data.synthetic import generate


@pytest.fixture
def staged(tmp_path: Path) -> Path:
    frames = {"BTCUSDT": generate(bars=500, seed=1), "ETHUSDT": generate(bars=500, seed=2)}
    export.write(frames, "5m", tmp_path / "exchange")
    return tmp_path / "exchange"


def test_export_writes_a_file_per_symbol_and_a_manifest(staged: Path):
    assert (staged / "BTCUSDT_5m.parquet").exists()
    assert (staged / "ETHUSDT_5m.parquet").exists()
    manifest = json.loads((staged / "manifest.json").read_text())
    assert len(manifest["datasets"]) == 2
    assert manifest["interval"] == "5m"
    assert all(len(d["sha256"]) == 64 for d in manifest["datasets"])


def test_verification_passes_on_untouched_files(staged: Path):
    ok, messages = export.verify(staged)
    assert ok
    assert all(m.startswith("OK") for m in messages)


def test_verification_catches_a_corrupted_file(staged: Path):
    target = staged / "BTCUSDT_5m.parquet"
    df = pd.read_parquet(target)
    df.loc[df.index[10], "close"] *= 1.05      # one price quietly altered
    df.to_parquet(target, compression="zstd")

    ok, messages = export.verify(staged)
    assert not ok
    assert any("CORRUPT" in m for m in messages)


def test_verification_catches_a_missing_file(staged: Path):
    (staged / "ETHUSDT_5m.parquet").unlink()
    ok, messages = export.verify(staged)
    assert not ok
    assert any("MISSING" in m for m in messages)


def test_verification_reports_a_missing_manifest(tmp_path: Path):
    ok, messages = export.verify(tmp_path)
    assert not ok
    assert "manifest.json" in messages[0]


def test_install_copies_into_the_cache_byte_for_byte(staged: Path, tmp_path: Path):
    cache = tmp_path / "cache"
    installed = export.install(staged, cache)
    assert len(installed) == 2
    original = pd.read_parquet(staged / "BTCUSDT_5m.parquet")
    copied = pd.read_parquet(cache / "BTCUSDT_5m.parquet")
    pd.testing.assert_frame_equal(original, copied)


def test_installed_candles_load_through_the_normal_loader(staged: Path, tmp_path: Path):
    from daytrader.data import loader
    cache = tmp_path / "cache"
    export.install(staged, cache)
    df = loader.load("BTCUSDT", "5m", cache)
    assert len(df) == 500
