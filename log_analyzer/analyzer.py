"""Główna klasa analizatora – uruchamia analizę w wybranym trybie.

Tryby:

* ``sequential`` – pliki jeden po drugim w bieżącym wątku,
* ``threads``    – ``ThreadPoolExecutor``; przez GIL nie przyspiesza obliczeń
  w czystym Pythonie (zostawiony jako punkt odniesienia w benchmarku),
* ``processes``  – ``ProcessPoolExecutor``; każdy proces ma własny interpreter
  i własny GIL, więc pliki są parsowane równolegle.
"""

import logging
import os
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial, wraps
from pathlib import Path
from typing import Any, Self

from log_analyzer.decorators import timer
from log_analyzer.exceptions import ConfigurationError
from log_analyzer.patterns import compile_user_pattern
from log_analyzer.reader import DEFAULT_CHUNK_SIZE
from log_analyzer.stats import FileStats, analyze_file

logger = logging.getLogger(__name__)

MODES = ("sequential", "threads", "processes")


def requires_files(method: Callable[..., Any]) -> Callable[..., Any]:
    """Dekorator metody: przed wywołaniem sprawdza pliki w ``self.paths``.

    Dzięki niemu błąd „brak pliku” pojawia się od razu, z czytelnym
    komunikatem, a nie dopiero w procesie roboczym po uruchomieniu puli.
    """

    @wraps(method)
    def wrapper(self: "LogAnalyzer", *args: Any, **kwargs: Any) -> Any:
        # self przychodzi jako pierwszy argument – tak jak w każdej metodzie
        if not self.paths:
            raise ConfigurationError("nie podano żadnych plików logów")
        missing = [str(p) for p in self.paths if not p.is_file()]
        if missing:
            raise ConfigurationError(f"brak plików: {', '.join(missing)}")
        return method(self, *args, **kwargs)

    return wrapper


@dataclass(frozen=True)
class AnalyzerConfig:
    """Parametry analizy wspólne dla wszystkich plików (walidowane od razu)."""

    chunk_size: int = DEFAULT_CHUNK_SIZE
    status: int | None = None
    url_pattern: str | None = None

    def __post_init__(self) -> None:
        # __post_init__ dataclass wywołuje automatycznie zaraz po __init__
        if self.chunk_size <= 0:
            raise ConfigurationError("chunk_size musi być dodatni")
        if self.status is not None and not (1 <= self.status <= 5 or 100 <= self.status <= 599):
            raise ConfigurationError("status musi być klasą 1–5 lub kodem 100–599")
        try:
            compile_user_pattern(self.url_pattern)  # tylko sprawdzamy; wynik nie jest potrzebny
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc


class LogAnalyzer:
    """Analizuje zbiór plików logów sekwencyjnie, wątkami lub procesami."""

    def __init__(
        self,
        paths: Iterable[str | Path],
        config: AnalyzerConfig | None = None,
        workers: int | None = None,
    ) -> None:
        self.paths = [Path(p) for p in paths]
        self.config = config or AnalyzerConfig()
        # „is None”, a nie „or”: 0 to fałsz, więc „workers or ...” po cichu zamieniłoby 0 na domyślną wartość
        self.workers = self.default_workers() if workers is None else workers  # przechodzi przez setter!

    @property
    def workers(self) -> int:
        """Liczba wątków/procesów w trybach równoległych."""
        return self._workers

    @workers.setter
    def workers(self, value: int) -> None:
        # bool jest podklasą int, więc True przeszłoby jako 1 – odrzucamy jawnie
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"workers musi być dodatnią liczbą całkowitą, podano {value!r}")
        self._workers = value

    @staticmethod
    def default_workers() -> int:
        """Domyślnie tyle workerów, ile rdzeni logicznych CPU."""
        return os.cpu_count() or 1  # cpu_count() może zwrócić None

    @classmethod
    def from_directory(cls, directory: str | Path, **kwargs: Any) -> Self:
        """Alternatywny konstruktor: wszystkie pliki ``*.log`` z katalogu."""
        directory = Path(directory)
        if not directory.is_dir():
            raise ConfigurationError(f"katalog nie istnieje: {directory}")
        return cls(sorted(directory.glob("*.log")), **kwargs)

    @requires_files  # najpierw sprawdzenie plików
    @timer           # potem pomiar czasu samej analizy
    def analyze(self, mode: str = "processes") -> FileStats:
        """Analizuje wszystkie pliki i zwraca połączone statystyki."""
        if mode not in MODES:
            raise ConfigurationError(f"nieznany tryb {mode!r}; dostępne: {', '.join(MODES)}")
        # partial „wpina” konfigurację w funkcję; obiekt partial da się przesłać przez pickle
        task = partial(
            analyze_file,
            chunk_size=self.config.chunk_size,
            status=self.config.status,
            url_pattern=self.config.url_pattern,
        )
        workers = min(self.workers, len(self.paths))  # więcej workerów niż plików nic nie da
        logger.info("analiza %d plików, tryb=%s, workers=%d", len(self.paths), mode, workers)

        if mode == "sequential":
            return FileStats.combine(map(task, self.paths))
        pool_class = ThreadPoolExecutor if mode == "threads" else ProcessPoolExecutor
        with pool_class(max_workers=workers) as pool:
            return FileStats.combine(pool.map(task, self.paths))
