# -*- coding: utf-8 -*-
"""Bổ sung thông tin hiển thị cho danh sách dự án (badge số mục, nhãn preset, số người).
Chỉ THÊM trường mới vào từng phần tử của /api/projects — không đổi trường cũ."""
from __future__ import annotations

from typing import Any

PRESET_LABELS = {
    "giodo": "Giỏ đồ",
    "chiase": "Chia sẻ",
    "anh_nhac": "Ảnh + Nhạc",
}


def _count_items(pdir) -> int:
    from utils import read_json

    bang = read_json(pdir / "text" / "bang.json", {}) or {}
    items = bang.get("items") or []
    if items:
        return len(items)
    script_p = pdir / "text" / "kich_ban.md"
    if script_p.is_file():
        try:
            from media_ops import parse_script_outline

            return int(parse_script_outline(script_p.read_text(encoding="utf-8")).get("count") or 0)
        except Exception:
            return 0
    return 0


def enrich_projects(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from pipeline import get_projects_root
    from utils import read_json

    root = get_projects_root()
    for p in projects:
        pdir = root / str(p.get("id", ""))
        try:
            proj = read_json(pdir / "project.json", {}) or {}
        except Exception:
            proj = {}
        preset = p.get("preset") or "giodo"
        has_two_people = bool(proj.get("clip_a_source") and proj.get("clip_b_source"))
        try:
            item_count = _count_items(pdir)
        except Exception:
            item_count = 0
        p["item_count"] = item_count
        p["preset_label"] = PRESET_LABELS.get(preset, preset)
        p["people_label"] = "2 người" if (has_two_people or preset in ("giodo", "chiase")) else "Không voice"
        p["is_demo"] = str(p.get("id", "")).endswith("-demo")
        p["bg_theme"] = (proj.get("settings") or {}).get("bgTheme", "beige")
    return projects
