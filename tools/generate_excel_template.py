#!/usr/bin/env python3
"""
Generate canonical Excel chip library template.

Usage:
  python3 tools/generate_excel_template.py
  python3 tools/generate_excel_template.py /custom/path/chip_library.xlsx
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ic_tester_app.config import Config
from ic_tester_app.chips.excel_io import create_excel_template


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Config.EXCEL_LIBRARY_PATH
    created = create_excel_template(path)
    print(f"Template created: {created}")


if __name__ == "__main__":
    main()
