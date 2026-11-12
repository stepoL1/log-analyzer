"""Własne wyjątki pakietu.

Wspólna klasa bazowa pozwala w CLI złapać wszystkie błędy jednym
``except LogAnalyzerError`` i wypisać czytelny komunikat.
"""


class LogAnalyzerError(Exception):
    """Bazowa klasa wszystkich błędów pakietu."""


class MalformedLineError(LogAnalyzerError, ValueError):
    """Linia logu nie pasuje do oczekiwanego formatu."""

    def __init__(self, line: str, reason: str) -> None:
        super().__init__(f"{reason}: {line[:80]!r}")
        self.line = line


class ConfigurationError(LogAnalyzerError):
    """Nieprawidłowa konfiguracja analizatora (brak plików, zły wzorzec itp.)."""


class TransientLookupError(LogAnalyzerError):
    """Chwilowy błąd (symulowanej) usługi geolokalizacji – warto ponowić próbę."""
