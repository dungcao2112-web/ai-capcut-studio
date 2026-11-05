# -*- coding: utf-8 -*-
"""Xử lý ảnh Bác sĩ / Sản phẩm theo dự án: làm nét 1 mục & ⚡ Tách nền + Làm nét Hàng Loạt."""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from services.image_enhancer import resolve_card_bg, safe_extract_doctor_subject_image

CUTOUT_MODES = ("cutout", "cutout_plain", "cutout_card", "crop_card")


def resolve_raw_image(pdir: Path, item: dict[str, Any], prep_by_i: dict[int, dict[str, Any]]) -> Path | None:
    """Tìm ảnh gốc của 1 mục (giống logic route edit-doctor-image) và lưu bản sao vào anh/doctor_raw/."""
    raw_dir = pdir / "anh" / "doctor_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    idx = int(item.get("i", 1))
    r_p = item.get("raw_image_path")
    if r_p and Path(r_p).is_file():
        return Path(r_p)
    for cand in sorted(raw_dir.glob(f"item_{idx:02d}_raw.*")):
        if cand.is_file():
            item["raw_image_path"] = str(cand)
            return cand
    candidates: list[Path] = []
    c_p = item.get("custom_image_path")
    if c_p and "doctor_edited" not in str(c_p):
        candidates.append(Path(c_p))
    pr = prep_by_i.get(idx, {})
    if pr.get("source_image") and "doctor_edited" not in str(pr["source_image"]):
        candidates.append(Path(pr["source_image"]))
    if pr.get("image_file"):
        candidates.append(pdir / "anh" / "products" / str(pr["image_file"]))
    for src in candidates:
        if src.is_file():
            dst = raw_dir / f"item_{idx:02d}_raw{src.suffix or '.png'}"
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)
            item["raw_image_path"] = str(dst)
            return dst
    return None


def _opts(options: dict[str, Any], item: dict[str, Any] | None = None) -> dict[str, Any]:
    mode = str(options.get("mode") or (item or {}).get("doctor_edit_mode") or "cutout")
    if mode not in CUTOUT_MODES:
        raise ValueError(f"Chế độ tách ảnh không hợp lệ: {mode}")
    card_bg = options.get("card_bg")
    if card_bg is not None:
        resolve_card_bg(card_bg)  # validate sớm, báo lỗi 400 nếu mã màu sai
    return {
        "mode": mode,
        "enhance": bool(options.get("enhance", True)),
        "enhance_strength": float(options.get("enhance_strength", 1.0)),
        "warm_tone": bool(options.get("warm_tone", True)),
        "card_bg": card_bg,
        "card_radius": int(options.get("card_radius", 40)),
    }


def _apply_result_to_item(item: dict[str, Any], out_path: Path, mode: str, res: dict[str, Any], o: dict[str, Any]) -> None:
    item["custom_image_path"] = str(out_path)
    item["doctor_edit_mode"] = mode
    item["doctor_crop_box"] = item.get("doctor_crop_box") or res.get("suggested_crop_box")
    item["is_scene_photo"] = True
    item["is_doctor_cutout"] = mode in ("cutout", "cutout_plain")
    item["image_enhanced"] = bool(o["enhance"])
    item["card_bg"] = res.get("card_bg")


def _rerun_step6(pid: str) -> str:
    try:
        from pipeline import execute_step

        execute_step(pid, 6, force_recompute=True, auto_approve=True)
        return ""
    except Exception as exc:  # Bước 6 có thể thiếu thư viện ảnh trên Cloud — không chặn kết quả
        return f"{type(exc).__name__}: {exc}"[:240]


def enhance_project_item(
    pid: str, pdir: Path, item_index: int, options: dict[str, Any], preview_only: bool = False
) -> dict[str, Any]:
    from utils import read_json, write_json

    bang = read_json(pdir / "text" / "bang.json", {"items": []}) or {"items": []}
    prep = read_json(pdir / "text" / "products_prepared.json", {"items": []}) or {"items": []}
    prep_by_i = {int(x.get("i", 0)): x for x in prep.get("items", [])}
    item = next((x for x in bang.get("items", []) if int(x.get("i", 0)) == int(item_index)), None)
    if item is None:
        return {"ok": False, "error": f"Không tìm thấy mục #{item_index}"}
    raw = resolve_raw_image(pdir, item, prep_by_i)
    if raw is None:
        return {"ok": False, "error": f"Mục #{item_index} chưa có ảnh gốc. Hãy tải ảnh lên trước!"}
    o = _opts(options, item)
    edited_dir = pdir / "anh" / "doctor_edited"
    name = f"preview_item_{item_index:02d}.png" if preview_only else f"item_{item_index:02d}_doctor.png"
    out = edited_dir / name
    crop_box = options.get("crop_box", item.get("doctor_crop_box"))
    res = safe_extract_doctor_subject_image(raw, out, crop_box=crop_box, **o)
    step6_err = ""
    if not preview_only:
        _apply_result_to_item(item, out, o["mode"], res, o)
        write_json(pdir / "text" / "bang.json", bang)
        step6_err = _rerun_step6(pid)
    else:
        write_json(pdir / "text" / "bang.json", bang)  # lưu raw_image_path vừa tìm được
    return {
        "ok": True,
        "item_index": int(item_index),
        "preview_only": preview_only,
        "result": res,
        "raw_rel": f"anh/doctor_raw/{raw.name}",
        "edited_rel": f"anh/doctor_edited/{out.name}",
        "step6_warning": step6_err,
    }


def batch_process_project(pid: str, pdir: Path, options: dict[str, Any]) -> dict[str, Any]:
    """⚡ Tách nền & Làm nét Hàng Loạt cho toàn bộ ảnh đã tải lên (6–10 ảnh / 1 nút bấm)."""
    from utils import read_json, write_json

    t0 = time.time()
    bang = read_json(pdir / "text" / "bang.json", {"items": []}) or {"items": []}
    prep = read_json(pdir / "text" / "products_prepared.json", {"items": []}) or {"items": []}
    prep_by_i = {int(x.get("i", 0)): x for x in prep.get("items", [])}
    o = _opts(options)
    keep_manual_crop = bool(options.get("keep_manual_crop", True))
    edited_dir = pdir / "anh" / "doctor_edited"
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in bang.get("items", []):
        idx = int(item.get("i", 1))
        raw = resolve_raw_image(pdir, item, prep_by_i)
        label = str(item.get("display_name") or item.get("ten") or f"Mục {idx}")
        if raw is None:
            skipped.append({"i": idx, "name": label, "reason": "Chưa có ảnh gốc"})
            continue
        out = edited_dir / f"item_{idx:02d}_doctor.png"
        crop = item.get("doctor_crop_box") if keep_manual_crop else None
        try:
            res = safe_extract_doctor_subject_image(raw, out, crop_box=crop, **o)
        except Exception as exc:
            skipped.append({"i": idx, "name": label, "reason": f"Lỗi xử lý: {exc}"[:200]})
            continue
        _apply_result_to_item(item, out, o["mode"], res, o)
        results.append(
            {
                "i": idx,
                "name": label,
                "engine": res.get("engine"),
                "person_detected": res.get("person_detected"),
                "sharpness_before": res.get("sharpness_before"),
                "sharpness_after": res.get("sharpness_after"),
                "edited_rel": f"anh/doctor_edited/{out.name}",
            }
        )
    write_json(pdir / "text" / "bang.json", bang)
    step6_err = _rerun_step6(pid) if results else ""
    return {
        "ok": True,
        "mode": o["mode"],
        "enhance": o["enhance"],
        "card_bg": resolve_card_bg(o["card_bg"]) if o["card_bg"] is not None else None,
        "processed_count": len(results),
        "skipped": skipped,
        "results": results,
        "elapsed_sec": round(time.time() - t0, 2),
        "step6_warning": step6_err,
    }
