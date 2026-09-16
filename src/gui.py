"""Alias cho run_gui — tương thích ngược."""
from run_gui import main

if __name__ == "__main__":
    import sys
    sys.exit(main())