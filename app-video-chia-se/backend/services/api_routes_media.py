# -*- coding: utf-8 -*-
"""API ảnh theo từng mục:
GET  /api/projects/<pid>/item-media?item_index=N          -> ảnh gốc, khung đã chọn, bố cục & các ô ghép
POST /api/projects/<pid>/item-frame                        -> {item_index, crop_box:[x,y,w,h], aspect}
POST /api/projects/<pid>/item-gallery                      -> {item_index, layout, slots:[{path, crop_box}], style:{bg, border}, preview_only}
POST /api/projects/<pid>/item-gallery-upload?item_index=&slot=&filename=   (body = bytes ảnh)
POST /api/projects/<pid>/item-gallery-web                  -> {item_index, slot, candidate_index, custom_query}
"""
from __future__ import annotations

from services.api_routes import route


def _q(qs, key, default=""):
    v = qs.get(key, [default])
    return v[0] if v else default


@route("GET", r"^/api/projects/([^/]+)/item-media$")
def _item_media(pid, body, qs):
    from pipeline import get_project_dir
    from services.item_media import item_media_info

    return item_media_info(pid, get_project_dir(pid), int(_q(qs, "item_index", "1") or 1))


@route("POST", r"^/api/projects/([^/]+)/item-frame$")
def _item_frame(pid, body, qs):
    from pipeline import get_project_dir, load_project_state
    from services.item_media import frame_item

    res = frame_item(pid, get_project_dir(pid), int(body.get("item_index", 1)), body.get("crop_box"), str(body.get("aspect") or "free"))
    res["project"] = load_project_state(pid)
    return res


@route("POST", r"^/api/projects/([^/]+)/item-gallery$")
def _item_gallery(pid, body, qs):
    from pipeline import get_project_dir, load_project_state
    from services.item_media import set_gallery

    res = set_gallery(pid, get_project_dir(pid), int(body.get("item_index", 1)), str(body.get("layout") or "2-ngang"),
                      body.get("slots") or [], style=body.get("style"), preview_only=bool(body.get("preview_only")))
    if not res.get("preview_only"):
        res["project"] = load_project_state(pid)
    return res


@route("POST", r"^/api/projects/([^/]+)/item-gallery-upload$", raw=True)
def _item_gallery_upload(pid, body, qs):
    import os

    from pipeline import get_project_dir
    from services.item_media import save_slot_upload

    return save_slot_upload(pid, get_project_dir(pid), int(_q(qs, "item_index", "1") or 1), int(_q(qs, "slot", "0") or 0),
                            os.path.basename(_q(qs, "filename", "anh.png")), body)


@route("POST", r"^/api/projects/([^/]+)/item-gallery-web$")
def _item_gallery_web(pid, body, qs):
    from pipeline import get_project_dir
    from services.item_media import fetch_slot_web

    res = fetch_slot_web(pid, get_project_dir(pid), int(body.get("item_index", 1)), int(body.get("slot", 0)),
                         int(body.get("candidate_index", 0)), str(body.get("custom_query") or ""),
                         layout=str(body.get("layout") or ""))
    return res if res.get("ok") else (res, 502)
