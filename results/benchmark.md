Python 3.12.10, GIL włączony: True, rdzenie logiczne: 16, Windows 11

| Scenariusz | Wariant | Czas [s] | Przyspieszenie |
|---|---|---:|---:|
| CPU: parsowanie logów | sequential | 8.627 | 1.00× |
| CPU: parsowanie logów | threads | 9.502 | 0.91× |
| CPU: parsowanie logów | processes | 2.147 | 4.02× |
| I/O: geolokalizacja IP | sequential | 3.053 | 1.00× |
| I/O: geolokalizacja IP | threads | 0.206 | 14.82× |
| I/O: geolokalizacja IP | asyncio | 0.221 | 13.83× |
