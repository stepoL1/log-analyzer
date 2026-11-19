"""Tekstowy raport z wynikami analizy."""

from log_analyzer.geoip import GeoInfo
from log_analyzer.stats import FileStats


def format_report(stats: FileStats, top: int = 10,
                  geo: dict[str, GeoInfo | None] | None = None) -> str:
    """Buduje raport z najważniejszymi statystykami."""
    lines = [
        "=== Raport analizy logów ===",
        f"Pliki:           {stats.files}",
        f"Żądania:         {stats.requests}",
        f"Błędne linie:    {stats.malformed}",
        f"Unikalne IP:     {len(stats.ip_counts)}",
        f"Wysłane dane:    {stats.bytes_sent / 1024 / 1024:.1f} MiB",
        f"Odsetek błędów:  {stats.error_rate:.2%}",
        f"Zakres czasu:    {stats.first_seen} – {stats.last_seen}",
        "",
        "Klasy odpowiedzi: " + ", ".join(f"{k}: {v}" for k, v in stats.status_classes().items()),
        "",
        f"Top {top} adresów IP:",
    ]
    for ip, count in stats.ip_counts.most_common(top):
        place = ""
        if geo is not None:
            info = geo.get(ip)
            place = f"  ({info.country}, {info.city})" if info else "  (nieznane)"
        lines.append(f"  {ip:<16} {count:>7}{place}")

    lines += ["", f"Top {top} URL:"]
    lines += [f"  {url:<30} {n:>7}" for url, n in stats.url_counts.most_common(top)]
    lines += ["", f"Top {top} URL z błędami (4xx/5xx):"]
    lines += [f"  {url:<30} {n:>7}" for url, n in stats.error_urls.most_common(top)]
    busiest = max(stats.hourly, key=stats.hourly.__getitem__, default=None)
    if busiest is not None:
        lines += ["", f"Najbardziej obciążona godzina: {busiest:02d}:00 "
                      f"({stats.hourly[busiest]} żądań)"]
    return "\n".join(lines)
