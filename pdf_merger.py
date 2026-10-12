# -*- coding: utf-8 -*-
"""发票 PDF 合并工具 - 程序入口。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gui.app import run

if __name__ == "__main__":
    run()
