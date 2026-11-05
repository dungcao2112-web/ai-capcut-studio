# -*- coding: utf-8 -*-
"""Đóng khung ảnh theo tỉ lệ người dùng chọn & ghép nhiều ảnh (bố cục 2 / 3 / 4 / 6 ảnh).

Kết quả luôn là canvas 1200x1200 RGBA trong suốt chứa 1 thẻ bo góc viền trắng + bóng đổ (cùng phong cách
frame_scene_photo_as_card cũ), để Bước 6 giữ nguyên ảnh (không tự cắt giữa 4:3 nữa).
Remotion / Live Preview tự cắt viền trong suốt (image_bbox) nên thẻ luôn lấp đầy khung hiển thị.
"""
from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw, ImageFilter

CANVAS = 1200  # Bước 6 giữ nguyên canvas vuông 800/1200 trong anh/framed => ảnh nét hơn khi lên video
CARD_MAX = 1140
BORDER = 16
RADIUS = 56

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
    from services.smart_crop import fit_tile

    rgb = apply_crop(im.convert("RGB"), crop_box)
    ratio = ASPECTS.get(aspect, None) if isinstance(aspect, str) else aspect
    ratio = float(ratio) if ratio else rgb.width / max(1, rgb.height)
    ratio = max(0.5, min(2.2, ratio))
    cw, ch = _card_size(ratio)
    # Vùng sếp đã cắt mà tỉ lệ khác khung => cắt thông minh (giữ chữ) thay vì cắt giữa
    tile, _info = fit_tile(rgb, cw, ch, None)
    return _finish_card(tile.convert("RGBA"))


# Kiểu nền & viền ảnh ghép (giống mẫu: thẻ nền kem bo góc lớn, khoảng cách rộng, ảnh có viền + bóng nhẹ)
BG_STYLES = {"cream": (255, 251, 244), "beige": (246, 239, 230), "white": (255, 255, 255), "transparent": None}
BORDER_STYLES = {"white": (255, 255, 255), "brown": (185, 139, 94), "gold": (224, 176, 90), "none": None}
DEFAULT_STYLE = {"bg": "cream", "border": "white"}


def _shadow(size: tuple[int, int], box: tuple[int, int, int, int], radius: int, blur: int, alpha: int, dy: int) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    x1, y1, x2, y2 = box
    ImageDraw.Draw(layer).rounded_rectangle([x1, y1 + dy, x2, y2 + dy], radius=radius, fill=(90, 60, 35, alpha))
    return layer.filter(ImageFilter.GaussianBlur(blur))


def compose_collage(images: list[Image.Image | None], layout: str, style: dict[str, Any] | None = None,
                    crop_boxes: list[list[float] | None] | None = None) -> tuple[Image.Image, list[dict[str, Any]]]:
    """Ghép ảnh theo bố cục. Ô thiếu ảnh để màu be nhạt. Trả về (canvas 1200x1200, thông tin từng ô).
    Ảnh không có crop_box được cắt thông minh (giữ chữ) hoặc giữ trọn trên nền mờ — xem smart_crop.fit_tile."""
    from services.smart_crop import fit_tile

    if layout not in LAYOUTS:
        raise ValueError(f"Bố cục không hợp lệ: {layout}")
    st = dict(DEFAULT_STYLE, **(style or {}))
    if st["bg"] not in BG_STYLES or st["border"] not in BORDER_STYLES:
        raise ValueError(f"Kiểu nền/viền không hợp lệ: {st}")
    ratio, cells = LAYOUTS[layout]
    cw, ch = _card_size(ratio)
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    ox, oy = (CANVAS - cw) // 2, (CANVAS - ch) // 2
    bg = BG_STYLES[st["bg"]]
    card_r = round(min(cw, ch) * 0.07)
    if bg is not None:
        canvas.alpha_composite(_shadow(canvas.size, (ox, oy, ox + cw, oy + ch), card_r, 22, 70, 12))
        card = Image.new("RGBA", (cw, ch), bg + (255,))
        grad = Image.linear_gradient("L").resize((cw, ch)).point(lambda v: int(v * 0.10))
        card.paste(Image.new("RGBA", (cw, ch), (236, 224, 206, 255)), (0, 0), grad)  # tối nhẹ dần xuống dưới
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=card_r, fill=255)
        canvas.paste(card, (ox, oy), mask)
        ImageDraw.Draw(canvas).rounded_rectangle([ox, oy, ox + cw - 1, oy + ch - 1], radius=card_r, outline=(236, 224, 206, 255), width=3)
    base = min(cw, ch)
    pad, gap = round(base * 0.06), round(base * 0.05)
    bw = max(5, round(base * 0.012)) if BORDER_STYLES[st["border"]] else 0
    tile_r = round(base * 0.04)
    iw, ih = cw - 2 * pad, ch - 2 * pad
    infos: list[dict[str, Any]] = []
    for k, (x, y, w, h) in enumerate(cells):
        x1 = ox + pad + round(x * iw) + (gap // 2 if x > 0 else 0)
        y1 = oy + pad + round(y * ih) + (gap // 2 if y > 0 else 0)
        x2 = ox + pad + round((x + w) * iw) - (gap // 2 if x + w < 0.999 else 0)
        y2 = oy + pad + round((y + h) * ih) - (gap // 2 if y + h < 0.999 else 0)
        tw, th = max(16, x2 - x1), max(16, y2 - y1)
        canvas.alpha_composite(_shadow(canvas.size, (x1, y1, x2, y2), tile_r, 10, 60, 6))
        if bw:
            ImageDraw.Draw(canvas).rounded_rectangle([x1, y1, x2 - 1, y2 - 1], radius=tile_r, fill=BORDER_STYLES[st["border"]] + (255,))
        img = images[k] if k < len(images) else None
        inner_w, inner_h = tw - 2 * bw, th - 2 * bw
        if img is not None:
            crop = crop_boxes[k] if crop_boxes and k < len(crop_boxes) else None
            tile, info = fit_tile(img, inner_w, inner_h, crop)
        else:
            tile, info = Image.new("RGB", (inner_w, inner_h), (246, 239, 230)), {"mode": "empty", "loss": 0.0}
        tmask = Image.new("L", (inner_w, inner_h), 0)
        ImageDraw.Draw(tmask).rounded_rectangle([0, 0, inner_w - 1, inner_h - 1], radius=max(4, tile_r - bw), fill=255)
        canvas.paste(tile.convert("RGBA"), (x1 + bw, y1 + bw), tmask)
        if st["border"] == "white":  # viền mảnh ngoài cùng cho ảnh nổi khối trên nền kem
            ImageDraw.Draw(canvas).rounded_rectangle([x1, y1, x2 - 1, y2 - 1], radius=tile_r, outline=(226, 212, 192, 255), width=2)
        infos.append(dict(info, slot=k))
    return canvas, infos


def layouts_payload() -> list[dict[str, Any]]:
    return [{"id": k, "label": LAYOUT_LABELS[k], "aspect": round(v[0], 3), "cells": [list(c) for c in v[1]]}
            for k, v in LAYOUTS.items()]


def styles_payload() -> dict[str, list[str]]:
    return {"bg": list(BG_STYLES), "border": list(BORDER_STYLES)}
