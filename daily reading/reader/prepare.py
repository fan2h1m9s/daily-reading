#!/usr/bin/env python3
"""选文件 + 转换，一条龙。

用法:
  python prepare.py               # 列出 pdf/ 让用户选
  python prepare.py "<某.pdf>"    # 直接指定（拖拽）
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT.parent / "pdf"
CURRENT = PDF_DIR / "current.pdf"
ARTICLE = ROOT / "article.json"


def fail(msg):
    print()
    print(f"  [x] {msg}")
    return 1


def choose():
    if not PDF_DIR.exists():
        PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(
        p for p in PDF_DIR.glob("*.pdf")
        if p.name.lower() != "current.pdf"
    )
    if not pdfs:
        return None, fail("pdf\\ 里没有 PDF，先放一篇进去")

    print()
    print("  pdf\\ 里的文章：")
    for i, p in enumerate(pdfs, 1):
        print(f"    {i}) {p.name}")

    if len(pdfs) == 1:
        print()
        print("  只有一篇，自动选中。")
        return pdfs[0], 0

    print()
    try:
        raw = input("  输入编号后回车：").strip()
    except (EOFError, KeyboardInterrupt):
        return None, 1
    if not raw.isdigit() or not 1 <= int(raw) <= len(pdfs):
        return None, fail("编号无效")
    return pdfs[int(raw) - 1], 0


def main():
    args = [a for a in sys.argv[1:] if a.strip()]
    if args:
        src = Path(args[0]).expanduser()
        if not src.is_absolute():
            src = (Path.cwd() / src).resolve()
    else:
        src, code = choose()
        if src is None:
            return code

    if not src.exists():
        return fail(f"文件不存在: {src}")
    if src.suffix.lower() != ".pdf":
        return fail(f"不是 PDF 文件: {src.name}")

    print()
    print(f"  正在解析: {src.name}")
    shutil.copy2(src, CURRENT)

    try:
        import pymupdf  # noqa: F401
    except ImportError:
        return fail("缺少 PyMuPDF，请先运行: pip install pymupdf")

    if ARTICLE.exists():
        ARTICLE.unlink()

    r = subprocess.run(
        [sys.executable, str(ROOT / "extract.py"), str(CURRENT), str(ARTICLE)],
        cwd=str(ROOT),
    )
    if r.returncode != 0 or not ARTICLE.exists():
        return fail("转换失败。如果是扫描版 PDF，需要先 OCR。")

    print()
    print("  [ok] 现在双击 2-开始阅读.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
