"""Geolokalizacja adresów IP – zadanie I/O-bound.

Zamiast prawdziwego API używamy lokalnej bazy (``data/ip_db.csv``) i
**symulujemy** sieć: każde zapytanie czeka ``latency`` sekund (``time.sleep``)
i może losowo się nie udać. ``time.sleep``, tak jak prawdziwe czekanie
na gniazdo sieciowe, zwalnia GIL, więc wiele wątków może czekać jednocześnie.
"""

import ipaddress
import random
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple, Self

from log_analyzer.decorators import retry
from log_analyzer.exceptions import ConfigurationError, TransientLookupError
from log_analyzer.patterns import is_valid_ipv4

# ścieżka liczona od tego pliku, więc działa niezależnie od katalogu, z którego uruchomiono program
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ip_db.csv"


class GeoInfo(NamedTuple):
    """Wynik geolokalizacji adresu IP."""

    country: str
    city: str


class IpDatabase:
    """Lokalna baza sieci IP (CIDR → kraj, miasto)."""

    def __init__(self, networks: list[tuple[ipaddress.IPv4Network, GeoInfo]]) -> None:
        self.networks = networks

    @classmethod
    def load(cls, path: str | Path = DEFAULT_DB_PATH) -> Self:
        """Wczytuje bazę z pliku CSV; puste linie i komentarze ``#`` są pomijane.

        Raises:
            ConfigurationError: gdy pliku nie ma albo linia ma zły format.
        """
        path = Path(path)
        if not path.is_file():
            raise ConfigurationError(f"brak bazy IP: {path}")
        networks = []
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip() or line.startswith("#"):
                continue
            try:
                # rozpakowanie na 3 zmienne rzuci ValueError, gdy kolumn jest inna liczba
                network, country, city = (part.strip() for part in line.split(","))
                networks.append((ipaddress.IPv4Network(network), GeoInfo(country, city)))
            except ValueError as exc:  # zła liczba kolumn albo niepoprawna sieć
                raise ConfigurationError(f"{path}:{lineno}: niepoprawna linia {line!r}") from exc
        return cls(networks)

    def lookup(self, ip: str) -> GeoInfo | None:
        """Zwraca położenie adresu albo ``None``, gdy nie należy do żadnej sieci."""
        address = ipaddress.IPv4Address(ip)
        # next(generator, None) = pierwsza pasująca sieć albo None
        return next((info for net, info in self.networks if address in net), None)


class IpResolver:
    """Klient symulowanej usługi geolokalizacji z cache współdzielonym przez wątki.

    Cache i liczniki chroni ``threading.Lock``. Bez niego dwa wątki mogłyby
    jednocześnie zwiększać ``requests_made`` i zgubić wynik, bo ``x += 1``
    to kilka instrukcji kodu bajtowego (odczyt, dodanie, zapis), a między
    nimi może nastąpić przełączenie wątku.
    """

    def __init__(
        self,
        database: IpDatabase,
        latency: float = 0.02,
        failure_rate: float = 0.0,
        seed: int | None = None,
    ) -> None:
        if latency < 0 or not 0 <= failure_rate < 1:
            raise ValueError("wymagane: latency >= 0 oraz 0 <= failure_rate < 1")
        self.database = database
        self.latency = latency
        self.failure_rate = failure_rate
        self._rng = random.Random(seed)
        self._lock = threading.Lock()
        self._cache: dict[str, GeoInfo | None] = {}
        self.requests_made = 0
        self.failures = 0

    @retry(attempts=4, delay=0.005, exceptions=(TransientLookupError,))
    def _query_remote(self, ip: str) -> GeoInfo | None:
        """Jedno „zapytanie sieciowe”, które może się chwilowo nie udać."""
        with self._lock:
            self.requests_made += 1
            fail = self._rng.random() < self.failure_rate
            if fail:
                self.failures += 1
        # Czekanie jest POZA blokadą. Gdyby było w środku, wątki czekałyby
        # na siebie po kolei i całość działałaby jak wersja sekwencyjna.
        time.sleep(self.latency)
        if fail:
            raise TransientLookupError(f"usługa nie odpowiedziała dla {ip}")
        return self.database.lookup(ip)

    def lookup(self, ip: str) -> GeoInfo | None:
        """Zwraca położenie IP, korzystając z cache."""
        if not is_valid_ipv4(ip):
            raise ValueError(f"niepoprawny adres IP: {ip!r}")
        with self._lock:
            if ip in self._cache:
                return self._cache[ip]
        try:
            info = self._query_remote(ip)
        except TransientLookupError:
            info = None  # wszystkie próby nieudane – traktujemy adres jako nieznany
        with self._lock:
            self._cache[ip] = info
        return info

    def resolve_sequential(self, ips: Iterable[str]) -> dict[str, GeoInfo | None]:
        """Adresy jeden po drugim – punkt odniesienia w benchmarku."""
        return {ip: self.lookup(ip) for ip in ips}

    def resolve_threaded(self, ips: Iterable[str], workers: int = 16) -> dict[str, GeoInfo | None]:
        """Adresy współbieżnie w puli wątków."""
        unique = list(dict.fromkeys(ips))  # usuwa duplikaty, zachowując kolejność
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # pool.map zwraca wyniki w tej samej kolejności co wejście, więc zip je dopasuje
            return dict(zip(unique, pool.map(self.lookup, unique)))
