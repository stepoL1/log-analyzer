"""Agregacja statystyk z wpisów logu."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Self

from log_analyzer.models import LogEntry
from log_analyzer.patterns import compile_user_pattern
from log_analyzer.reader import DEFAULT_CHUNK_SIZE, ParseReport, filter_entries, parse_lines, read_lines


@dataclass
class FileStats:
    """Statystyki zebrane z jednego lub wielu plików logów."""

    files: int = 0
    requests: int = 0
    malformed: int = 0
    bytes_sent: int = 0
    status_counts: Counter[int] = field(default_factory=Counter)
    ip_counts: Counter[str] = field(default_factory=Counter)
    url_counts: Counter[str] = field(default_factory=Counter)
    error_urls: Counter[str] = field(default_factory=Counter)
    hourly: Counter[int] = field(default_factory=Counter)
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    def add(self, entry: LogEntry) -> None:
        """Dolicza pojedynczy wpis."""
        self.requests += 1                          # jedno żądanie więcej
        self.bytes_sent += entry.size               # suma wysłanych bajtów
        self.status_counts[entry.status] += 1       # np. status_counts[200] += 1
        self.ip_counts[entry.ip] += 1
        self.url_counts[entry.path] += 1            # path = URL bez ?parametrów
        if entry.is_error:                          # tylko 4xx/5xx
            self.error_urls[entry.path] += 1
        self.hourly[entry.timestamp.hour] += 1      # godzina 0–23
        if self.first_seen is None or entry.timestamp < self.first_seen:
            self.first_seen = entry.timestamp
        if self.last_seen is None or entry.timestamp > self.last_seen:
            self.last_seen = entry.timestamp

    def merge(self, other: "FileStats") -> Self:
        """Dołącza wyniki other (z innego procesu) i zwraca self."""
        self.files += other.files
        self.requests += other.requests
        self.malformed += other.malformed
        self.bytes_sent += other.bytes_sent
        self.status_counts.update(other.status_counts)
        self.ip_counts.update(other.ip_counts)
        self.url_counts.update(other.url_counts)
        self.error_urls.update(other.error_urls)
        self.hourly.update(other.hourly)
        dates = [d for d in (self.first_seen, other.first_seen,
                             self.last_seen, other.last_seen) if d]
        if dates:
            self.first_seen, self.last_seen = min(dates), max(dates)
        return self

    @classmethod
    def combine(cls, parts: Iterable["FileStats"]) -> Self:
        """Łączy statystyki częściowe (po jednej na plik) w jedną całość."""
        total = cls()  # pusty obiekt: same zera i puste Countery
        for part in parts:
            total.merge(part)
        return total

    @property
    def error_rate(self) -> float:
        """Odsetek odpowiedzi 4xx/5xx (0.0–1.0)."""
        if not self.requests:  # brak żądań -> unikamy ZeroDivisionError
            return 0.0
        errors = sum(n for code, n in self.status_counts.items() if code >= 400)
        return errors / self.requests

    def status_classes(self) -> dict[str, int]:
        """Liczba odpowiedzi w klasach 2xx, 3xx, 4xx, 5xx."""
        classes: Counter[str] = Counter()
        for code, n in self.status_counts.items():
            classes[f"{code // 100}xx"] += n  # 404 // 100 == 4 -> "4xx"
        return dict(sorted(classes.items()))


def analyze_file(
    path: str | Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    status: int | None = None,
    url_pattern: str | None = None,
) -> FileStats:
    """Analizuje jeden plik logu i zwraca jego statystyki.

    Funkcja jest na poziomie modułu, bo ProcessPoolExecutor przesyła ją do
    innego procesu przez pickle (zapisuje ją jako „moduł + nazwa”).
    Wzorzec URL przychodzi jako str i jest kompilowany dopiero tutaj,
    już wewnątrz procesu roboczego.
    """
    report = ParseReport()
    entries = filter_entries(
        parse_lines(read_lines([path], chunk_size), report),
        status=status,
        url_pattern=compile_user_pattern(url_pattern),
    )
    stats = FileStats(files=1)
    for entry in entries:  # cały potok generatorów
        stats.add(entry)
    stats.malformed = report.malformed  # licznik wypełnił się w trakcie pętli
    return stats