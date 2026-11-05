# -*- coding: utf-8 -*-
"""Local Multi-threaded HTTP Server for 'Video Chia Sẻ Hội Thoại 2 Người' App.

Zero external web framework dependencies required; supports HTTP Range (206 Partial Content)
for smooth audio/video playback in the browser.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent
APP_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = APP_ROOT / "frontend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from capcut_export import (
    apply_final_revision_notes,
    export_project_to_capcut_draft,
    launch_capcut_desktop,
    sync_edits_from_capcut_draft,
)
from media_ops import (
    align_piece_text_to_audio,
    analyze_clip_energy_and_asr,
    download_web_image_for_item,
    extract_doctor_subject_image,
    extract_piece_audio_previews,
    parse_and_fetch_anh_nhac_list,
    parse_script_outline,
    parse_table_image_with_ai,
    parse_table_tsv_text,
)
from pipeline import (
    STEP_DEFINITIONS,
    cleanup_old_rendered_videos,
    create_project,
    create_sample_giodo1tr_project,
    create_sample_giodo5tr_project,
    delete_project_safe,
    execute_step,
    get_project_dir,
    list_projects,
    load_project_state,
    reset_project_state,
    save_project_state,
    start_pipeline_background,
)
from services.api_routes import dispatch_extra
from services.image_enhancer import enhance_options_from_request, safe_extract_doctor_subject_image
from services.project_meta import enrich_projects
from utils import (
    ffprobe_media,
    list_source_videos,
    load_config,
    move_to_recycle_bin,
    open_in_explorer,
    pick_file_dialog,
    read_json,
    save_config,
    write_json,
    write_text,
)


class AppRequestHandler(BaseHTTPRequestHandler):
    server_version = "VdChiaSeApp/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy console logging
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _serve_file_with_range(self, file_path: Path) -> None:
        if not file_path.is_file():
            self._send_json({"error": f"File not found: {file_path}"}, status=404)
            return
        ctype, _ = mimetypes.guess_type(str(file_path))
        if not ctype:
            ctype = "application/octet-stream"
        file_size = file_path.stat().st_size
        range_header = self.headers.get("Range")

        if range_header:
            m = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if m:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else file_size - 1
                end = min(end, file_size - 1)
                if start > end or start >= file_size:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{file_size}")
                    self.end_headers()
                    return
                chunk_len = end - start + 1
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(chunk_len))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                with file_path.open("rb") as f:
                    f.seek(start)
                    remaining = chunk_len
                    while remaining > 0:
                        buf = f.read(min(65536, remaining))
                        if not buf:
                            break
                        try:
                            self.wfile.write(buf)
                        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                            break
                        remaining -= len(buf)
                return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(file_size))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with file_path.open("rb") as f:
            while True:
                buf = f.read(65536)
                if not buf:
                    break
                try:
                    self.wfile.write(buf)
                except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                    break

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        try:
            if dispatch_extra(self, "GET", path, qs):
                return

            if path == "/api/config":
                self._send_json({"config": load_config(), "steps_meta": STEP_DEFINITIONS})
                return

            if path == "/api/projects":
                self._send_json({"projects": enrich_projects(list_projects())})
                return

            if path == "/api/system/source-videos":
                self._send_json({"videos": list_source_videos()})
                return

            m_proj = re.match(r"^/api/projects/([^/]+)$", path)
            if m_proj:
                pid = urllib.parse.unquote(m_proj.group(1))
                self._send_json(load_project_state(pid))
                return

            m_file = re.match(r"^/api/projects/([^/]+)/file$", path)
            if m_file:
                pid = urllib.parse.unquote(m_file.group(1))
                rel_or_abs = qs.get("path", [""])[0]
                pdir = get_project_dir(pid)
                cand = Path(rel_or_abs)
                if not cand.is_absolute():
                    cand = pdir / rel_or_abs
                self._serve_file_with_range(cand.resolve())
                return

            m_log = re.match(r"^/api/projects/([^/]+)/logs/(\d+)$", path)
            if m_log:
                pid = urllib.parse.unquote(m_log.group(1))
                step_num = int(m_log.group(2))
                pdir = get_project_dir(pid)
                lf = pdir / "logs" / f"step_{step_num:02d}.log"
                txt = lf.read_text(encoding="utf-8", errors="replace") if lf.is_file() else ""
                if step_num == 8 and (pdir / "logs" / "remotion_render.log").is_file():
                    r_txt = (pdir / "logs" / "remotion_render.log").read_text(encoding="utf-8", errors="replace")
                    txt += "\n--- REMOTION RENDER LOG ---\n" + r_txt[-4000:]
                self._send_json({"step": step_num, "log": txt})
                return

            # Static frontend files
            if path == "/" or path == "/index.html":
                self._serve_file_with_range(FRONTEND_DIR / "index.html")
                return
            rel_static = path.lstrip("/")
            static_file = (FRONTEND_DIR / rel_static).resolve()
            if str(static_file).startswith(str(FRONTEND_DIR.resolve())) and static_file.is_file():
                self._serve_file_with_range(static_file)
                return

            self._send_json({"error": "Not found"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc), "trace": traceback.format_exc()}, status=500)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        try:
            if dispatch_extra(self, "POST", path, qs):
                return

            if path == "/api/config":
                body = self._read_json_body()
                save_config(body)
                self._send_json({"ok": True, "config": load_config()})
                return

            if path == "/api/projects":
                body = self._read_json_body()
                proj = create_project(body)
                self._send_json(proj)
                return

            if path == "/api/projects/sample-giodo1tr":
                body = self._read_json_body()
                proj = create_sample_giodo1tr_project(
                    use_cached_analysis=bool(body.get("use_cached_analysis", True))
                )
                self._send_json(proj)
                return

            if path == "/api/projects/sample-giodo5tr":
                body = self._read_json_body()
                proj = create_sample_giodo5tr_project(
                    use_cached_analysis=bool(body.get("use_cached_analysis", True))
                )
                self._send_json(proj)
                return

            m_reset_proj = re.match(r"^/api/projects/([^/]+)/reset$", path)
            if m_reset_proj:
                pid = urllib.parse.unquote(m_reset_proj.group(1))
                body = self._read_json_body()
                keep_sources = bool(body.get("keep_sources", True))
                proj = reset_project_state(pid, keep_sources=keep_sources)
                self._send_json(proj)
                return

            m_del_proj = re.match(r"^/api/projects/([^/]+)/delete$", path)
            if m_del_proj:
                pid = urllib.parse.unquote(m_del_proj.group(1))
                res = delete_project_safe(pid)
                self._send_json(res)
                return

            if path == "/api/system/pick-file":
                body = self._read_json_body()
                chosen = pick_file_dialog(
                    title=body.get("title", "Chọn file"),
                    filter_str=body.get("filter", "Tất cả file (*.*)|*.*"),
                    initial_dir=body.get("initial_dir"),
                )
                probe_info = None
                if chosen and Path(chosen).is_file() and Path(chosen).suffix.lower() in (".mp4", ".mov", ".mkv", ".avi"):
                    try:
                        cfg = load_config()
                        probe_info = ffprobe_media(cfg["paths"]["ffprobe_exe"], Path(chosen))
                    except Exception:
                        pass
                self._send_json({"path": chosen, "probe": probe_info})
                return

            if path == "/api/system/probe":
                body = self._read_json_body()
                fpath = Path(body.get("path", ""))
                if not fpath.is_file():
                    self._send_json({"error": f"Không tìm thấy file: {fpath}"}, status=400)
                    return
                cfg = load_config()
                info = ffprobe_media(cfg["paths"]["ffprobe_exe"], fpath)
                self._send_json({"probe": info})
                return

            if path == "/api/system/open-explorer":
                body = self._read_json_body()
                target = Path(body.get("path", ""))
                if target.exists():
                    open_in_explorer(target)
                    self._send_json({"ok": True})
                else:
                    self._send_json({"error": f"Đường dẫn không tồn tại: {target}"}, status=400)
                return

            if path == "/api/system/recycle":
                body = self._read_json_body()
                target = Path(body.get("path", ""))
                ok = move_to_recycle_bin(target)
                self._send_json({"ok": ok, "path": str(target)})
                return

            # Project-scoped POST endpoints
            m_upload = re.match(r"^/api/projects/([^/]+)/upload$", path)
            if m_upload:
                pid = urllib.parse.unquote(m_upload.group(1))
                pdir = get_project_dir(pid)
                filename = os.path.basename(qs.get("filename", ["uploaded.bin"])[0])
                role = qs.get("role", ["nguon"])[0]
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw_bytes = self.rfile.read(length) if length > 0 else b""
                dest_dir = pdir / ("anh" if role == "product" else "nguon")
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / filename
                dest_path.write_bytes(raw_bytes)

                proj = read_json(pdir / "project.json")
                if role == "clip_a":
                    proj["clip_a_source"] = str(dest_path)
                    save_project_state(pdir, proj)
                elif role == "clip_b":
                    proj["clip_b_source"] = str(dest_path)
                    save_project_state(pdir, proj)
                elif role == "clip_aux":
                    aux_list = proj.get("clip_aux_sources", [])
                    aux_list.append({"who": "B", "path": str(dest_path), "label": dest_path.stem})
                    proj["clip_aux_sources"] = aux_list
                    save_project_state(pdir, proj)
                elif role == "product":
                    item_idx_str = qs.get("item_index", [""])[0]
                    if item_idx_str.isdigit():
                        item_idx = int(item_idx_str)
                        bang_data = read_json(pdir / "text" / "bang.json", {"items": []})
                        for it in bang_data.get("items", []):
                            if int(it.get("i", 0)) == item_idx:
                                it["custom_image_path"] = str(dest_path)
                                break
                        write_json(pdir / "text" / "bang.json", bang_data)
                        execute_step(pid, 6, force_recompute=True)
                        self._send_json({"ok": True, "path": str(dest_path), "project": load_project_state(pid)})
                        return

                probe_info = None
                if dest_path.suffix.lower() in (".mp4", ".mov", ".mkv"):
                    try:
                        cfg = load_config()
                        probe_info = ffprobe_media(cfg["paths"]["ffprobe_exe"], dest_path)
                    except Exception:
                        pass
                self._send_json({"ok": True, "path": str(dest_path), "probe": probe_info})
                return

            m_settings = re.match(r"^/api/projects/([^/]+)/settings$", path)
            if m_settings:
                pid = urllib.parse.unquote(m_settings.group(1))
                pdir = get_project_dir(pid)
                proj = read_json(pdir / "project.json")
                body = self._read_json_body()

                if "title" in body:
                    proj["title"] = str(body["title"]).strip()
                if "clip_a_source" in body:
                    proj["clip_a_source"] = str(body["clip_a_source"]).strip()
                if "clip_b_source" in body:
                    proj["clip_b_source"] = str(body["clip_b_source"]).strip()
                if "clip_aux_sources" in body:
                    proj["clip_aux_sources"] = body["clip_aux_sources"]
                if "chia_se_items" in body:
                    proj["chia_se_items"] = body["chia_se_items"]
                if "turn_listener_overrides" in body:
                    proj["turn_listener_overrides"] = body["turn_listener_overrides"]
                if "settings" in body and isinstance(body["settings"], dict):
                    proj.setdefault("settings", {}).update(body["settings"])
                raw_script_in = str(body.get("script_text") or "").strip()
                if "script_text" in body:
                    write_text(pdir / "text" / "kich_ban.md", raw_script_in + "\n")
                is_anh_nhac_mode = proj.get("settings", {}).get("preset") == "anh_nhac"
                if "bang" in body and isinstance(body["bang"], dict):
                    bang_in = body["bang"]
                    if is_anh_nhac_mode and raw_script_in:
                        outline = parse_script_outline(raw_script_in, current_title=proj.get("title", ""))
                        if outline.get("title"):
                            proj["title"] = outline["title"]
                            bang_in["tieu_de"] = outline["title"]
                        if outline.get("subtitle"):
                            bang_in["subtitle"] = outline["subtitle"]
                            proj.setdefault("settings", {})["summarySubtitle"] = outline["subtitle"].upper()
                        out_entries = outline.get("entries") or []
                        cur_items = bang_in.get("items") or []
                        if out_entries and len(out_entries) != len(cur_items):
                            try:
                                parsed_res = parse_and_fetch_anh_nhac_list(
                                    pdir,
                                    raw_script_in,
                                    current_title=outline["title"],
                                    use_ai=False,
                                )
                                bang_in = parsed_res["bang"]
                            except Exception:
                                pass
                    write_json(pdir / "text" / "bang.json", bang_in)
                    prep_p = pdir / "text" / "products_prepared.json"
                    if prep_p.is_file():
                        prep_data = read_json(prep_p, {"items": []})
                        b_map = {
                            int(it.get("i", i + 1)): it
                            for i, it in enumerate(bang_in.get("items", []))
                        }
                        for p_it in prep_data.get("items", []):
                            b_it = b_map.get(int(p_it.get("i", 0)))
                            if b_it and "image_scale" in b_it:
                                p_it["image_scale"] = float(b_it["image_scale"])
                        write_json(prep_p, prep_data)

                save_project_state(pdir, proj)
                self._send_json(load_project_state(pid))
                return

            m_cut = re.match(r"^/api/projects/([^/]+)/cut$", path)
            if m_cut:
                pid = urllib.parse.unquote(m_cut.group(1))
                pdir = get_project_dir(pid)
                body = self._read_json_body()
                cut_data = body.get("cut", body)
                write_json(pdir / "text" / "cut.json", cut_data)
                if body.get("regenerate_previews", True):
                    extract_piece_audio_previews(pdir, cut_data)
                    write_json(pdir / "text" / "cut.json", cut_data)
                self._send_json(load_project_state(pid))
                return

            m_align_piece = re.match(r"^/api/projects/([^/]+)/align-piece-text$", path)
            if m_align_piece:
                pid = urllib.parse.unquote(m_align_piece.group(1))
                pdir = get_project_dir(pid)
                body = self._read_json_body()
                ti = int(body.get("turn_index", 0))
                pi = int(body.get("piece_index", 0))
                cut_data = body.get("cut") or read_json(pdir / "text" / "cut.json", {})
                turn = cut_data["turns"][ti]
                piece = turn["pieces"][pi]
                who = str(turn.get("who") or "B")
                align_res = align_piece_text_to_audio(
                    pdir,
                    who=who,
                    target_text=str(piece.get("text") or ""),
                    cur_start=float(piece.get("start") or 0.0),
                    cur_end=float(piece.get("end") or 0.0),
                )
                sub_pieces = align_res.get("sub_pieces") or []
                orig_item = piece.get("item")
                if len(sub_pieces) > 1:
                    new_objs = []
                    item_assigned = False
                    for sp_idx, sp in enumerate(sub_pieces):
                        assign_it = None
                        if orig_item is not None and not item_assigned:
                            if "[" in sp.get("text", "") or sp_idx == 0:
                                assign_it = orig_item
                                item_assigned = True
                        new_objs.append(
                            {
                                "start": sp["start"],
                                "end": sp["end"],
                                "text": sp["text"],
                                "item": assign_it,
                                "custom_pad": sp["custom_pad"],
                                "pad_in": sp["pad_in"],
                                "pad_out": sp["pad_out"],
                            }
                        )
                    if pi > 0:
                        prev_end = float(turn["pieces"][pi - 1].get("end") or 0.0)
                        if new_objs[0]["start"] < prev_end:
                            new_objs[0]["start"] = round(prev_end + 0.02, 2)
                    if pi + 1 < len(turn["pieces"]):
                        next_start = float(turn["pieces"][pi + 1].get("start") or 0.0)
                        if next_start > 0 and new_objs[-1]["end"] > next_start:
                            new_objs[-1]["end"] = round(next_start - 0.02, 2)
                    turn["pieces"][pi : pi + 1] = new_objs
                else:
                    piece["start"] = align_res["start"]
                    piece["end"] = align_res["end"]
                    if pi > 0:
                        prev_end = float(turn["pieces"][pi - 1].get("end") or 0.0)
                        if piece["start"] < prev_end:
                            piece["start"] = round(prev_end + 0.02, 2)
                    if pi + 1 < len(turn["pieces"]):
                        next_start = float(turn["pieces"][pi + 1].get("start") or 0.0)
                        if next_start > 0 and piece["end"] > next_start:
                            piece["end"] = round(next_start - 0.02, 2)
                    piece["custom_pad"] = align_res["custom_pad"]
                    piece["pad_in"] = align_res["pad_in"]
                    piece["pad_out"] = align_res["pad_out"]
                write_json(pdir / "text" / "cut.json", cut_data)
                extract_piece_audio_previews(pdir, cut_data)
                write_json(pdir / "text" / "cut.json", cut_data)
                self._send_json(
                    {
                        "ok": True,
                        "alignment": align_res,
                        "project": load_project_state(pid),
                    }
                )
                return

            m_idle = re.match(r"^/api/projects/([^/]+)/idle$", path)
            if m_idle:
                pid = urllib.parse.unquote(m_idle.group(1))
                pdir = get_project_dir(pid)
                proj = read_json(pdir / "project.json")
                body = self._read_json_body()
                if "idle" in body:
                    write_json(pdir / "text" / "idle.json", body["idle"])
                if "turn_listener_overrides" in body:
                    proj["turn_listener_overrides"] = body["turn_listener_overrides"]
                if "clip_aux_sources" in body:
                    proj["clip_aux_sources"] = body["clip_aux_sources"]
                save_project_state(pdir, proj)
                self._send_json(load_project_state(pid))
                return

            m_bang = re.match(r"^/api/projects/([^/]+)/bang$", path)
            if m_bang:
                pid = urllib.parse.unquote(m_bang.group(1))
                pdir = get_project_dir(pid)
                body = self._read_json_body()
                bang_data = body.get("bang", body)
                write_json(pdir / "text" / "bang.json", bang_data)
                if body.get("run_step6", True):
                    execute_step(pid, 6, force_recompute=True)
                else:
                    prep_p = pdir / "text" / "products_prepared.json"
                    if prep_p.is_file():
                        prep_data = read_json(prep_p, {"items": []})
                        b_map = {
                            int(it.get("i", i + 1)): it
                            for i, it in enumerate(bang_data.get("items", []))
                        }
                        for p_it in prep_data.get("items", []):
                            b_it = b_map.get(int(p_it.get("i", 0)))
                            if b_it and "image_scale" in b_it:
                                p_it["image_scale"] = float(b_it["image_scale"])
                        write_json(prep_p, prep_data)
                self._send_json(load_project_state(pid))
                return

            m_parse_img = re.match(r"^/api/projects/([^/]+)/parse-table-image$", path)
            if m_parse_img:
                pid = urllib.parse.unquote(m_parse_img.group(1))
                pdir = get_project_dir(pid)
                proj = read_json(pdir / "project.json")
                ctype = (self.headers.get("Content-Type") or "").lower()
                provider = qs.get("provider", [proj.get("settings", {}).get("step6_provider", "agy")])[0]

                if "application/json" in ctype:
                    body = self._read_json_body()
                    provider = body.get("provider", provider)
                    src_p = body.get("path", "")
                    img_path = Path(src_p) if src_p else (pdir / "anh" / "bang_nguon.jpg")
                    if not img_path.is_file():
                        self._send_json({"error": f"Không tìm thấy ảnh bảng: {img_path}"}, status=400)
                        return
                else:
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw_bytes = self.rfile.read(length) if length > 0 else b""
                    if not raw_bytes:
                        self._send_json({"error": "Dữ liệu ảnh trống."}, status=400)
                        return
                    (pdir / "anh").mkdir(parents=True, exist_ok=True)
                    img_path = pdir / "anh" / "bang_upload_tmp.png"
                    img_path.write_bytes(raw_bytes)

                parsed_res = parse_table_image_with_ai(pdir, img_path, preferred_provider=provider)
                if parsed_res.get("title"):
                    proj["title"] = parsed_res["title"]
                if parsed_res.get("chia_se_items"):
                    proj["chia_se_items"] = parsed_res["chia_se_items"]
                write_json(pdir / "text" / "bang.json", parsed_res["bang"])
                write_text(pdir / "text" / "kich_ban.md", parsed_res["script_text"])
                save_project_state(pdir, proj)
                self._send_json({"ok": True, "parsed": parsed_res, "project": load_project_state(pid)})
                return

            m_parse_txt = re.match(r"^/api/projects/([^/]+)/parse-table-text$", path)
            if m_parse_txt:
                pid = urllib.parse.unquote(m_parse_txt.group(1))
                pdir = get_project_dir(pid)
                proj = read_json(pdir / "project.json")
                body = self._read_json_body()
                raw_text = str(body.get("text") or "")
                parsed_res = parse_table_tsv_text(raw_text, default_title=proj.get("title", ""))
                if parsed_res.get("title"):
                    proj["title"] = parsed_res["title"]
                write_json(pdir / "text" / "bang.json", parsed_res["bang"])
                write_text(pdir / "text" / "kich_ban.md", parsed_res["script_text"])
                save_project_state(pdir, proj)
                self._send_json({"ok": True, "parsed": parsed_res, "project": load_project_state(pid)})
                return

            m_parse_anh_nhac = re.match(r"^/api/projects/([^/]+)/parse-anh-nhac-list$", path)
            if m_parse_anh_nhac:
                pid = urllib.parse.unquote(m_parse_anh_nhac.group(1))
                pdir = get_project_dir(pid)
                proj = read_json(pdir / "project.json")
                body = self._read_json_body()
                raw_text = str(body.get("text") or "").strip()
                use_ai = bool(body.get("use_ai", False))
                custom_request = str(body.get("custom_request") or "").strip()
                cur_title = str(body.get("title") or proj.get("title") or "").strip()
                parsed_res = parse_and_fetch_anh_nhac_list(
                    pdir,
                    raw_text,
                    current_title=cur_title,
                    use_ai=use_ai,
                    custom_request=custom_request,
                )
                if parsed_res.get("title"):
                    proj["title"] = parsed_res["title"]
                proj.setdefault("settings", {})["preset"] = "anh_nhac"
                if parsed_res.get("subtitle"):
                    proj["settings"]["summarySubtitle"] = str(parsed_res["subtitle"]).upper()
                if "itemDurationSec" in body:
                    proj["settings"]["itemDurationSec"] = float(body.get("itemDurationSec") or 2.4)
                if "bgmPath" in body:
                    proj["settings"]["bgmPath"] = str(body.get("bgmPath") or "")
                rev_res = None
                if custom_request:
                    try:
                        rev_res = apply_final_revision_notes(pdir, proj, custom_request, use_ai=False)
                    except Exception:
                        pass
                save_project_state(pdir, proj)
                # Run Step 3, Step 5 & Step 6 so images and timeline are immediately prepared
                try:
                    execute_step(pid, 3, force_recompute=False, auto_approve=True)
                    execute_step(pid, 5, force_recompute=True, auto_approve=True)
                    execute_step(pid, 6, force_recompute=True, auto_approve=True)
                except Exception:
                    pass
                self._send_json({"ok": True, "parsed": parsed_res, "revision": rev_res, "project": load_project_state(pid)})
                return

            m_web_img = re.match(r"^/api/projects/([^/]+)/search-item-web-image$", path)
            if m_web_img:
                pid = urllib.parse.unquote(m_web_img.group(1))
                pdir = get_project_dir(pid)
                proj = read_json(pdir / "project.json")
                body = self._read_json_body()
                item_idx = int(body.get("item_index", 1))
                custom_q = str(body.get("custom_query") or "").strip()
                cycle_next = bool(body.get("cycle_next", True))

                bang_data = read_json(pdir / "text" / "bang.json", {"items": []})
                target_item = None
                for it in bang_data.get("items", []):
                    if int(it.get("i", 0)) == item_idx:
                        target_item = it
                        break
                if not target_item:
                    self._send_json({"error": f"Không tìm thấy mục #{item_idx}"}, status=404)
                    return

                cand_idx = int(target_item.get("web_candidate_index", 0))
                if cycle_next and not custom_q:
                    cand_idx = (cand_idx + 1) % 8
                elif custom_q:
                    cand_idx = 0

                web_cache_dir = pdir / "anh" / "web_items"
                web_cache_dir.mkdir(parents=True, exist_ok=True)
                from utils import slugify
                item_name = str(target_item.get("display_name") or target_item.get("ten") or f"item_{item_idx}").strip()
                out_img = web_cache_dir / f"item_{item_idx:02d}_{slugify(item_name)}_v{cand_idx}.png"
                dl = download_web_image_for_item(
                    item_name=item_name,
                    project_title=str(proj.get("title") or bang_data.get("tieu_de") or ""),
                    out_path=out_img,
                    candidate_index=cand_idx,
                    custom_query=custom_q,
                )
                if dl.get("ok") and dl.get("path"):
                    target_item["custom_image_path"] = dl["path"]
                    target_item["web_candidate_index"] = cand_idx
                    target_item["web_image_source"] = dl.get("source_title", "")
                    write_json(pdir / "text" / "bang.json", bang_data)
                    execute_step(pid, 6, force_recompute=True, auto_approve=True)

                self._send_json({"ok": bool(dl.get("ok")), "download": dl, "project": load_project_state(pid)})
                return

            m_doc_upload = re.match(r"^/api/projects/([^/]+)/upload-doctor-image$", path)
            if m_doc_upload:
                pid = urllib.parse.unquote(m_doc_upload.group(1))
                pdir = get_project_dir(pid)
                ctype = (self.headers.get("Content-Type") or "").lower()
                raw_dir = pdir / "anh" / "doctor_raw"
                edited_dir = pdir / "anh" / "doctor_edited"
                raw_dir.mkdir(parents=True, exist_ok=True)
                edited_dir.mkdir(parents=True, exist_ok=True)

                if "application/json" in ctype:
                    body = self._read_json_body()
                    item_idx = int(body.get("item_index", 1))
                    mode = str(body.get("mode") or "cutout")
                    crop_box = body.get("crop_box")
                    run_step6 = bool(body.get("run_step6", True))
                    src_p = Path(str(body.get("source_path") or ""))
                    if not src_p.is_file():
                        self._send_json({"error": f"Không tìm thấy file ảnh: {src_p}"}, status=400)
                        return
                    ext = src_p.suffix.lower() or ".png"
                    raw_path = raw_dir / f"item_{item_idx:02d}_raw{ext}"
                    if src_p.resolve() != raw_path.resolve():
                        shutil.copy2(src_p, raw_path)
                else:
                    item_idx = int(qs.get("item_index", ["1"])[0] or 1)
                    mode = str(qs.get("mode", ["cutout"])[0] or "cutout")
                    run_step6 = qs.get("run_step6", ["1"])[0] != "0"
                    crop_str = qs.get("crop_box", [""])[0]
                    crop_box = [float(x) for x in crop_str.split(",")] if crop_str and "," in crop_str else None
                    filename = os.path.basename(qs.get("filename", ["doctor.png"])[0])
                    ext = Path(filename).suffix.lower() or ".png"
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw_bytes = self.rfile.read(length) if length > 0 else b""
                    if not raw_bytes:
                        self._send_json({"error": "Dữ liệu ảnh tải lên trống."}, status=400)
                        return
                    raw_path = raw_dir / f"item_{item_idx:02d}_raw{ext}"
                    raw_path.write_bytes(raw_bytes)

                edited_path = edited_dir / f"item_{item_idx:02d}_doctor.png"
                enh_opts = enhance_options_from_request(body if "application/json" in ctype else qs)
                res = safe_extract_doctor_subject_image(
                    src_path=raw_path,
                    out_path=edited_path,
                    mode=mode,
                    crop_box=crop_box,
                    **enh_opts,
                )

                bang_data = read_json(pdir / "text" / "bang.json", {"items": []})
                for it in bang_data.get("items", []):
                    if int(it.get("i", 0)) == item_idx:
                        it["raw_image_path"] = str(raw_path)
                        it["custom_image_path"] = str(edited_path)
                        it["doctor_edit_mode"] = mode
                        it["doctor_crop_box"] = crop_box or res.get("suggested_crop_box")
                        it["is_scene_photo"] = True
                        it["is_doctor_cutout"] = mode in ("cutout", "cutout_plain")
                        break
                write_json(pdir / "text" / "bang.json", bang_data)

                if run_step6:
                    try:
                        execute_step(pid, 6, force_recompute=True, auto_approve=True)
                    except Exception:
                        pass

                self._send_json(
                    {
                        "ok": True,
                        "item_index": item_idx,
                        "result": res,
                        "raw_rel": f"anh/doctor_raw/{raw_path.name}",
                        "edited_rel": f"anh/doctor_edited/{edited_path.name}",
                        "project": load_project_state(pid),
                    }
                )
                return

            m_doc_edit = re.match(r"^/api/projects/([^/]+)/edit-doctor-image$", path)
            if m_doc_edit:
                pid = urllib.parse.unquote(m_doc_edit.group(1))
                pdir = get_project_dir(pid)
                body = self._read_json_body()
                mode = str(body.get("mode") or "cutout")
                crop_box = body.get("crop_box")
                preview_only = bool(body.get("preview_only", False))
                apply_all = bool(body.get("apply_all", False))
                item_idx = int(body.get("item_index", 1))

                raw_dir = pdir / "anh" / "doctor_raw"
                edited_dir = pdir / "anh" / "doctor_edited"
                raw_dir.mkdir(parents=True, exist_ok=True)
                edited_dir.mkdir(parents=True, exist_ok=True)

                bang_data = read_json(pdir / "text" / "bang.json", {"items": []})
                prep_data = read_json(pdir / "text" / "products_prepared.json", {"items": []})
                prep_by_i = {int(x.get("i", 0)): x for x in prep_data.get("items", [])}

                def _resolve_raw_for_item(b_it: dict[str, Any]) -> Path | None:
                    idx_num = int(b_it.get("i", 1))
                    r_p = b_it.get("raw_image_path")
                    if r_p and Path(r_p).is_file():
                        return Path(r_p)
                    # Check if raw_dir already has item_XX_raw.*
                    for cand in raw_dir.glob(f"item_{idx_num:02d}_raw.*"):
                        if cand.is_file():
                            b_it["raw_image_path"] = str(cand)
                            return cand
                    # Fall back to current custom_image_path or prepared product image and save a copy as raw
                    c_p = b_it.get("custom_image_path")
                    if c_p and Path(c_p).is_file() and "doctor_edited" not in str(c_p):
                        dst_raw = raw_dir / f"item_{idx_num:02d}_raw{Path(c_p).suffix or '.png'}"
                        shutil.copy2(c_p, dst_raw)
                        b_it["raw_image_path"] = str(dst_raw)
                        return dst_raw
                    pr_it = prep_by_i.get(idx_num, {})
                    src_im = pr_it.get("source_image") or ""
                    if src_im and Path(src_im).is_file() and "doctor_edited" not in str(src_im):
                        dst_raw = raw_dir / f"item_{idx_num:02d}_raw{Path(src_im).suffix or '.png'}"
                        shutil.copy2(src_im, dst_raw)
                        b_it["raw_image_path"] = str(dst_raw)
                        return dst_raw
                    img_f = pr_it.get("image_file") or ""
                    if img_f and (pdir / "anh" / "products" / img_f).is_file():
                        dst_raw = raw_dir / f"item_{idx_num:02d}_raw.png"
                        shutil.copy2(pdir / "anh" / "products" / img_f, dst_raw)
                        b_it["raw_image_path"] = str(dst_raw)
                        return dst_raw
                    return None

                if apply_all:
                    processed_count = 0
                    for b_it in bang_data.get("items", []):
                        idx_num = int(b_it.get("i", 1))
                        raw_p = _resolve_raw_for_item(b_it)
                        if not raw_p:
                            continue
                        ed_p = edited_dir / f"item_{idx_num:02d}_doctor.png"
                        res_i = safe_extract_doctor_subject_image(
                            src_path=raw_p,
                            out_path=ed_p,
                            mode=mode,
                            crop_box=None,
                            **enhance_options_from_request(body),
                        )
                        b_it["custom_image_path"] = str(ed_p)
                        b_it["doctor_edit_mode"] = mode
                        b_it["doctor_crop_box"] = res_i.get("suggested_crop_box")
                        b_it["is_scene_photo"] = True
                        b_it["is_doctor_cutout"] = mode in ("cutout", "cutout_plain")
                        processed_count += 1
                    write_json(pdir / "text" / "bang.json", bang_data)
                    execute_step(pid, 6, force_recompute=True, auto_approve=True)
                    self._send_json(
                        {
                            "ok": True,
                            "processed_count": processed_count,
                            "mode": mode,
                            "project": load_project_state(pid),
                        }
                    )
                    return

                target_it = next((x for x in bang_data.get("items", []) if int(x.get("i", 0)) == item_idx), None)
                if not target_it:
                    self._send_json({"error": f"Không tìm thấy mục #{item_idx}"}, status=404)
                    return

                raw_p = _resolve_raw_for_item(target_it)
                if not raw_p or not raw_p.is_file():
                    self._send_json({"error": f"Mục #{item_idx} chưa có ảnh gốc để tách/cắt hình bác sĩ. Hãy tải ảnh lên trước!"}, status=400)
                    return

                out_fname = f"preview_item_{item_idx:02d}.png" if preview_only else f"item_{item_idx:02d}_doctor.png"
                ed_p = edited_dir / out_fname
                res = safe_extract_doctor_subject_image(
                    src_path=raw_p,
                    out_path=ed_p,
                    mode=mode,
                    crop_box=crop_box,
                    **enhance_options_from_request(body),
                )

                if not preview_only:
                    target_it["custom_image_path"] = str(ed_p)
                    target_it["doctor_edit_mode"] = mode
                    target_it["doctor_crop_box"] = crop_box or res.get("suggested_crop_box")
                    target_it["is_scene_photo"] = True
                    target_it["is_doctor_cutout"] = mode in ("cutout", "cutout_plain")
                    write_json(pdir / "text" / "bang.json", bang_data)
                    execute_step(pid, 6, force_recompute=True, auto_approve=True)
                else:
                    # Save raw_image_path if newly resolved
                    write_json(pdir / "text" / "bang.json", bang_data)

                self._send_json(
                    {
                        "ok": True,
                        "item_index": item_idx,
                        "result": res,
                        "raw_rel": f"anh/doctor_raw/{raw_p.name}",
                        "edited_rel": f"anh/doctor_edited/{ed_p.name}",
                        "project": None if preview_only else load_project_state(pid),
                    }
                )
                return

            m_fine = re.match(r"^/api/projects/([^/]+)/fine-analyze$", path)
            if m_fine:
                pid = urllib.parse.unquote(m_fine.group(1))
                pdir = get_project_dir(pid)
                body = self._read_json_body()
                who = body.get("who", "A")
                t0 = float(body.get("from", 0.0))
                t1 = float(body.get("to", 15.0))
                gap = float(body.get("gap", 0.06))
                thr = float(body.get("thr", -48.0))
                clip_p = pdir / "nguon" / ("A_hoi.mp4" if who == "A" else "B_dap.mp4")
                res = analyze_clip_energy_and_asr(
                    clip_p,
                    who=who,
                    project_dir=pdir,
                    thr_db=thr,
                    gap_sec=gap,
                    t0=t0,
                    t1=t1,
                    write_project_files=False,
                )
                self._send_json(res)
                return

            m_run = re.match(r"^/api/projects/([^/]+)/run$", path)
            if m_run:
                pid = urllib.parse.unquote(m_run.group(1))
                body = self._read_json_body()
                start_step = int(body.get("start_step", 1))
                stop_at_gates = bool(body.get("stop_at_gates", True))
                single_step_only = bool(body.get("single_step_only", False))
                force_recompute = bool(body.get("force_recompute", False))
                res = start_pipeline_background(
                    pid,
                    start_step=start_step,
                    stop_at_gates=stop_at_gates,
                    single_step_only=single_step_only,
                    force_recompute=force_recompute,
                )
                self._send_json(res)
                return

            m_approve = re.match(r"^/api/projects/([^/]+)/approve$", path)
            if m_approve:
                pid = urllib.parse.unquote(m_approve.group(1))
                pdir = get_project_dir(pid)
                proj = read_json(pdir / "project.json")
                body = self._read_json_body()
                gate = body.get("gate") or proj.get("waiting_gate")

                if gate == "DUNG_1":
                    proj["steps"]["3"]["status"] = "done"
                    proj["steps"]["3"]["message"] = "Sếp đã duyệt DỪNG 1 (bản chữ & cut.json)."
                    proj["waiting_gate"] = None
                    save_project_state(pdir, proj)
                    res = start_pipeline_background(pid, start_step=4, stop_at_gates=True)
                elif gate == "DUNG_2":
                    proj["steps"]["4"]["status"] = "done"
                    proj["steps"]["4"]["message"] = "Sếp đã duyệt DỪNG 2 (ứng viên cảnh người nghe)."
                    proj["waiting_gate"] = None
                    save_project_state(pdir, proj)
                    res = start_pipeline_background(pid, start_step=5, stop_at_gates=True)
                elif gate == "DUNG_3":
                    proj["steps"]["7"]["status"] = "done"
                    proj["steps"]["7"]["message"] = "Sếp đã duyệt DỪNG 3 (3 ảnh mẫu Remotion)."
                    proj["waiting_gate"] = None
                    save_project_state(pdir, proj)
                    res = start_pipeline_background(pid, start_step=8, stop_at_gates=True)
                else:
                    self._send_json({"error": f"Không rõ điểm dừng cần duyệt: {gate}"}, status=400)
                    return

                self._send_json({"ok": True, "gate": gate, "run": res})
                return

            m_capcut = re.match(r"^/api/projects/([^/]+)/export-capcut$", path)
            if m_capcut:
                pid = urllib.parse.unquote(m_capcut.group(1))
                pdir = get_project_dir(pid)
                body = self._read_json_body()
                rebuild = bool(body.get("rebuild_timeline", False))
                custom_name = str(body.get("draft_name", "")).strip()

                if rebuild or not (pdir / "media" / "timeline.json").is_file():
                    if (pdir / "text" / "cut.json").is_file():
                        execute_step(pid, 5, force_recompute=True, auto_approve=True)
                if rebuild or not (pdir / "text" / "products_prepared.json").is_file():
                    if (pdir / "text" / "bang.json").is_file():
                        execute_step(pid, 6, force_recompute=True, auto_approve=True)

                proj = read_json(pdir / "project.json")
                cc_info = proj.get("capcut_draft")
                if not bool(body.get("skip_capcut", False)):
                    cc_info = export_project_to_capcut_draft(pdir, proj, custom_draft_name=custom_name)
                    proj["capcut_draft"] = cc_info
                    save_project_state(pdir, proj)

                    if body.get("open_capcut", False):
                        try:
                            launch_capcut_desktop()
                        except Exception:
                            pass

                self._send_json({"ok": True, "capcut_draft": cc_info, "project": load_project_state(pid)})
                return

            m_sync_cc = re.match(r"^/api/projects/([^/]+)/sync-from-capcut$", path)
            if m_sync_cc:
                pid = urllib.parse.unquote(m_sync_cc.group(1))
                pdir = get_project_dir(pid)
                proj = read_json(pdir / "project.json")
                sync_res = sync_edits_from_capcut_draft(pdir, proj)
                save_project_state(pdir, proj)
                if (pdir / "text" / "bang.json").is_file():
                    try:
                        execute_step(pid, 6, force_recompute=False, auto_approve=True)
                    except Exception:
                        pass
                self._send_json({"ok": True, "sync": sync_res, "project": load_project_state(pid)})
                return

            m_clean_vid = re.match(r"^/api/projects/([^/]+)/cleanup-old-renders$", path)
            if m_clean_vid:
                pid = urllib.parse.unquote(m_clean_vid.group(1))
                body = self._read_json_body()
                all_proj = bool(body.get("all_projects", False))
                res = cleanup_old_rendered_videos(pid, clean_all_projects=all_proj)
                self._send_json(res)
                return

            m_rev = re.match(r"^/api/projects/([^/]+)/apply-final-revision$", path)
            if m_rev:
                pid = urllib.parse.unquote(m_rev.group(1))
                pdir = get_project_dir(pid)
                body = self._read_json_body()
                notes = str(body.get("notes", "")).strip()
                script_text = str(body.get("script_text") or "").strip()
                reparse_script = bool(body.get("reparse_script", False))
                use_ai = bool(body.get("use_ai", False))
                rerender_mp4 = bool(body.get("rerender_mp4", False))
                open_cc = bool(body.get("open_capcut", False))
                export_cc = bool(body.get("export_capcut", False)) or open_cc
                restill_step7 = bool(body.get("restill_step7", False))

                proj = read_json(pdir / "project.json")
                is_anh_nhac_preset = proj.get("settings", {}).get("preset") == "anh_nhac"
                ran_fast_anh_nhac_ai = False
                if is_anh_nhac_preset:
                    kb_file = pdir / "text" / "kich_ban.md"
                    raw_kb = script_text or (kb_file.read_text(encoding="utf-8", errors="replace").strip() if kb_file.is_file() else "")
                    if script_text:
                        write_text(kb_file, script_text + "\n")
                    if raw_kb:
                        outline = parse_script_outline(raw_kb, current_title=proj.get("title", ""))
                        cur_bang = read_json(pdir / "text" / "bang.json", {"items": []})
                        cur_items = cur_bang.get("items") or []
                        outline_diff = outline.get("count", 0) > 0 and (
                            outline["count"] != len(cur_items)
                            or outline.get("title", "").upper() != str(proj.get("title") or "").upper()
                        )
                        if reparse_script or outline_diff or use_ai:
                            try:
                                parsed_res = parse_and_fetch_anh_nhac_list(
                                    pdir,
                                    raw_kb,
                                    current_title=outline.get("title") or proj.get("title", ""),
                                    use_ai=use_ai,
                                    custom_request=notes,
                                )
                                if parsed_res.get("title"):
                                    proj["title"] = parsed_res["title"]
                                if parsed_res.get("subtitle"):
                                    proj.setdefault("settings", {})["summarySubtitle"] = str(parsed_res["subtitle"]).upper()
                                ran_fast_anh_nhac_ai = True
                            except Exception:
                                pass
                elif script_text:
                    write_text(pdir / "text" / "kich_ban.md", script_text + "\n")

                rev_res = apply_final_revision_notes(
                    pdir,
                    proj,
                    notes,
                    use_ai=(use_ai and not ran_fast_anh_nhac_ai),
                )
                if ran_fast_anh_nhac_ai:
                    cur_b = read_json(pdir / "text" / "bang.json", {"items": []})
                    it_names = [str(it.get("display_name") or it.get("ten") or "") for it in (cur_b.get("items") or [])]
                    summary_msg = f"Đã phân tích kịch bản '{proj.get('title')}' ({len(it_names)} mục: {', '.join(it_names[:6])}) & cập nhật nội dung + hình ảnh theo yêu cầu"
                    rev_res["changes"] = [summary_msg] + [
                        c for c in (rev_res.get("changes") or []) if "Đã lưu yêu cầu chỉnh sửa" not in c
                    ]
                    if proj.get("revision_history"):
                        proj["revision_history"][0]["changes"] = rev_res["changes"]
                save_project_state(pdir, proj)

                # Rebuild timeline (if needed or at final step) & product cards so changes take effect immediately
                is_anh_nhac_preset = proj.get("settings", {}).get("preset") == "anh_nhac"
                need_s5 = rev_res.get("needs_step5", False) or not (pdir / "media" / "timeline.json").is_file() or not restill_step7
                if need_s5 and ((pdir / "text" / "cut.json").is_file() or is_anh_nhac_preset):
                    execute_step(pid, 5, force_recompute=True, auto_approve=True)
                if (pdir / "text" / "bang.json").is_file():
                    execute_step(pid, 6, force_recompute=True, auto_approve=True)

                if restill_step7 and not rerender_mp4:
                    execute_step(pid, 7, force_recompute=True, auto_approve=False)

                proj = read_json(pdir / "project.json")
                cc_info = None
                if export_cc:
                    try:
                        cc_info = export_project_to_capcut_draft(pdir, proj)
                        proj["capcut_draft"] = cc_info
                        save_project_state(pdir, proj)
                    except Exception:
                        pass

                if open_cc:
                    try:
                        launch_capcut_desktop()
                    except Exception:
                        pass

                run_info = None
                if rerender_mp4:
                    proj["pipeline_status"] = "running"
                    proj["current_step"] = 7
                    proj["render_progress"] = {
                        "percent": 2,
                        "rendered_frames": 0,
                        "total_frames": 1200,
                        "phase": "⏳ Đang chụp lại Ảnh mẫu & Render lại Video MP4 theo chỉnh sửa mới...",
                    }
                    save_project_state(pdir, proj)
                    run_info = start_pipeline_background(
                        pid,
                        start_step=7,
                        stop_at_gates=False,
                        force_recompute=True,
                    )

                self._send_json({
                    "ok": True,
                    "revision": rev_res,
                    "capcut_draft": cc_info,
                    "run": run_info,
                    "project": load_project_state(pid),
                })
                return

            if path == "/api/system/open-capcut":
                res = launch_capcut_desktop()
                self._send_json(res)
                return

            self._send_json({"error": "Not found"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc), "trace": traceback.format_exc()}, status=500)


def main() -> None:
    cfg = load_config()
    port = int(cfg.get("port", 8765))
    if "--port" in sys.argv and sys.argv.index("--port") + 1 < len(sys.argv):
        port = int(sys.argv[sys.argv.index("--port") + 1])
    host = "127.0.0.1"
    if "--no-demo" not in sys.argv:
        try:
            from services.demo_seed import ensure_demo_projects

            ensure_demo_projects()
        except Exception as exc:
            print(f"[Cảnh báo] Không tạo được dự án mẫu: {exc}", flush=True)
    server = ThreadingHTTPServer((host, port), AppRequestHandler)
    url = f"http://{host}:{port}"
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print(f"Server running at {url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
