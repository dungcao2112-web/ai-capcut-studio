# -*- coding: utf-8 -*-
"""Đóng khung ảnh theo tỉ lệ người dùng chọn & ghép nhiều ảnh (bố cục 2 / 3 / 4 / 6 ảnh).

Kết quả luôn là canvas 800x800 RGBA trong suốt chứa 1 thẻ bo góc viền trắng + bóng đổ (cùng phong cách
frame_scene_photo_as_card cũ), để Bước 6 giữ nguyên ảnh (không tự cắt giữa 4:3 nữa).
Remotion / Live Preview tự cắt viền trong suốt (image_bbox) nên thẻ luôn lấp đầy khung hiển thị.
"""
from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw, ImageFilter

CANVAS = 800
CARD_MAX = 760
BORDER = 12
RADIUS = 38
GAP = 10

ASPECTS: dict[str, float | None] = {"free": None, "4:3": 4 / 3, "1:1": 1.0, "3:4": 3 / 4, "16:9": 16 / 9, "3:2": 1.5}

# Bố cục ghép: tên -> (tỉ lệ thẻ, [ô (x, y, w, h) chuẩn hoá 0..1])
LAYOUTS: dict[str, tuple[float, list[tuple[float, float, float, float]]]] = {
    "1": (4 / 3, [(0, 0, 1, 1)]),
    "2-ngang": (1.6, [(0, 0, 0.5, 1), (0.5, 0, 0.5, 1)]),
    "2-doc": (1.0, [(0, 0, 1, 0.5), (0, 0.5, 1, 0.5)]),
    "3-1lon2nho": (1.5, [(0, 0, 0.62, 1), (0.62, 0, 0.38, 0.5), (0.62, 0.5, 0.38, 0.5)]),
    "3-ngang": (1.8, [(0, 0, 1 / 3, 1), (1 / 3, 0, 1 / 3, 1), (2 / 3, 0, 1 / 3, 1)]),
    "4-luoi": (4 / 3, [(0, 0, 0.5, 0.5), (0.5, 0, 0.5, 0.5), (0, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5)]),
    "4-1lon3nho": (4 / 3, [(0, 0, 1, 0.62), (0, 0.62, 1 / 3, 0.38), (1 / 3, 0.62, 1 / 3, 0.38), (2 / 3, 0.62, 1 / 3, 0.38)]),
    "6-luoi": (1.5, [(c / 3, r / 2, 1 / 3, 0.5) for r in range(2) for c in range(3)]),
}
LAYOUT_LABELS = {
    "1": "1 ảnh", "2-ngang": "2 ảnh ngang", "2-doc": "2 ảnh dọc", "3-1lon2nho": "3 ảnh (1 lớn + 2 nhỏ)",
    "3-ngang": "3 ảnh ngang", "4-luoi": "4 ảnh lưới 2×2", "4-1lon3nho": "4 ảnh (1 lớn + 3 nhỏ)", "6-luoi": "6 ảnh lưới 3×2",
}


def apply_crop(im: Image.Image, crop_box: list[float] | None) -> Image.Image:
    """crop_box = [x, y, w, h] chuẩn hoá 0..1 trên ảnh gốc."""
    if not crop_box or len(crop_box) != 4:
        return im
    W, H = im.size
    x, y, w, h = [float(v) for v in crop_box]
    x1, y1 = max(0, int(round(x * W))), max(0, int(round(y * H)))
    x2, y2 = min(W, int(round((x + w) * W))), min(H, int(round((y + h) * H)))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return im
    return im.crop((x1, y1, x2, y2))


def cover_fit(im: Image.Image, w: int, h: int) -> Image.Image:
    """Phóng/cắt giữa để lấp kín ô w×h (giống object-fit: cover)."""
    sc = max(w / max(1, im.width), h / max(1, im.height))
    nw, nh = max(w, int(round(im.width * sc))), max(h, int(round(im.height * sc)))
    big = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return big.crop((left, top, left + w, top + h))


def _card_size(aspect: float) -> tuple[int, int]:
    if aspect >= 1:
        return CARD_MAX, max(120, int(round(CARD_MAX / aspect)))
    return max(120, int(round(CARD_MAX * aspect))), CARD_MAX


def _finish_card(inner: Image.Image) -> Image.Image:
    """Bo góc + viền trắng + bóng đổ, đặt giữa canvas 800x800 trong suốt."""
    cw, ch = inner.size
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    ox, oy = (CANVAS - cw) // 2, (CANVAS - ch) // 2
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=RADIUS, fill=255)
    shadow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    sh = Image.new("RGBA", (cw, ch), (60, 40, 25, 110))
    shadow.paste(sh, (ox + 2, oy + 10), mask)
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))
    white = Image.new("RGBA", (cw, ch), (255, 255, 255, 255))
    canvas.paste(white, (ox, oy), mask)
    inner_mask = Image.new("L", (cw - 2 * BORDER, ch - 2 * BORDER), 0)
    ImageDraw.Draw(inner_mask).rounded_rectangle([0, 0, cw - 2 * BORDER - 1, ch - 2 * BORDER - 1], radius=RADIUS - BORDER, fill=255)
    canvas.paste(inner.crop((BORDER, BORDER, cw - BORDER, ch - BORDER)), (ox + BORDER, oy + BORDER), inner_mask)
    return canvas


def frame_photo(im: Image.Image, crop_box: list[float] | None = None, aspect: str | float | None = "free") -> Image.Image:
    """Cắt theo vùng người dùng chọn rồi đóng thẻ đúng tỉ lệ vùng chọn (hoặc tỉ lệ ép buộc)."""
    rgb = apply_crop(im.convert("RGB"), crop_box)
    ratio = ASPECTS.get(aspect, None) if isinstance(aspect, str) else aspect
    ratio = float(ratio) if ratio else rgb.width / max(1, rgb.height)
    ratio = max(0.5, min(2.2, ratio))
    cw, ch = _card_size(ratio)
    return _finish_card(cover_fit(rgb, cw, ch).convert("RGBA"))


def compose_collage(images: list[Image.Image], layout: str) -> Image.Image:
    """Ghép ảnh theo bố cục. Ô thiếu ảnh để màu be nhạt (#F6EFE6)."""
    if layout not in LAYOUTS:
        raise ValueError(f"Bố cục không hợp lệ: {layout}")
    ratio, cells = LAYOUTS[layout]
    cw, ch = _card_size(ratio)
    inner = Image.new("RGBA", (cw, ch), (255, 255, 255, 255))
    iw, ih = cw - 2 * BORDER, ch - 2 * BORDER
    for k, (x, y, w, h) in enumerate(cells):
        x1 = BORDER + int(round(x * iw)) + (GAP // 2 if x > 0 else 0)
        y1 = BORDER + int(round(y * ih)) + (GAP // 2 if y > 0 else 0)
        x2 = BORDER + int(round((x + w) * iw)) - (GAP // 2 if x + w < 0.999 else 0)
        y2 = BORDER + int(round((y + h) * ih)) - (GAP // 2 if y + h < 0.999 else 0)
        tw, th = max(8, x2 - x1), max(8, y2 - y1)
        if k < len(images) and images[k] is not None:
            tile = cover_fit(images[k].convert("RGB"), tw, th).convert("RGBA")
        else:
            tile = Image.new("RGBA", (tw, th), (246, 239, 230, 255))
        tmask = Image.new("L", (tw, th), 0)
        ImageDraw.Draw(tmask).rounded_rectangle([0, 0, tw - 1, th - 1], radius=14, fill=255)
        inner.paste(tile, (x1, y1), tmask)
    return _finish_card(inner)


def layouts_payload() -> list[dict[str, Any]]:
    return [{"id": k, "label": LAYOUT_LABELS[k], "aspect": round(v[0], 3), "cells": [list(c) for c in v[1]]}
            for k, v in LAYOUTS.items()]
