# -*- coding: utf-8 -*-
"""Tự động áp dụng cho TẤT CẢ mục ngay từ Bước 1 (không phải làm tay ở Bước 3):

- 🧩 Mẫu ghép ảnh chung (settings.collageLayout: "1" = 1 ảnh, "2-ngang", "4-luoi", ...) + nền/viền
- 🔗 Link nguồn (settings.sourceLinks): ưu tiên ẢNH & THÔNG TIN từ các link sếp dán; thiếu thì tự tìm web
- 📝 settings.autoInfoFromSources: mục chưa có mô tả => lấy 1 câu thông tin từ nguồn làm mô tả

Được gọi tự động sau "🔍 Tự tìm & Gắn Hình Ảnh" (media_ops.parse_and_fetch_anh_nhac_list) và từ nút
"🧩 Áp dụng cho các mục hiện có" (POST /api/projects/<pid>/auto-media).
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PIL import Image


FALLBACK_LAYOUT = {1: "1", 2: "2-ngang", 3: "3-1lon2nho", 4: "4-luoi", 5: "4-luoi"}


def media_settings(proj: dict[str, Any]) -> dict[str, Any]:
    s = proj.get("settings") or {}
    links = [str(u) for u in (s.get("sourceLinks") or []) if str(u).startswith(("http://", "https://"))]
    return {"layout": str(s.get("collageLayout") or "1"), "style": dict(s.get("collageStyle") or {}),
            "links": links, "auto_info": bool(s.get("autoInfoFromSources", True)),
            "template": str(s.get("infoTemplate") or ""), "ai_with_sources": bool(s.get("aiWithSources", True))}


def web_candidate(name: str, title: str, out_path: Path, cand: int) -> Path | None:
    """1 ảnh web (bản gốc chưa cắt) cho mục. Tách riêng để kiểm thử có thể thay thế khi không có mạng."""
    from media_ops import download_web_image_for_item

    dl = download_web_image_for_item(item_name=name, project_title=title, out_path=out_path, candidate_index=cand)
    if not dl.get("ok"):
        return None
    p = Path(dl.get("original_path") or dl["path"])
    return p if p.is_file() else None


def _current_original(item: dict[str, Any]) -> Path | None:
    from services.item_media import GENERATED_DIRS, original_of

    for key in ("base_image_path", "custom_image_path", "image_source_path", "raw_image_path"):
        v = str(item.get(key) or "")
        if v and Path(v).is_file() and not any(d in Path(v).parts for d in GENERATED_DIRS):
            return original_of(v)
    return None


def process_item(pdir: Path, item: dict[str, Any], k: int, n: int, cfg: dict[str, Any],
                 sources: list[dict[str, Any]], title: str) -> dict[str, Any]:
    from services.photo_frame import DEFAULT_STYLE, LAYOUTS, compose_collage
    from services.smart_crop import fit_score
    from services.source_info import template_for_item
    from services.source_links import download_image, images_for_item

    idx = int(item.get("i", k + 1))
    name = str(item.get("ten") or item.get("display_name") or "").strip()
    rep: dict[str, Any] = {"i": idx, "name": name, "from_sources": 0, "from_web": 0, "layout": cfg["layout"]}
    need = len(LAYOUTS.get(cfg["layout"], LAYOUTS["1"])[1])
    if not item.get("base_image_path"):  # nhớ ảnh gốc ban đầu của mục => áp dụng lại nhiều lần vẫn ổn định
        base = _current_original(item)
        if base:
            item["base_image_path"] = str(base)
    pool: list[tuple[Path, bool]] = []  # (ảnh gốc, từ nguồn?)
    if sources:
        for j, cand in enumerate(images_for_item(name, k, n, sources, limit=need + 2)):
            p = download_image(cand["url"], pdir / "anh" / "gallery" / f"item_{idx:02d}_src{j}.png")
            if p:
                pool.append((p, True))
                item.setdefault("image_source_urls", []).append(cand["url"])
            if len(pool) >= need:
                break
        info, desc = template_for_item(name, sources, cfg["template"])
        info["template_bullets"] = desc
        item["source_info"] = info
        rep["facts"] = len(info["facts"])
        rep["snippets"] = len(info["snippets"])
        # Chỉ điền cho mục CHƯA có mô tả (mô tả sếp viết không bao giờ bị ghi đè); mô tả lấy tự động thì được làm mới
        # (mô tả do Agy CLI viết theo mẫu được giữ — chỉ làm mới mô tả do app tự điền)
        if cfg["auto_info"] and (not item.get("bullets") or (item.get("bullets_from_sources") and item.get("bullets_source") != "ai")):
            if desc:
                item["bullets"] = desc
                item["ghi_chu"] = " | ".join(desc)
                item["bullets_from_sources"] = True
                rep["info_added"] = desc
    rep["from_sources"] = len(pool)
    cur = _current_original(item)
    if cur and all(cur != p for p, _ in pool) and len(pool) < need:
        pool.append((cur, False))
    tries = 0
    while len(pool) < need and tries < need + 2:
        tries += 1
        p = web_candidate(name, title, pdir / "anh" / "gallery" / f"item_{idx:02d}_web{tries}.png", tries)
        if p and all(p != q for q, _ in pool):
            pool.append((p, False))
            rep["from_web"] += 1
    if not pool:
        rep["status"] = "Không có ảnh"
        return rep
    layout = cfg["layout"]
    if len(pool) < need:  # không đủ ảnh => tự đổi sang bố cục vừa số ảnh (không để ô trống trên video)
        layout = FALLBACK_LAYOUT.get(len(pool), "1")
        rep["layout"] = layout
        rep["note"] = f"Chỉ tìm được {len(pool)}/{need} ảnh — tự đổi sang bố cục {len(pool)} ảnh"
        need = len(LAYOUTS[layout][1])
    if need == 1:
        item["custom_image_path"] = str(pool[0][0])
        item["image_source_path"] = str(pool[0][0])
        item.update({"is_scene_photo": True, "collage_layout": "1"})
        rep["status"] = "Ảnh nguồn" if pool[0][1] else "Giữ ảnh hiện tại"
        return rep
    ratio, cells = LAYOUTS[layout]
    big_aspect = (cells[0][2] * ratio) / cells[0][3]
    src_first = [p for p, s in pool if s]
    def _score(path: Path) -> float:
        with Image.open(path) as im:
            return fit_score(im, big_aspect)

    others = sorted((p for p, s in pool if not s), key=lambda p: -_score(p))
    ordered = (src_first + others)[:need]
    images = []
    for p in ordered:
        with Image.open(p) as im:
            images.append(im.convert("RGB"))
    style = dict(DEFAULT_STYLE, **cfg["style"])
    canvas, infos = compose_collage(images, layout, style)
    out = pdir / "anh" / "framed" / f"item_{idx:02d}_collage_{int(time.time() * 1000)}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    for old in out.parent.glob(f"item_{idx:02d}_*.png"):
        old.unlink(missing_ok=True)
    canvas.save(out)
    item.update({"custom_image_path": str(out), "is_scene_photo": True, "is_doctor_cutout": False,
                 "collage_layout": layout, "collage_style": style, "image_source_path": str(ordered[0]),
                 "gallery": [{"path": str(p), "crop_box": None} for p in ordered]})
    rep["status"] = f"Ghép {len(ordered)}/{need} ảnh"
    rep["modes"] = [i["mode"] for i in infos]
    return rep


def apply_to_bang(pdir: Path, bang: dict[str, Any], proj: dict[str, Any], refresh_sources: bool = False) -> dict[str, Any]:
    from services.source_links import load_sources

    cfg = media_settings(proj)
    sources = load_sources(pdir, cfg["links"], refresh=refresh_sources) if cfg["links"] else []
    items = bang.get("items") or []
    title = str(proj.get("title") or bang.get("tieu_de") or "")
    with ThreadPoolExecutor(max_workers=4) as ex:
        reports = list(ex.map(lambda kv: process_item(pdir, kv[1], kv[0], len(items), cfg, sources, title), enumerate(items)))
    return {"layout": cfg["layout"], "links": len(cfg["links"]), "items": reports,
            "sources": [{"url": s["url"], "ok": s.get("ok"), "title": s.get("title", ""), "images": len(s.get("images") or []),
                         "error": s.get("error", "")} for s in sources]}


def apply_after_fetch(pdir: Path, result: dict[str, Any]) -> dict[str, Any]:
    """Sau khi tự tìm ảnh xong: áp mẫu ghép + nguồn link (nếu sếp đã chọn ở Bước 1)."""
    from utils import read_json, write_json

    proj = read_json(pdir / "project.json", {}) or {}
    cfg = media_settings(proj)
    if cfg["layout"] == "1" and not cfg["links"]:
        return result
    bang = result.get("bang") or read_json(pdir / "text" / "bang.json", {"items": []})
    report = apply_to_bang(pdir, bang, proj)
    write_json(pdir / "text" / "bang.json", bang)
    result["bang"] = bang
    result["auto_media"] = report
    return result


def apply_project_media(pid: str, pdir: Path, refresh_sources: bool = False) -> dict[str, Any]:
    """Nút '🧩 Áp dụng cho các mục hiện có': dùng ảnh đang có + tìm thêm, rồi chạy lại Bước 6."""
    from pipeline import execute_step
    from utils import read_json, write_json

    proj = read_json(pdir / "project.json", {}) or {}
    bang = read_json(pdir / "text" / "bang.json", {"items": []}) or {"items": []}
    if not bang.get("items"):
        raise ValueError("Chưa có mục nào — hãy dán kịch bản và bấm 'Tự tìm & Gắn Hình Ảnh' trước.")
    report = apply_to_bang(pdir, bang, proj, refresh_sources=refresh_sources)
    write_json(pdir / "text" / "bang.json", bang)
    try:
        execute_step(pid, 6, force_recompute=True, auto_approve=True)
    except Exception as exc:
        report["step6_warning"] = f"Bước 6 chưa chạy được: {exc}"[:240]
    return report
