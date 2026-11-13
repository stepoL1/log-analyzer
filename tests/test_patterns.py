"""Testy wyrażeń regularnych i funkcji z log_analyzer.patterns."""

from datetime import datetime, timedelta, timezone

import pytest

from log_analyzer.patterns import (
    LOG_LINE_RE,
    compile_user_pattern,
    is_valid_ipv4,
    parse_timestamp,
)

# Przykładowe linie logu
GOOD = '83.1.2.3 - - [12/Nov/2026:10:15:32 +0100] "GET /products/7?x=1 HTTP/1.1" 200 5123 "-" "Mozilla/5.0"'
SHORT = '62.0.0.1 - - [12/Nov/2026:23:59:59 +0100] "GET /static/app.js HTTP/1.1" 304 -'


# --- LOG_LINE_RE ---------------------------------------------------------

def test_log_line_full() -> None:
    match = LOG_LINE_RE.fullmatch(GOOD)
    assert match is not None
    assert match["ip"] == "83.1.2.3"
    assert match["method"] == "GET"
    assert match["status"] == "200"
    assert match["agent"] == "Mozilla/5.0"


def test_log_line_short_has_no_agent() -> None:
    match = LOG_LINE_RE.fullmatch(SHORT)
    assert match is not None
    assert match["size"] == "-"
    assert match["agent"] is None


def test_log_line_rejects_garbage() -> None:
    assert LOG_LINE_RE.fullmatch("to nie jest linia logu") is None


# --- is_valid_ipv4 -------------------------------------------------------

@pytest.mark.parametrize(("ip", "valid"), [
    ("83.1.2.3", True),
    ("0.0.0.0", True),
    ("255.255.255.255", True),
    ("256.1.1.1", False),      # oktet > 255
    ("1.2.3", False),          # za mało oktetów
    ("01.2.3.4", False),       # zero wiodące
    ("a.b.c.d", False),        # litery
    ("1.2.3.456", False),      # łapie błąd match zamiast fullmatch
])
def test_ipv4_validation(ip: str, valid: bool) -> None:
    assert is_valid_ipv4(ip) is valid


# --- parse_timestamp -----------------------------------------------------

def test_parse_timestamp_negative_offset() -> None:
    expected = datetime(2026, 11, 12, 10, 15, 32,
                        tzinfo=timezone(-timedelta(hours=5, minutes=30)))
    assert parse_timestamp("12/Nov/2026:10:15:32 -0530") == expected


@pytest.mark.parametrize("text", [
    "32/Nov/2026:10:00:00 +0100",   # dzień nie istnieje -> odrzuca datetime
    "12/Foo/2026:10:00:00 +0100",   # zły miesiąc -> odrzuca słownik _MONTHS
    "12/Nov/2026 10:00:00 +0100",   # spacja zamiast ':' -> odrzuca regex
])
def test_parse_timestamp_rejects_bad_input(text: str) -> None:
    with pytest.raises(ValueError):
        parse_timestamp(text)


# --- compile_user_pattern ------------------------------------------------

def test_compile_user_pattern() -> None:
    assert compile_user_pattern(None) is None
    assert compile_user_pattern(r"^/api").search("/api/v1")
    with pytest.raises(ValueError, match="niepoprawne"):
        compile_user_pattern("([")