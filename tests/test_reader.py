"""Testy iteratora ChunkReader i potoku generatorów."""

from pathlib import Path

import pytest

from log_analyzer.patterns import compile_user_pattern
from log_analyzer.reader import ChunkReader, ParseReport, filter_entries, parse_lines, read_lines


@pytest.mark.parametrize("chunk_size", [1, 3, 7, 1 << 16])
def test_chunk_reader_any_chunk_size(tmp_path: Path, chunk_size: int) -> None:
    """Linie (i polskie znaki) rozcięte granicą bloku muszą wrócić w całości."""
    lines = ["pierwsza", "", "zażółć gęślą jaźń", "ostatnia bez znaku nowej linii"]
    path = tmp_path / "f.log"
    path.write_bytes("\r\n".join(lines).encode("utf-8"))
    with ChunkReader(path, chunk_size) as reader:
        assert list(reader) == lines


def test_chunk_reader_iterator_protocol(tmp_path: Path) -> None:
    """__iter__ zwraca self, __next__ oddaje linie, a na końcu StopIteration."""
    path = tmp_path / "f.log"
    path.write_text("a\nb\n")
    reader = ChunkReader(path)
    assert iter(reader) is reader
    assert next(reader) == "a"
    assert next(reader) == "b"
    with pytest.raises(StopIteration):
        next(reader)


def test_chunk_reader_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ChunkReader(tmp_path / "brak.log")
    (tmp_path / "f.log").write_text("x")
    with pytest.raises(ValueError):
        ChunkReader(tmp_path / "f.log", chunk_size=0)


def test_read_lines_many_files_and_lazy(tmp_path: Path) -> None:
    """Linie z kolejnych plików idą po sobie; brak pliku wychodzi dopiero przy iteracji."""
    (tmp_path / "a.log").write_text("a1\na2\n")
    (tmp_path / "b.log").write_text("b1\n")
    assert list(read_lines([tmp_path / "a.log", tmp_path / "b.log"])) == ["a1", "a2", "b1"]

    lines = read_lines([tmp_path / "a.log", tmp_path / "brak.log"])  # jeszcze bez błędu
    assert next(lines) == "a1"
    assert next(lines) == "a2"
    with pytest.raises(FileNotFoundError):
        next(lines)


def test_pipeline_skips_and_counts_malformed(log_file: Path) -> None:
    report = ParseReport()
    entries = list(parse_lines(read_lines([log_file], chunk_size=16), report))
    assert len(entries) == 4
    assert report.malformed == 2


def test_filter_entries(log_file: Path) -> None:
    def statuses(**kwargs) -> list[int]:
        return [e.status for e in filter_entries(parse_lines(read_lines([log_file])), **kwargs)]

    assert statuses() == [200, 401, 304, 200]
    assert statuses(status=4) == [401]         # klasa 4xx
    assert statuses(status=200) == [200, 200]  # dokładny kod
    assert statuses(url_pattern=compile_user_pattern(r"^/products")) == [200, 200]
