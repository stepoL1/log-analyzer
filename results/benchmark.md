Python 3.12.10, GIL włączony: True, rdzenie logiczne: 16, Windows 11

| Scenariusz | Wariant | Czas [s] | Przyspieszenie |
|---|---|---:|---:|
| CPU: parsowanie logów | sequential | 8.713 | 1.00× |
| CPU: parsowanie logów | threads | 8.969 | 0.97× |
| CPU: parsowanie logów | processes | 1.711 | 5.09× |
| I/O: geolokalizacja IP | sequential | 3.049 | 1.00× |
| I/O: geolokalizacja IP | threads | 0.205 | 14.85× |
