# -*- coding: utf-8 -*-
"""📚 THÔNG TIN lấy từ link nguồn cho từng mục (phần chính của link nguồn, không chỉ hình ảnh).

Thứ tự ưu tiên:
1. Mục con trong bài dạng danh sách: tiêu đề nhỏ khớp tên mục (VD <h2>BV Từ Dũ</h2>) => lấy đoạn chữ bên dưới
2. Trang chỉ nói về 1 mục (tiêu đề trang khớp tên mục) => mô tả trang + nội dung đầu trang
3. Câu bất kỳ trong các trang có nhắc tên mục
Rút "thông tin chính": Địa chỉ, Giá, Hotline, Giờ mở cửa => làm mô tả/pill trên video.

MẪU CÂU MÔ TẢ (settings.infoTemplate) do sếp viết, mỗi dòng 1 câu, có chỗ trống {…}:
    📍 {địa chỉ}
    Giá sinh thường: {giá}
    Bác sĩ trưởng khoa: {bác sĩ trưởng khoa}      <- chỗ trống tự đặt: tìm "Bác sĩ trưởng khoa: ..." trong nguồn
App CHỈ điền thông tin vào đúng mẫu; dòng nào nguồn không có thông tin thì bỏ dòng đó (không thêm câu tự do).
"""
from __future__ import annotations

import re
from typing import Any

from services.source_links import match_score, norm

UNIT = r"(?:k|nghìn|ngàn|triệu|tr|đ|đồng|vnđ|vnd|₫)"
NUM = rf"\d[\d\.,]*\s*{UNIT}"
FACT_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("address", "Địa chỉ", re.compile(r"(?:địa\s*chỉ|đ/c)\s*[:：\-]\s*([^\n|;]{6,140})", re.I)),
    ("price", "Giá", re.compile(rf"\bgiá(?:\s+(?:bán|tham\s*khảo|chỉ|gói|sinh(?:\s*thường|\s*mổ)?|dịch\s*vụ))*\s*(?:từ|chỉ|khoảng)?\s*[:：\-]?\s*((?:từ\s*)?(?:\d[\d\.,]*\s*(?:{UNIT})?\s*[-–]\s*{NUM}|{NUM}))", re.I)),
    ("phone", "Hotline", re.compile(r"(?:hotline|sđt|số\s*điện\s*thoại|điện\s*thoại|liên\s*hệ)\s*[:：\-]?\s*((?:\+?84|0)[\d \.]{8,13}\d)", re.I)),
    ("hours", "Mở cửa", re.compile(r"(?:giờ\s*(?:mở\s*cửa|làm\s*việc|hoạt\s*động)|mở\s*cửa)\s*[:：\-]?\s*([^\n|;]{4,60})", re.I)),
]


def extract_facts(text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for key, label, rx in FACT_PATTERNS:
        m = rx.search(text or "")
        if m:
            val = " ".join(m.group(1).split()).strip(" .,-")
            if key == "address":
                val = re.split(r"\s+(?:hotline|sđt|điện thoại|giá|giờ)\b", val, flags=re.I)[0].strip(" .,-")
            out.append({"key": key, "label": label, "text": val})
    return out


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[\.\!\?])\s+|\n+", text or "")
    return [" ".join(p.split()) for p in parts if 15 <= len(" ".join(p.split())) <= 320]


def heading_matches(name: str, heading: str) -> bool:
    """Tiêu đề mục con khớp tên mục theo 2 chiều: 'BV Hùng Vương' ~ '2. Hùng Vương' ~ 'Bệnh viện Hùng Vương (Q5)'."""
    h = re.sub(r"^\s*\d+\s*[\.\)\-:]\s*", "", heading or "")
    toks = [w for w in norm(h).split() if len(w) >= 2]
    if not toks:
        return False
    specific = len(toks) >= 2 or len(toks[0]) >= 4  # tiêu đề quá chung (VD chỉ "BV") không được khớp ngược
    return match_score(name, h) >= 0.99 or (specific and match_score(h, name) >= 0.99)


def _relevant_texts(name: str, sources: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """[(văn bản liên quan, link nguồn)] theo thứ tự ưu tiên."""
    out: list[tuple[str, str]] = []
    for s in sources:
        if not s.get("ok"):
            continue
        for sec in s.get("sections") or []:
            if heading_matches(name, sec.get("heading", "")) and sec.get("text"):
                out.append((sec["text"], s["url"]))
    for s in sources:
        if s.get("ok") and match_score(name, s.get("title", "")) >= 0.99:
            out.append(((s.get("description") or "") + "\n" + (s.get("text") or "")[:3000], s["url"]))
    n = norm(name)
    for s in sources:
        if not s.get("ok") or not n:
            continue
        hits = [x for x in sentences(s.get("text", "")) if f" {n} " in f" {norm(x)} "]
        if hits:
            out.append(("\n".join(hits[:5]), s["url"]))
    return out


def info_for_item(name: str, sources: list[dict[str, Any]], max_snippets: int = 3, max_len: int = 220) -> dict[str, Any]:
    texts = _relevant_texts(name, sources)
    facts: dict[str, dict[str, str]] = {}
    snippets: list[dict[str, str]] = []
    seen: set[str] = set()
    for text, src in texts:
        for f in extract_facts(text):
            facts.setdefault(f["key"], dict(f, source=src))
        for sent in sentences(text):
            k = norm(sent)
            if k in seen or extract_facts(sent) and len(sent) < 60:
                continue  # câu chỉ chứa địa chỉ/giá đã nằm trong "thông tin chính"
            seen.add(k)
            snippets.append({"text": sent[:max_len], "source": src})
            if len(snippets) >= max_snippets:
                break
    return {"facts": list(facts.values()), "snippets": snippets[:max_snippets],
            "sources": list(dict.fromkeys(src for _t, src in texts))}


def shorten(text: str, n: int = 90) -> str:
    t = " ".join(str(text).split())
    t = re.split(r"(?<=[\.\!\?])\s", t)[0]
    if len(t) <= n:
        return t.rstrip(".")
    return t[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def describe(info: dict[str, Any], max_bullets: int = 2) -> list[str]:
    """Mô tả ngắn cho video: ưu tiên Địa chỉ, Giá, Hotline, Giờ mở cửa; không có thì 1 câu tóm tắt."""
    order = {"address": 0, "price": 1, "phone": 2, "hours": 3}
    facts = sorted(info.get("facts") or [], key=lambda f: order.get(f["key"], 9))
    bullets = [f["text"] if f["key"] == "address" else f"{f['label']}: {f['text']}" for f in facts][:max_bullets]
    if not bullets and info.get("snippets"):
        bullets = [shorten(info["snippets"][0]["text"])]
    return [shorten(b, 90) for b in bullets]


def ai_context(names: list[str], sources: list[dict[str, Any]], max_chars: int = 5000, template: str = "") -> str:
    """Khối thông tin theo từng mục để đưa cho AI (Agy CLI) viết mô tả chính xác theo nguồn & đúng mẫu."""
    lines = []
    if str(template or "").strip():
        lines.append("MẪU CÂU MÔ TẢ BẮT BUỘC (chỉ điền chỗ {…} bằng thông tin có trong nguồn; thiếu thông tin thì BỎ dòng đó,"
                     " KHÔNG thêm câu ngoài mẫu):\n" + str(template).strip())
    for k, name in enumerate(names, 1):
        info = info_for_item(name, sources)
        parts = [f"{f['label']}: {f['text']}" for f in info["facts"]] + [s["text"] for s in info["snippets"][:2]]
        if parts:
            lines.append(f"{k}. {name}: " + " | ".join(parts))
    return "\n".join(lines)[:max_chars]


PLACEHOLDER_RE = re.compile(r"\{([^{}]{1,60})\}")
KNOWN_KEYS = {"dia chi": "address", "gia": "price", "gia ca": "price", "hotline": "phone", "sdt": "phone",
              "so dien thoai": "phone", "dien thoai": "phone", "gio mo cua": "hours", "mo cua": "hours", "gio lam viec": "hours"}
SUMMARY_KEYS = {"tom tat", "mo ta", "gioi thieu"}


def _custom_value(label: str, texts: list[str]) -> str:
    """Tìm 'Nhãn: giá trị' trong nguồn (không phân biệt dấu/hoa thường) cho chỗ trống tự đặt."""
    want = norm(label)
    for text in texts:
        for line in re.split(r"\n+|\s[•|]\s", text):  # không tách theo dấu chấm (giữ "PGS. Lê Văn B")
            m = re.match(r"\s*([^:：]{2,60})[:：]\s*(.{1,140})", line)
            if m and norm(m.group(1)).endswith(want):
                val = re.split(r"\.\s+(?=[A-ZĐÀ-Ỹ][^:：.]{1,30}[:：])", m.group(2))[0]  # dừng ở nhãn kế tiếp
                return " ".join(val.split()).strip(" .,-")
    return ""


def fill_template(template: str | list[str], info: dict[str, Any], texts: list[str] | None = None) -> list[str]:
    """Điền thông tin vào mẫu câu mô tả. Dòng có chỗ trống không tìm được giá trị => bỏ cả dòng."""
    lines = template if isinstance(template, list) else str(template or "").splitlines()
    facts = {f["key"]: f["text"] for f in info.get("facts") or []}
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        ok = True

        def sub(m: re.Match) -> str:
            nonlocal ok
            key = norm(m.group(1))
            if key in KNOWN_KEYS and facts.get(KNOWN_KEYS[key]):
                return facts[KNOWN_KEYS[key]]
            if key in SUMMARY_KEYS and info.get("snippets"):
                return shorten(info["snippets"][0]["text"], 80)
            val = _custom_value(m.group(1), texts or [])
            if not val:
                ok = False
            return val

        filled = " ".join(PLACEHOLDER_RE.sub(sub, line).split())
        if ok and filled:
            # chỉ giới hạn độ dài (không cắt theo dấu chấm để giữ "PGS. Lê Văn B", "3.500.000đ")
            out.append(filled if len(filled) <= 110 else filled[:110].rsplit(" ", 1)[0].rstrip(",;:") + "…")
    return out


def template_for_item(name: str, sources: list[dict[str, Any]], template: str | list[str]) -> tuple[dict[str, Any], list[str]]:
    """(thông tin tìm được, mô tả điền theo mẫu) cho 1 mục. Không có mẫu => mô tả mặc định describe()."""
    info = info_for_item(name, sources)
    has_tpl = bool(str("\n".join(template) if isinstance(template, list) else template or "").strip())
    if not has_tpl:
        return info, describe(info)
    texts = [t for t, _src in _relevant_texts(name, sources)]
    return info, fill_template(template, info, texts)
