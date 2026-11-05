# -*- coding: utf-8 -*-
"""Phân tích "Yêu cầu thiết kế" (visual_prompt) tiếng Việt -> bộ thông số giao diện video.

Dùng chung cho: Live Preview 9:16 (frontend có bản JS tương đương), Remotion (settings -> config),
và Auto-QA (kiểm tra bgTheme/customBgColor có khớp yêu cầu không).
Không động vào productImageSize để tránh phóng to 2 lần với apply_final_revision_notes.
"""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path
from typing import Any

BEIGE_BG, CREAM_CARD = "#F6EFE6", "#FFFDF9"
PINK_BG, MEDICAL_BG, DARK_BG = "#FCE8EC", "#F0F7FF", "#0F172A"

GRADIENTS = {
    BEIGE_BG: "radial-gradient(circle at 50% 35%, #fffdf9 0%, #f6efe6 58%, #e9dccb 100%)",
    PINK_BG: "radial-gradient(circle at 50% 35%, #fffaf7 0%, #fce8ec 58%, #f3d1d8 100%)",
    MEDICAL_BG: "radial-gradient(circle at 50% 35%, #ffffff 0%, #f0f7ff 58%, #d9e8f7 100%)",
}

# (nhãn hiển thị, các từ khoá, thay đổi style)
RULES: list[tuple[str, tuple[str, ...], dict[str, Any]]] = [
    ("Nền màu be ấm #F6EFE6", ("nền màu be", "nền be", "màu be", "be ấm", "tông be", "nền kem", "#f6efe6"),
     {"bgTheme": "beige", "bgColor": BEIGE_BG, "cardColor": CREAM_CARD}),
    ("Tông hồng phấn Mẹ & Bé", ("hồng phấn", "nền hồng", "mẹ & bé", "mẹ và bé", "hồng pastel"),
     {"bgTheme": "beige", "bgColor": PINK_BG, "cardColor": "#FFF8FA", "accent": "#D6336C", "nameColor": "#C2255C"}),
    ("Nền xanh y khoa #F0F7FF", ("xanh y khoa", "nền y khoa", "xanh y tế", "#f0f7ff"),
     {"bgTheme": "beige", "bgColor": MEDICAL_BG, "cardColor": "#FFFFFF", "accent": "#1C64B8"}),
    ("Nền tối Studio", ("nền tối", "nền đen", "dark mode", "nền tím"),
     {"bgTheme": "dark", "bgColor": DARK_BG, "cardColor": "#1E293B", "nameColor": "#FFD54F"}),
    ("Phóng to khung ảnh chính", ("phóng to khung ảnh", "ảnh to", "ảnh lớn", "phóng to ảnh", "ảnh bác sĩ to", "to rõ kịch khung"),
     {"heroImageScale": 1.15}),
    ("Căn giữa địa chỉ & thông tin", ("căn giữa",),
     {"centerInfoPills": True}),
    ("Khung thẻ bác sĩ chuẩn y khoa", ("khung thẻ bác sĩ", "thẻ bác sĩ", "chuẩn y khoa", "phong cách bác sĩ"),
     {"doctorCardFrame": True, "accent": "#1C64B8"}),
    ("Bảng tổng hợp chữ to rõ", ("bảng tổng hợp chữ to", "tổng hợp chữ to", "chữ to rõ", "bảng tổng hợp to"),
     {"summaryLargeText": True}),
    ("Chữ vàng viền đậm", ("chữ vàng", "viền đậm"),
     {"nameColor": "#F5B700", "nameStrokeBold": True}),
]

DEFAULT_STYLE: dict[str, Any] = {
    "bgTheme": "beige",
    "bgColor": BEIGE_BG,
    "cardColor": CREAM_CARD,
    "nameColor": "#8A4B12",
    "accent": "#B7791F",
    "heroImageScale": 1.0,
    "centerInfoPills": True,
    "doctorCardFrame": False,
    "summaryLargeText": False,
    "nameStrokeBold": False,
}

# style key -> settings key (Remotion config)
SETTINGS_MAP = {
    "bgTheme": "bgTheme",
    "bgColor": "customBgColor",
    "cardColor": "cardColor",
    "nameColor": "itemNameColor",
    "accent": "accentColor",
    "heroImageScale": "heroImageScale",
    "centerInfoPills": "centerInfoPills",
    "doctorCardFrame": "doctorCardFrame",
    "summaryLargeText": "summaryLargeText",
    "nameStrokeBold": "nameStrokeBold",
}


def parse_visual_prompt(text: str) -> dict[str, Any]:
    low = (text or "").lower()
    style = dict(DEFAULT_STYLE)
    matched: list[str] = []
    for label, keys, changes in RULES:
        if any(k in low for k in keys):
            style.update(changes)
            matched.append(label)
    m_hex = re.search(r"nền[^#\n;]{0,20}#([0-9a-f]{6})\b", low)
    if m_hex and "#" + m_hex.group(1).upper() != style["bgColor"]:
        style["bgColor"] = "#" + m_hex.group(1).upper()
        matched.append(f"Nền tuỳ chỉnh #{m_hex.group(1).upper()}")
    m_scale = re.search(r"(?:phóng to|ảnh)[^\d\n;]{0,24}(\d{2,3})\s*%", low)
    if m_scale and any(x.startswith("Phóng to") for x in matched):
        pct = int(m_scale.group(1))
        if 80 <= pct <= 160:
            style["heroImageScale"] = round(pct / 100.0, 2)
    style["matched"] = matched
    return style


def style_from_settings(settings: dict[str, Any]) -> dict[str, Any]:
    style = dict(DEFAULT_STYLE)
    for s_key, set_key in SETTINGS_MAP.items():
        if set_key in settings and settings[set_key] not in (None, ""):
            style[s_key] = settings[set_key]
    if settings.get("bgTheme") == "dark" and "customBgColor" not in settings:
        style["bgColor"] = DARK_BG
    return style


def load_visual_prompt(pdir: Path) -> str:
    from utils import read_json

    proj = read_json(pdir / "project.json", {}) or {}
    return str(proj.get("visual_prompt") or proj.get("final_revision_notes") or "")


def save_and_apply_visual_prompt(pdir: Path, text: str, apply: bool = True) -> dict[str, Any]:
    from pipeline import save_project_state
    from utils import read_json

    proj = read_json(pdir / "project.json", {}) or {}
    proj["visual_prompt"] = text.strip()
    style = parse_visual_prompt(text)
    applied: dict[str, Any] = {}
    if apply and style["matched"]:
        settings = proj.setdefault("settings", {})
        touched = set()
        for _label, keys, changes in RULES:
            if any(k in text.lower() for k in keys):
                touched.update(changes.keys())
        if any(x.startswith("Nền tuỳ chỉnh") for x in style["matched"]):
            touched.add("bgColor")
        if style["heroImageScale"] != 1.0:
            touched.add("heroImageScale")
        for s_key in touched:
            set_key = SETTINGS_MAP[s_key]
            settings[set_key] = style[s_key]
            applied[set_key] = style[s_key]
        if "bgColor" in touched:
            bg = style["bgColor"]
            settings["backgroundColor"] = "" if style["bgTheme"] == "dark" else GRADIENTS.get(bg, bg)
            applied["backgroundColor"] = settings["backgroundColor"]
    save_project_state(pdir, proj)
    return {"ok": True, "visual_prompt": proj["visual_prompt"], "style": style, "applied_settings": applied,
            "changes": style["matched"]}


def _file_url(pid: str, path_str: str, pdir: Path | None = None) -> str:
    """Gắn &v=<thời điểm sửa file> để Live Preview tải lại khi ảnh đổi (tên file Bước 6 giữ nguyên)."""
    url = f"/api/projects/{urllib.parse.quote(pid)}/file?path={urllib.parse.quote(path_str)}"
    fp = Path(path_str) if Path(path_str).is_absolute() or pdir is None else pdir / path_str
    try:
        return f"{url}&v={int(fp.stat().st_mtime * 1000)}"
    except OSError:
        return url


def item_image_ref(pdir: Path, item: dict[str, Any], prep_item: dict[str, Any] | None) -> str:
    """Đường dẫn ảnh tốt nhất cho 1 mục (ưu tiên ảnh đã tách nền/sửa của người dùng)."""
    c = str(item.get("custom_image_path") or "")
    if prep_item and prep_item.get("image_file"):
        p = pdir / "anh" / "products" / str(prep_item["image_file"])
        same_source = not c or str(prep_item.get("source_image") or "") == c
        if p.is_file() and same_source:  # ảnh Bước 6 = đúng ảnh Remotion sẽ dùng
            return f"anh/products/{prep_item['image_file']}"
    if c and Path(c).is_file():
        return c
    return ""


def build_preview_data(pid: str, pdir: Path) -> dict[str, Any]:
    from media_ops import parse_script_outline
    from utils import read_json

    proj = read_json(pdir / "project.json", {}) or {}
    settings = proj.get("settings") or {}
    script_p = pdir / "text" / "kich_ban.md"
    script = script_p.read_text(encoding="utf-8") if script_p.is_file() else ""
    outline = parse_script_outline(script, current_title=str(proj.get("title") or ""))
    bang = read_json(pdir / "text" / "bang.json", {"items": []}) or {"items": []}
    prep = read_json(pdir / "text" / "products_prepared.json", {"items": []}) or {"items": []}
    prep_by_i = {int(x.get("i", 0)): x for x in prep.get("items", [])}
    items = []
    for idx, it in enumerate(bang.get("items") or []):
        i_num = int(it.get("i", idx + 1))
        ref = item_image_ref(pdir, it, prep_by_i.get(i_num))
        items.append({
            "i": i_num,
            "name": str(it.get("display_name") or it.get("ten") or ""),
            "bullets": list(it.get("bullets") or ([it["ghi_chu"]] if it.get("ghi_chu") else [])),
            "image_url": _file_url(pid, ref, pdir) if ref else "",
        })
    style = style_from_settings(settings)
    vp = str(proj.get("visual_prompt") or "")
    if vp:
        parsed = parse_visual_prompt(vp)
        if parsed["matched"]:
            for k in DEFAULT_STYLE:
                if parsed[k] != DEFAULT_STYLE[k]:
                    style[k] = parsed[k]
        style["matched"] = parsed["matched"]
    return {
        "ok": True,
        "project_id": pid,
        "title": str(proj.get("title") or outline.get("title") or ""),
        "subtitle": str(bang.get("subtitle") or outline.get("subtitle") or ""),
        "summary_subtitle": str(settings.get("summarySubtitle") or ""),
        "summary_note": str(settings.get("summaryNote") or ""),
        "preset": settings.get("preset", "giodo"),
        "outline_count": outline.get("count", 0),
        "items": items,
        "style": style,
        "visual_prompt": vp,
    }
