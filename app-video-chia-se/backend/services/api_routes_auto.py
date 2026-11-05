# -*- coding: utf-8 -*-
"""API Mẫu ghép chung & Link nguồn (chọn ngay ở Bước 1):
POST /api/projects/<pid>/media-settings  -> {collageLayout, collageStyle:{bg,border}, sourceLinks:[...], autoInfoFromSources}
POST /api/projects/<pid>/auto-media      -> áp dụng mẫu ghép + nguồn cho tất cả mục hiện có, chạy lại Bước 6
POST /api/sources/inspect                -> {links:[...], project_id?} => đọc thử từng link (tiêu đề, số ảnh, lỗi)
POST /api/sources/extract                -> {text} => danh sách link nhận diện được
"""
from __future__ import annotations

from services.api_routes import route

ALLOWED_KEYS = ("collageLayout", "collageStyle", "sourceLinks", "autoInfoFromSources")


@route("POST", r"^/api/projects/([^/]+)/media-settings$")
def _media_settings(pid, body, qs):
    from pipeline import get_project_dir, save_project_state
    from services.photo_frame import BG_STYLES, BORDER_STYLES, LAYOUTS
    from services.source_links import extract_links
    from utils import read_json

    pdir = get_project_dir(pid)
    proj = read_json(pdir / "project.json", {}) or {}
    st = proj.setdefault("settings", {})
    if "collageLayout" in body:
        lay = str(body["collageLayout"] or "1")
        if lay not in LAYOUTS:
            raise ValueError(f"Bố cục không hợp lệ: {lay}")
        st["collageLayout"] = lay
    if "collageStyle" in body:
        cs = dict(body.get("collageStyle") or {})
        if cs.get("bg", "cream") not in BG_STYLES or cs.get("border", "white") not in BORDER_STYLES:
            raise ValueError("Kiểu nền/viền không hợp lệ")
        st["collageStyle"] = {"bg": cs.get("bg", "cream"), "border": cs.get("border", "white")}
    if "sourceLinks" in body:
        raw = body.get("sourceLinks") or []
        st["sourceLinks"] = extract_links(" ".join(raw) if isinstance(raw, list) else str(raw))
    if "autoInfoFromSources" in body:
        st["autoInfoFromSources"] = bool(body["autoInfoFromSources"])
    save_project_state(pdir, proj)
    return {"ok": True, "settings": {k: st.get(k) for k in ALLOWED_KEYS}}


@route("POST", r"^/api/projects/([^/]+)/auto-media$")
def _auto_media(pid, body, qs):
    from pipeline import get_project_dir, load_project_state
    from services.auto_media import apply_project_media

    report = apply_project_media(pid, get_project_dir(pid), refresh_sources=bool(body.get("refresh_sources")))
    return {"ok": True, "report": report, "project": load_project_state(pid)}


@route("POST", r"^/api/sources/inspect$")
def _inspect(body, qs):
    from services.source_links import extract_links, fetch_source, load_sources

    links = extract_links(" ".join(body.get("links") or []) if isinstance(body.get("links"), list) else str(body.get("links") or ""))
    pid = str(body.get("project_id") or "")
    if pid:
        from pipeline import get_project_dir

        srcs = load_sources(get_project_dir(pid), links, refresh=bool(body.get("refresh")))
    else:
        srcs = [fetch_source(u) for u in links]
    return {"ok": True, "sources": [{"url": s["url"], "kind": s.get("kind"), "ok": bool(s.get("ok")), "title": s.get("title", ""),
                                     "images": len(s.get("images") or []), "error": s.get("error", "")} for s in srcs]}


@route("POST", r"^/api/sources/extract$")
def _extract(body, qs):
    from services.source_links import extract_links, link_kind

    links = extract_links(str(body.get("text") or ""))
    return {"ok": True, "links": [{"url": u, "kind": link_kind(u)} for u in links]}
