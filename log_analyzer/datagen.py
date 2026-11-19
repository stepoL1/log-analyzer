"""Generator syntetycznych logów (dane testowe).

Linie powstają z nieskończonego generatora ``log_lines``, z którego
``itertools.islice`` bierze tyle linii, ile potrzeba. Ziarno (``seed``)
sprawia, że dane są zawsze takie same, a pomiary – powtarzalne.
"""

import ipaddress
import itertools
import random
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Sieci z data/ip_db.csv + dwie spoza bazy (adres „nieznany”).
NETWORKS = ["83.0.0.0/11", "89.64.0.0/12", "31.0.0.0/12", "46.112.0.0/12", "62.0.0.0/12",
            "81.0.0.0/12", "51.140.0.0/14", "104.16.0.0/12", "13.32.0.0/12",
            "198.51.100.0/24", "192.0.2.0/24"]

# (URL, możliwe kody odpowiedzi) – kod losujemy z listy, więc częstsze powtarzamy.
PAGES = [
    ("/", [200] * 19 + [304]),
    ("/products", [200] * 30 + [500]),
    ("/products/{id}", [200] * 9 + [404]),
    ("/search?q={id}", [200] * 49 + [500]),
    ("/api/v1/orders", [200] * 8 + [401, 503]),
    ("/login", [200, 200, 302, 401]),
    ("/static/app.js", [200, 304, 304]),
    ("/favicon.ico", [200, 404]),
    ("/wp-login.php", [404]),
]
AGENTS = ["Mozilla/5.0 (Windows NT 10.0)", "Mozilla/5.0 (iPhone)", "curl/8.10", "Googlebot/2.1"]


def random_ips(rng: random.Random, count: int) -> list[str]:
    """Losuje *count* adresów IP z sieci ``NETWORKS``."""
    nets = [ipaddress.IPv4Network(n) for n in NETWORKS]
    ips = []
    for _ in range(count):
        net = rng.choice(nets)
        ips.append(str(net[rng.randrange(1, net.num_addresses - 1)]))
    return ips


def log_lines(rng: random.Random, start: datetime, mean_gap: float) -> Iterator[str]:
    """Nieskończony generator linii logu w formacie Combined Log Format."""
    ips = random_ips(rng, 2000)
    # Waga 1/pozycja (rozkład Zipfa): kilka adresów generuje dużą część ruchu,
    # dzięki czemu ranking „top IP” wygląda jak w prawdziwym serwerze.
    weights = [1 / (i + 1) for i in range(len(ips))]
    when = start
    while True:
        when += timedelta(seconds=rng.expovariate(1 / mean_gap))
        if rng.random() < 0.01:  # 1% uszkodzonych linii – do testowania obsługi błędów
            yield rng.choice(["### restart serwera ###",
                              f'300.1.2.3 - - [{when:%d/%b/%Y:%H:%M:%S %z}] "GET / HTTP/1.1" 200 1'])
            continue
        ip = rng.choices(ips, weights)[0]
        template, statuses = rng.choice(PAGES)
        status = rng.choice(statuses)
        size = "-" if status in (302, 304) else rng.randrange(200, 60_000)
        yield (f'{ip} - - [{when:%d/%b/%Y:%H:%M:%S %z}] '
               f'"GET {template.format(id=rng.randrange(500))} HTTP/1.1" {status} {size} '
               f'"-" "{rng.choice(AGENTS)}"')


def generate_logs(out_dir: str | Path, files: int = 8, lines: int = 100_000,
                  seed: int = 42) -> list[Path]:
    """Tworzy *files* plików ``access-RRRR-MM-DD.log`` po *lines* linii (jeden dzień każdy)."""
    if files < 1 or lines < 1:
        raise ValueError("files i lines muszą być dodatnie")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    first_day = datetime(2026, 11, 1, tzinfo=timezone(timedelta(hours=1)))
    paths = []
    for i in range(files):
        day = first_day + timedelta(days=i)
        path = out / f"access-{day:%Y-%m-%d}.log"
        stream = log_lines(random.Random(seed + i), day, mean_gap=86_400 / lines)
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.writelines(line + "\n" for line in itertools.islice(stream, lines))
        paths.append(path)
    return paths
