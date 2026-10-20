"""Write Tableau-ready CSV files from the official PostgreSQL marts.

Usage:
    python scripts/export_tableau.py
    python scripts/export_tableau.py --output-dir data/exports/tableau
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboards.exports import write_exports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/exports/tableau"),
        help="Directory for the CSV files",
    )
    args = parser.parse_args()
    counts = write_exports(args.output_dir)
    for name, rows in counts.items():
        print(f"{name}: {rows} rows -> {args.output_dir / (name + '.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
