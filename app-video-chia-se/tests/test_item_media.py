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
        assert canvas.size == (800, 800) and canvas.mode == "RGBA"
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
    canvas = compose_collage([_photo(color=(30 * k, 80, 120)) for k in range(n - 1)], layout)  # 1 ô để trống
    assert canvas.size == (800, 800)
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
