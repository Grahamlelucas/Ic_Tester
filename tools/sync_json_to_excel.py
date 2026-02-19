#!/usr/bin/env python3
"""
Synchronize JSON chip definitions into Excel workbook.

Usage:
  python3 tools/sync_json_to_excel.py
  python3 tools/sync_json_to_excel.py /path/to/chip_library.xlsx
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ic_tester_app.config import Config
from ic_tester_app.chips.excel_io import sync_json_chips_to_excel


def main():
    workbook = Path(sys.argv[1]) if len(sys.argv) > 1 else Config.EXCEL_LIBRARY_PATH
    stats = sync_json_chips_to_excel(
        chips_dir=Config.CHIPS_DIR,
        workbook_path=workbook,
        board=Config.DEFAULT_BOARD,
        preserve_results=True,
    )
    print(f"Synchronized JSON -> Excel: {workbook}")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
