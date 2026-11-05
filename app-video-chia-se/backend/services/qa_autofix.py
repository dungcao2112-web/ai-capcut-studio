# -*- coding: utf-8 -*-
"""Tự sửa lỗi bố cục 1 chạm cho Auto-QA (qa-autofix).

- Đồng bộ lại bang.json theo kịch bản (preset Ảnh + Nhạc), GIỮ ảnh/khung cắt/tỉ lệ đã chỉnh theo tên mục
- Đánh số lại 1..N, chuẩn hoá con số trên tiêu đề (project.title, bang.tieu_de, dòng đầu kịch bản)
- Áp dụng lại visual_prompt -> settings (bgTheme, customBgColor, centerInfoPills...)
- Bật autoFitText (Remotion tự co chữ) khi tên/địa chỉ dài
- Chạy lại Bước 5 (timeline) + Bước 6 (storyboard ảnh) để mọi tầng khớp số mục
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

KEEP_KEYS = (
    "custom_image_path", "raw_image_path", "doctor_edit_mode", "doctor_crop_box", "is_doctor_cutout",
    "image_scale", "search_query", "web_image_query", "web_candidate_index", "web_image_source",
    "image_enhanced", "card_bg", "sl", "dv", "gia", "gia_text", "custom_label",
)


def _status(report: dict[str, Any], cid: str) -> str:
    return next((c["status"] for c in report["checks"] if c["id"] == cid), "pass")


def _fix_title_number(text: str, n: int) -> str:
    return re.sub(r"^(\s*(?:TOP\s+)?)(\d+)(\s+\S)", lambda m: f"{m.group(1)}{n}{m.group(3)}", text, count=1, flags=re.I)


def _rebuild_bang_from_outline(bang: dict[str, Any], outline: dict[str, Any], preset: str) -> dict[str, Any]:
    from services.qa_validator import _norm

    old = bang.get("items") or []
    by_name = {_norm(it.get("display_name") or it.get("ten") or ""): it for it in old}
    by_idx = {int(it.get("i", k + 1) or k + 1): it for k, it in enumerate(old)}
    used: set[int] = set()
    new_items = []
    for k, ent in enumerate(outline.get("entries") or [], start=1):
        heading = str(ent.get("heading") or "").strip()
        prev = by_name.get(_norm(heading))
        if prev is None or id(prev) in used:
            cand = by_idx.get(k)
            prev = cand if cand is not None and id(cand) not in used and _norm(cand.get("ten", "")) not in {
                _norm(e.get("heading", "")) for e in outline.get("entries") or []} else {}
        if prev:
            used.add(id(prev))
        bullets = list(ent.get("bullets") or []) or list(prev.get("bullets") or [])
        item = {"i": k, "nhom": 1, "ten": heading, "display_name": heading.upper(), "sl": 1, "dv": "Mục", "gia": 0,
                "ghi_chu": " | ".join(bullets) if bullets else str(prev.get("ghi_chu") or ""), "bullets": bullets}
        if preset == "anh_nhac":
            item.update({"no_price": True, "is_scene_photo": True})
        for key in KEEP_KEYS:
            if key in prev and prev[key] not in (None, ""):
                item[key] = prev[key]
        new_items.append(item)
    out = dict(bang)
    out["items"] = new_items
    return out


def apply_autofix(pid: str, pdir: Path, before: dict[str, Any], rerun_steps: bool = True) -> tuple[list[str], list[str]]:
    from pipeline import save_project_state
    from services.qa_validator import _load, title_number
    from services.visual_prompt import save_and_apply_visual_prompt
    from utils import write_json, write_text

    fixes: list[str] = []
    warnings: list[str] = []
    d = _load(pdir)
    proj, outline, bang = d["proj"], d["outline"], d["bang"]
    settings = proj.setdefault("settings", {})
    preset = settings.get("preset", "giodo")
    bang_changed = False

    # 1) Đồng bộ bang.json theo kịch bản (chỉ preset Ảnh + Nhạc: kịch bản = danh sách mục)
    if preset == "anh_nhac" and outline.get("count"):
        need = any(_status(before, c) != "pass" for c in ("count_consistency", "names_match", "index_sequence"))
        if need and (len(bang.get("items") or []) != outline["count"] or _status(before, "names_match") == "fail"
                     or _status(before, "index_sequence") != "pass"):
            bang = _rebuild_bang_from_outline(bang, outline, preset)
            bang_changed = True
            fixes.append(f"Đồng bộ bảng mục theo kịch bản: {outline['count']} mục (giữ nguyên ảnh đã gán theo tên)")
    # 2) Đánh số lại 1..N
    items = bang.get("items") or []
    if [int(it.get("i", 0) or 0) for it in items] != list(range(1, len(items) + 1)):
        for k, it in enumerate(items, start=1):
            it["i"] = k
        bang_changed = True
        fixes.append(f"Đánh số lại các mục 1..{len(items)}")

    # 3) Con số trên tiêu đề
    n = len(items) if preset != "anh_nhac" else int(outline.get("count") or len(items))
    title = str(proj.get("title") or outline.get("title") or "")
    tn = title_number(title)
    if tn is not None and n and tn != n:
        new_title = _fix_title_number(title, n)
        proj["title"] = new_title
        bang["tieu_de"] = _fix_title_number(str(bang.get("tieu_de") or new_title), n)
        bang_changed = True
        if d["script"].strip():
            lines = d["script"].splitlines()
            idx = next((k for k, ln in enumerate(lines) if ln.strip()), 0)
            m = re.match(r"^(\s*\d+[\.\)\-:]\s*)(.*)$", lines[idx])
            lines[idx] = (m.group(1) + _fix_title_number(m.group(2), n)) if m else _fix_title_number(lines[idx], n)
            write_text(pdir / "text" / "kich_ban.md", "\n".join(lines).rstrip() + "\n")
        fixes.append(f'Chuẩn hoá tiêu đề: "{title}" → "{new_title}"')

    # 4) Chữ dài -> bật tự co chữ trong Remotion
    if _status(before, "text_overflow") != "pass" and not settings.get("autoFitText"):
        settings["autoFitText"] = True
        fixes.append("Bật tự co chữ thông minh (autoFitText) cho tên/địa chỉ dài")

    if bang_changed:
        write_json(pdir / "text" / "bang.json", bang)
    save_project_state(pdir, proj)

    # 5) Áp dụng lại yêu cầu thiết kế (sau khi lưu project để không bị ghi đè)
    vp = str(proj.get("visual_prompt") or proj.get("final_revision_notes") or "")
    if vp and _status(before, "bg_theme_match") != "pass":
        res = save_and_apply_visual_prompt(pdir, vp, apply=True)
        if res.get("applied_settings"):
            fixes.append("Áp dụng lại yêu cầu thiết kế: " + ", ".join(res["changes"]))

    # 6) Dựng lại timeline + storyboard để mọi tầng khớp số mục
    stale = bang_changed or _status(before, "count_consistency") != "pass"
    if rerun_steps and stale:
        from pipeline import execute_step

        for step in ((5, 6) if preset == "anh_nhac" else (6,)):
            try:
                execute_step(pid, step, force_recompute=True, auto_approve=True)
                fixes.append(f"Chạy lại Bước {step} ({'Timeline' if step == 5 else 'Storyboard ảnh'})")
            except Exception as exc:
                warnings.append(f"Bước {step} chưa chạy được: {exc}"[:260])
    if _status(before, "images_present") == "fail":
        warnings.append("Còn mục thiếu ảnh — hãy tải ảnh lên hoặc bấm 'Tự tìm & Gắn Hình Ảnh'.")
    if _status(before, "image_quality") != "pass":
        warnings.append("Có ảnh độ phân giải thấp/rỗng — nên thay ảnh hoặc dùng '⚡ Tách nền & Làm nét Hàng Loạt'.")
    return fixes, warnings
