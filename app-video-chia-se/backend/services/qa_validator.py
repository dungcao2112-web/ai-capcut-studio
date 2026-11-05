# -*- coding: utf-8 -*-
"""Auto-QA Engine: kiểm định 10 tiêu chí trước khi xuất video + tự sửa lỗi bố cục 1 chạm.

Đối chiếu xuyên suốt: kịch bản gốc (kich_ban.md) -> script_outline -> bang.json -> storyboard
(text/products_prepared.json, hoặc text/storyboard.json nếu có) -> thư mục ảnh anh/products/ ->
timeline (media/timeline.json itemMarks) -> Bảng Tổng Hợp cuối video (= danh sách products Remotion).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

MAX_NAME_CHARS = 38
MAX_BULLET_CHARS = 70
MIN_IMAGE_SIDE = 400


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower()).replace("đ", "d")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def title_number(title: str) -> int | None:
    m = re.match(r"^\s*(?:TOP\s+)?(\d+)\s+\S", str(title or ""), flags=re.I)
    return int(m.group(1)) if m else None


def outline_warnings(outline: dict[str, Any]) -> list[dict[str, Any]]:
    """Cảnh báo cho kết quả parse_script_outline (đồng bộ với frontend script_inspector_pro.js)."""
    entries = outline.get("entries") or []
    n = len(entries)
    out: list[dict[str, Any]] = []
    if not n:
        return [{"level": "error", "code": "empty", "message": "Chưa nhận diện được mục nào trong kịch bản."}]
    tn = title_number(outline.get("title", ""))
    if tn is not None and tn != n:
        out.append({"level": "error", "code": "title_count", "fixable": True,
                    "message": f'Tiêu đề ghi "{tn}" nhưng danh sách thực tế có {n} mục.'})
    with_b = [e for e in entries if e.get("bullets")]
    if with_b and len(with_b) < n:
        miss = [str(k + 1) for k, e in enumerate(entries) if not e.get("bullets")]
        out.append({"level": "warning", "code": "missing_bullets",
                    "message": f"Mục {', '.join(miss)} thiếu dòng mô tả/địa chỉ (các mục khác đều có)."})
    seen: dict[str, int] = {}
    for k, e in enumerate(entries, start=1):
        key = _norm(e.get("heading", ""))
        if key in seen:
            out.append({"level": "warning", "code": "duplicate", "message": f"Mục {seen[key]} và {k} trùng tên."})
        seen.setdefault(key, k)
        if len(str(e.get("heading", ""))) > MAX_NAME_CHARS:
            out.append({"level": "warning", "code": "long_name", "message": f"Tên mục {k} dài — video sẽ tự co chữ."})
        for b in e.get("bullets") or []:
            if len(b) > MAX_BULLET_CHARS:
                out.append({"level": "warning", "code": "long_bullet", "message": f"Mô tả mục {k} dài {len(b)} ký tự (nên ≤ {MAX_BULLET_CHARS})."})
    return out


def _load(pdir: Path) -> dict[str, Any]:
    from media_ops import parse_script_outline
    from utils import read_json

    proj = read_json(pdir / "project.json", {}) or {}
    script_p = pdir / "text" / "kich_ban.md"
    script = script_p.read_text(encoding="utf-8") if script_p.is_file() else ""
    outline = parse_script_outline(script, current_title=str(proj.get("title") or ""))
    bang = read_json(pdir / "text" / "bang.json", {"items": []}) or {"items": []}
    story = read_json(pdir / "text" / "storyboard.json") or read_json(pdir / "text" / "products_prepared.json")
    timeline = read_json(pdir / "media" / "timeline.json")
    return {"proj": proj, "script": script, "outline": outline, "bang": bang, "story": story, "timeline": timeline}


def _check(cid: str, name: str, status: str, detail: str, fixable: bool = False) -> dict[str, Any]:
    return {"id": cid, "name": name, "status": status, "detail": detail, "fixable": fixable and status != "pass"}


def _image_info(path: Path) -> tuple[int, int, float] | None:
    try:
        import numpy as np
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
            rgba = im.convert("RGBA").resize((64, 64))
            arr = np.asarray(rgba, dtype=np.float32)
            visible = arr[..., 3] > 20
            std = float(arr[..., :3][visible].std()) if visible.any() else 0.0
            return w, h, std
    except Exception:
        return None


def run_qa_check(pdir: Path) -> dict[str, Any]:
    from services.visual_prompt import parse_visual_prompt

    d = _load(pdir)
    proj, outline, bang = d["proj"], d["outline"], d["bang"]
    settings = proj.get("settings") or {}
    preset = settings.get("preset", "giodo")
    items = bang.get("items") or []
    story_items = (d["story"] or {}).get("items") if d["story"] else None
    marks = (d["timeline"] or {}).get("itemMarks") if d["timeline"] else None
    n_script = int(outline.get("count") or 0) if preset == "anh_nhac" else len(items)
    counts = {"script": n_script, "bang": len(items), "storyboard": None if story_items is None else len(story_items),
              "timeline": None if marks is None else len(marks), "summary": None if story_items is None else len(story_items)}
    checks: list[dict[str, Any]] = []

    checks.append(_check("script_items", "Kịch bản có danh sách mục", "pass" if n_script else "fail",
                         f"Nhận diện {n_script} mục từ {'kịch bản' if preset == 'anh_nhac' else 'bảng sản phẩm'}."))
    known = {k: v for k, v in counts.items() if v is not None}
    same = len(set(known.values())) == 1
    missing_stage = [k for k, v in counts.items() if v is None]
    status = "fail" if not same else ("warn" if missing_stage else "pass")
    labels = {"script": "Kịch bản", "bang": "Bảng mục", "storyboard": "Storyboard", "timeline": "Timeline", "summary": "Bảng Tổng Hợp"}
    detail = (" = " if same else " ≠ ").join(f"{labels[k]} {v}" for k, v in known.items())
    if missing_stage:
        detail += f" (chưa có: {', '.join(missing_stage)} — cần chạy Bước 5/6)"
    checks.append(_check("count_consistency", "Số mục khớp xuyên suốt Kịch bản → Storyboard → Bảng Tổng Hợp", status, detail, True))

    title = str(proj.get("title") or outline.get("title") or "")
    tn = title_number(title)
    checks.append(_check("title_count", "Con số trên tiêu đề khớp số mục",
                         "pass" if tn is None or tn == n_script else "fail",
                         f'Tiêu đề "{title}"' + (f" ghi {tn}, thực tế {n_script} mục." if tn is not None else " (không ghi số)."), True))

    idxs = [int(it.get("i", 0) or 0) for it in items]
    seq_ok = idxs == list(range(1, len(items) + 1))
    names = [_norm(it.get("display_name") or it.get("ten") or "") for it in items]
    dup = len(set(names)) != len(names)
    checks.append(_check("index_sequence", "Đánh số mục 1..N liên tục, không trùng tên",
                         "pass" if seq_ok and not dup else ("fail" if not seq_ok else "warn"),
                         f"Thứ tự hiện tại: {idxs[:12]}" + (" • Có mục trùng tên" if dup else ""), True))

    if preset == "anh_nhac" and outline.get("entries"):
        heads = [_norm(e["heading"]) for e in outline["entries"]]
        bad = [str(k + 1) for k, (a, b) in enumerate(zip(heads, names)) if a != b]
        clean = lambda xs: [str(x).strip() for x in (xs or []) if str(x).strip()]  # noqa: E731
        bul_bad = [str(k + 1) for k, (e, it) in enumerate(zip(outline["entries"], items))
                   if clean(e.get("bullets")) and clean(e.get("bullets")) != clean(it.get("bullets"))]
        st = "fail" if bad or len(heads) != len(names) else ("warn" if bul_bad else "pass")
        detail = "Khớp 100% (tên & mô tả)." if st == "pass" else (
            f"Lệch tên ở mục: {', '.join(bad) or 'số lượng'}" if st == "fail" else f"Mô tả/địa chỉ lệch kịch bản ở mục: {', '.join(bul_bad)}")
        checks.append(_check("names_match", "Tên mục & mô tả trong bảng khớp kịch bản", st, detail, True))
    else:
        checks.append(_check("names_match", "Tên mục trong bảng khớp kịch bản", "pass", "Preset dùng bảng sản phẩm làm chuẩn."))

    prep_by_i = {int(x.get("i", 0)): x for x in (story_items or [])}
    no_img, low_res, blank = [], [], []
    for it in items:
        i_num = int(it.get("i", 0) or 0)
        cands = []
        if prep_by_i.get(i_num, {}).get("image_file"):
            cands.append(pdir / "anh" / "products" / str(prep_by_i[i_num]["image_file"]))
        if it.get("custom_image_path"):
            cands.append(Path(str(it["custom_image_path"])))
        path = next((c for c in cands if c.is_file()), None)
        if path is None:
            no_img.append(str(i_num))
            continue
        info = _image_info(path)
        if info is None or info[2] < 4.0:
            blank.append(str(i_num))
        elif min(info[0], info[1]) < MIN_IMAGE_SIDE:
            low_res.append(f"{i_num} ({info[0]}×{info[1]})")
    checks.append(_check("images_present", "Mọi mục đều có file ảnh", "pass" if not no_img else "fail",
                         "Đủ ảnh." if not no_img else f"Thiếu ảnh mục: {', '.join(no_img)} — cần tải ảnh / tự tìm ảnh"))
    checks.append(_check("image_quality", f"Ảnh hợp lệ, cạnh ngắn ≥ {MIN_IMAGE_SIDE}px, không rỗng",
                         "fail" if blank else ("warn" if low_res else "pass"),
                         "; ".join(x for x in (f"Ảnh rỗng/lỗi: {', '.join(blank)}" if blank else "",
                                               f"Độ phân giải thấp: {', '.join(low_res)}" if low_res else "") if x) or "Đạt chuẩn."))

    long_names = [str(it.get("i")) for it in items if len(str(it.get("display_name") or it.get("ten") or "")) > MAX_NAME_CHARS]
    long_b = [str(it.get("i")) for it in items for b in (it.get("bullets") or []) if len(str(b)) > MAX_BULLET_CHARS]
    many_b = [str(it.get("i")) for it in items if len(it.get("bullets") or []) > 3]
    over = bool(long_b or many_b)
    checks.append(_check("text_overflow", "Tên / địa chỉ / bullet không tràn khung",
                         "warn" if (over or long_names) else "pass",
                         "; ".join(x for x in (f"Tên dài (tự co chữ): {', '.join(long_names)}" if long_names else "",
                                               f"Bullet > {MAX_BULLET_CHARS} ký tự: {', '.join(sorted(set(long_b)))}" if long_b else "",
                                               f"> 3 bullet: {', '.join(many_b)}" if many_b else "") if x) or "Gọn trong khung.", True))

    with_b = [it for it in items if it.get("bullets")]
    cons = not with_b or len(with_b) == len(items)
    checks.append(_check("bullets_consistency", "Các mục đều có (hoặc đều không có) dòng mô tả/địa chỉ",
                         "pass" if cons else "warn",
                         "Đồng nhất." if cons else f"{len(items) - len(with_b)} mục thiếu mô tả trong khi {len(with_b)} mục có."))

    vp = str(proj.get("visual_prompt") or proj.get("final_revision_notes") or "")
    style = parse_visual_prompt(vp)
    mism = []
    if style["matched"]:
        if any(x.startswith(("Nền", "Tông")) for x in style["matched"]):
            if settings.get("bgTheme", "beige") != style["bgTheme"]:
                mism.append(f"bgTheme={settings.get('bgTheme', 'beige')} (cần {style['bgTheme']})")
            if str(settings.get("customBgColor", "")).upper() != style["bgColor"].upper():
                mism.append(f"customBgColor={settings.get('customBgColor', '—')} (cần {style['bgColor']})")
        matched_txt = " ".join(style["matched"])
        required = [(label, key) for label, key in (("Căn giữa", "centerInfoPills"), ("Khung thẻ", "doctorCardFrame"),
                                                    ("Bảng tổng hợp", "summaryLargeText"), ("Chữ vàng", "nameStrokeBold"))
                    if label in matched_txt]
        mism.extend(f"{key} chưa bật" for _label, key in required if settings.get(key) is not True)
        if "Phóng to" in matched_txt and float(settings.get("heroImageScale") or 1.0) != float(style["heroImageScale"]):
            mism.append(f"heroImageScale={settings.get('heroImageScale', 1.0)} (cần {style['heroImageScale']})")
    checks.append(_check("bg_theme_match", "Màu nền & kiểu dáng khớp Yêu cầu thiết kế (visual_prompt)",
                         "pass" if not mism else "fail",
                         ("Khớp: " + ", ".join(style["matched"])) if not mism and style["matched"] else
                         ("Không có yêu cầu riêng — dùng mặc định nền be ấm." if not mism else "Lệch: " + "; ".join(mism)), True))

    passed = sum(1 for c in checks if c["status"] == "pass")
    warns = sum(1 for c in checks if c["status"] == "warn")
    score = round(100 * (passed + 0.5 * warns) / len(checks))
    return {"ok": all(c["status"] != "fail" for c in checks), "score": score, "passed": passed, "warnings": warns,
            "failed": sum(1 for c in checks if c["status"] == "fail"), "total": len(checks), "counts": counts,
            "preset": preset, "checks": checks, "fixable_count": sum(1 for c in checks if c["fixable"])}


def run_qa_autofix(pid: str, pdir: Path, rerun_steps: bool = True) -> dict[str, Any]:
    from services.qa_autofix import apply_autofix

    before = run_qa_check(pdir)
    fixes, warnings = apply_autofix(pid, pdir, before, rerun_steps=rerun_steps)
    after = run_qa_check(pdir)
    for c in after["checks"]:
        if c["status"] == "fail":
            msg = f"Còn lỗi cần xử lý tay: {c['name']} — {c['detail']}"
            if msg not in warnings:
                warnings.append(msg)
    return {"ok": after["ok"], "fixes": fixes, "warnings": warnings, "before": before, "after": after}
