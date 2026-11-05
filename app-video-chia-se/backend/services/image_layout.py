# -*- coding: utf-8 -*-
"""Đo vùng có nội dung (bỏ viền trong suốt) của ảnh sản phẩm để Remotion phóng ảnh lấp đầy khung.

Ảnh sau Bước 6 là canvas 800x800 có viền trong suốt; nếu hiển thị nguyên canvas thì thẻ ảnh thật
chỉ chiếm ~70% => trông nhỏ và thấp. image_bbox = [x, y, w, h] (0..1) giúp TSX cắt bỏ viền đó.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def content_bbox(path: Path, alpha_threshold: int = 24) -> tuple[list[float], float] | None:
    try:
        with Image.open(path) as im:
            rgba = im.convert("RGBA")
    except Exception:
        return None
    W, H = rgba.size
    a = np.asarray(rgba.getchannel("A"))
    ys, xs = np.where(a > alpha_threshold)
    if len(xs) < 16:
        return None
    x1, x2, y1, y2 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    bbox = [round(x1 / W, 4), round(y1 / H, 4), round((x2 - x1) / W, 4), round((y2 - y1) / H, 4)]
    return bbox, round((x2 - x1) / max(1, (y2 - y1)), 4)


def enrich_products_layout(products: list[dict[str, Any]], product_dirs: list[Path]) -> int:
    """Gắn image_bbox & image_aspect cho từng sản phẩm (dùng ảnh đầu tiên tìm thấy). Trả về số mục đã gắn."""
    done = 0
    for p in products:
        fname = str(p.get("image_file") or "")
        if not fname:
            continue
        src = next((d / fname for d in product_dirs if (d / fname).is_file()), None)
        info = content_bbox(src) if src else None
        if info:
            p["image_bbox"], p["image_aspect"] = info
            done += 1
    return done
