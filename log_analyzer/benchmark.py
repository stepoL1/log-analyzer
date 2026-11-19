"""Pomiar porównawczy sekwencyjnie / wątki / procesy – wpływ GIL.

Dwa scenariusze, bo GIL zachowuje się w nich zupełnie inaczej:

1. **CPU-bound** – parsowanie wielu plików logów (``LogAnalyzer.analyze``),
2. **I/O-bound** – geolokalizacja adresów IP z symulowanym opóźnieniem sieci.
"""

import os
import platform
import random
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from log_analyzer.analyzer import MODES, LogAnalyzer
from log_analyzer.datagen import generate_logs, random_ips
from log_analyzer.geoip import IpDatabase, IpResolver


@dataclass
class Measurement:
    """Wynik jednego wariantu."""

    scenario: str
    variant: str
    seconds: float
    speedup: float = 1.0


def best_time(func: Callable[[], object], repeats: int) -> float:
    """Najkrótszy z *repeats* przebiegów – najmniej zaburzony przez inne programy."""
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        func()
        times.append(time.perf_counter() - start)
    return min(times)


def gil_enabled() -> bool:
    """``False`` tylko w free-threaded Pythonie 3.13t+ (tam istnieje ``sys._is_gil_enabled``)."""
    check = getattr(sys, "_is_gil_enabled", None)
    return True if check is None else check()


def cpu_benchmark(paths: list[Path], workers: int, repeats: int) -> list[Measurement]:
    """Parsowanie plików logów w trzech trybach."""
    analyzer = LogAnalyzer(paths, workers=workers)
    return [Measurement("CPU: parsowanie logów", mode,
                        best_time(lambda: analyzer.analyze(mode), repeats))
            for mode in MODES]


def io_benchmark(ip_count: int, latency: float, workers: int, repeats: int) -> list[Measurement]:
    """Geolokalizacja IP sekwencyjnie i w wątkach.

    Każdy przebieg dostaje nowy ``IpResolver`` – inaczej drugi przebieg
    trafiałby w cache i nic by nie mierzył.
    """
    database = IpDatabase.load()
    ips = random_ips(random.Random(7), ip_count)
    seq = best_time(lambda: IpResolver(database, latency).resolve_sequential(ips), repeats)
    thr = best_time(lambda: IpResolver(database, latency).resolve_threaded(ips, workers), repeats)
    return [Measurement("I/O: geolokalizacja IP", "sequential", seq),
            Measurement("I/O: geolokalizacja IP", "threads", thr)]


def to_markdown(rows: list[Measurement]) -> str:
    """Tabela wyników w Markdown (do README)."""
    header = (f"Python {platform.python_version()}, GIL włączony: {gil_enabled()}, "
              f"rdzenie logiczne: {os.cpu_count()}, {platform.system()} {platform.release()}\n\n"
              "| Scenariusz | Wariant | Czas [s] | Przyspieszenie |\n|---|---|---:|---:|\n")
    return header + "\n".join(f"| {r.scenario} | {r.variant} | {r.seconds:.3f} | {r.speedup:.2f}× |"
                              for r in rows)


def save_chart(rows: list[Measurement], path: Path) -> None:
    """Wykres słupkowy wyników (wymaga matplotlib)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scenarios = list(dict.fromkeys(r.scenario for r in rows))
    fig, axes = plt.subplots(1, len(scenarios), figsize=(11, 4))
    for ax, scenario in zip(axes, scenarios):
        part = [r for r in rows if r.scenario == scenario]
        bars = ax.bar([r.variant for r in part], [r.seconds for r in part],
                      color=["#8a8f98", "#4c78a8", "#f58518"][:len(part)])
        ax.bar_label(bars, labels=[f"{r.seconds:.2f} s ({r.speedup:.1f}×)" for r in part])
        ax.set_title(scenario)
        ax.set_ylabel("czas [s] – mniej = lepiej")
        ax.set_ylim(0, max(r.seconds for r in part) * 1.2)
    fig.tight_layout()
    fig.savefig(path, dpi=110)


def run_benchmark(data_dir: Path, out_dir: Path, files: int = 8, lines: int = 100_000,
                  repeats: int = 3, ip_count: int = 150, latency: float = 0.02) -> list[Measurement]:
    """Uruchamia oba scenariusze i zapisuje ``benchmark.md`` oraz ``benchmark.png``."""
    paths = sorted(data_dir.glob("access-*.log"))[:files]
    if len(paths) < files:
        paths = generate_logs(data_dir, files=files, lines=lines)
    workers = min(files, os.cpu_count() or 1)

    rows = []
    for part in (cpu_benchmark(paths, workers, repeats),
                 io_benchmark(ip_count, latency, workers=16, repeats=repeats)):
        for r in part:
            r.speedup = part[0].seconds / r.seconds  # względem wersji sekwencyjnej
        rows += part

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "benchmark.md").write_text(to_markdown(rows) + "\n", encoding="utf-8")
    save_chart(rows, out_dir / "benchmark.png")
    return rows
