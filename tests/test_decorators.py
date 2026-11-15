"""Testy dekoratorów timer i retry."""

import logging

import pytest

from log_analyzer.decorators import retry, timer


def test_timer_keeps_function_metadata() -> None:
    @timer
    def add(a: int, b: int) -> int:
        """Dodaje."""
        return a + b

    assert add(2, 3) == 5
    assert (add.__name__, add.__doc__) == ("add", "Dodaje.")


def test_timer_logs_even_on_exception(caplog: pytest.LogCaptureFixture) -> None:
    @timer
    def boom() -> None:
        raise RuntimeError

    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError):
        boom()
    assert "wykonano w" in caplog.text


def test_retry_succeeds_after_failures() -> None:
    calls = []

    @retry(attempts=3, delay=0)
    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 3


def test_retry_gives_up_and_reraises() -> None:
    calls = []

    @retry(attempts=2, delay=0, exceptions=(ConnectionError,))
    def always_fails() -> None:
        calls.append(1)
        raise ConnectionError

    with pytest.raises(ConnectionError):
        always_fails()
    assert len(calls) == 2


def test_retry_ignores_other_exceptions() -> None:
    calls = []

    @retry(attempts=5, delay=0, exceptions=(ConnectionError,))
    def wrong() -> None:
        calls.append(1)
        raise KeyError

    with pytest.raises(KeyError):
        wrong()
    assert len(calls) == 1  # KeyError nie jest „chwilowy” – bez ponawiania


def test_retry_validates_parameters() -> None:
    with pytest.raises(ValueError):
        retry(attempts=0)
    with pytest.raises(ValueError):
        retry(delay=-1)
