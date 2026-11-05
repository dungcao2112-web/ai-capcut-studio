# -*- coding: utf-8 -*-
"""Làm nét & cân bằng sáng ảnh chân dung Bác sĩ / Sản phẩm + nền thẻ + tách nền an toàn.

- auto_enhance_portrait : CLAHE (kênh sáng Y) + khử nhiễu nhẹ + Unsharp Mask + tông ấm
- apply_card_background : đặt ảnh tách nền lên thẻ bo góc #FFFDF9 / #F6EFE6 / #F0F7FF hoặc giữ trong suốt
- safe_extract_doctor_subject_image : gọi bộ tách nền AI gốc (u2net + OpenCV); nếu máy thiếu
  onnxruntime/cv2/model (Linux Cloud) thì tự chuyển sang bộ tách nền dự phòng thuần NumPy.
Chỉ dùng Pillow + NumPy (OpenCV là tuỳ chọn).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

BG_PRESETS: dict[str, str | None] = {
    "cream": "#FFFDF9",
    "beige": "#F6EFE6",
    "medical": "#F0F7FF",
    "transparent": None,
}


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = str(value).strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise ValueError(f"Mã màu không hợp lệ: {value}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def resolve_card_bg(value: Any) -> str | None:
    """'beige' | '#F6EFE6' | 'transparent' | None -> mã hex hoặc None (trong suốt)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("transparent", "none", "trong suốt", "trong_suot"):
        return None
    if s.lower() in BG_PRESETS:
        return BG_PRESETS[s.lower()]
    hex_to_rgb(s)  # validate
    return "#" + s.lstrip("#").upper()


def clahe_channel(gray: np.ndarray, clip_limit: float = 2.0, tiles: int = 8) -> np.ndarray:
    """CLAHE thuần NumPy (tương đương cv2.createCLAHE) với nội suy song tuyến giữa các ô."""
    h, w = gray.shape
    ty, tx = max(1, min(tiles, h // 16)), max(1, min(tiles, w // 16))
    ys = np.linspace(0, h, ty + 1).astype(int)
    xs = np.linspace(0, w, tx + 1).astype(int)
    luts = np.zeros((ty, tx, 256), dtype=np.float32)
    for i in range(ty):
        for j in range(tx):
            tile = gray[ys[i]:ys[i + 1], xs[j]:xs[j + 1]]
            hist = np.bincount(tile.ravel(), minlength=256).astype(np.float32)
            limit = max(1.0, clip_limit * tile.size / 256.0)
            excess = np.clip(hist - limit, 0, None).sum()
            hist = np.minimum(hist, limit) + excess / 256.0
            cdf = np.cumsum(hist)
            luts[i, j] = (cdf - cdf[0]) / max(1.0, cdf[-1] - cdf[0]) * 255.0
    cy = (ys[:-1] + ys[1:]) / 2.0
    cx = (xs[:-1] + xs[1:]) / 2.0
    gy = np.clip(np.interp(np.arange(h), cy, np.arange(ty)), 0, ty - 1)
    gx = np.clip(np.interp(np.arange(w), cx, np.arange(tx)), 0, tx - 1)
    y0 = np.floor(gy).astype(int)
    x0 = np.floor(gx).astype(int)
    y1 = np.minimum(y0 + 1, ty - 1)
    x1 = np.minimum(x0 + 1, tx - 1)
    wy = (gy - y0)[:, None]
    wx = (gx - x0)[None, :]
    g = gray.astype(int)
    a = luts[y0[:, None], x0[None, :], g]
    b = luts[y0[:, None], x1[None, :], g]
    c = luts[y1[:, None], x0[None, :], g]
    d = luts[y1[:, None], x1[None, :], g]
    out = (a * (1 - wx) + b * wx) * (1 - wy) + (c * (1 - wx) + d * wx) * wy
    return np.clip(out, 0, 255).astype(np.uint8)


def measure_sharpness(im: Image.Image) -> float:
    """Độ nét = phương sai Laplacian của ảnh xám (càng cao càng nét)."""
    g = np.asarray(im.convert("L"), dtype=np.float32)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    lap = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    return float(lap.var())


def auto_enhance_portrait(
    im: Image.Image,
    strength: float = 1.0,
    warm: bool = True,
    denoise: bool = True,
    clahe: bool = True,
) -> Image.Image:
    """Làm sáng rõ, sắc nét ảnh chân dung tải từ Facebook/TikTok (giữ nguyên kênh alpha)."""
    s = float(max(0.0, min(2.0, strength)))
    alpha = im.getchannel("A") if im.mode in ("RGBA", "LA") else None
    rgb = im.convert("RGB")
    if denoise and s > 0:
        rgb = Image.blend(rgb, rgb.filter(ImageFilter.MedianFilter(3)), min(0.6, 0.35 * s))
    if clahe and s > 0:
        ycc = rgb.convert("YCbCr")
        y, cb, cr = ycc.split()
        y_arr = np.asarray(y, dtype=np.uint8)
        y_eq = clahe_channel(y_arr, clip_limit=1.4 + 0.8 * s, tiles=8)
        mix = min(0.85, 0.55 * s)
        y_new = (y_arr.astype(np.float32) * (1 - mix) + y_eq.astype(np.float32) * mix)
        mean_y = float(y_new.mean())
        if mean_y < 118:  # ảnh tối -> nâng gamma nhẹ
            gamma = 1.0 - min(0.25, (118 - mean_y) / 400.0) * s
            y_new = 255.0 * np.power(np.clip(y_new / 255.0, 0, 1), gamma)
        y = Image.fromarray(np.clip(y_new, 0, 255).astype(np.uint8))
        rgb = Image.merge("YCbCr", (y, cb, cr)).convert("RGB")
    if s > 0:
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=2, percent=int(70 + 60 * s), threshold=3))
        rgb = ImageEnhance.Color(rgb).enhance(1.0 + 0.06 * s)
    if warm and s > 0:
        arr = np.asarray(rgb, dtype=np.float32)
        arr[..., 0] *= 1.0 + 0.035 * s
        arr[..., 1] *= 1.0 + 0.012 * s
        arr[..., 2] *= 1.0 - 0.04 * s
        rgb = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if alpha is not None:
        rgb = rgb.convert("RGBA")
        rgb.putalpha(alpha)
    return rgb


def apply_card_background(
    im: Image.Image,
    bg_hex: str | None,
    radius: int = 40,
    border_color: str | None = "#DECBB1",
    border_px: int = 4,
) -> Image.Image:
    """Đặt ảnh (đã tách nền) lên thẻ bo góc màu bg_hex. bg_hex=None => giữ trong suốt."""
    rgba = im.convert("RGBA")
    if bg_hex is None:
        return rgba
    w, h = rgba.size
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mask = Image.new("L", (w, h), 0)
    r = max(0, min(int(radius), min(w, h) // 2))
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    fill = Image.new("RGBA", (w, h), hex_to_rgb(bg_hex) + (255,))
    card.paste(fill, (0, 0), mask)
    card.alpha_composite(rgba)
    if border_color and border_px > 0:
        ImageDraw.Draw(card).rounded_rectangle(
            [border_px // 2, border_px // 2, w - 1 - border_px // 2, h - 1 - border_px // 2],
            radius=r, outline=hex_to_rgb(border_color) + (255,), width=border_px,
        )
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)
    return out


def enhance_options_from_request(src: dict[str, Any] | None) -> dict[str, Any]:
    """Đọc tuỳ chọn làm nét/nền thẻ từ JSON body hoặc query string (giá trị dạng list).
    Chỉ trả về khoá có mặt => lời gọi cũ (không gửi tuỳ chọn) giữ nguyên hành vi 100%."""
    if not src:
        return {}

    def _get(key: str):
        v = src.get(key)
        return v[0] if isinstance(v, list) and v else v

    out: dict[str, Any] = {}
    if _get("enhance") is not None:
        out["enhance"] = str(_get("enhance")).lower() in ("1", "true", "yes", "on")
    if _get("enhance_strength") is not None:
        out["enhance_strength"] = float(_get("enhance_strength"))
    if _get("warm_tone") is not None:
        out["warm_tone"] = str(_get("warm_tone")).lower() in ("1", "true", "yes", "on")
    if _get("card_bg") is not None:
        out["card_bg"] = str(_get("card_bg"))
    if _get("card_radius") is not None:
        out["card_radius"] = int(float(_get("card_radius")))
    return out


def safe_extract_doctor_subject_image(
    src_path: Path,
    out_path: Path,
    mode: str = "cutout",
    crop_box: list[float] | None = None,
    target_box: int = 800,
    enhance: bool = False,
    enhance_strength: float = 1.0,
    warm_tone: bool = True,
    card_bg: str | None = None,
    card_radius: int = 40,
) -> dict[str, Any]:
    """Bản thay thế an toàn cho media_ops.extract_doctor_subject_image (cùng tham số & kết quả)."""
    src_path, out_path = Path(src_path), Path(out_path)
    work_src = src_path
    if enhance:
        with Image.open(src_path) as raw:
            enh = auto_enhance_portrait(raw.convert("RGBA"), strength=enhance_strength, warm=warm_tone)
        work_src = out_path.parent / f"_enh_{src_path.stem}.png"
        work_src.parent.mkdir(parents=True, exist_ok=True)
        enh.save(work_src)
    engine, fallback_reason = "u2net", ""
    try:
        from media_ops import extract_doctor_subject_image

        res = extract_doctor_subject_image(
            src_path=work_src, out_path=out_path, mode=mode, crop_box=crop_box, target_box=target_box
        )
    except Exception as exc:  # thiếu cv2/onnxruntime/model hoặc không tải được model
        from services.subject_fallback import fallback_extract_subject

        engine, fallback_reason = "fallback", f"{type(exc).__name__}: {exc}"[:240]
        res = fallback_extract_subject(work_src, out_path, mode=mode, crop_box=crop_box, target_box=target_box,
                                       mask_src_path=src_path)
    bg_hex = resolve_card_bg(card_bg) if card_bg is not None else None
    if card_bg is not None and bg_hex is not None and mode in ("cutout", "cutout_plain"):
        with Image.open(out_path) as done:
            apply_card_background(done, bg_hex, radius=card_radius).save(out_path)
    res.update(
        {
            "engine": engine,
            "fallback_reason": fallback_reason,
            "enhanced": bool(enhance),
            "card_bg": bg_hex if card_bg is not None else None,
        }
    )
    if enhance:
        try:
            with Image.open(src_path) as a, Image.open(work_src) as b:
                res["sharpness_before"] = round(measure_sharpness(a), 1)
                res["sharpness_after"] = round(measure_sharpness(b), 1)
        except Exception:
            pass
        try:
            work_src.unlink()
        except OSError:
            pass
    return res
