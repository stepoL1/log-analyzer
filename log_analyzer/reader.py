"""Leniwe wczytywanie logów: iterator blokowy i potok generatorów."""

from collections import deque
from pathlib import Path
from typing import Self

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
