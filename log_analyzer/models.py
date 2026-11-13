"""Model pojedynczego wpisu w logu."""

from dataclasses import dataclass
from datetime import datetime
from typing import Self

from log_analyzer.exceptions import MalformedLineError
from log_analyzer.patterns import LOG_LINE_RE, is_valid_ipv4, parse_timestamp


@dataclass(frozen=True, slots=True)
class LogEntry:
    """Jedno żądanie HTTP odczytane z logu serwera."""

    ip: str
    timestamp: datetime
    method: str
    url: str
    status: int
    size: int
    agent: str | None = None

    @classmethod
    def from_line(cls, line: str) -> Self:
        """Tworzy wpis z linii tekstu.

        Raises:
            MalformedLineError: gdy linia nie pasuje do formatu, ma
                niepoprawny adres IP albo niemożliwą datę.
        """
        match = LOG_LINE_RE.fullmatch(line)
        if match is None:
            raise MalformedLineError(line, "niepoprawny format")
        if not is_valid_ipv4(match["ip"]):
            raise MalformedLineError(line, f"niepoprawny adres IP {match['ip']!r}")
        try:
            timestamp = parse_timestamp(match["timestamp"])
        except ValueError as exc:
            raise MalformedLineError(line, str(exc)) from exc
        return cls(
            ip=match["ip"],
            timestamp=timestamp,
            method=match["method"],
            url=match["url"],
            status=int(match["status"]),
            size=0 if match["size"] == "-" else int(match["size"]),
            agent=match["agent"],
        )

    @property
    def is_error(self) -> bool:
        """Czy odpowiedź to błąd klienta lub serwera (4xx/5xx)."""
        return self.status >= 400

    @property
    def path(self) -> str:
        """Ścieżka URL bez parametrów (/search?q=x -> /search)."""
        return self.url.split("?", 1)[0]