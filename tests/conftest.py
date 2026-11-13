"""Wspólne dane testowe: przykładowe linie logu, poprawne i uszkodzone."""

GOOD = '83.1.2.3 - - [12/Nov/2026:10:15:32 +0100] "GET /products/7?x=1 HTTP/1.1" 200 5123 "-" "Mozilla/5.0"'
ERROR = '31.0.0.9 - - [12/Nov/2026:11:00:00 +0100] "POST /login HTTP/1.1" 401 - "-" "curl/8"'
SHORT = '62.0.0.1 - - [12/Nov/2026:23:59:59 +0100] "GET /static/app.js HTTP/1.1" 304 -'
BROKEN = "to nie jest linia logu"
BAD_IP = '300.1.2.3 - - [12/Nov/2026:10:15:32 +0100] "GET / HTTP/1.1" 200 1'