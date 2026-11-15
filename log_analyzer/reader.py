"""Leniwe wczytywanie logów: iterator blokowy i potok generatorów.

Potok przetwarzania (każdy etap obsługuje jedną linię naraz, więc zużycie
pamięci nie zależy od rozmiaru pliku)::

    read_lines(paths) -> parse_lines(...) -> filter_entries(...)
"""

import re
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from log_analyzer.exceptions import MalformedLineError
from log_analyzer.models import LogEntry

DEFAULT_CHUNK_SIZE = 64 * 1024  # 64 KiB


class ChunkReader:
    """Iterator czytający plik blokami bajtów i zwracający kolejne linie.

    Plik czytamy porcjami po ``chunk_size`` bajtów, więc w pamięci jest
    naraz tylko jeden blok – niezależnie od rozmiaru pliku. Linia przecięta
    granicą bloku trafia do ``_buffer`` i jest sklejana z początkiem
    następnego bloku.
    """

    def __init__(self, path: str | Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size musi być dodatni")
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"plik logu nie istnieje: {self.path}")
        self.chunk_size = chunk_size
        self._file = self.path.open("rb")  # tryb binarny: sami dekodujemy całe linie
        self._buffer = b""                  # niedokończona linia z poprzedniego bloku
        self._lines: deque[bytes] = deque()  # pełne linie czekające na zwrócenie
        self._eof = False

    def __iter__(self) -> Self:
        # Iterator jest sam dla siebie obiektem iterowalnym – dzięki temu działa w pętli for, w list(), w yield from itd.
        return self

    def __next__(self) -> str:
        # Dopóki nie mamy gotowej linii, dociągamy kolejne bloki.
        while not self._lines:
            if self._eof:
                self.close()
                raise StopIteration  # sygnał dla pętli for: koniec danych
            self._read_chunk()
        return self._lines.popleft().rstrip(b"\r").decode("utf-8", errors="replace")

    def _read_chunk(self) -> None:
        """Wczytuje kolejny blok i dzieli go na pełne linie."""
        chunk = self._file.read(self.chunk_size)
        if not chunk:
            self._eof = True
            if self._buffer:
                self._lines.append(self._buffer)
                self._buffer = b""
            return
        *complete, self._buffer = (self._buffer + chunk).split(b"\n")
        self._lines.extend(complete)

    def close(self) -> None:
        """Zamyka plik; dalsze ``next()`` zgłaszają ``StopIteration``."""
        self._eof = True
        self._lines.clear()
        self._file.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


@dataclass
class ParseReport:
    """Licznik błędnych linii"""

    malformed: int = 0


def read_lines(paths: Iterable[str | Path], chunk_size: int = DEFAULT_CHUNK_SIZE) -> Iterator[str]:
    """Generator: zwraca kolejno linie ze wszystkich podanych plików."""
    for path in paths:
        with ChunkReader(path, chunk_size) as reader:
            yield from reader


def parse_lines(lines: Iterable[str], report: ParseReport | None = None) -> Iterator[LogEntry]:
    """Generator: zamienia linie tekstu na obiekty :class:`LogEntry`.

    Błędne linie są zliczane i pomijane – jedna uszkodzona linia nie może
    przerwać analizy pozostałych.
    """
    for line in lines:
        if not line.strip():  # puste linie
            continue
        try:
            yield LogEntry.from_line(line)
        except MalformedLineError:
            if report is not None:
                report.malformed += 1


def filter_entries(
    entries: Iterable[LogEntry],
    status: int | None = None,
    url_pattern: re.Pattern[str] | None = None,
) -> Iterator[LogEntry]:
    """Filtruje wpisy wyrażeniem generującym (nic nie liczy, dopóki ktoś nie iteruje).

    Args:
        status: dokładny kod (np. 404) albo klasa kodów 1–5 (np. 4 → 4xx).
        url_pattern: tylko wpisy, których URL pasuje do wzorca.
    """

    def status_ok(code: int) -> bool:
        if status is None:
            return True
        # status < 10 oznacza klasę kodów: 4 → wszystkie 4xx (code // 100 == 4)
        return code // 100 == status if status < 10 else code == status

    return (
        entry
        for entry in entries
        if status_ok(entry.status) and (url_pattern is None or url_pattern.search(entry.url))
    )


