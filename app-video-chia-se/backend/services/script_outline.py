# -*- coding: utf-8 -*-
"""Bộ phân tích dàn ý mở rộng — bọc quanh parse_script_outline cũ (media_ops), bổ sung:

1. TIÊU ĐỀ PHỤ (có hoặc không có tuỳ kịch bản):
   - Ghi rõ:  "Tiêu đề phụ: Chất lượng - Xài bền - Kinh tế"  (hoặc "Phụ đề:", "Dòng phụ:", "Sub:")
   - Tự nhận: khối 1 dòng đứng riêng ngay sau tiêu đề, có dấu ngăn " - ", " – ", "•", "|"
     và phía sau còn các mục khác.
2. ĐỊNH DẠNG KHỐI (các mục cách nhau bằng dòng trống, không dùng gạch đầu dòng):
       Sokfarm                                  <- tên mục
       Nước tương và Mật hoa dừa quốc dân       <- mô tả 1
       Gia vị nêm nếm nhạt, vị ngọt tự nhiên    <- mô tả 2
   => mỗi khối = 1 mục; dòng đầu là tên, các dòng sau là mô tả/địa chỉ.

Các định dạng cũ (gạch đầu dòng "-", danh sách mỗi dòng 1 mục) giữ nguyên kết quả như trước.
Bản JS tương đương nằm trong frontend/modules/script_inspector_pro.js — giữ đồng bộ luật.
"""
from __future__ import annotations

import re
from typing import Any, Callable

SUBTITLE_MARKER_RE = re.compile(r"^\s*(?:tiêu\s*đề\s*phụ|phụ\s*đề|dòng\s*phụ|sub(?:title)?)\s*[:：]\s*(.+)$", re.I)
BULLET_RE = re.compile(r"^\s*[\-\*\•\+]\s+")
NUMBERED_RE = re.compile(r"^\s*\d+[\.\)\-:]\s*")
SEPARATOR_RE = re.compile(r"\s[\-–—|•]\s|\s•|•\s")


def _blocks(lines: list[str]) -> list[list[str]]:
    out: list[list[str]] = []
    cur: list[str] = []
    for ln in lines:
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _clean_heading(s: str) -> str:
    return NUMBERED_RE.sub("", s).strip()


def _clean_bullet(s: str) -> str:
    return re.sub(r"^\s*[\-\*\•\+]\s*", "", s).strip()


def _title_consumed(first_line: str, title: str) -> bool:
    a = NUMBERED_RE.sub("", first_line).strip().upper()
    return bool(title) and (a == title.strip().upper() or first_line.strip().upper() == title.strip().upper())


def looks_like_subtitle(line: str) -> bool:
    s = line.strip()
    return bool(s) and not NUMBERED_RE.match(s) and not BULLET_RE.match(s) and bool(SEPARATOR_RE.search(f" {s} "))


def parse_outline_extended(raw_text: str, current_title: str, legacy: Callable[[str, str], dict[str, Any]]) -> dict[str, Any]:
    raw_lines = (raw_text or "").splitlines()
    explicit = ""
    kept: list[str] = []
    for ln in raw_lines:
        m = SUBTITLE_MARKER_RE.match(ln)
        if m and not explicit:
            explicit = m.group(1).strip()
            continue
        kept.append(ln)
    text = "\n".join(kept)
    base = legacy(text, current_title)
    base.setdefault("format", "list")

    nonempty = [i for i, ln in enumerate(kept) if ln.strip()]
    if not nonempty:
        if explicit:
            base["subtitle"] = explicit
        return base
    first_idx = nonempty[0]
    body = kept[first_idx + 1:] if _title_consumed(kept[first_idx], base.get("title", "")) else kept[first_idx:]
    if any(BULLET_RE.match(ln) for ln in body):
        if explicit:
            base["subtitle"] = explicit
        base["format"] = "bullets"
        return base  # định dạng gạch đầu dòng: luật cũ đã đúng

    blocks = _blocks(body)
    subtitle = explicit
    if not subtitle and len(blocks) >= 2 and len(blocks[0]) == 1 and looks_like_subtitle(blocks[0][0]):
        subtitle = blocks[0][0]
        blocks = blocks[1:]

    if len(blocks) >= 2 and any(len(b) >= 2 for b in blocks):
        entries = [{"heading": _clean_heading(b[0]), "bullets": [_clean_bullet(x) for x in b[1:] if _clean_bullet(x)]}
                   for b in blocks if _clean_heading(b[0])]
        fmt = "blocks"
    elif subtitle and subtitle != base.get("subtitle"):
        entries = [{"heading": _clean_heading(_clean_bullet(ln)), "bullets": []}
                   for b in blocks for ln in b if _clean_heading(_clean_bullet(ln))]
        fmt = "list"
    else:
        if explicit:
            base["subtitle"] = explicit
        return base
    return {"title": base.get("title", ""), "subtitle": subtitle or "", "entries": entries,
            "count": len(entries), "format": fmt}
