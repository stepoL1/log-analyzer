"""Testy klasy LogAnalyzer, jej konfiguracji i trybów."""

from pathlib import Path

import pytest

from log_analyzer.analyzer import MODES, AnalyzerConfig, LogAnalyzer
from log_analyzer.exceptions import ConfigurationError
from log_analyzer.stats import analyze_file


@pytest.mark.parametrize("mode", MODES)
def test_all_modes_give_same_result(log_file: Path, mode: str) -> None:
    expected = analyze_file(log_file)
    stats = LogAnalyzer([log_file, log_file], workers=2).analyze(mode)
    assert stats.requests == 2 * expected.requests
    assert stats.ip_counts == expected.ip_counts + expected.ip_counts


def test_config_filters(log_file: Path) -> None:
    analyzer = LogAnalyzer([log_file], AnalyzerConfig(status=4))
    assert analyzer.analyze("sequential").requests == 1


@pytest.mark.parametrize("kwargs", [{"chunk_size": 0}, {"status": 9}, {"url_pattern": "(["}])
def test_config_validation(kwargs: dict) -> None:
    with pytest.raises(ConfigurationError):
        AnalyzerConfig(**kwargs)


def test_workers_setter_validates(log_file: Path) -> None:
    analyzer = LogAnalyzer([log_file])
    analyzer.workers = 3
    assert analyzer.workers == 3
    for bad in (0, -1, 2.5, True):
        with pytest.raises(ValueError):
            analyzer.workers = bad  # type: ignore[assignment]


def test_requires_files_decorator(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="żadnych"):
        LogAnalyzer([]).analyze()
    with pytest.raises(ConfigurationError, match="brak plików"):
        LogAnalyzer([tmp_path / "nie_ma.log"]).analyze()


def test_unknown_mode(log_file: Path) -> None:
    with pytest.raises(ConfigurationError):
        LogAnalyzer([log_file]).analyze("gpu")


def test_from_directory(tmp_path: Path, log_file: Path) -> None:
    (tmp_path / "notatki.txt").write_text("")
    assert [p.name for p in LogAnalyzer.from_directory(tmp_path).paths] == ["access.log"]
