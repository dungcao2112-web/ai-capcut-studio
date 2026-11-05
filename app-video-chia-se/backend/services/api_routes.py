# -*- coding: utf-8 -*-
"""Đăng ký các API mới cho Studio Pro. server.py gọi dispatch_extra() TRƯỚC các route cũ;
chỉ những đường dẫn mới (không trùng route cũ) được xử lý ở đây => tương thích ngược 100%.

GET  /api/system/environment                  -> Thông tin môi trường (Cloud Demo / Windows Local)
POST /api/script/analyze                      -> Phân tích kịch bản (tiêu đề, số mục, cảnh báo)
POST /api/demo/seed                           -> Tạo lại 2 dự án mẫu (Cloud Demo)
GET  /api/projects/<pid>/qa-check             -> Kiểm định chất lượng 10 tiêu chí
POST /api/projects/<pid>/qa-autofix           -> Tự sửa lỗi bố cục 1 chạm
GET  /api/projects/<pid>/visual-prompt        -> Yêu cầu thiết kế đã lưu + phân tích
POST /api/projects/<pid>/visual-prompt        -> Lưu & áp dụng yêu cầu thiết kế
GET  /api/projects/<pid>/preview-data         -> Dữ liệu cho Live Preview 9:16
POST /api/projects/<pid>/enhance-doctor-image -> Làm nét / đổi nền thẻ 1 ảnh
POST /api/projects/<pid>/batch-process-images -> Tách nền & làm nét hàng loạt
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Callable

_ROUTES: list[tuple[str, re.Pattern, Callable]] = []


def route(method: str, pattern: str):
    def deco(fn: Callable) -> Callable:
        _ROUTES.append((method.upper(), re.compile(pattern), fn))
        return fn

    return deco


def dispatch_extra(handler: Any, method: str, path: str, qs: dict[str, list[str]]) -> bool:
    """Trả về True nếu route đã được xử lý (đã gửi response)."""
    for meth, rx, fn in _ROUTES:
        if meth != method.upper():
            continue
        m = rx.match(path)
        if not m:
            continue
        args = [urllib.parse.unquote(g) for g in m.groups()]
        body = handler._read_json_body() if method.upper() == "POST" else {}
        try:
            result = fn(*args, body=body or {}, qs=qs)
        except FileNotFoundError as exc:
            handler._send_json({"error": str(exc)}, status=404)
            return True
        except (ValueError, KeyError) as exc:
            handler._send_json({"error": str(exc)}, status=400)
            return True
        status = 200
        if isinstance(result, tuple):
            result, status = result
        handler._send_json(result, status=status)
        return True
    return False


def _bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


# ---------------------------------------------------------------------------
# Hệ thống
# ---------------------------------------------------------------------------
@route("GET", r"^/api/system/environment$")
def _env(body, qs):
    from services.cloud_env import environment_report

    return environment_report()


@route("POST", r"^/api/script/analyze$")
def _analyze_script(body, qs):
    from media_ops import parse_script_outline
    from services.qa_validator import outline_warnings

    text = str(body.get("text") or body.get("script_text") or "")
    outline = parse_script_outline(text, current_title=str(body.get("title") or ""))
    outline["warnings"] = outline_warnings(outline)
    return {"ok": True, "outline": outline}


@route("POST", r"^/api/demo/seed$")
def _seed(body, qs):
    from services.demo_seed import ensure_demo_projects

    return ensure_demo_projects(force=_bool(body.get("force")), require_cloud=False)


# ---------------------------------------------------------------------------
# Auto-QA
# ---------------------------------------------------------------------------
@route("GET", r"^/api/projects/([^/]+)/qa-check$")
def _qa_check(pid, body, qs):
    from pipeline import get_project_dir
    from services.qa_validator import run_qa_check

    return run_qa_check(get_project_dir(pid))


@route("POST", r"^/api/projects/([^/]+)/qa-autofix$")
def _qa_autofix(pid, body, qs):
    from pipeline import get_project_dir, load_project_state
    from services.qa_validator import run_qa_autofix

    res = run_qa_autofix(pid, get_project_dir(pid), rerun_steps=_bool(body.get("rerun_steps"), True))
    res["project"] = load_project_state(pid)
    return res


# ---------------------------------------------------------------------------
# Yêu cầu thiết kế (visual_prompt) & Live Preview
# ---------------------------------------------------------------------------
@route("GET", r"^/api/projects/([^/]+)/visual-prompt$")
def _vp_get(pid, body, qs):
    from pipeline import get_project_dir
    from services.visual_prompt import load_visual_prompt, parse_visual_prompt

    text = load_visual_prompt(get_project_dir(pid))
    return {"ok": True, "visual_prompt": text, "style": parse_visual_prompt(text)}


@route("POST", r"^/api/projects/([^/]+)/visual-prompt$")
def _vp_post(pid, body, qs):
    from pipeline import get_project_dir, load_project_state
    from services.visual_prompt import save_and_apply_visual_prompt

    res = save_and_apply_visual_prompt(
        get_project_dir(pid), str(body.get("text") or ""), apply=_bool(body.get("apply"), True)
    )
    res["project"] = load_project_state(pid)
    return res


@route("GET", r"^/api/projects/([^/]+)/preview-data$")
def _preview_data(pid, body, qs):
    from pipeline import get_project_dir
    from services.visual_prompt import build_preview_data

    return build_preview_data(pid, get_project_dir(pid))


# ---------------------------------------------------------------------------
# Ảnh bác sĩ / sản phẩm Pro
# ---------------------------------------------------------------------------
@route("POST", r"^/api/projects/([^/]+)/enhance-doctor-image$")
def _enhance_one(pid, body, qs):
    from pipeline import get_project_dir, load_project_state
    from services.image_batch import enhance_project_item

    res = enhance_project_item(
        pid,
        get_project_dir(pid),
        item_index=int(body.get("item_index", 1)),
        options=body,
        preview_only=_bool(body.get("preview_only")),
    )
    if not res.get("ok"):
        return res, 400
    if not res.get("preview_only"):
        res["project"] = load_project_state(pid)
    return res


@route("POST", r"^/api/projects/([^/]+)/batch-process-images$")
def _batch(pid, body, qs):
    from pipeline import get_project_dir, load_project_state
    from services.image_batch import batch_process_project

    res = batch_process_project(pid, get_project_dir(pid), options=body)
    res["project"] = load_project_state(pid)
    return res
