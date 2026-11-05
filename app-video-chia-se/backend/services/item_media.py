# -*- coding: utf-8 -*-
"""Ảnh theo từng mục: 🖼️ Chọn khung hình (cắt theo ý sếp) & 🧩 Ghép nhiều ảnh (bố cục 2/3/4/6).

Ảnh gốc KHÔNG bị ghi đè: ảnh đã đóng khung lưu ở anh/framed/, ảnh từng ô ghép lưu ở anh/gallery/.
bang.json mỗi mục có thêm: image_source_path, image_crop_box, image_aspect, collage_layout, gallery[].
"""
from __future__ import annotations

import time
import urllib.parse
from pathlib import Path
from typing import Any

from PIL import Image

GENERATED_DIRS = ("doctor_edited", "framed", "collage")


def _file_url(pid: str, path: str) -> str:
    return f"/api/projects/{urllib.parse.quote(pid)}/file?path={urllib.parse.quote(str(path))}&t={int(time.time())}"


def _load(pdir: Path) -> dict[str, Any]:
    from utils import read_json

    return read_json(pdir / "text" / "bang.json", {"items": []}) or {"items": []}


def _item(bang: dict[str, Any], idx: int) -> dict[str, Any]:
    it = next((x for x in bang.get("items", []) if int(x.get("i", 0)) == int(idx)), None)
    if it is None:
        raise ValueError(f"Không tìm thấy mục #{idx}")
    return it


def resolve_source(pdir: Path, item: dict[str, Any]) -> Path | None:
    """Ảnh gốc để chọn khung: ảnh mới nhất người dùng/web gán (không phải ảnh do app tạo ra)."""
    from utils import read_json

    cands: list[str] = []
    c = str(item.get("custom_image_path") or "")
    if c and not any(f"{d}" in Path(c).parts for d in GENERATED_DIRS):
        cands.append(c)
    cands += [str(item.get("image_source_path") or ""), str(item.get("raw_image_path") or "")]
    prep = read_json(pdir / "text" / "products_prepared.json", {"items": []}) or {"items": []}
    pr = next((x for x in prep.get("items", []) if int(x.get("i", 0)) == int(item.get("i", 0))), {})
    cands.append(str(pr.get("source_image") or ""))
    if pr.get("image_file"):
        cands.append(str(pdir / "anh" / "products" / str(pr["image_file"])))
    for s in cands:
        if s and Path(s).is_file() and not any(d in Path(s).parts for d in GENERATED_DIRS):
            return Path(s)
    return None


def _safe_path(pdir: Path, item: dict[str, Any], path: str) -> Path:
    """Chỉ cho dùng file trong thư mục dự án hoặc file đã gắn với mục này (chống đọc file tuỳ ý)."""
    p = Path(path)
    known = {str(item.get(k) or "") for k in ("custom_image_path", "image_source_path", "raw_image_path")}
    known |= {str(s.get("path") or "") for s in item.get("gallery") or []}
    try:
        inside = p.resolve().is_relative_to(pdir.resolve())
    except (OSError, ValueError):
        inside = False
    if not p.is_file() or not (inside or str(p) in known):
        raise ValueError(f"Ảnh không hợp lệ cho mục này: {path}")
    return p


def item_media_info(pid: str, pdir: Path, idx: int) -> dict[str, Any]:
    from services.photo_frame import layouts_payload

    it = _item(_load(pdir), idx)
    src = resolve_source(pdir, it)
    gallery = []
    for s in it.get("gallery") or []:
        ok = s.get("path") and Path(str(s["path"])).is_file()
        gallery.append({"path": s.get("path") if ok else "", "crop_box": s.get("crop_box"),
                        "url": _file_url(pid, s["path"]) if ok else ""})
    size = None
    if src:
        with Image.open(src) as im:
            size = list(im.size)
    return {"ok": True, "item_index": idx, "name": it.get("display_name") or it.get("ten") or "",
            "source_path": str(src) if src else "", "source_url": _file_url(pid, str(src)) if src else "",
            "source_size": size, "crop_box": it.get("image_crop_box"), "aspect": it.get("image_aspect") or "free",
            "layout": it.get("collage_layout") or "1", "gallery": gallery, "layouts": layouts_payload()}


def _save_and_apply(pid: str, pdir: Path, bang: dict[str, Any], it: dict[str, Any], canvas: Image.Image, name: str) -> dict[str, Any]:
    from utils import write_json

    out = pdir / "anh" / "framed" / f"item_{int(it['i']):02d}_{name}_{int(time.time())}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    for old in out.parent.glob(f"item_{int(it['i']):02d}_*.png"):
        old.unlink(missing_ok=True)  # chỉ giữ bản mới nhất của mục này
    canvas.save(out)
    it["custom_image_path"] = str(out)
    it["is_scene_photo"] = True
    it["is_doctor_cutout"] = False
    write_json(pdir / "text" / "bang.json", bang)
    warn = ""
    try:
        from pipeline import execute_step

        execute_step(pid, 6, force_recompute=True, auto_approve=True)
    except Exception as exc:
        warn = f"Bước 6 chưa chạy được: {exc}"[:240]
    return {"ok": True, "item_index": int(it["i"]), "output_url": _file_url(pid, str(out)), "step6_warning": warn}


def frame_item(pid: str, pdir: Path, idx: int, crop_box: list[float] | None, aspect: str = "free") -> dict[str, Any]:
    """🖼️ Chọn khung hình: cắt ảnh gốc theo vùng sếp chọn, đóng thẻ đúng tỉ lệ đó."""
    from services.photo_frame import ASPECTS, frame_photo

    if aspect not in ASPECTS:
        raise ValueError(f"Tỉ lệ không hợp lệ: {aspect}")
    bang = _load(pdir)
    it = _item(bang, idx)
    src = resolve_source(pdir, it)
    if src is None:
        raise ValueError(f"Mục #{idx} chưa có ảnh. Hãy tải ảnh hoặc tự tìm ảnh trước.")
    with Image.open(src) as im:
        canvas = frame_photo(im, crop_box, aspect)
    it.update({"image_source_path": str(src), "image_crop_box": crop_box, "image_aspect": aspect, "collage_layout": "1"})
    return _save_and_apply(pid, pdir, bang, it, canvas, "frame")


def set_gallery(pid: str, pdir: Path, idx: int, layout: str, slots: list[dict[str, Any]]) -> dict[str, Any]:
    """🧩 Ghép nhiều ảnh: slots = [{path, crop_box}] theo thứ tự ô của bố cục."""
    from services.photo_frame import LAYOUTS, apply_crop, compose_collage

    if layout not in LAYOUTS:
        raise ValueError(f"Bố cục không hợp lệ: {layout}")
    bang = _load(pdir)
    it = _item(bang, idx)
    n = len(LAYOUTS[layout][1])
    clean, images = [], []
    for s in (slots or [])[:n]:
        path = str((s or {}).get("path") or "")
        if not path:
            clean.append({"path": "", "crop_box": None})
            images.append(None)
            continue
        p = _safe_path(pdir, it, path)
        with Image.open(p) as im:
            images.append(apply_crop(im.convert("RGB"), s.get("crop_box")))
        clean.append({"path": str(p), "crop_box": s.get("crop_box")})
    if not any(images):
        raise ValueError("Chưa có ảnh nào trong các ô ghép.")
    canvas = compose_collage(images, layout)
    it.update({"collage_layout": layout, "gallery": clean})
    res = _save_and_apply(pid, pdir, bang, it, canvas, "collage")
    res["filled_slots"] = sum(1 for x in images if x is not None)
    res["total_slots"] = n
    return res


def save_slot_upload(pid: str, pdir: Path, idx: int, slot: int, filename: str, raw: bytes) -> dict[str, Any]:
    from utils import write_json

    if not raw:
        raise ValueError("Dữ liệu ảnh tải lên trống.")
    ext = (Path(filename).suffix.lower() or ".png")[:6]
    out = pdir / "anh" / "gallery" / f"item_{idx:02d}_slot{slot}_{int(time.time() * 1000)}{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    try:
        with Image.open(out) as im:
            im.verify()
    except Exception:
        out.unlink(missing_ok=True)
        raise ValueError("File tải lên không phải ảnh hợp lệ.")
    bang = _load(pdir)
    it = _item(bang, idx)
    gal = list(it.get("gallery") or [])
    while len(gal) <= slot:
        gal.append({"path": "", "crop_box": None})
    gal[slot] = {"path": str(out), "crop_box": None}
    it["gallery"] = gal
    write_json(pdir / "text" / "bang.json", bang)
    return {"ok": True, "slot": slot, "path": str(out), "url": _file_url(pid, str(out))}


def fetch_slot_web(pid: str, pdir: Path, idx: int, slot: int, candidate_index: int, custom_query: str = "") -> dict[str, Any]:
    from media_ops import download_web_image_for_item
    from utils import read_json, write_json

    bang = _load(pdir)
    it = _item(bang, idx)
    proj = read_json(pdir / "project.json", {}) or {}
    out = pdir / "anh" / "gallery" / f"item_{idx:02d}_slot{slot}_web{candidate_index}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    dl = download_web_image_for_item(item_name=str(it.get("display_name") or it.get("ten") or ""),
                                     project_title=str(proj.get("title") or ""), out_path=out,
                                     candidate_index=int(candidate_index), custom_query=custom_query)
    if not dl.get("ok") or not dl.get("path"):
        return {"ok": False, "error": dl.get("error") or "Không tải được ảnh web (kiểm tra kết nối mạng)."}
    gal = list(it.get("gallery") or [])
    while len(gal) <= slot:
        gal.append({"path": "", "crop_box": None})
    gal[slot] = {"path": str(dl["path"]), "crop_box": None}
    it["gallery"] = gal
    write_json(pdir / "text" / "bang.json", bang)
    return {"ok": True, "slot": slot, "path": str(dl["path"]), "url": _file_url(pid, str(dl["path"]))}
