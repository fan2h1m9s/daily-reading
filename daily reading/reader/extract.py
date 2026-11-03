#!/usr/bin/env python3
"""PDF -> 可划选的阅读结构(JSON)。

用法: python extract.py <in.pdf> <out.json>
"""
import json
import re
import statistics
import sys
from pathlib import Path

import pymupdf

MAX_BLOCK = 6000
MERGE_GAP = 12.0          # 行间距上限；超过视为新段落
MIN_PROSE_WORDS = 8

FOOTER_MARKERS = (
    "Become A Pro", "Subscribe to CNBC PRO", "CNBC Newsletters", "News Tips",
    "Sign up for free newsletters", "Advertise With Us", "PLEASE CONTACT US",
    "Privacy Policy", "Cookie Notice", "CA Notice", "Terms of Service",
    "© 20", "All Rights Reserved", "Data is a real-time snapshot",
    "Market Data Terms of Use", "Data also provided by", "Licensing & Reprints",
    "Get this delivered to your inbox", "Ad Choice", "Do Not Sell",
)

JUNK_RE = (
    re.compile(r"^[A-Z]{1,6}\s[-+]?\d"),                    # 行情条 SBUX -0.46
    re.compile(r"^\d{2}:\d{2}\s+\d{2}:\d{2}$"),             # 时间码
    re.compile(r"^V\s?I\s?D\s?E\s?O\b"),                    # 视频占位
    re.compile(r"^(Listen\s+\d+\s?min|1x|\d+x)$"),
    re.compile(r"^(WATCH|LIVE|MORE IN|TRENDING NOW|MOST POPULAR|READ MORE)\b"),
    re.compile(r"^(SPONSORED|ADVERTISEMENT|FOLLOW|SHARE|COPY LINK|PRINT)\b"),
    re.compile(r"^In this article\b"),
    re.compile(r"^Choose CNBC as your preferred source"),
    re.compile(r"^Become A Pro\b"),
    re.compile(r"^Subscribe to CNBC"),
    re.compile(r"^News Tips\b"),
    re.compile(r"^[A-Z][A-Z\s&'\-]{1,28}$"),                # 全大写短标签
    re.compile(r"^(PUBLISHED|UPDATED)\b"),
    re.compile(r"^Follow your favorite stocks"),
    re.compile(r"^•"),                                      # KEY POINTS 要点（正文里有）
    re.compile(r"^[^\w]{1,12}$"),                           # 纯符号
)

PROMO_RE = re.compile(
    r"Choose CNBC as your preferred source on Google[^.]*\.\s*"
    r"|Get this delivered to your inbox[^.]*\.\s*",
    re.I,
)


def clean_lines(lines):
    if not lines:
        return ""
    out = lines[0]
    for nxt in lines[1:]:
        if out.endswith("-") and nxt[:1].islower():
            out = out[:-1] + nxt
        else:
            out = out + " " + nxt
    return re.sub(r"\s+", " ", out).strip()


def is_junk(text):
    if not text:
        return True
    return any(rx.match(text) for rx in JUNK_RE)


def collect(doc):
    raw = []
    for pno, page in enumerate(doc):
        height = page.rect.height
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            lines = block.get("lines", [])
            if not lines:
                continue
            text = clean_lines([
                "".join(span.get("text", "") for span in line.get("spans", []))
                for line in lines
            ])
            if not text:
                continue
            if re.fullmatch(r"[\divxlcVDXLC\.\-–—\s]{1,8}", text):
                continue
            y0, y1 = block["bbox"][1], block["bbox"][3]
            if (y0 < height * 0.055 or y1 > height * 0.945) and len(text) < 90:
                continue
            sizes = [
                span.get("size", 0)
                for line in lines
                for span in line.get("spans", [])
                if span.get("text", "").strip()
            ]
            raw.append({
                "text": text,
                "size": statistics.median(sizes) if sizes else 0,
                "p": pno + 1,
                "y0": y0,
                "y1": y1,
            })
    return raw


def classify(raw):
    if not raw:
        return raw
    median = statistics.median([r["size"] for r in raw]) or 10
    has_h1 = False
    for r in raw:
        r["kind"] = "p"
        if r["size"] > median * 1.2 and len(r["text"]) <= 160:
            if not has_h1:
                r["kind"] = "h1"
                has_h1 = True
            else:
                r["kind"] = "h2"
    return raw


def merge(raw):
    """把被切成一行一行的正文粘回段落。"""
    out = []
    prev = None
    for b in raw:
        if prev and prev["kind"] == "p" and b["kind"] == "p" and b["p"] == prev["p"]:
            gap = b["y0"] - prev["y1"]
            head = b["text"][:1]
            cont = head.islower() or head in ",.;:%)]"
            if gap <= MERGE_GAP or (cont and gap <= MERGE_GAP * 2.5):
                sep = "" if head in ",.;:%)]" else " "
                prev["text"] = prev["text"] + sep + b["text"]
                prev["y1"] = b["y1"]
                continue
        out.append(b)
        prev = b
    return out


def tidy_title(text):
    m = re.match(r"^(?:[A-Z][A-Z&'\- ]{2,24})\s+(?=[A-Z][a-z])", text)
    return text[m.end():].strip() if m else text.strip()


def find_footer(raw):
    """在原始块上定位页脚起点（必须在剔除垃圾之前做，否则标记行已被删掉）。"""
    seen = 0
    for i, b in enumerate(raw):
        if len(b["text"].split()) >= MIN_PROSE_WORDS and not is_junk(b["text"]):
            seen += 1
        if seen >= 3 and any(m in b["text"] for m in FOOTER_MARKERS):
            return i
    return len(raw)


def trim(blocks):
    # 导航头截断：从第一段真正文开始收
    start = 0
    for i, b in enumerate(blocks):
        if b["kind"] == "p" and len(b["text"].split()) >= MIN_PROSE_WORDS and not is_junk(b["text"]):
            start = i
            break
    for i in range(start, -1, -1):
        if blocks[i]["kind"] == "h1":
            start = i
            break
    blocks = blocks[start:]

    kept = []
    for b in blocks:
        t = PROMO_RE.sub("", b["text"]).strip()
        if not t:
            continue
        b["text"] = t
        if b["kind"] == "p" and (is_junk(t) or len(t.split()) < 3):
            continue
        if b["kind"] == "h2" and (is_junk(t) or len(t.split()) < 2):
            continue
        kept.append(b)

    # 收尾：以小节开头的碎块并回上一段
    joined = []
    for b in kept:
        if (joined and b["kind"] == "p" and joined[-1]["kind"] == "p"
                and b["text"][:1].islower()):
            joined[-1]["text"] = joined[-1]["text"] + " " + b["text"]
        else:
            joined.append(b)

    # 去掉文末的"相关阅读"标题（没有句末标点的短行）
    while joined:
        t = joined[-1]["text"].rstrip()
        if (joined[-1]["kind"] == "p" and len(t.split()) < 20
                and not t.endswith((".", "!", "?", '"', "”", ":", ")"))):
            joined.pop()
            continue
        break
    return joined


def main():
    src, dst = sys.argv[1], sys.argv[2]
    doc = pymupdf.open(src)

    raw_all = collect(doc)
    if not raw_all:
        sys.exit("这个 PDF 没有文字层（可能是扫描件），需要先 OCR。")

    body = raw_all[:find_footer(raw_all)]
    raw = [b for b in body if not is_junk(b["text"])]
    if not raw:
        sys.exit("没能提取到正文，可能版面太特殊。")

    blocks = trim(merge(classify(raw)))
    if not blocks:
        sys.exit("没能提取到正文，可能版面太特殊。")

    title = next((b["text"] for b in blocks if b["kind"] == "h1"), Path(src).stem)
    title = tidy_title(title)
    if blocks and blocks[0]["kind"] == "h1":
        blocks[0]["text"] = title

    out_blocks = [{"t": b["kind"], "s": b["text"][:MAX_BLOCK], "p": b["p"]} for b in blocks]
    words = sum(len(b["s"].split()) for b in out_blocks if b["t"] == "p")
    Path(dst).write_text(json.dumps({
        "title": title,
        "source": str(src),
        "pages": doc.page_count,
        "words": words,
        "blocks": out_blocks,
    }, ensure_ascii=False), encoding="utf-8")

    print(f"标题: {title}", flush=True)
    print(f"已解析: {doc.page_count} 页 / 约 {words} 词 / {len(out_blocks)} 段", flush=True)


main()
