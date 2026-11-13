"""Testy modelu LogEntry."""

from dataclasses import FrozenInstanceError

import pytest

from conftest import BAD_IP, BROKEN, ERROR, GOOD, SHORT
from log_analyzer.exceptions import MalformedLineError
from log_analyzer.models import LogEntry


def test_entry_from_line() -> None:
    entry = LogEntry.from_line(GOOD)
    assert (entry.ip, entry.method, entry.status, entry.size) == ("83.1.2.3", "GET", 200, 5123)
    assert entry.agent == "Mozilla/5.0"
    assert not entry.is_error


def test_entry_path_strips_query() -> None:
    assert LogEntry.from_line(GOOD).path == "/products/7"       # ?x=1 obcięte
    assert LogEntry.from_line(SHORT).path == "/static/app.js"   # bez ? zostaje całe


def test_entry_optional_fields() -> None:
    error = LogEntry.from_line(ERROR)
    assert error.is_error                                # 401 >= 400
    assert error.size == 0                               # rozmiar "-" zamieniony na 0
    assert LogEntry.from_line(SHORT).agent is None       # brak części "combined"


@pytest.mark.parametrize("line", [BROKEN, BAD_IP])
def test_entry_rejects_malformed(line: str) -> None:
    with pytest.raises(MalformedLineError):
        LogEntry.from_line(line)


def test_entry_rejects_impossible_date() -> None:
    with pytest.raises(MalformedLineError, match="day is out of range"):
        LogEntry.from_line(GOOD.replace("12/Nov", "32/Nov"))


def test_entry_is_frozen() -> None:
    entry = LogEntry.from_line(GOOD)
    with pytest.raises(FrozenInstanceError):
        entry.status = 500  # type: ignore[misc]