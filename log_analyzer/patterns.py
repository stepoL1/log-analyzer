"""Wyrażenia regularne do parsowania i walidacji danych z logów."""

import re
from datetime import datetime, timedelta, timezone

# 83.1.2.3 - - [12/Nov/2026:10:15:32 +0100] "GET /index.html HTTP/1.1" 200 5123 "-" "Mozilla/5.0"
LOG_LINE_RE = re.compile(
    r"(?P<ip>\S+) \S+ \S+ "                    # IP = wszystko do spacji
    r"\[(?P<timestamp>[^\]]+)\] "              # wszystko oprócz znaku ]
    r'"(?P<method>[A-Z]+) (?P<url>\S+) HTTP/[\d.]+" '   # metoda = same wielkie litery
    r"(?P<status>[1-5]\d{2}) (?P<size>\d+|-)"  # status 100–599; size = liczba albo -
    r'(?: "(?P<referer>[^"]*)" "(?P<agent>[^"]*)")?'  # ta część jest opcjonalna
)

# Walidacja adresu IPv4
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
IPV4_RE = re.compile(rf"{_OCTET}(?:\.{_OCTET}){{3}}")

# Znacznik czasu z logu, np. 12/Nov/2026:10:15:32 +0100
TIMESTAMP_RE = re.compile(
    r"(?P<day>\d{2})/(?P<month>[A-Z][a-z]{2})/(?P<year>\d{4})"
    r":(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r" (?P<tz>[+-]\d{4})"
)

def is_valid_ipv4(address: str) -> bool:
    """Zwraca True, jeśli adres jest poprawnym adresem IPv4."""
    return IPV4_RE.fullmatch(address) is not None

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

def parse_timestamp(text: str) -> datetime:
    """Zamienia znacznik czasu z logu na datetime ze strefą czasową.

    Raises:
        ValueError: gdy tekst nie pasuje do formatu albo data jest niemożliwa.
    """

    match = TIMESTAMP_RE.fullmatch(text)
    if match is None or match['month'] not in _MONTHS:
        raise ValueError(f"Niepoprawny znacznik czasu: {text!r}")

    tz = match['tz']
    offset = timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5]))
    if tz[0] == "-":
        offset = -offset

    return datetime(
        int(match['year']), _MONTHS[match['month']], int(match['day']),
        int(match['hour']), int(match['minute']), int(match['second']),
        tzinfo=timezone(offset),
    )

def compile_user_pattern(pattern: str | None) -> re.Pattern[str] | None:
    """Kompiluje wzorzec URL podany przez użytkownika (opcja --url-regex).

    Raises:
        ValueError: z czytelnym komunikatem zamiast surowego re.error.
    """

    if pattern is None:
        return None

    try:
        return re.compile(pattern)
    except re.error as e:
        raise ValueError(f"niepoprawne wyrażenie regularne {pattern!r}: {e}") from e