# -*- coding: utf-8 -*-
"""发票 PDF 合并核心逻辑：多文件多页 -> 指定页数网格排版 -> A4 纵向输出。"""
import datetime
import math
import os
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24 推荐写法
except ImportError:  # 旧版本兼容
    import fitz  # PyMuPDF

# A4 纵向（pt）
A4_W, A4_H = 595.0, 842.0
OUTER_MARGIN = 14.0   # 页面四周留白
GUTTER = 10.0         # 格子间距


def default_desktop_dir() -> str:
    """返回桌面路径，优先检测 OneDrive 重定向。"""
    candidates = []
    for var in ("OneDriveConsumer", "OneDriveCommercial", "OneDrive"):
        root = os.environ.get(var)
        if root:
            candidates.append(Path(root) / "Desktop")
    candidates.append(Path.home() / "Desktop")
    for p in candidates:
        if p.is_dir():
            return str(p)
    return str(Path.home())


def build_output_path(file_count: int, target_pages: int, output_dir: str | None = None) -> str:
    """生成 m合n-date.pdf 命名；重名时追加 (1)、(2) ...。"""
    date = datetime.date.today().strftime("%Y-%m-%d")
    directory = Path(output_dir) if output_dir else Path(default_desktop_dir())
    directory.mkdir(parents=True, exist_ok=True)
    base = f"{file_count}合{target_pages}-{date}"
    candidate = directory / f"{base}.pdf"
    seq = 1
    while candidate.exists():
        candidate = directory / f"{base} ({seq}).pdf"
        seq += 1
    return str(candidate)


def _collect_source_pages(file_paths: list[str]):
    """打开所有 PDF 并收集 (doc, page_no) 引用；非法输入抛 ValueError。"""
    if not file_paths:
        raise ValueError("请先添加至少一个 PDF 文件")
    docs = []
    pages = []  # (doc, pno, width, height)
    for path in file_paths:
        p = Path(path)
        if not p.is_file():
            raise ValueError(f"文件不存在：{p}")
        if p.suffix.lower() != ".pdf":
            raise ValueError(f"不是 PDF 文件：{p.name}")
        try:
            doc = fitz.open(str(p))
        except Exception as e:
            raise ValueError(f"无法打开 PDF：{p.name}（{e}）") from e
        if doc.needs_pass:
            doc.close()
            raise ValueError(f"PDF 已加密，暂不支持：{p.name}")
        if doc.page_count == 0:
            doc.close()
            raise ValueError(f"PDF 没有页面：{p.name}")
        docs.append(doc)
        for pno in range(doc.page_count):
            rect = doc[pno].rect
            pages.append((doc, pno, rect.width, rect.height))
    return docs, pages


def _distribute(total: int, target_pages: int) -> list[int]:
    """把 total 个源页尽量均匀拆到 target_pages 页，返回每页数量列表（跳过 0）。"""
    if total <= 0:
        raise ValueError("没有可合并的页面")
    if target_pages < 1:
        raise ValueError("目标页数必须 ≥ 1")
    if target_pages > total:
        target_pages = total  # 源页不足时，每页一张
    base, rem = divmod(total, target_pages)
    counts = []
    for i in range(target_pages):
        c = base + (1 if i < rem else 0)
        if c > 0:
            counts.append(c)
    return counts


def _factor_pairs(count: int) -> list[tuple[int, int]]:
    """count 的所有 (cols, rows) 因子对，cols <= rows，恰好占满无空格。"""
    return [
        (cols, count // cols)
        for cols in range(1, math.isqrt(count) + 1)
        if count % cols == 0
    ]


def _layout_candidates(count: int) -> list[tuple[int, int]]:
    """基础因子对 + 其转置（如 (1,2) 与 (2,1)），供利用率比较。"""
    pairs = _factor_pairs(count)
    transposed = [(rows, cols) for cols, rows in pairs if rows != cols]
    return pairs + transposed


def _layout_utilization(count: int, avg_aspect: float, cols: int, rows: int) -> float:
    """给定布局下，count 个宽高比为 avg_aspect 的源页等比缩放后的纸面利用率（0~1）。"""
    content_w = A4_W - 2 * OUTER_MARGIN - (cols - 1) * GUTTER
    content_h = A4_H - 2 * OUTER_MARGIN - (rows - 1) * GUTTER
    cell_w, cell_h = content_w / cols, content_h / rows
    # 单格内等比缩放后的实际绘制尺寸
    w = min(cell_w, cell_h * avg_aspect)
    h = w / avg_aspect
    return count * w * h / (A4_W * A4_H)


def _choose_layout(count: int, avg_aspect: float) -> tuple[int, int]:
    """智能选择 (cols, rows)：因子对规则保证对称无空格，极端宽高比时按利用率覆盖。

    基础规则取“最大的 cols <= sqrt(count)”：k=2/3→单列堆叠、k=4→2x2、k=6→2x3、k=5→1x5。
    仅当其他因子对利用率 >= 基础布局的 1.8 倍（极端宽高比）时改选利用率最高的布局。
    """
    pairs = _layout_candidates(count)
    # 基础规则：cols <= rows 的因子对中取最大 cols，保证对称、无空格
    base_cols, base_rows = max(_factor_pairs(count), key=lambda p: p[0])
    base_util = _layout_utilization(count, avg_aspect, base_cols, base_rows)
    best_cols, best_rows, best_util = base_cols, base_rows, base_util
    for cols, rows in pairs:
        util = _layout_utilization(count, avg_aspect, cols, rows)
        if util > best_util:
            best_cols, best_rows, best_util = cols, rows, util
    if best_util >= base_util * 1.8:
        return best_cols, best_rows
    return base_cols, base_rows


def merge(file_paths: list[str], target_pages: int, output_dir: str | None = None) -> str:
    """合并多个 PDF 为指定页数，返回输出文件完整路径；非法输入抛 ValueError。"""
    docs, pages = _collect_source_pages(file_paths)
    try:
        counts = _distribute(len(pages), target_pages)
        out = fitz.open()
        idx = 0
        for count in counts:
            page = out.new_page(width=A4_W, height=A4_H)
            items = pages[idx : idx + count]
            avg_aspect = sum(w / h for _, _, w, h in items) / count
            cols, rows = _choose_layout(count, avg_aspect)
            cell_w = (A4_W - 2 * OUTER_MARGIN - (cols - 1) * GUTTER) / cols
            cell_h = (A4_H - 2 * OUTER_MARGIN - (rows - 1) * GUTTER) / rows
            for i, (doc, pno, _, _) in enumerate(items):
                r, c = divmod(i, cols)
                x0 = OUTER_MARGIN + c * (cell_w + GUTTER)
                y0 = OUTER_MARGIN + r * (cell_h + GUTTER)
                rect = fitz.Rect(x0, y0, x0 + cell_w, y0 + cell_h)
                # keep_proportion=True：保持源页面宽高比，等比缩放并在格子内居中
                page.show_pdf_page(rect, doc, pno, keep_proportion=True)
            idx += count

        out_path = build_output_path(len(file_paths), target_pages, output_dir)
        tmp_path = out_path + ".tmp"
        out.save(tmp_path, garbage=3, deflate=True)
        out.close()
        os.replace(tmp_path, out_path)
        return out_path
    finally:
        for doc in docs:
            doc.close()
