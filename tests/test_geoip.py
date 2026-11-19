"""Baza IP i wielowątkowy IpResolver."""

import asyncio
from pathlib import Path

import pytest

from log_analyzer.exceptions import ConfigurationError
from log_analyzer.geoip import GeoInfo, IpDatabase, IpResolver


@pytest.fixture
def db() -> IpDatabase:
    return IpDatabase.load()


def test_database_lookup(db: IpDatabase) -> None:
    assert db.lookup("83.20.1.1") == GeoInfo("PL", "Warszawa")
    assert db.lookup("8.8.8.8") is None


def test_database_rejects_bad_file(tmp_path: Path) -> None:
    bad = tmp_path / "db.csv"
    bad.write_text("to,nie,jest,poprawne\n")
    with pytest.raises(ConfigurationError):
        IpDatabase.load(bad)


def test_cache_avoids_repeated_queries(db: IpDatabase) -> None:
    resolver = IpResolver(db, latency=0)
    resolver.resolve_sequential(["83.1.1.1", "83.1.1.1", "62.0.0.5"])
    assert resolver.requests_made == 2


def test_threads_do_not_lose_counter_updates(db: IpDatabase) -> None:
    resolver = IpResolver(db, latency=0.001)
    result = resolver.resolve_threaded([f"83.{i}.0.1" for i in range(30)] * 3, workers=8)
    assert len(result) == 30
    assert resolver.requests_made == 30  # licznik chroniony Lockiem


def test_retry_recovers_from_transient_failures(db: IpDatabase) -> None:
    resolver = IpResolver(db, latency=0, failure_rate=0.3, seed=1)
    result = resolver.resolve_threaded([f"62.0.{i}.1" for i in range(40)], workers=4)
    unresolved = sum(info is None for info in result.values())
    assert resolver.failures > 0
    # Każda porażka powoduje ponowienie – oprócz ostatniej próby adresu, który się „poddał”.
    assert resolver.requests_made == 40 + resolver.failures - unresolved
    assert unresolved <= 10


def test_async_gives_same_result_as_threads(db: IpDatabase) -> None:
    ips = [f"83.{i}.0.1" for i in range(30)] * 2
    expected = IpResolver(db, latency=0.001).resolve_threaded(ips, workers=8)
    resolver = IpResolver(db, latency=0.001)
    result = asyncio.run(resolver.resolve_async(ips, concurrency=8))
    assert result == expected
    assert resolver.requests_made == 30  # duplikaty usunięte, bez Locka nic nie zginęło


def test_async_retry_recovers_from_transient_failures(db: IpDatabase) -> None:
    resolver = IpResolver(db, latency=0, failure_rate=0.3, seed=1)
    result = asyncio.run(resolver.resolve_async([f"62.0.{i}.1" for i in range(40)]))
    unresolved = sum(info is None for info in result.values())
    assert resolver.failures > 0
    assert resolver.requests_made == 40 + resolver.failures - unresolved
