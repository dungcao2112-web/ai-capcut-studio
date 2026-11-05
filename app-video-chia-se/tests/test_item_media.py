# -*- coding: utf-8 -*-
"""🖼️ Chọn khung hình, 🧩 Ghép nhiều ảnh, và đo vùng có nội dung để ảnh lấp đầy khung video."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

APP = Path(__file__).resolve().parents[1]


def _photo(w=1280, h=853, color=(40, 90, 60)):
    im = Image.new("RGB", (w, h), color)
    im.paste((220, 30, 30), (w // 2, h // 3, w // 2 + 80, h // 3 + 80))
    return im


def _png_bytes(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_frame_photo_keeps_chosen_aspect():
    from services.image_layout import content_bbox
    from services.photo_frame import frame_photo

    for aspect, want in (("1:1", 1.0), ("3:4", 0.75), ("16:9", 16 / 9), ("4:3", 4 / 3)):
        canvas = frame_photo(_photo(), crop_box=[0.1, 0.1, 0.6, 0.8], aspect=aspect)
        assert canvas.size == (1200, 1200) and canvas.mode == "RGBA"
        tmp = Path(f"/tmp/_frame_{aspect.replace(':', '_')}.png")
        canvas.save(tmp)
        bbox, ar = content_bbox(tmp)
        assert abs(ar - want) < 0.08, (aspect, ar)
        assert max(bbox[2], bbox[3]) > 0.93  # thẻ chiếm gần trọn canvas
    free = frame_photo(_photo(), crop_box=[0, 0, 0.5, 1], aspect="free")  # vùng chọn 640x853 => dọc
    a = np.asarray(free.getchannel("A"))
    ys, xs = np.where(a > 24)
    assert (xs.max() - xs.min()) < (ys.max() - ys.min())


@pytest.mark.parametrize("layout,n", [("2-ngang", 2), ("2-doc", 2), ("3-1lon2nho", 3), ("3-ngang", 3), ("4-luoi", 4), ("4-1lon3nho", 4), ("6-luoi", 6)])
def test_collage_layouts(layout, n):
    from services.photo_frame import LAYOUTS, compose_collage

    assert len(LAYOUTS[layout][1]) == n
    canvas, infos = compose_collage([_photo(color=(30 * k, 80, 120)) for k in range(n - 1)], layout)  # 1 ô để trống
    assert canvas.size == (1200, 1200) and len(infos) == n and infos[-1]["mode"] == "empty"
    with pytest.raises(ValueError):
        compose_collage([], "khong-co")


def test_content_bbox_trims_transparent_margin(tmp_path):
    from services.image_layout import content_bbox, enrich_products_layout

    canvas = Image.new("RGBA", (800, 800), (0, 0, 0, 0))
    canvas.paste((255, 255, 255, 255), (40, 130, 760, 670))
    canvas.save(tmp_path / "01.png")
    bbox, ar = content_bbox(tmp_path / "01.png")
    assert bbox == [0.05, 0.1625, 0.9, 0.675] and abs(ar - 720 / 540) < 0.01
    prods = [{"i": 1, "image_file": "01.png"}, {"i": 2, "image_file": ""}]
    assert enrich_products_layout(prods, [tmp_path]) == 1 and "image_bbox" in prods[0] and "image_bbox" not in prods[1]


def test_item_frame_and_gallery_api(api, fresh_demo):
    pid = "7-benh-vien-di-sinh-demo"
    st, info = api.get(f"/api/projects/{pid}/item-media?item_index=2")
    assert st == 200 and info["source_url"] and info["source_size"] == [900, 720]
    assert {l["id"] for l in info["layouts"]} >= {"2-ngang", "3-1lon2nho", "4-luoi", "6-luoi"}
    st, res = api.post(f"/api/projects/{pid}/item-frame", {"item_index": 2, "crop_box": [0.1, 0.1, 0.5, 0.6], "aspect": "1:1"})
    assert st == 200 and not res["step6_warning"]
    it2 = next(i for i in res["project"]["bang"]["items"] if i["i"] == 2)
    assert "/framed/" in it2["custom_image_path"] and it2["image_aspect"] == "1:1" and it2["image_crop_box"] == [0.1, 0.1, 0.5, 0.6]
    # Mở lại: ảnh gốc vẫn là ảnh ban đầu (không lấy ảnh đã đóng khung làm gốc)
    st, info2 = api.get(f"/api/projects/{pid}/item-media?item_index=2")
    assert info2["source_path"].endswith("item_02.png") and info2["crop_box"] == [0.1, 0.1, 0.5, 0.6]
    st, bad = api.post(f"/api/projects/{pid}/item-frame", {"item_index": 2, "aspect": "7:3"})
    assert st == 400
    # Ghép 3 ảnh: 2 ảnh tải lên + ảnh hiện tại
    paths = []
    for k in range(2):
        st, up = api.request("POST", f"/api/projects/{pid}/item-gallery-upload?item_index=3&slot={k}&filename=a{k}.png", raw=_png_bytes(_photo(color=(20, 60 * k, 90))))
        assert st == 200 and up["ok"]
        paths.append(up["path"])
    st, info3 = api.get(f"/api/projects/{pid}/item-media?item_index=3")
    slots = [{"path": paths[0]}, {"path": paths[1], "crop_box": [0, 0, 0.5, 0.5]}, {"path": info3["source_path"]}]
    st, g = api.post(f"/api/projects/{pid}/item-gallery", {"item_index": 3, "layout": "3-1lon2nho", "slots": slots})
    assert st == 200 and g["filled_slots"] == 3 and g["total_slots"] == 3
    it3 = next(i for i in g["project"]["bang"]["items"] if i["i"] == 3)
    assert it3["collage_layout"] == "3-1lon2nho" and len(it3["gallery"]) == 3
    prep3 = next(i for i in g["project"]["products_prepared"]["items"] if i["i"] == 3)
    assert prep3["image_file"]


def test_gallery_rejects_files_outside_project(api, fresh_demo, tmp_path):
    outside = tmp_path / "bi_mat.png"
    _photo().save(outside)
    st, res = api.post("/api/projects/7-benh-vien-di-sinh-demo/item-gallery",
                       {"item_index": 1, "layout": "2-ngang", "slots": [{"path": str(outside)}, {"path": "/etc/passwd"}]})
    assert st == 400
    st, res = api.request("POST", "/api/projects/7-benh-vien-di-sinh-demo/item-gallery-upload?item_index=1&slot=0&filename=x.png", raw=b"khong-phai-anh")
    assert st == 400


def test_remotion_props_carry_bbox_and_tsx_uses_it(api, fresh_demo):
    import json

    from pipeline import _sync_remotion_active_props, get_project_dir
    from utils import load_config, read_json

    pdir = get_project_dir("7-benh-vien-di-sinh-demo")
    _sync_remotion_active_props(pdir, read_json(pdir / "project.json"))
    active = json.loads((Path(load_config()["paths"]["remotion_dir"]) / "src" / "convo_app_active.json").read_text(encoding="utf-8"))
    p0 = active["products"][0]
    assert len(p0["image_bbox"]) == 4 and p0["image_aspect"] > 1
    tsx = (APP / "remotion" / "ConvoAppDynamic.tsx").read_text(encoding="utf-8")
    assert "item.image_bbox" in tsx and "maxBoxW" in tsx


def _text_photo(w, h, top_text_rows=(0.03, 0.12)):
    """Ảnh có dải chữ đậm sát mép trên (giống 'Hộp đựng thức ăn cho bé') + sản phẩm phẳng ở giữa."""
    im = Image.new("RGB", (w, h), (245, 240, 232))
    a = np.asarray(im).copy()
    y1, y2 = int(top_text_rows[0] * h), int(top_text_rows[1] * h)
    rng = np.random.default_rng(1)
    a[y1:y2, int(w * 0.05):int(w * 0.95)] = (rng.random((y2 - y1, int(w * 0.95) - int(w * 0.05), 1)) > 0.5) * 200
    a[int(h * 0.35):int(h * 0.85), int(w * 0.3):int(w * 0.7)] = (150, 190, 230)
    return Image.fromarray(a.astype("uint8"))


def test_smart_crop_keeps_top_text_instead_of_center():
    from services.smart_crop import best_crop

    im = _text_photo(1000, 1000)
    (x1, y1, x2, y2), loss = best_crop(im, 1.6)  # khung ngang => phải bỏ ~37% chiều cao
    assert y1 <= 25, "Phải giữ dải chữ ở mép trên (cắt giữa sẽ bắt đầu từ y≈187)"
    assert abs((x2 - x1) / (y2 - y1) - 1.6) < 0.02


def test_fit_tile_contains_when_aspect_mismatch_is_large():
    from services.smart_crop import fit_tile

    tile, info = fit_tile(_text_photo(800, 1200), 600, 400)  # ảnh dọc vào ô ngang
    assert tile.size == (600, 400) and info["mode"] == "contain"
    tile, info = fit_tile(_text_photo(1000, 900), 600, 450)
    assert info["mode"] == "smart_crop"
    tile, info = fit_tile(_text_photo(1000, 900), 600, 450, crop_box=[0, 0, 1, 1])
    assert info["mode"] == "manual"


def test_collage_styles_and_preview_api(api, fresh_demo):
    from services.photo_frame import compose_collage

    _c, infos = compose_collage([_photo()], "2-ngang", {"bg": "beige", "border": "brown"})
    with pytest.raises(ValueError):
        compose_collage([_photo()], "2-ngang", {"bg": "tim", "border": "white"})
    pid = "7-benh-vien-di-sinh-demo"
    st, info = api.get(f"/api/projects/{pid}/item-media?item_index=1")
    assert info["styles"]["border"] == ["white", "brown", "gold", "none"] and info["collage_style"]["bg"] == "cream"
    body = {"item_index": 1, "layout": "2-ngang", "slots": [{"path": info["source_path"]}], "style": {"bg": "white", "border": "gold"}, "preview_only": True}
    st, prev = api.post(f"/api/projects/{pid}/item-gallery", body)
    assert st == 200 and prev["preview_only"] and "_preview" in prev["preview_url"] and "project" not in prev
    st, after = api.get(f"/api/projects/{pid}/item-media?item_index=1")
    assert after["layout"] == "1"  # xem trước không thay đổi dự án
    body.pop("preview_only")
    st, done = api.post(f"/api/projects/{pid}/item-gallery", body)
    it = next(i for i in done["project"]["bang"]["items"] if i["i"] == 1)
    assert it["collage_style"] == {"bg": "white", "border": "gold"}


def test_web_download_keeps_original_and_source_prefers_it(tmp_path, fresh_demo):
    from pipeline import get_project_dir
    from services.item_media import original_of, resolve_source

    framed = tmp_path / "item_01_web0.png"
    Image.new("RGBA", (800, 800)).save(framed)
    _photo().save(tmp_path / "item_01_web0_goc.png")
    assert original_of(framed).name == "item_01_web0_goc.png"
    src = resolve_source(get_project_dir("7-benh-vien-di-sinh-demo"), {"i": 1, "custom_image_path": str(framed)})
    assert src.name == "item_01_web0_goc.png"
    media_ops = (APP / "backend" / "media_ops.py").read_text(encoding="utf-8")
    assert '"original_path": str(original_path)' in media_ops and "rgba.width in (800, 1200)" in media_ops


def test_full_width_headline_is_never_cut_on_the_sides():
    from services.smart_crop import crop_report, fit_tile

    im = Image.new("RGB", (1400, 800), (230, 245, 230))
    a = np.asarray(im).copy()
    rng = np.random.default_rng(3)
    a[30:110, 20:1380] = (rng.random((80, 1360, 1)) > 0.5) * 40  # dòng chữ dài gần hết chiều ngang
    a[300:760, 900:1100] = (60, 40, 30)
    im = Image.fromarray(a.astype("uint8"))
    rep = crop_report(im, 1.4)
    assert rep["dense_cut"] > 0.06
    _tile, info = fit_tile(im, 560, 400)
    assert info["mode"] == "contain"
