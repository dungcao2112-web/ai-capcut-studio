# -*- coding: utf-8 -*-
"""Cắt ảnh thông minh — tránh mất chữ / mất nội dung khi đưa ảnh vào khung có tỉ lệ khác.

1. Đo "năng lượng chi tiết" (độ gắt cạnh) của từng cột/hàng — chữ, logo, sản phẩm có năng lượng cao.
2. Trượt cửa sổ đúng tỉ lệ khung, chọn vị trí giữ nhiều chi tiết nhất & KHÔNG cắt ngang vùng nhiều chi tiết
   (VD chữ "Hộp đựng thức ăn cho bé" ở mép trên sẽ được giữ lại thay vì cắt giữa).
3. Nếu cắt kiểu nào cũng mất > max_loss chi tiết, hoặc tỉ lệ lệch quá nhiều (mất > 28% diện tích)
   => giữ TRỌN ảnh (contain) trên nền mờ lấy từ chính ảnh.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

MAX_LOSS = 0.12  # tỉ lệ chi tiết tối đa được phép cắt bỏ
MAX_AREA_CUT = 0.28  # tỉ lệ khung lệch nhiều (cắt mất > 28% diện tích ảnh) => giữ trọn ảnh trên nền mờ


def energy_map(im: Image.Image, max_side: int = 240) -> np.ndarray:
    k = max_side / max(im.width, im.height)
    small = im.convert("L").resize((max(8, round(im.width * k)), max(8, round(im.height * k))), Image.Resampling.BILINEAR)
    g = np.asarray(small, dtype=np.float32)
    e = np.zeros_like(g)
    e[:, 1:] += np.abs(np.diff(g, axis=1))
    e[1:, :] += np.abs(np.diff(g, axis=0))
    return e


DENSE_FACTOR = 3.0  # dải có mật độ chi tiết > 3× trung vị = dòng chữ / logo
MAX_DENSE_CUT = 0.06  # được phép cắt tối đa 6% một dòng chữ


def best_crop(im: Image.Image, aspect: float, boundary_weight: float = 3.0) -> tuple[tuple[int, int, int, int], float]:
    """Trả về (hộp cắt pixel x1,y1,x2,y2 đúng tỉ lệ aspect, tỉ lệ chi tiết bị mất 0..1)."""
    rep = crop_report(im, aspect, boundary_weight)
    return rep["box"], rep["loss"]


def _dense_band_cut(e: np.ndarray, off: int, win: int, horizontal: bool, bands: int = 24) -> float:
    """Tỉ lệ bị cắt lớn nhất của các dải dày chi tiết (dòng chữ) — cắt ngang chữ là lỗi nặng."""
    m = e if horizontal else e.T  # trượt theo cột: chia ảnh thành các dải hàng
    edges = np.linspace(0, m.shape[0], bands + 1).astype(int)
    tot = np.array([m[a:b].sum() for a, b in zip(edges[:-1], edges[1:])])
    keep = np.array([m[a:b, off:off + win].sum() for a, b in zip(edges[:-1], edges[1:])])
    dens = tot / np.maximum(1, np.diff(edges))
    med = float(np.median(dens)) or 1e-6
    dense = (dens > DENSE_FACTOR * med) & (tot > 0)
    if not dense.any():
        return 0.0
    return float(np.max(1.0 - keep[dense] / tot[dense]))


def crop_report(im: Image.Image, aspect: float, boundary_weight: float = 3.0) -> dict[str, Any]:
    W, H = im.size
    ar = W / max(1, H)
    if abs(ar - aspect) / aspect < 0.02:
        return {"box": (0, 0, W, H), "loss": 0.0, "dense_cut": 0.0}
    e = energy_map(im)
    h, w = e.shape
    total = float(e.sum()) or 1.0
    horizontal = ar > aspect  # ảnh rộng hơn khung => trượt theo chiều ngang
    prof = e.sum(axis=0) if horizontal else e.sum(axis=1)
    n = len(prof)
    win = max(1, min(n, round((h * aspect) if horizontal else (w / aspect))))
    cum = np.concatenate([[0.0], np.cumsum(prof)])
    best, best_off, best_inside = -1e18, 0, 0.0
    for off in range(0, n - win + 1):
        inside = cum[off + win] - cum[off]
        cut = (prof[off] if off > 0 else 0.0) + (prof[off + win - 1] if off + win < n else 0.0)
        score = inside - boundary_weight * cut
        if score > best:
            best, best_off, best_inside = score, off, inside
    loss = max(0.0, 1.0 - best_inside / total)
    dense_cut = _dense_band_cut(e, best_off, win, horizontal)
    if horizontal:
        cw = round(H * aspect)
        x1 = min(W - cw, round(best_off * W / w))
        return {"box": (x1, 0, x1 + cw, H), "loss": loss, "dense_cut": dense_cut}
    ch = round(W / aspect)
    y1 = min(H - ch, round(best_off * H / h))
    return {"box": (0, y1, W, y1 + ch), "loss": loss, "dense_cut": dense_cut}


def contain_on_blur(im: Image.Image, w: int, h: int) -> Image.Image:
    """Giữ trọn ảnh trong ô w×h; phần trống phủ nền mờ sáng lấy từ chính ảnh (không viền đen)."""
    rgb = im.convert("RGB")
    sc = max(w / rgb.width, h / rgb.height)
    bg = rgb.resize((max(w, round(rgb.width * sc)), max(h, round(rgb.height * sc))), Image.Resampling.BILINEAR)
    left, top = (bg.width - w) // 2, (bg.height - h) // 2
    bg = bg.crop((left, top, left + w, top + h)).filter(ImageFilter.GaussianBlur(max(6, w // 16)))
    bg = Image.blend(ImageEnhance.Brightness(bg).enhance(1.08), Image.new("RGB", (w, h), (255, 251, 244)), 0.45)
    sc2 = min(w / rgb.width, h / rgb.height)
    fg = rgb.resize((max(1, round(rgb.width * sc2)), max(1, round(rgb.height * sc2))), Image.Resampling.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return bg


def fit_tile(im: Image.Image, w: int, h: int, crop_box: list[float] | None = None,
             max_loss: float = MAX_LOSS) -> tuple[Image.Image, dict[str, Any]]:
    """Đưa ảnh vào ô w×h. crop_box do người dùng chọn => tôn trọng tuyệt đối (cover).
    Không có crop_box => cắt thông minh; mất nhiều chi tiết quá thì giữ trọn ảnh trên nền mờ."""
    from services.photo_frame import apply_crop, cover_fit

    rgb = im.convert("RGB")
    if crop_box:
        return cover_fit(apply_crop(rgb, crop_box), w, h), {"mode": "manual", "loss": 0.0}
    aspect = w / max(1, h)
    ar = rgb.width / max(1, rgb.height)
    area_cut = 1.0 - min(ar, aspect) / max(ar, aspect)
    rep = crop_report(rgb, aspect)
    box, loss = rep["box"], rep["loss"]
    info = {"loss": round(float(loss), 3), "dense_cut": round(float(rep["dense_cut"]), 3)}
    if loss <= max_loss and area_cut <= MAX_AREA_CUT and rep["dense_cut"] <= MAX_DENSE_CUT:
        return rgb.crop(box).resize((w, h), Image.Resampling.LANCZOS), dict(info, mode="smart_crop")
    return contain_on_blur(rgb, w, h), dict(info, mode="contain")


def fit_score(im: Image.Image, aspect: float) -> float:
    """Điểm phù hợp của ảnh với ô (1 = hoàn hảo): dùng để chọn ảnh web hợp ô nhất."""
    rep = crop_report(im.convert("RGB"), aspect)
    res = min(1.0, min(im.width, im.height) / 600.0)
    text_penalty = 0.5 if rep["dense_cut"] > MAX_DENSE_CUT else 0.0  # ảnh phải cắt ngang chữ => kém hợp
    return round(max(0.0, (1.0 - rep["loss"]) * 0.8 + res * 0.2 - text_penalty), 4)
