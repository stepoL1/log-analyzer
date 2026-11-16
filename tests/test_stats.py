"""Testy agregacji statystyk: FileStats i analyze_file."""

from pathlib import Path

import pytest

from log_analyzer.stats import FileStats, analyze_file


def test_analyze_file(log_file: Path) -> None:
    stats = analyze_file(log_file)
    assert (stats.files, stats.requests, stats.malformed) == (1, 4, 2)
    assert stats.status_counts == {200: 2, 401: 1, 304: 1}
    assert stats.ip_counts["83.1.2.3"] == 2
    assert stats.url_counts["/products/7"] == 2  # path bez ?x=1
    assert stats.error_urls == {"/login": 1}
    assert stats.bytes_sent == 2 * 5123  # "-" liczy się jako 0
    assert stats.error_rate == pytest.approx(0.25)
    assert stats.status_classes() == {"2xx": 2, "3xx": 1, "4xx": 1}


def test_first_and_last_seen(log_file: Path) -> None:
    stats = analyze_file(log_file)
    assert (stats.first_seen.hour, stats.first_seen.minute) == (10, 15)
    assert (stats.last_seen.hour, stats.last_seen.minute) == (23, 59)


def test_analyze_file_with_filter(log_file: Path) -> None:
    assert analyze_file(log_file, status=4).requests == 1  # tylko 401
    assert analyze_file(log_file, url_pattern=r"^/products").requests == 2


def test_combine_adds_counters(log_file: Path) -> None:
    one = analyze_file(log_file)
    total = FileStats.combine([analyze_file(log_file), analyze_file(log_file)])
    assert total.files == 2
    assert total.requests == 2 * one.requests
    assert total.malformed == 2 * one.malformed
    assert total.ip_counts["83.1.2.3"] == 4
    assert (total.first_seen, total.last_seen) == (one.first_seen, one.last_seen)


def test_empty_stats() -> None:
    empty = FileStats.combine([])
    assert empty.requests == 0
    assert empty.error_rate == 0.0  # bez ZeroDivisionError
    assert empty.first_seen is None
