"""Własne dekoratory funkcji.

* ``timer`` – bez parametrów: loguje czas wykonania,
* ``retry(...)`` – z parametrami: ponawia wywołanie po chwilowym błędzie.
"""

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


def timer(func: Callable[..., Any]) -> Callable[..., Any]:
    """Loguje (poziom INFO) czas wykonania udekorowanej funkcji."""

    @wraps(func)  # zachowuje __name__, __doc__ itd. oryginalnej funkcji
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:  # czas logujemy także wtedy, gdy funkcja rzuci wyjątek
            elapsed = time.perf_counter() - start
            logger.info("%s wykonano w %.3f s", func.__qualname__, elapsed)

    return wrapper


def retry(
    attempts: int = 3,
    delay: float = 0.1,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Ponawia wywołanie funkcji, gdy rzuci jeden z wyjątków *exceptions*.

    Dekorator z parametrami ma trzy poziomy funkcji:
    ``retry(...)`` zwraca ``decorator``, który owija funkcję w ``wrapper``.

    Args:
        attempts: maksymalna liczba prób (>= 1).
        delay: pauza między próbami w sekundach; podwaja się po każdej
            porażce (*exponential backoff* – nie zasypujemy usługi zapytaniami).
        exceptions: tylko te błędy są ponawiane; inne przechodzą od razu.
    """
    # walidacja przy dekorowaniu, a nie przy pierwszym wywołaniu – błąd wychodzi od razu
    if attempts < 1 or delay < 0:
        raise ValueError("attempts musi być >= 1, a delay >= 0")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            wait = delay
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == attempts:
                        logger.warning("%s: wyczerpano %d prób", func.__qualname__, attempts)
                        raise  # rzuca dalej ten sam wyjątek, z oryginalnym tracebackiem
                    logger.debug("%s: próba %d nieudana (%s)", func.__qualname__, attempt, exc)
                    time.sleep(wait)
                    wait *= 2

        return wrapper

    return decorator
