#!/usr/bin/env python3
"""AI 影视工作台 CLI 入口。

用法：python workbench.py <command> [options]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "packages"))

from cli.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
