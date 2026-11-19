"""Geolokalizacja adresów IP – zadanie I/O-bound.

Zamiast prawdziwego API używamy lokalnej bazy (``data/ip_db.csv``) i
**symulujemy** sieć: każde zapytanie czeka ``latency`` sekund (``time.sleep``)
i może losowo się nie udać. ``time.sleep``, tak jak prawdziwe czekanie
na gniazdo sieciowe, zwalnia GIL, więc wiele wątków może czekać jednocześnie.
Dla porównania jest też wariant ``asyncio`` (``resolve_async``): jeden wątek
i wiele korutyn czekających razem na ``await asyncio.sleep``.
"""

import asyncio
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

    # --- wariant asyncio: jeden wątek, wiele korutyn ---------------------------

    async def lookup_async(self, ip: str, attempts: int = 4, delay: float = 0.005) -> GeoInfo | None:
        """Asynchroniczna wersja :meth:`lookup` (to samo zadanie, inny model współbieżności).

        Wszystkie korutyny działają w JEDNYM wątku, a przełączenie między nimi
        następuje tylko w miejscu ``await``. Dlatego ``requests_made += 1`` nie
        potrzebuje tu blokady – nikt nie przerwie tej instrukcji w połowie.
        Ponawianie jest napisane ręcznie, bo dekorator ``retry`` używa
        ``time.sleep``, który zablokowałby całą pętlę zdarzeń.
        """
        if not is_valid_ipv4(ip):
            raise ValueError(f"niepoprawny adres IP: {ip!r}")
        if ip in self._cache:
            return self._cache[ip]
        info = None
        wait = delay
        for attempt in range(1, attempts + 1):
            self.requests_made += 1
            fail = self._rng.random() < self.failure_rate
            if fail:
                self.failures += 1
            await asyncio.sleep(self.latency)  # oddaje sterowanie innym korutynom
            if not fail:
                info = self.database.lookup(ip)
                break
            if attempt < attempts:
                await asyncio.sleep(wait)  # exponential backoff, jak w retry
                wait *= 2
        self._cache[ip] = info
        return info

    async def resolve_async(self, ips: Iterable[str], concurrency: int = 16) -> dict[str, GeoInfo | None]:
        """Adresy współbieżnie w pętli zdarzeń ``asyncio``.

        ``Semaphore`` ogranicza liczbę jednocześnie otwartych zapytań do
        concurrency – tak samo jak liczba wątków w :meth:`resolve_threaded`,
        żeby porównanie w benchmarku było uczciwe.
        """
        unique = list(dict.fromkeys(ips))
        semaphore = asyncio.Semaphore(concurrency)

        async def limited(ip: str) -> GeoInfo | None:
            async with semaphore:
                return await self.lookup_async(ip)

        # gather uruchamia wszystkie korutyny naraz i zwraca wyniki w kolejności wejścia
        results = await asyncio.gather(*(limited(ip) for ip in unique))
        return dict(zip(unique, results))
