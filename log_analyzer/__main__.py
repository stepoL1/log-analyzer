"""Umożliwia uruchomienie pakietu poleceniem ``python -m log_analyzer``."""

import sys

from log_analyzer.cli import main

if __name__ == "__main__":  # multiprocessing Windows
    sys.exit(main())
