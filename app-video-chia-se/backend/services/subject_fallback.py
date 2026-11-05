# -*- coding: utf-8 -*-
"""Bộ tách nền DỰ PHÒNG (không cần OpenCV / onnxruntime / model u2net).

Dùng khi chạy trên Linux Cloud hoặc máy chưa cài model: ước lượng màu nền từ viền ảnh,
tính khoảng cách màu, ngưỡng Otsu, giữ vùng liên thông lớn nhất, lấp lỗ, làm mềm biên.
Cho kết quả tốt với ảnh chân dung nền tương đối đồng màu (ảnh chụp studio, ảnh thẻ, ảnh chụp màn hình).
Kết quả trả về cùng định dạng với media_ops.extract_doctor_subject_image.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _otsu(values: np.ndarray) -> float:
    hist, edges = np.histogram(values, bins=128)
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total <= 0:
        return float(values.mean())
    centers = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = total - w0
    m0 = np.cumsum(hist * centers) / np.maximum(w0, 1)
    m1 = ((hist * centers).sum() - np.cumsum(hist * centers)) / np.maximum(w1, 1)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(centers[int(np.argmax(between))])


def _components(mask: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """Gán nhãn vùng liên thông 4-hướng (BFS). Trả về (labels, areas) — areas[k] của nhãn k+1."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    areas: list[int] = []
    flat = mask.ravel()
    lab_flat = labels.ravel()
    for start in np.flatnonzero(flat):
        if lab_flat[start]:
            continue
        lbl = len(areas) + 1
        lab_flat[start] = lbl
        q = deque([start])
        area = 0
        while q:
            idx = q.popleft()
            area += 1
            y, x = divmod(idx, w)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w:
                    n = ny * w + nx
                    if flat[n] and not lab_flat[n]:
                        lab_flat[n] = lbl
                        q.append(n)
        areas.append(area)
    return labels, areas


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    inv = ~mask
    labels, _ = _components(inv)
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])).tolist())
    border.discard(0)
    outside = np.isin(labels, list(border)) if border else np.zeros_like(mask)
    return mask | (inv & ~outside)


def _running_median(profile: np.ndarray, k: int = 15) -> np.ndarray:
    """Median trượt theo chiều dọc (loại ngoại lai khi chủ thể chạm mép trong đoạn ngắn)."""
    pad = k // 2
    padded = np.pad(profile, ((pad, pad), (0, 0)), mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(padded, k, axis=0)
    return np.median(win, axis=-1).astype(np.float32)


def fallback_subject_mask(rgb: Image.Image) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
    """Trả về (alpha uint8 HxW, bbox xyxy) giống compute_human_segmentation_mask."""
    W, H = rgb.size
    scale = 256.0 / max(W, H)
    sw, sh = max(8, int(round(W * scale))), max(8, int(round(H * scale)))
    small = np.asarray(rgb.convert("RGB").resize((sw, sh), Image.Resampling.BILINEAR), dtype=np.float32)
    bw = max(2, int(round(min(sw, sh) * 0.04)))
    # Mô hình nền THEO TỪNG HÀNG: nội suy giữa viền trái & phải của chính hàng đó (làm mượt theo chiều dọc)
    # => xử lý tốt nền gradient & áo blouse trắng trên nền sáng (bảng màu toàn cục dễ nhầm áo là nền)
    left = _running_median(np.median(small[:, :bw], axis=1))
    right = _running_median(np.median(small[:, -bw:], axis=1))
    t = np.linspace(0.0, 1.0, sw, dtype=np.float32)[None, :, None]
    bg_rows = left[:, None, :] * (1 - t) + right[:, None, :] * t
    dist_rows = np.linalg.norm(small - bg_rows, axis=2)
    # Vùng trên cùng: so thêm với viền trên theo từng cột (nền thay đổi theo chiều ngang)
    top = np.median(small[:bw], axis=0)
    dist_top = np.linalg.norm(small - top[None, :, :], axis=2)
    w_top = np.clip(1.0 - np.arange(sh, dtype=np.float32) / max(1.0, sh * 0.25), 0, 1)[:, None]
    dist = dist_rows * (1 - w_top) + np.minimum(dist_rows, dist_top) * w_top
    resid = np.concatenate([dist_rows[: int(sh * 0.8), :bw].ravel(), dist_rows[: int(sh * 0.8), -bw:].ravel(), dist_top[:bw].ravel()])
    # Độ nhiễu nền: p90 (bỏ qua logo/chữ nhỏ chạm viền) — không để vùng tóc tối kéo ngưỡng Otsu lên
    noise = float(np.percentile(resid, 90))
    thr = float(np.clip(noise * 1.6 + 8.0, 14.0, min(60.0, max(20.0, _otsu(dist)))))
    fg = dist > thr
    labels, areas = _components(fg)
    if areas:
        max_area = max(areas)
        keep = [i + 1 for i, a in enumerate(areas) if a >= max_area * 0.22 and a >= 12]
        fg = np.isin(labels, keep)
        fg = _fill_holes(fg)
    if fg.sum() < sw * sh * 0.01:  # không tìm thấy chủ thể rõ ràng => giữ toàn ảnh
        fg = np.ones_like(fg, dtype=bool)
    m_small = Image.fromarray((fg * 255).astype(np.uint8))
    m_small = m_small.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    m_full = m_small.resize((W, H), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(max(1.0, W / 600)))
    arr = np.asarray(m_full, dtype=np.float32)
    alpha = (np.clip((arr - 40.0) / (215.0 - 40.0), 0, 1) * 255).astype(np.uint8)
    ys, xs = np.where(alpha > 75)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if len(xs) > 20 else None
    return alpha, bbox


def fallback_extract_subject(
    src_path: Path,
    out_path: Path,
    mode: str = "cutout",
    crop_box: list[float] | None = None,
    target_box: int = 800,
    mask_src_path: Path | None = None,
) -> dict[str, Any]:
    """mask_src_path: ảnh gốc (chưa làm nét) dùng để tính mặt nạ — điểm ảnh vẫn lấy từ src_path."""
    from media_ops import frame_scene_photo_as_card

    with Image.open(src_path) as raw:
        orig = raw.convert("RGBA")
    ow, oh = orig.size
    white = Image.new("RGBA", orig.size, (255, 255, 255, 255))
    white.alpha_composite(orig)
    work = white.convert("RGB")
    manual = False
    if crop_box and len(crop_box) == 4:
        cx, cy, cw, ch = [float(v) for v in crop_box]
        if cw > 0.03 and ch > 0.03:
            x1, y1 = int(round(cx * ow)), int(round(cy * oh))
            x2, y2 = min(ow, int(round((cx + cw) * ow))), min(oh, int(round((cy + ch) * oh)))
            if x2 - x1 >= 10 and y2 - y1 >= 10 and (x1, y1, x2, y2) != (0, 0, ow, oh):
                work, manual = work.crop((x1, y1, x2, y2)), True
    mask_img = work
    if mask_src_path is not None and Path(mask_src_path) != Path(src_path):
        with Image.open(mask_src_path) as m_raw:
            m_rgba = m_raw.convert("RGBA")
        if m_rgba.size == orig.size:
            m_white = Image.new("RGBA", m_rgba.size, (255, 255, 255, 255))
            m_white.alpha_composite(m_rgba)
            mask_img = m_white.convert("RGB")
            if manual:
                mask_img = mask_img.crop((x1, y1, x2, y2))
    alpha, bbox = fallback_subject_mask(mask_img)
    w, h = work.size

    if mode == "crop_card":
        if not manual and bbox:
            bx1, by1, bx2, by2 = bbox
            px, pt, pb = int((bx2 - bx1) * 0.22), int((by2 - by1) * 0.14), int((by2 - by1) * 0.08)
            work = work.crop((max(0, bx1 - px), max(0, by1 - pt), min(w, bx2 + px), min(h, by2 + pb)))
        canvas = frame_scene_photo_as_card(work, target_box=target_box)
    else:
        cut = work.convert("RGBA")
        cut.putalpha(Image.fromarray(alpha))
        if bbox:
            cut = cut.crop((max(0, bbox[0] - 6), max(0, bbox[1] - 6), min(w, bbox[2] + 6), min(h, bbox[3] + 6)))
        if mode == "cutout_card":
            card = Image.new("RGBA", (720, 540), (244, 238, 228, 255))
            sc = min(660 / max(1, cut.width), 510 / max(1, cut.height))
            doc = cut.resize((max(1, int(cut.width * sc)), max(1, int(cut.height * sc))), Image.Resampling.LANCZOS)
            card.alpha_composite(doc, ((720 - doc.width) // 2, 540 - doc.height))
            canvas = frame_scene_photo_as_card(card.convert("RGB"), target_box=target_box)
        else:
            inner = target_box - 88
            sc = min(inner / max(1, cut.width), inner / max(1, cut.height))
            doc = cut.resize((max(1, int(cut.width * sc)), max(1, int(cut.height * sc))), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (target_box, target_box), (0, 0, 0, 0))
            ox, oy = (target_box - doc.width) // 2, (target_box - doc.height) // 2
            a = doc.getchannel("A")
            shadow = Image.new("RGBA", doc.size, (0, 0, 0, 255))
            shadow.putalpha(a.point(lambda v: int(v * 0.48)))
            sh_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            sh_layer.alpha_composite(shadow, (ox + 4, oy + 10))
            canvas.alpha_composite(sh_layer.filter(ImageFilter.GaussianBlur(12)))
            if mode == "cutout":
                dil = a
                for _ in range(4):
                    dil = dil.filter(ImageFilter.MaxFilter(5))
                stroke = Image.new("RGBA", doc.size, (255, 255, 255, 255))
                stroke.putalpha(dil.filter(ImageFilter.GaussianBlur(1.5)))
                canvas.alpha_composite(stroke, (ox, oy))
            canvas.alpha_composite(doc, (ox, oy))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    norm = [0.05, 0.05, 0.90, 0.90]
    if not manual and bbox:
        bx1, by1, bx2, by2 = bbox
        bw_, bh_ = bx2 - bx1, by2 - by1
        px1, py1 = max(0, bx1 - int(bw_ * 0.12)), max(0, by1 - int(bh_ * 0.10))
        px2, py2 = min(ow, bx2 + int(bw_ * 0.12)), min(oh, by2 + int(bh_ * 0.06))
        norm = [round(px1 / ow, 4), round(py1 / oh, 4), round((px2 - px1) / ow, 4), round((py2 - py1) / oh, 4)]
    return {
        "ok": True,
        "out_path": str(out_path),
        "mode": mode,
        "person_detected": bbox is not None,
        "suggested_crop_box": norm,
        "orig_size": [ow, oh],
    }


def draw_demo_portrait(path: Path, label: str, hue: tuple[int, int, int], size: tuple[int, int] = (720, 900)) -> Path:
    """Vẽ ảnh chân dung minh hoạ (dùng cho dự án mẫu & kiểm thử) — nền sáng, người ở giữa."""
    w, h = size
    im = Image.new("RGB", size, (236, 241, 246))
    d = ImageDraw.Draw(im)
    for y in range(h):  # nền gradient nhẹ
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(236 - 18 * t), int(241 - 14 * t), int(246 - 8 * t)))
    d.ellipse([w * 0.18, h * 0.52, w * 0.82, h * 1.25], fill=(250, 250, 252))  # áo blouse trắng
    d.polygon([(w * 0.5, h * 0.56), (w * 0.42, h * 0.75), (w * 0.58, h * 0.75)], fill=hue)  # cổ áo màu
    d.rectangle([w * 0.44, h * 0.44, w * 0.56, h * 0.58], fill=(226, 186, 160))  # cổ
    d.ellipse([w * 0.33, h * 0.17, w * 0.67, h * 0.52], fill=(232, 194, 168))  # mặt
    d.chord([w * 0.31, h * 0.12, w * 0.69, h * 0.40], 180, 360, fill=(52, 38, 30))  # tóc
    for ex in (0.43, 0.57):
        d.ellipse([w * ex - 9, h * 0.33 - 6, w * ex + 9, h * 0.33 + 6], fill=(40, 30, 25))
    d.arc([w * 0.44, h * 0.38, w * 0.56, h * 0.45], 20, 160, fill=(170, 80, 70), width=4)
    d.rectangle([w * 0.06, h * 0.03, w * 0.94, h * 0.08], fill=hue)
    d.text((w * 0.08, h * 0.035), label[:40], fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path
