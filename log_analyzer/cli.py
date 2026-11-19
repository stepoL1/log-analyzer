"""Interfejs wiersza poleceń: ``python -m log_analyzer {generate,analyze,benchmark}``."""

import argparse
import logging
import sys
from pathlib import Path

from log_analyzer.analyzer import MODES, AnalyzerConfig, LogAnalyzer
from log_analyzer.benchmark import run_benchmark, to_markdown
from log_analyzer.datagen import generate_logs
from log_analyzer.exceptions import LogAnalyzerError
from log_analyzer.geoip import IpDatabase, IpResolver
from log_analyzer.report import format_report


def build_parser() -> argparse.ArgumentParser:
    """Parser z trzema podpoleceniami; ``-v`` działa w każdym z nich."""
    parser = argparse.ArgumentParser(prog="python -m log_analyzer",
                                     description="Analizator logów serwera WWW.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true", help="pokaż logi (czasy, postęp)")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", parents=[common], help="wygeneruj logi testowe")
    gen.add_argument("--out", type=Path, default=Path("data/logs"))
    gen.add_argument("--files", type=int, default=8)
    gen.add_argument("--lines", type=int, default=100_000)

    ana = sub.add_parser("analyze", parents=[common], help="przeanalizuj pliki lub katalogi")
    ana.add_argument("paths", nargs="+", type=Path, help="pliki .log lub katalogi")
    ana.add_argument("--mode", choices=MODES, default="processes")
    ana.add_argument("--workers", type=int, default=None)
    ana.add_argument("--top", type=int, default=10)
    ana.add_argument("--status", type=int, default=None, help="kod HTTP (404) lub klasa (4 = 4xx)")
    ana.add_argument("--url-regex", default=None, help="filtr URL – wyrażenie regularne")
    ana.add_argument("--resolve-ips", action="store_true", help="geolokalizuj top IP (wątki)")

    ben = sub.add_parser("benchmark", parents=[common], help="sekwencyjnie / wątki / procesy")
    ben.add_argument("--data", type=Path, default=Path("data/logs"))
    ben.add_argument("--out", type=Path, default=Path("results"))
    ben.add_argument("--repeats", type=int, default=3)
    return parser


def cmd_analyze(args: argparse.Namespace) -> None:
    files: list[Path] = []
    for path in args.paths:  # katalogi rozwijamy sami – cmd/PowerShell nie rozwijają "*.log"
        files += LogAnalyzer.from_directory(path).paths if path.is_dir() else [path]
    config = AnalyzerConfig(status=args.status, url_pattern=args.url_regex)
    stats = LogAnalyzer(files, config, args.workers).analyze(args.mode)

    geo = None
    if args.resolve_ips:
        resolver = IpResolver(IpDatabase.load(), latency=0.02, failure_rate=0.05)
        geo = resolver.resolve_threaded(ip for ip, _ in stats.ip_counts.most_common(args.top))
    print(format_report(stats, args.top, geo))


def main(argv: list[str] | None = None) -> int:
    """Punkt wejścia; zwraca kod wyjścia (0 = sukces, 1 = błąd)."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        if args.command == "generate":
            paths = generate_logs(args.out, args.files, args.lines)
            print(f"Wygenerowano {len(paths)} plików w {args.out}")
        elif args.command == "analyze":
            cmd_analyze(args)
        else:
            print(to_markdown(run_benchmark(args.data, args.out, repeats=args.repeats)))
        return 0
    except (LogAnalyzerError, ValueError, OSError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)  # komunikat zamiast tracebacku
        return 1
