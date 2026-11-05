import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import re
from pathlib import Path
from typing import Any

from utils import CREATE_NO_WINDOW, load_config, read_json, run_hidden, slugify, write_json


def _format_vn_price(num: Any, mask_last_digit: bool = True, suffix: str = " K") -> str:
    n = int(float(num or 0))
    if mask_last_digit:
        if n < 10:
            return f"{n}{suffix}"
        if n >= 1000:
            s = str(n)
            return f"{s[:-3]}.{s[-3:-1]}x{suffix}"
        return f"{str(n)[:-1]}x{suffix}"
    if n >= 1000:
        s = str(n)
        return f"{s[:-3]}.{s[-3:]}{suffix}"
    return f"{n}{suffix}"

VENDOR_DIR = Path(__file__).resolve().parent / "capcut_vendor"
if str(VENDOR_DIR / "capcut-deps") not in sys.path:
    sys.path.append(str(VENDOR_DIR / "capcut-deps"))
if str(VENDOR_DIR / "capcut-draft-importer") not in sys.path:
    sys.path.append(str(VENDOR_DIR / "capcut-draft-importer"))

try:
    import pycapcut as cc
    from capcut_draft_importer.portable_import import (
        _clear_template_timeline_state,
        _md5_file,
        _write_id_mapping,
        _write_local_metadata,
        _write_project_files,
    )

    CAPCUT_EXPORT_AVAILABLE = True
    CAPCUT_IMPORT_ERROR = ""
except ImportError as _cc_import_err:  # Cloud/Linux: thư mục capcut_vendor/ không được đóng gói
    cc = None
    CAPCUT_EXPORT_AVAILABLE = False
    CAPCUT_IMPORT_ERROR = str(_cc_import_err)


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def _frame_to_us(frame: int, fps: int = 30) -> int:
    return round(int(frame) * 1_000_000 / fps)


def _save_compact_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _is_capcut_running() -> bool:
    try:
        res = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
        )
        return res.returncode == 0 and '"CapCut.exe"' in res.stdout
    except Exception:
        return False


def export_project_to_capcut_draft(
    pdir: Path,
    proj: dict[str, Any],
    custom_draft_name: str = "",
) -> dict[str, Any]:
    """
    Build a native CapCut Desktop 9.2.8 multi-track draft from project timeline & media,
    save a local copy in <pdir>/capcut_draft/, and install + register it directly in
    C:\\Users\\Dung\\AppData\\Local\\CapCut\\User Data\\Projects\\com.lveditor.draft
    """
    if not CAPCUT_EXPORT_AVAILABLE:
        raise RuntimeError(
            "Chưa có thư viện xuất CapCut (backend/capcut_vendor/ — pycapcut). "
            f"Tính năng này chỉ chạy trên máy Windows đã cài đủ. Chi tiết: {CAPCUT_IMPORT_ERROR}"
        )
    cfg = load_config()
    ffmpeg_exe = cfg["paths"]["ffmpeg_exe"]
    remotion_dir = Path(cfg["paths"]["remotion_dir"])

    timeline_path = pdir / "media" / "timeline.json"
    if not timeline_path.is_file():
        raise RuntimeError("Chưa có media/timeline.json (Cần chạy đến Bước 5 trước khi xuất CapCut Draft).")

    timeline = read_json(timeline_path)
    fps = int(timeline.get("fps", 30))
    voice_frames = int(timeline.get("frames", 900))
    settings = proj.get("settings", {})
    preset = settings.get("preset", "giodo")
    asker_side = settings.get("askerSide", "right")
    mask_price = settings.get("maskPrice", True)
    tail_frames = 151 if preset == "giodo" else 0
    total_frames = voice_frames + tail_frames
    total_duration_us = _frame_to_us(total_frames, fps)

    media_dir_name = f"convo_app_{proj['slug']}"
    remotion_media_dir = remotion_dir / "public" / media_dir_name

    bang = read_json(pdir / "text" / "bang.json", {"items": []})
    prod_prep = read_json(pdir / "text" / "products_prepared.json", {"items": []})
    bang_by_i = {int(it.get("i", idx + 1)): it for idx, it in enumerate(bang.get("items", []))}
    products_list = prod_prep.get("items") or bang.get("items", [])
    prod_by_i: dict[int, dict[str, Any]] = {}
    for idx, it in enumerate(products_list):
        i_num = int(it.get("i", idx + 1))
        merged_it = dict(it)
        if i_num in bang_by_i:
            b_it = bang_by_i[i_num]
            for k_sync in ("image_scale", "display_name", "sl", "dv", "gia", "name_and_qty"):
                if k_sync in b_it and b_it[k_sync] not in (None, ""):
                    merged_it[k_sync] = b_it[k_sync]
        prod_by_i[i_num] = merged_it

    # Determine ASCII-safe draft folder name (just like 'Thit kho tau RAW v2' in CapCut 9.x)
    raw_title = (custom_draft_name or proj.get("title") or proj["slug"]).strip()
    ascii_slug = slugify(raw_title).replace("-", " ").title()
    short_tag = proj["id"].split("_")[-1] if "_" in proj.get("id", "") else proj.get("slug", "")[:6]
    draft_name = f"{ascii_slug} {short_tag}".strip()

    capcut_root = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Dung\AppData\Local")) / (
        r"CapCut\User Data\Projects\com.lveditor.draft"
    )
    # Prefer the most recent local CapCut draft in com.lveditor.draft (e.g. 1025 or 1010) as donor for exact version match
    template_dir = VENDOR_DIR / "template_0819"
    for cand_name in ("1025", "1024", "1021", "1010"):
        cand_dir = capcut_root / cand_name
        if (cand_dir / "draft_content.json").is_file() and (cand_dir / "draft_meta_info.json").is_file():
            template_dir = cand_dir
            break
    if not template_dir.is_dir():
        raise RuntimeError(f"Không tìm thấy template CapCut mẫu tại: {template_dir}")

    # Build in project's local staging folder first
    local_pack_dir = pdir / "capcut_draft"
    if local_pack_dir.exists():
        shutil.rmtree(local_pack_dir, ignore_errors=True)
    project_draft_dir = local_pack_dir / draft_name
    res_dir = project_draft_dir / "Resources"
    orig_dir = project_draft_dir / "Nguon goc"
    res_dir.mkdir(parents=True, exist_ok=True)
    orig_dir.mkdir(parents=True, exist_ok=True)

    donor_content = read_json(template_dir / "draft_content.json")
    donor_meta = read_json(template_dir / "draft_meta_info.json")

    prev_cc = proj.get("capcut_draft") or {}
    timeline_id = _uid()
    draft_id = prev_cc.get("draft_id") or _uid()
    project_id = _uid()
    now_us = time.time_ns() // 1000

    script = cc.ScriptFile(1080, 1080, fps)
    script.content = copy.deepcopy(donor_content)
    script.content.update(
        id=timeline_id,
        name=draft_name,
        create_time=now_us,
        update_time=now_us,
        fps=float(fps),
    )

    # Create multi-layer video, image & editable text tracks matching Remotion 1080x1080 layout
    script.add_track(cc.TrackType.video, "Người ĐÁP (B)", relative_index=0)
    script.add_track(cc.TrackType.video, "Người HỎI (A)", relative_index=1)
    script.add_track(cc.TrackType.video, "Ảnh Sản Phẩm PNG", relative_index=2)
    script.add_track(cc.TrackType.video, "Bảng Tổng / Ảnh Mẫu", relative_index=3)
    script.add_track(cc.TrackType.text, "Tên Sản Phẩm (Text)", relative_index=0)
    script.add_track(cc.TrackType.text, "Giá Tiền (Text)", relative_index=1)
    script.add_track(cc.TrackType.text, "Tiêu Đề (Text)", relative_index=2)
    script.add_track(cc.TrackType.audio, "Voice Hội Thoại", relative_index=0)
    script.add_track(cc.TrackType.audio, "SFX Hiệu Ứng", relative_index=1)

    # Compute exact Remotion 1080x1080 canvas transforms for 720x1280 source clips
    # In Remotion (SIZE=1080):
    #   isRightSide: faceX = 810 else 270
    #   s = scaleA (1.0) or scaleB (1.06)
    #   left = faceX - cropVal * s, top = -topVal, width = 720 * s, height = 1280 * s
    # In CapCut (1080x1080 canvas), a 720x1280 clip at scale=1.0 has height=1080px, width=607.5px.
    # So CapCut scale = (1280 * s) / 1080, transform_x = (cx - 540) / 540, transform_y = (540 - cy) / 540.
    def _person_clip_settings(who: str) -> cc.ClipSettings:
        asker_on_right = asker_side != "left"
        is_right = (who == "A" and asker_on_right) or (who == "B" and not asker_on_right)
        face_x = 810.0 if is_right else 270.0
        s = float(settings.get("scaleA", 1.0) if who == "A" else settings.get("scaleB", 1.06))
        crop_val = float(settings.get("cropA", 329.0) if who == "A" else settings.get("cropB", 325.0))
        top_val = float(settings.get("topA", 180.0) if who == "A" else settings.get("topB", 215.0))
        w_px = 720.0 * s
        h_px = 1280.0 * s
        left_px = face_x - crop_val * s
        top_px = -top_val
        cx = left_px + w_px / 2.0
        cy = top_px + h_px / 2.0
        cc_scale = round(h_px / 1080.0, 4)
        tx = round((cx - 540.0) / 540.0, 4)
        ty = round((540.0 - cy) / 540.0, 4)
        return cc.ClipSettings(
            transform_x=tx,
            transform_y=ty,
            scale_x=cc_scale,
            scale_y=cc_scale,
        )

    clip_cfg_b = _person_clip_settings("B")
    clip_cfg_a = _person_clip_settings("A")

    # Helper to add Track A / Track B segments sequentially without overlap
    def _populate_person_track(
        track_items: list[dict[str, Any]],
        track_name: str,
        clip_cfg: cc.ClipSettings,
    ) -> int:
        cursor_us = 0
        added_count = 0
        for idx, seg_info in enumerate(track_items):
            fname = seg_info.get("file", "")
            src_file = remotion_media_dir / fname
            if not src_file.is_file():
                continue
            dst_file = res_dir / fname
            if not dst_file.exists():
                shutil.copy2(src_file, dst_file)

            start_f = int(seg_info.get("from", 0))
            dur_f = int(seg_info.get("frames", 30))
            # If last segment and giodo tail exists, extend last hold segment to cover tail_frames
            if idx == len(track_items) - 1 and tail_frames > 0:
                dur_f += tail_frames

            seg_start_us = max(cursor_us, _frame_to_us(start_f, fps))
            seg_end_us = _frame_to_us(start_f + dur_f, fps)
            seg_dur_us = max(33_333, seg_end_us - seg_start_us)

            mat = cc.VideoMaterial(str(dst_file), material_name=fname)
            mat.local_material_id = mat.material_id
            if mat.material_type == "video" and mat.duration < seg_dur_us:
                mat.duration = seg_dur_us

            vseg = cc.VideoSegment(
                mat,
                cc.Timerange(seg_start_us, seg_dur_us),
                source_timerange=cc.Timerange(0, seg_dur_us),
                volume=0.0,
                clip_settings=copy.deepcopy(clip_cfg),
            )
            script.add_segment(vseg, track_name)
            cursor_us = seg_start_us + seg_dur_us
            added_count += 1
        return added_count

    vtracks = timeline.get("visualTracks") or {}
    count_b = _populate_person_track(vtracks.get("B") or timeline.get("trackB", []), "Người ĐÁP (B)", clip_cfg_b)
    count_a = _populate_person_track(vtracks.get("A") or timeline.get("trackA", []), "Người HỎI (A)", clip_cfg_a)

    # Map app font key to native CapCut FontType (defaulting to Anton as sếp's favorite)
    def _resolve_capcut_font(font_key: str) -> Any:
        if not hasattr(cc, "FontType"):
            return None
        ft = cc.FontType
        mapping = {
            "Anton": getattr(ft, "Anton", None),
            "BarlowCondensed": getattr(ft, "BebasNeue", getattr(ft, "Anton", None)),
            "BeVietnamPro": getattr(ft, "Poppins_Bold", getattr(ft, "Anton", None)),
            "Montserrat": getattr(ft, "Montserrat", getattr(ft, "Anton", None)),
            "Oswald": getattr(ft, "BebasNeue", getattr(ft, "Anton", None)),
            "Baloo2": getattr(ft, "CC_Bouncy_Sans", getattr(ft, "Anton", None)),
            "PaytoneOne": getattr(ft, "Poppins_Bold", getattr(ft, "Anton", None)),
            "Bangers": getattr(ft, "BANGERS", getattr(ft, "Anton", None)),
            "Phudu": getattr(ft, "Anton", None),
            "Coiny": getattr(ft, "CC_Bouncy_Sans", getattr(ft, "Anton", None)),
            "Kanit": getattr(ft, "Poppins_Bold", getattr(ft, "Anton", None)),
            "ChakraPetch": getattr(ft, "Core_Sans_D_77_Cn_Black", getattr(ft, "Anton", None)),
            "Mali": getattr(ft, "ReenieBeanie_Regular", getattr(ft, "Anton", None)),
            "PatrickHand": getattr(ft, "ReenieBeanie_Regular", getattr(ft, "Anton", None)),
            "Lexend": getattr(ft, "PublicSans", getattr(ft, "Anton", None)),
        }
        return mapping.get(font_key) or getattr(ft, "Anton", None)

    cc_title_font = _resolve_capcut_font(settings.get("titleFont", "Anton"))
    cc_sub_font = _resolve_capcut_font(settings.get("subFont", "Anton"))

    # Title Text Track ("GIỎ ĐỒ 5TR" at top center, y=140px -> transform_y=+0.74)
    video_title_text = (proj.get("title") or bang.get("tieu_de") or "GIỎ ĐỒ ĐI SINH").strip().upper()
    voice_dur_us = _frame_to_us(voice_frames, fps)
    if video_title_text and voice_dur_us > 0:
        title_seg = cc.TextSegment(
            video_title_text,
            cc.Timerange(0, voice_dur_us),
            font=cc_title_font,
            style=cc.TextStyle(
                size=15.0,
                bold=True,
                color=(1.0, 1.0, 1.0),
                align=1,
            ),
            border=cc.TextBorder(
                color=(0.0, 0.0, 0.0),
                width=65.0,
            ),
            clip_settings=cc.ClipSettings(
                transform_x=0.0,
                transform_y=0.74,
            ),
        )
        script.add_segment(title_seg, "Tiêu Đề (Text)")

    # Track 3 + Editable Text Tracks: Product PNGs (bottom-left) + Product Name & Price (bottom-right)
    # In Remotion GioDoItemCard:
    #   Left person center X = 270 -> transform_x = -0.50, center Y = 827.5 -> transform_y = -0.5324, scale = 400/1080 = 0.3704
    #   Right person center X = 810 -> transform_x = +0.50 (centered on right person / viewer perspective)
    #     Product Name (larger 50px): center Y = 750 -> transform_y = -0.3889, size = 12.5
    #     Product Price (105px red #E5121F): center Y = 865 -> transform_y = -0.6019, size = 23.0
    left_center_x = float(settings.get("productLeftCenterX", 270.0))
    right_center_x = float(settings.get("productRightCenterX", 810.0))
    prod_img_px = float(settings.get("productImageSize", 400.0))
    prod_name_px = float(settings.get("productNameFontSize", 50.0))
    prod_price_px = float(settings.get("productPriceFontSize", 105.0))
    card_top_px = float(settings.get("productCardTop", 610.0))
    card_center_y = (card_top_px + 1045.0) / 2.0
    cc_prod_tx = round((left_center_x - 540.0) / 540.0, 4)
    cc_prod_ty = round((540.0 - card_center_y) / 540.0, 4)
    cc_text_tx = round((right_center_x - 540.0) / 540.0, 4)
    cc_prod_scale = round(prod_img_px / 1080.0, 4)
    cc_name_size = round(prod_name_px * 0.25, 2)
    cc_price_size = round(prod_price_px * 0.22, 2)

    marks_sorted = sorted(
        ((int(k), int(v)) for k, v in (timeline.get("itemMarks") or {}).items()),
        key=lambda x: x[1],
    )
    prod_Cursor_us = 0
    prod_added = 0
    for m_idx, (item_num, f_start) in enumerate(marks_sorted):
        f_end = marks_sorted[m_idx + 1][1] if (m_idx + 1 < len(marks_sorted)) else voice_frames
        if f_end <= f_start:
            f_end = f_start + 30
        start_us = max(prod_Cursor_us, _frame_to_us(f_start, fps))
        end_us = _frame_to_us(f_end, fps)
        dur_us = max(33_333, end_us - start_us)

        p_info = prod_by_i.get(item_num)
        if p_info:
            img_fname = p_info.get("image_file", "")
            img_src = pdir / "anh" / "products" / img_fname if img_fname else None
            if img_src and img_src.is_file():
                dst_img = res_dir / img_fname
                if not dst_img.exists():
                    shutil.copy2(img_src, dst_img)
                p_mat = cc.VideoMaterial(
                    str(dst_img),
                    material_name=f"SP #{item_num:02d} {p_info.get('display_name') or p_info.get('ten')}",
                )
                p_mat.local_material_id = p_mat.material_id
                item_scale = float(p_info.get("image_scale") or 1.0)
                if item_scale <= 0:
                    item_scale = 1.0
                eff_scale = round(cc_prod_scale * item_scale, 4)
                p_clip = cc.ClipSettings(
                    transform_x=cc_prod_tx,
                    transform_y=cc_prod_ty,
                    scale_x=eff_scale,
                    scale_y=eff_scale,
                )
                p_seg = cc.VideoSegment(
                    p_mat,
                    cc.Timerange(start_us, dur_us),
                    source_timerange=cc.Timerange(0, dur_us),
                    volume=0.0,
                    clip_settings=p_clip,
                )
                script.add_segment(p_seg, "Ảnh Sản Phẩm PNG")
                prod_added += 1

            # Editable Product Name + Qty Text Segment
            base_name = (p_info.get("display_name") or p_info.get("ten") or "").strip()
            sl = p_info.get("sl", "")
            dv = p_info.get("dv", "")
            qty_txt = f"{sl} {dv}".strip() if sl else ""
            full_label = (p_info.get("name_and_qty") or f"{base_name} {qty_txt}").strip().upper()
            price_suffix = settings.get("priceSuffix", " K")
            price_str = _format_vn_price(p_info.get("gia", 0), mask_price, price_suffix)

            if full_label:
                name_seg = cc.TextSegment(
                    full_label,
                    cc.Timerange(start_us, dur_us),
                    font=cc_sub_font,
                    style=cc.TextStyle(
                        size=cc_name_size,
                        bold=True,
                        color=(0.07, 0.07, 0.07),
                        align=1,
                        auto_wrapping=True,
                        max_line_width=0.48,
                    ),
                    border=cc.TextBorder(
                        color=(1.0, 1.0, 1.0),
                        width=68.0,
                    ),
                    clip_settings=cc.ClipSettings(
                        transform_x=cc_text_tx,
                        transform_y=-0.3889,
                    ),
                )
                script.add_segment(name_seg, "Tên Sản Phẩm (Text)")

            if price_str:
                price_seg = cc.TextSegment(
                    price_str,
                    cc.Timerange(start_us, dur_us),
                    font=cc_sub_font,
                    style=cc.TextStyle(
                        size=cc_price_size,
                        bold=True,
                        color=(0.898, 0.071, 0.122),
                        align=1,
                    ),
                    border=cc.TextBorder(
                        color=(1.0, 1.0, 1.0),
                        width=75.0,
                    ),
                    clip_settings=cc.ClipSettings(
                        transform_x=cc_text_tx,
                        transform_y=-0.6019,
                    ),
                )
                script.add_segment(price_seg, "Giá Tiền (Text)")

        prod_Cursor_us = start_us + dur_us

    # Track 4: Summary Table at the tail (if still_3_end.png exists)
    still3_path = pdir / "final" / "still_3_end.png"
    if tail_frames > 0 and still3_path.is_file():
        dst_still3 = res_dir / "bang_tong_cuoi.png"
        shutil.copy2(still3_path, dst_still3)
        s_mat = cc.VideoMaterial(str(dst_still3), material_name="Bảng Tổng Kết Cuối")
        s_mat.local_material_id = s_mat.material_id
        s_start_us = _frame_to_us(voice_frames, fps)
        s_dur_us = _frame_to_us(tail_frames, fps)
        s_seg = cc.VideoSegment(
            s_mat,
            cc.Timerange(s_start_us, s_dur_us),
            source_timerange=cc.Timerange(0, s_dur_us),
            volume=0.0,
        )
        script.add_segment(s_seg, "Bảng Tổng / Ảnh Mẫu")

    # Audio Track 1: Joined Conversation Voice (voice.m4a)
    voice_wav = pdir / "media" / "voice.wav"
    if voice_wav.is_file():
        voice_m4a = res_dir / "voice_hoi_thoai.m4a"
        run_hidden(
            [
                ffmpeg_exe,
                "-hide_banner",
                "-y",
                "-i",
                str(voice_wav),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(voice_m4a),
            ]
        )
        v_dur_us = _frame_to_us(voice_frames, fps)
        a_mat = cc.AudioMaterial(str(voice_m4a), material_name="Voice Hội Thoại Đã Ghép")
        a_mat.duration = max(a_mat.duration, v_dur_us)
        a_seg = cc.AudioSegment(
            a_mat,
            cc.Timerange(0, v_dur_us),
            source_timerange=cc.Timerange(0, v_dur_us),
            volume=1.0,
        )
        script.add_segment(a_seg, "Voice Hội Thoại")

    # Audio Track 2: SFX Pop at each product mark & Ting at summary table
    pop_src = remotion_media_dir / "sfx_pop.mp3"
    ting_src = remotion_media_dir / "sfx_ting.mp3"
    sfx_cursor_us = 0
    if pop_src.is_file():
        dst_pop = res_dir / "sfx_pop.mp3"
        shutil.copy2(pop_src, dst_pop)
        for _, f_mark in marks_sorted:
            m_start_us = _frame_to_us(f_mark, fps)
            if m_start_us < sfx_cursor_us:
                continue
            pop_mat = cc.AudioMaterial(str(dst_pop), material_name="SFX Pop")
            pop_dur_us = min(pop_mat.duration, 250_000)
            pop_seg = cc.AudioSegment(
                pop_mat,
                cc.Timerange(m_start_us, pop_dur_us),
                source_timerange=cc.Timerange(0, pop_dur_us),
                volume=0.45,
            )
            script.add_segment(pop_seg, "SFX Hiệu Ứng")
            sfx_cursor_us = m_start_us + pop_dur_us + 10_000

    if tail_frames > 0 and ting_src.is_file():
        dst_ting = res_dir / "sfx_ting.mp3"
        shutil.copy2(ting_src, dst_ting)
        t_start_us = max(sfx_cursor_us, _frame_to_us(voice_frames, fps))
        ting_mat = cc.AudioMaterial(str(dst_ting), material_name="SFX Ting Bảng Tổng")
        ting_dur_us = min(ting_mat.duration, 800_000)
        ting_seg = cc.AudioSegment(
            ting_mat,
            cc.Timerange(t_start_us, ting_dur_us),
            source_timerange=cc.Timerange(0, ting_dur_us),
            volume=0.55,
        )
        script.add_segment(ting_seg, "SFX Hiệu Ứng")

    # Copy full rendered video into Resources if Step 8 was already run (so it's in CapCut's media bin)
    exports = proj.get("exports", {})
    full_render_p = Path(exports.get("full_path", "")) if exports else None
    if full_render_p and full_render_p.is_file():
        shutil.copy2(full_render_p, res_dir / full_render_p.name)

    # Copy original uncut A_hoi.mp4 and B_dap.mp4 into Nguon goc/
    for src_name in ("A_hoi.mp4", "B_dap.mp4"):
        sp = pdir / "nguon" / src_name
        if sp.is_file():
            shutil.copy2(sp, orig_dir / src_name)

    # Determine final target path inside CapCut Desktop Drafts root
    capcut_installed_dir = (capcut_root / draft_name) if capcut_root.is_dir() else project_draft_dir

    content = json.loads(script.dumps())
    content["canvas_config"]["ratio"] = "1:1"
    content["canvas_config"]["width"] = 1080
    content["canvas_config"]["height"] = 1080
    content["materials"] = {**{k: [] for k in donor_content["materials"]}, **content["materials"]}
    _clear_template_timeline_state(content)

    # Point material paths to the installed CapCut draft Resources folder
    target_res_dir = capcut_installed_dir / "Resources"
    for kind in ("videos", "audios"):
        for mat in content["materials"].get(kind, []):
            fname = Path(mat["path"]).name
            mat["path"] = (target_res_dir / fname).as_posix()
            mat["local_material_id"] = mat["id"]

    tl_dir = project_draft_dir / "Timelines" / timeline_id
    for folder in (project_draft_dir, tl_dir):
        for fn in ("draft_content.json", "draft_content.json.bak", "template-2.tmp"):
            _save_compact_json(folder / fn, content)

    _write_id_mapping(project_draft_dir, tl_dir, content)
    _write_project_files(
        project_draft_dir,
        project_id=project_id,
        timeline_id=timeline_id,
        name="Dòng thời gian 01",
        now_us=now_us,
    )
    _write_local_metadata(
        project_draft_dir,
        donor_metadata=donor_meta,
        content=content,
        draft_id=draft_id,
        final_path=capcut_installed_dir,
        drafts_root=capcut_installed_dir.parent,
        output_name=draft_name,
        now_us=now_us,
    )

    for fn in (
        "draft_agency_config.json",
        "draft_biz_config.json",
        "attachment_pc_common.json",
        "performance_opt_info.json",
    ):
        if (template_dir / fn).is_file():
            shutil.copy2(template_dir / fn, project_draft_dir / fn)

    # Create draft_cover.jpg from still_1_open.png or A_001.jpg
    cover_path = project_draft_dir / "draft_cover.jpg"
    still1 = pdir / "final" / "still_1_open.png"
    first_jpg = next(remotion_media_dir.glob("*.jpg"), None)
    cover_src = still1 if still1.is_file() else first_jpg
    if cover_src and cover_src.is_file():
        run_hidden(
            [
                ffmpeg_exe,
                "-hide_banner",
                "-y",
                "-i",
                str(cover_src),
                "-frames:v",
                "1",
                "-vf",
                "scale=540:540",
                str(cover_path),
            ]
        )

    localmeta = read_json(project_draft_dir / "draft_meta_info.json")
    localmeta.update(
        draft_cover=(capcut_installed_dir / "draft_cover.jpg").as_posix(),
        draft_json_file=(capcut_installed_dir / "draft_content.json").as_posix(),
    )
    # If full_render_p was copied into Resources, also register it in draft_materials[0] so it appears in Media Bin
    if full_render_p and (res_dir / full_render_p.name).is_file():
        rendered_res_file = res_dir / full_render_p.name
        extra_mat_entry = {
            "create_time": now_us // 1_000_000,
            "duration": total_duration_us,
            "extra_info": f"[Bản Render Sẵn] {full_render_p.name}",
            "file_Path": (target_res_dir / full_render_p.name).as_posix(),
            "height": 1080,
            "id": _uid(),
            "import_time": now_us // 1_000_000,
            "import_time_ms": now_us,
            "item_source": 1,
            "md5": _md5_file(rendered_res_file),
            "metetype": "video",
            "roughcut_time_range": {"duration": total_duration_us, "start": 0},
            "sub_time_range": {"duration": -1, "start": -1},
            "type": 0,
            "width": 1080,
        }
        for dm in localmeta.get("draft_materials", []):
            if dm.get("type") == 0 and isinstance(dm.get("value"), list):
                dm["value"].insert(0, extra_mat_entry)
                break

    _save_compact_json(project_draft_dir / "draft_meta_info.json", localmeta)

    # Copy into CapCut Desktop's com.lveditor.draft and register in root_meta_info.json
    registered_in_capcut = False
    capcut_running = _is_capcut_running()
    if capcut_root.is_dir():
        shutil.copytree(project_draft_dir, capcut_installed_dir, dirs_exist_ok=True)

        root_index_path = capcut_root / "root_meta_info.json"
        if root_index_path.is_file():
            reg = read_json(root_index_path)
            backup_path = local_pack_dir / "root_meta_info.before.json"
            shutil.copy2(root_index_path, backup_path)

            store = reg.get("all_draft_store", [])
            template_entry = copy.deepcopy(store[0]) if store else {}
            # Remove any existing entry for this draft_id or draft_name so we update in-place at top of CapCut list
            store = [
                e
                for e in store
                if e.get("draft_id") != draft_id
                and e.get("draft_name") != draft_name
                and e.get("draft_fold_path") != capcut_installed_dir.as_posix()
            ]
            for k in list(template_entry):
                if k in localmeta:
                    template_entry[k] = localmeta[k]

            mat_size = sum(p.stat().st_size for p in (capcut_installed_dir / "Resources").iterdir() if p.is_file())
            template_entry.update(
                draft_id=draft_id,
                draft_name=draft_name,
                draft_fold_path=capcut_installed_dir.as_posix(),
                draft_root_path=capcut_root.as_posix(),
                draft_json_file=(capcut_installed_dir / "draft_content.json").as_posix(),
                draft_cover=(capcut_installed_dir / "draft_cover.jpg").as_posix(),
                draft_timeline_materials_size=mat_size,
                tm_duration=int(content["duration"]),
                tm_draft_create=now_us,
                tm_draft_modified=now_us,
                tm_draft_removed=0,
                streaming_edit_draft_ready=True,
            )
            store.insert(0, template_entry)
            reg["all_draft_store"] = store
            _save_compact_json(root_index_path, reg)
            registered_in_capcut = True

    result_info = {
        "draft_name": draft_name,
        "draft_id": draft_id,
        "capcut_draft_path": str(capcut_installed_dir),
        "local_backup_path": str(project_draft_dir),
        "registered_in_capcut": registered_in_capcut,
        "capcut_was_running": capcut_running,
        "tracks_summary": {
            "track_B_segments": count_b,
            "track_A_segments": count_a,
            "product_png_segments": prod_added,
            "duration_sec": round(total_duration_us / 1_000_000, 2),
        },
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return result_info


def launch_capcut_desktop() -> dict[str, Any]:
    """
    Launch CapCut Desktop visibly on the user's real interactive desktop (WinSta0\\Default)
    by delegating ShellExecute out-of-proc to Windows Explorer (explorer.exe) via ShellWindows COM.
    Kills any sandboxed/headless CapCut processes (--use-gl=disabled) first so single-instance lock doesn't block UI.
    """
    ps_script = r"""
$sandboxed = Get-CimInstance Win32_Process -Filter "Name LIKE 'CapCut%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match '--use-gl=disabled|--disable-gpu-sandbox' }
if ($sandboxed) {
    Get-Process -Name "CapCut*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 600
}
$exe = "$env:LOCALAPPDATA\CapCut\Apps\CapCut.exe"
if (-not (Test-Path $exe)) {
    $exe = "C:\Program Files\CapCut\CapCut.exe"
}
if (-not (Test-Path $exe)) {
    Write-Error "NOT_FOUND"
    exit 1
}
$sw = New-Object -ComObject Shell.Application
$desktop = $sw.Windows() | Where-Object { $_.LocationName -ne $null } | Select-Object -First 1
if (-not $desktop) {
    $desktop = $sw.Windows().Item()
}
if ($desktop -and $desktop.Document -and $desktop.Document.Application) {
    $desktop.Document.Application.ShellExecute($exe, "", (Split-Path $exe), "open", 1)
} else {
    Start-Process -FilePath "explorer.exe" -ArgumentList "`"$exe`""
}
Write-Output "OK:$exe"
"""
    p = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    if "OK:" in (p.stdout or ""):
        return {"ok": True, "exe": (p.stdout or "").strip().split("OK:")[-1]}
    raise RuntimeError("Không tìm thấy CapCut.exe trên máy.")


def _extract_capcut_text_string(mat: dict[str, Any]) -> str:
    raw = mat.get("content", "")
    if not isinstance(raw, str):
        return ""
    raw_s = raw.strip()
    if raw_s.startswith("{"):
        try:
            obj = json.loads(raw_s)
            if isinstance(obj, dict) and "text" in obj:
                return str(obj["text"]).strip()
        except Exception:
            pass
    return raw_s


def sync_edits_from_capcut_draft(pdir: Path, proj: dict[str, Any]) -> dict[str, Any]:
    """
    Read the active CapCut Desktop draft back from C:\\Users\\Dung\\AppData\\Local\\CapCut\\User Data\\Projects\\com.lveditor.draft
    and sync edits made inside CapCut (Title text, Product names, Product prices, Product timings/images, and Person A/B framing)
    back into the App's project.json, text/bang.json, and media/timeline.json!
    """
    capcut_root = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Dung\AppData\Local")) / (
        r"CapCut\User Data\Projects\com.lveditor.draft"
    )
    cc_info = proj.get("capcut_draft") or {}
    draft_dir: Path | None = None

    if cc_info.get("capcut_draft_path"):
        cand = Path(cc_info["capcut_draft_path"])
        if (cand / "draft_content.json").is_file():
            draft_dir = cand

    if draft_dir is None and capcut_root.is_dir():
        raw_title = (proj.get("title") or proj["slug"]).strip()
        ascii_slug = slugify(raw_title).replace("-", " ").title()
        short_tag = proj["id"].split("_")[-1] if "_" in proj.get("id", "") else proj.get("slug", "")[:6]
        cand = capcut_root / f"{ascii_slug} {short_tag}".strip()
        if (cand / "draft_content.json").is_file():
            draft_dir = cand

    if draft_dir is None:
        raise RuntimeError("Chưa tìm thấy bản nháp CapCut của dự án này để đồng bộ ngược về App.")

    content_path = draft_dir / "draft_content.json"
    content = read_json(content_path, {})
    if not content:
        raise RuntimeError(f"Không đọc được {content_path}")

    fps = int(float(content.get("fps") or 30))
    materials = content.get("materials") or {}
    text_by_id = {
        m["id"]: _extract_capcut_text_string(m)
        for m in materials.get("texts", [])
        if isinstance(m, dict) and "id" in m
    }
    video_by_id = {
        m["id"]: m
        for m in materials.get("videos", [])
        if isinstance(m, dict) and "id" in m
    }

    bang_path = pdir / "text" / "bang.json"
    bang = read_json(bang_path, {"items": []})
    items = bang.get("items", [])
    timeline_path = pdir / "media" / "timeline.json"
    timeline = read_json(timeline_path, {})
    settings = proj.setdefault("settings", {})
    mask_price = bool(settings.get("maskPrice", True))

    changes: list[str] = []
    tracks = content.get("tracks") or []

    # Separate tracks by type and relative order
    text_tracks = [t for t in tracks if t.get("type") == "text" and t.get("segments")]
    video_tracks = [t for t in tracks if t.get("type") == "video" and t.get("segments")]

    marks_sorted = sorted(
        ((int(k), int(v)) for k, v in (timeline.get("itemMarks") or {}).items()),
        key=lambda x: x[1],
    )
    item_by_num = {int(it.get("i", i + 1)): it for i, it in enumerate(items)}

    # 1. Sync Title, Product Names, and Product Prices from CapCut Text Tracks
    for t in text_tracks:
        segs = sorted(t.get("segments", []), key=lambda s: int((s.get("target_timerange") or {}).get("start", 0)))
        if not segs:
            continue
        first_clip = segs[0].get("clip") or {}
        first_ty = float((first_clip.get("transform") or {}).get("y", 0.0))

        # Case A: Title track (top of canvas, transform_y > 0.25)
        if len(segs) == 1 and first_ty > 0.25:
            new_title = text_by_id.get(segs[0].get("material_id"), "").strip()
            if new_title and new_title.upper() != (proj.get("title") or "").strip().upper():
                old_t = proj.get("title", "")
                proj["title"] = new_title
                bang["tieu_de"] = new_title
                changes.append(f"Tiêu đề: '{old_t}' → '{new_title}'")
            continue

        # Case B: Price track (bottom-right below product name, transform_y < -0.50)
        if first_ty < -0.50:
            price_suffix = settings.get("priceSuffix", " K")
            for idx, s in enumerate(segs):
                item_num = marks_sorted[idx][0] if idx < len(marks_sorted) else (idx + 1)
                target_item = item_by_num.get(item_num)
                if not target_item:
                    continue
                raw_p = text_by_id.get(s.get("material_id"), "").strip()
                if not raw_p:
                    continue
                cur_gia = target_item.get("gia", 0)
                cur_formatted = _format_vn_price(cur_gia, mask_price, price_suffix)
                if raw_p.upper() != cur_formatted.upper():
                    clean_num = re.sub(r"[^0-9xX]", "", raw_p).lower().replace("x", "0")
                    if clean_num.isdigit():
                        new_gia = int(clean_num)
                        if new_gia != int(cur_gia or 0):
                            target_item["gia"] = new_gia
                            changes.append(f"Giá SP #{item_num:02d} ({target_item.get('ten')}): {cur_gia}K → {new_gia}K")
        # Case C: Product Name track (-0.50 <= transform_y <= 0.25)
        else:
            for idx, s in enumerate(segs):
                item_num = marks_sorted[idx][0] if idx < len(marks_sorted) else (idx + 1)
                target_item = item_by_num.get(item_num)
                if not target_item:
                    continue
                raw_lbl = text_by_id.get(s.get("material_id"), "").strip()
                if not raw_lbl:
                    continue
                base_n = (target_item.get("display_name") or target_item.get("ten") or "").strip()
                sl = target_item.get("sl", "")
                dv = target_item.get("dv", "")
                qty_txt = f"{sl} {dv}".strip() if sl else ""
                cur_lbl = (target_item.get("name_and_qty") or f"{base_n} {qty_txt}").strip()
                if raw_lbl.upper() != cur_lbl.upper():
                    target_item["name_and_qty"] = raw_lbl
                    m_qty = re.match(r"^(.+?)\s+(\d+)\s+(\S+)$", raw_lbl)
                    if m_qty:
                        target_item["display_name"] = m_qty.group(1).strip()
                        target_item["sl"] = int(m_qty.group(2))
                        target_item["dv"] = m_qty.group(3).strip()
                    else:
                        target_item["display_name"] = raw_lbl
                    changes.append(f"Tên SP #{item_num:02d}: '{cur_lbl}' → '{raw_lbl}'")

    # 2. Sync Product PNG Track timings (itemMarks) & any swapped product images
    if len(video_tracks) >= 3:
        prod_track = video_tracks[2]
        p_segs = sorted(
            prod_track.get("segments", []),
            key=lambda s: int((s.get("target_timerange") or {}).get("start", 0)),
        )
        marks_sorted = sorted(
            ((int(k), int(v)) for k, v in (timeline.get("itemMarks") or {}).items()),
            key=lambda x: x[1],
        )
        for idx, s in enumerate(p_segs):
            start_us = int((s.get("target_timerange") or {}).get("start", 0))
            new_frame = round(start_us * fps / 1_000_000)
            if idx < len(marks_sorted):
                item_num, old_frame = marks_sorted[idx]
                if abs(new_frame - old_frame) >= 2:
                    timeline.setdefault("itemMarks", {})[str(item_num)] = new_frame
                    changes.append(
                        f"Mốc hiện SP #{item_num:02d}: {round(old_frame / fps, 2)}s → {round(new_frame / fps, 2)}s"
                    )
                # Sync product image scale if resized inside CapCut
                p_clip_info = s.get("clip") or {}
                p_cc_scale = float((p_clip_info.get("scale") or {}).get("x", 0.0))
                if p_cc_scale > 0.05:
                    base_prod_px = float(settings.get("productImageSize", 400.0))
                    new_item_scale = round((p_cc_scale * 1080.0) / max(100.0, base_prod_px), 2)
                    target_it = item_by_num.get(item_num)
                    if target_it:
                        old_item_scale = float(target_it.get("image_scale", 1.0))
                        if abs(new_item_scale - old_item_scale) >= 0.04:
                            target_it["image_scale"] = new_item_scale
                            changes.append(
                                f"Kích thước ảnh SP #{item_num:02d}: {round(old_item_scale * 100)}% → {round(new_item_scale * 100)}%"
                            )
                mat = video_by_id.get(s.get("material_id"), {})
                mat_path = Path(mat.get("path", "")) if mat.get("path") else None
                if mat_path and mat_path.is_file():
                    dst_prod_dir = pdir / "anh" / "products"
                    dst_prod_dir.mkdir(parents=True, exist_ok=True)
                    expected_f = dst_prod_dir / mat_path.name
                    if not expected_f.is_file() or mat_path.stat().st_mtime > expected_f.stat().st_mtime + 2:
                        shutil.copy2(mat_path, expected_f)
                        for it in items:
                            if int(it.get("i", 0)) == item_num:
                                it["image_file"] = mat_path.name
                        changes.append(f"Cập nhật file ảnh SP #{item_num:02d} từ CapCut ({mat_path.name})")

    # 3. Sync Person B (video_tracks[0]) and Person A (video_tracks[1]) scale/position if dragged in CapCut
    asker_on_right = settings.get("askerSide", "right") != "left"
    for t_idx, who in ((0, "B"), (1, "A")):
        if t_idx >= len(video_tracks):
            continue
        segs = video_tracks[t_idx].get("segments", [])
        if not segs:
            continue
        clip = segs[0].get("clip") or {}
        cc_scale = float((clip.get("scale") or {}).get("y", 0.0))
        tx = float((clip.get("transform") or {}).get("x", 0.0))
        ty = float((clip.get("transform") or {}).get("y", 0.0))
        if cc_scale <= 0.1:
            continue
        new_s = round(cc_scale * 1080.0 / 1280.0, 3)
        old_s = float(settings.get("scaleA", 1.0) if who == "A" else settings.get("scaleB", 1.06))
        if abs(new_s - old_s) >= 0.02:
            settings[f"scale{who}"] = new_s
            changes.append(f"Scale Người {who}: {old_s} → {new_s}")
        is_right = (who == "A" and asker_on_right) or (who == "B" and not asker_on_right)
        face_x = 810.0 if is_right else 270.0
        cx = 540.0 + tx * 540.0
        cy = 540.0 - ty * 540.0
        w_px = 720.0 * new_s
        h_px = 1280.0 * new_s
        left_px = cx - w_px / 2.0
        top_px = cy - h_px / 2.0
        new_crop = round((face_x - left_px) / max(0.2, new_s))
        new_top = round(-top_px)
        old_crop = int(settings.get(f"crop{who}", 329 if who == "A" else 325))
        old_top = int(settings.get(f"top{who}", 180 if who == "A" else 215))
        if abs(new_crop - old_crop) >= 6:
            settings[f"crop{who}"] = new_crop
            changes.append(f"Vị trí ngang Người {who} (crop{who}): {old_crop} → {new_crop}")
        if abs(new_top - old_top) >= 6:
            settings[f"top{who}"] = new_top
            changes.append(f"Vị trí dọc Người {who} (top{who}): {old_top} → {new_top}")

    # Save updated bang.json, timeline.json, and copy latest draft_content.json to local backup
    write_json(bang_path, bang)
    if timeline:
        write_json(timeline_path, timeline)

    local_backup_dir = pdir / "capcut_draft" / draft_dir.name
    local_backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(content_path, local_backup_dir / "draft_content.json")

    return {
        "ok": True,
        "draft_name": draft_dir.name,
        "draft_path": str(draft_dir),
        "changes": changes,
        "changes_count": len(changes),
        "synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def apply_final_revision_notes(
    pdir: Path,
    proj: dict[str, Any],
    notes: str,
    use_ai: bool = False,
) -> dict[str, Any]:
    """
    Parse natural-language revision notes entered by sếp at the final step
    (e.g. changing title, product prices/names/quantities, video speed, speaker framing, or dialogue cuts)
    and apply them directly to project.json, text/bang.json, and text/cut.json.
    """
    notes_clean = (notes or "").strip()
    if not notes_clean:
        raise RuntimeError("Sếp chưa nhập nội dung yêu cầu chỉnh sửa.")

    proj["final_revision_notes"] = notes_clean
    history = proj.setdefault("revision_history", [])
    applied_changes: list[str] = []
    needs_step5 = False

    bang_path = pdir / "text" / "bang.json"
    bang = read_json(bang_path, {"items": []})
    items = bang.get("items", [])
    settings = proj.setdefault("settings", {})

    # 1. Deterministic fast Vietnamese command parsing
    for line in [ln.strip() for ln in re.split(r"[\n;]+", notes_clean) if ln.strip()]:
        low = line.lower()

        # Title change: "tiêu đề: GIỎ ĐỒ 5 TRIỆU" or "đổi tiêu đề thành ..."
        m_title = re.search(r"(?:đổi\s+|sửa\s+)?tiêu\s*đề\s*(?:thành|là|sang|:|=)\s*[\"']?(.+?)[\"']?$", line, flags=re.I)
        if m_title:
            new_t = m_title.group(1).strip()
            if new_t:
                proj["title"] = new_t
                bang["tieu_de"] = new_t
                applied_changes.append(f"Đổi tiêu đề video thành '{new_t}'")
                continue

        # Summary note ('Săn Sell để được giá hời') & Summary subtitle ('ĐỦ CHO MẸ & BÉ ĐI SINH')
        if re.search(r"săn\s*sell.*săn\s*sale|sell\s*(?:thành|bằng|sang|->|=>)\s*sale", low):
            cur_note = str(settings.get("summaryNote") or "(Săn Sell để được giá hời)")
            new_note = re.sub(r"sell", "Sale", cur_note, flags=re.I)
            if "sale" not in new_note.lower():
                new_note = "(Săn Sale để được giá hời)"
            settings["summaryNote"] = new_note
            applied_changes.append(f"Đổi dòng chú giải thành '{new_note}'")
            continue

        if any(k in low for k in ("bỏ dòng chú giải", "xóa dòng chú giải", "ẩn dòng chú giải", "bỏ chữ săn sell", "bỏ chữ săn sale", "xóa dòng săn")):
            settings["summaryNote"] = ""
            applied_changes.append("Đã ẩn dòng chú giải trên nút Tổng")
            continue

        m_note = re.search(r"(?:đổi\s+|sửa\s+)?(?:dòng\s*)?(?:chú\s*giải|dòng\s*đỏ|dòng\s*săn\s*sale|dòng\s*săn\s*sell)\s*(?:thành|là|sang|:|=)\s*[\"']?(.+?)[\"']?$", line, flags=re.I)
        if m_note:
            val_note = m_note.group(1).strip()
            settings["summaryNote"] = val_note
            applied_changes.append(f"Đổi dòng chú giải thành '{val_note}'")
            continue

        m_sub_tot = re.search(r"(?:đổi\s+|sửa\s+)?(?:dòng\s*phụ|dòng\s*dưới\s*tổng|chữ\s*dưới\s*tổng)\s*(?:thành|là|sang|:|=)\s*[\"']?(.+?)[\"']?$", line, flags=re.I)
        if m_sub_tot:
            val_sub = m_sub_tot.group(1).strip()
            settings["summarySubtitle"] = val_sub
            applied_changes.append(f"Đổi dòng phụ dưới tổng thành '{val_sub}'")
            continue

        # Zero price label: e.g. "giá 0 hiện chữ TẶNG", "số 0 đổi thành TẶNG", "món giá 0 ghi là Tặng kèm"
        m_zero = re.search(r"(?:giá\s*0|số\s*0|0\s*đ|0\s*k)\s*(?:đổi\s*thành|thành|hiện\s*chữ|hiện\s*là|ghi\s*là|thay\s*bằng|:|=)\s*[\"']?(.+?)[\"']?$", line, flags=re.I)
        if m_zero:
            z_lbl = m_zero.group(1).strip()
            settings["zeroPriceLabel"] = z_lbl
            for it in items:
                try:
                    g_val = float(it.get("gia") or 0)
                except Exception:
                    g_val = -1
                if g_val == 0:
                    it["gia_text"] = z_lbl
            applied_changes.append(f"Đổi hiển thị các món giá 0 thành '{z_lbl}'")
            continue

        # Swap left/right speaker sides
        if any(k in low for k in ("đổi bên 2 người", "đổi vị trí 2 người", "hoán đổi 2 người", "đổi trái phải 2 người")):
            cur_side = settings.get("askerSide", "right")
            new_side = "left" if cur_side != "left" else "right"
            settings["askerSide"] = new_side
            applied_changes.append(f"Đã hoán đổi vị trí trái/phải của 2 người ({new_side})")
            continue

        # Font change: "đổi font Anton", "font tiêu đề Montserrat", "font phụ đề Baloo"
        if "font" in low or "phông" in low:
            font_aliases = [
                ("Anton", ["anton"]),
                ("BarlowCondensed", ["barlow", "barlow condensed"]),
                ("BeVietnamPro", ["be vietnam", "bevietnam", "be vietnam pro"]),
                ("Montserrat", ["montserrat", "monserat"]),
                ("Oswald", ["oswald"]),
                ("Baloo2", ["baloo", "baloo 2", "baloo2"]),
                ("PaytoneOne", ["paytone", "paytone one"]),
                ("Bangers", ["bangers", "banger"]),
                ("Phudu", ["phudu", "phù du"]),
                ("Coiny", ["coiny"]),
                ("Kanit", ["kanit"]),
                ("ChakraPetch", ["chakra", "chakra petch"]),
                ("Mali", ["mali"]),
                ("PatrickHand", ["patrick", "patrick hand"]),
                ("Lexend", ["lexend"]),
            ]
            matched_font = None
            for f_key, aliases in font_aliases:
                if any(a in low for a in aliases):
                    matched_font = f_key
                    break
            if matched_font:
                if "tiêu đề" in low and "phụ đề" not in low and "sản phẩm" not in low:
                    settings["titleFont"] = matched_font
                    applied_changes.append(f"Đổi font chữ Tiêu đề thành '{matched_font}'")
                elif any(x in low for x in ("phụ đề", "sản phẩm", "giá", "sub")):
                    settings["subFont"] = matched_font
                    applied_changes.append(f"Đổi font chữ Sản phẩm / Phụ đề thành '{matched_font}'")
                else:
                    settings["titleFont"] = matched_font
                    settings["subFont"] = matched_font
                    applied_changes.append(f"Đổi toàn bộ font chữ (Tiêu đề & Sản phẩm/Phụ đề) thành '{matched_font}'")
                continue

        # Remove / restore 'K' suffix after price: "Bỏ chữ K phía sau giá", "Xóa chữ K", "Thêm chữ K"
        if re.search(r"(?:bỏ|xóa|ẩn|không\s*để|không\s*hiện)\s*(?:chữ\s*)?k\b", low):
            settings["priceSuffix"] = ""
            applied_changes.append("Đã bỏ chữ 'K' phía sau giá (ví dụ: '6x K' → '6x')")
            continue
        if re.search(r"(?:thêm|hiện|khôi\s*phục|để\s*lại)\s*(?:chữ\s*)?k\b", low):
            settings["priceSuffix"] = " K"
            applied_changes.append("Đã bật lại chữ 'K' phía sau giá ('6x K')")
            continue

        # Speed change: "tốc độ 1.35" or "speed 1.25x"
        m_spd = re.search(r"(?:tốc\s*độ|speed)\s*(?:thành|là|:|=)?\s*(\d+(?:[\.,]\d+)?)\s*x?", low)
        if m_spd:
            val = float(m_spd.group(1).replace(",", "."))
            if 0.7 <= val <= 2.0:
                settings["speed"] = val
                needs_step5 = True
                applied_changes.append(f"Đổi tốc độ nói thành {val}x")
                continue

        # Item display duration for Preset Ảnh + Nhạc: "mỗi hình hiện 3 giây", "thời lượng mỗi ảnh 2.8s", "mỗi mục 3.5 giây"
        m_idur = re.search(
            r"(?:mỗi\s*(?:hình|ảnh|mục|sản\s*phẩm|thẻ)|thời\s*lượng\s*mỗi\s*(?:hình|ảnh|mục))\s*(?:hiện|hiển\s*thị|là|thành|:|=)?\s*(\d+(?:[\.,]\d+)?)\s*(?:s|giây)?",
            low,
        )
        if m_idur:
            dur_val = float(m_idur.group(1).replace(",", "."))
            if 0.8 <= dur_val <= 15.0:
                settings["itemDurationSec"] = dur_val
                needs_step5 = True
                applied_changes.append(f"Đổi thời lượng hiển thị mỗi hình ảnh thành {dur_val} giây")
                continue

        # Background theme / color: "nền màu be", "nền kem", "nền hồng", "nền tối"
        if any(k in low for k in ("nền màu be", "nền be", "nền kem", "màu be", "tông be", "nền sáng")):
            settings["bgTheme"] = "beige"
            settings["backgroundColor"] = "radial-gradient(circle at 50% 35%, #fffdf9 0%, #f5ebe0 58%, #e6d5c3 100%)"
            applied_changes.append("Đổi nền video sang tông màu be ấm áp (#fffdf9 → #f5ebe0 → #e6d5c3)")
            continue
        if any(k in low for k in ("nền hồng", "màu hồng pastel")):
            settings["bgTheme"] = "beige"
            settings["backgroundColor"] = "radial-gradient(circle at 50% 35%, #fffaf7 0%, #fce8ec 58%, #f3d1d8 100%)"
            applied_changes.append("Đổi nền video sang tông hồng kem pastel")
            continue
        if any(k in low for k in ("nền tối", "nền đen", "nền tím")):
            settings["bgTheme"] = "dark"
            settings["backgroundColor"] = ""
            applied_changes.append("Đổi nền video sang tông tối Studio")
            continue

        # Subtitle under main title (bang.subtitle): "dòng phụ dưới tiêu đề: ...", "bỏ dòng phụ dưới tiêu đề"
        if any(k in low for k in ("bỏ dòng phụ dưới tiêu đề", "xóa dòng phụ dưới tiêu đề", "ẩn dòng phụ dưới tiêu đề")):
            bang["subtitle"] = ""
            applied_changes.append("Đã ẩn dòng phụ dưới tiêu đề chính")
            continue
        m_bsub = re.search(
            r"(?:đổi\s+|sửa\s+|thêm\s+)?(?:dòng\s*phụ\s*dưới\s*tiêu\s*đề|tiêu\s*đề\s*phụ|tagline)\s*(?:thành|là|sang|:|=)\s*[\"']?(.+?)[\"']?$",
            line,
            flags=re.I,
        )
        if m_bsub:
            sub_val = m_bsub.group(1).strip()
            bang["subtitle"] = sub_val
            settings["summarySubtitle"] = sub_val.upper()
            applied_changes.append(f"Đổi dòng phụ dưới tiêu đề thành '{sub_val}'")
            continue

        # Mask price toggle
        if any(k in low for k in ("bỏ che giá", "hiện giá thật", "không che giá", "tắt che giá")):
            settings["maskPrice"] = False
            applied_changes.append("Tắt chế độ che số cuối giá (hiện giá đầy đủ)")
            continue
        if any(k in low for k in ("bật che giá", "che số cuối", "che giá")):
            settings["maskPrice"] = True
            applied_changes.append("Bật chế độ che số cuối giá ('6x K')")
            continue

        # Total price change: "tổng tiền 4950" or "tổng: 5000k"
        m_tot = re.search(r"tổng(?:\s*tiền|\s*cộng)?\s*(?:thành|là|:|=)?\s*(\d+)\s*k?", low)
        if m_tot:
            new_tot = int(m_tot.group(1))
            bang["tong"] = new_tot
            applied_changes.append(f"Đổi Tổng tiền thành {new_tot}K")
            continue

        # Title font size / Product name font size / Product price font size
        m_tfs = re.search(r"cỡ\s*chữ\s*tiêu\s*đề\s*(?:thành|là|:|=)?\s*(\d+)", low)
        if m_tfs:
            settings["titleFontSize"] = int(m_tfs.group(1))
            applied_changes.append(f"Đổi cỡ chữ tiêu đề thành {m_tfs.group(1)}px")
            continue

        m_pns = re.search(r"cỡ\s*chữ\s*(?:tên\s*)?(?:sản\s*phẩm|sp)\s*(?:thành|là|:|=)?\s*(\d+)", low)
        if m_pns:
            settings["productNameFontSize"] = int(m_pns.group(1))
            applied_changes.append(f"Đổi cỡ chữ tên sản phẩm thành {m_pns.group(1)}px")
            continue

        m_pps = re.search(r"cỡ\s*chữ\s*giá(?:\s*tiền)?\s*(?:thành|là|:|=)?\s*(\d+)", low)
        if m_pps:
            settings["productPriceFontSize"] = int(m_pps.group(1))
            applied_changes.append(f"Đổi cỡ chữ giá tiền thành {m_pps.group(1)}px")
            continue

        # Product image size (global): e.g. "cỡ ảnh sản phẩm 340px", "kích thước hình ảnh 320", "thu nhỏ ảnh 80%", "phóng to ảnh sản phẩm"
        if any(k in low for k in ("cỡ ảnh", "kích thước ảnh", "kích thước hình", "cỡ hình", "thu nhỏ ảnh", "phóng to ảnh", "ảnh sản phẩm to", "ảnh sản phẩm nhỏ")) and not re.search(r"(?:sp|món)\s*#?\d+", low):
            m_pct = re.search(r"(\d+)\s*%", low)
            m_px = re.search(r"(\d{3})\s*(?:px)?", low)
            cur_sz = int(settings.get("productImageSize", 400))
            if m_pct:
                pct = int(m_pct.group(1))
                new_sz = max(160, min(680, round(400 * pct / 100.0)))
                settings["productImageSize"] = new_sz
                applied_changes.append(f"Đổi kích thước ảnh sản phẩm thành {pct}% ({new_sz}px)")
                continue
            elif m_px:
                new_sz = max(160, min(680, int(m_px.group(1))))
                settings["productImageSize"] = new_sz
                applied_changes.append(f"Đổi kích thước ảnh sản phẩm thành {new_sz}px")
                continue
            elif "thu nhỏ" in low or "nhỏ lại" in low or "bé lại" in low:
                new_sz = max(180, cur_sz - 60)
                settings["productImageSize"] = new_sz
                applied_changes.append(f"Thu nhỏ kích thước ảnh sản phẩm: {cur_sz}px → {new_sz}px")
                continue
            elif "phóng to" in low or "to lên" in low or "lớn hơn" in low:
                new_sz = min(650, cur_sz + 60)
                settings["productImageSize"] = new_sz
                applied_changes.append(f"Phóng to kích thước ảnh sản phẩm: {cur_sz}px → {new_sz}px")
                continue

        # Match any product in bang.json mentioned in the instruction line
        matched_prod = None
        for it in items:
            ten_low = (it.get("ten") or "").strip().lower()
            disp_low = (it.get("display_name") or "").strip().lower()
            if (ten_low and ten_low in low) or (disp_low and disp_low in low):
                matched_prod = it
                break
        if not matched_prod:
            m_sp_idx = re.search(r"(?:sp|món|sản\s*phẩm|mục|hình|ảnh)\s*#?(\d+)", low)
            if m_sp_idx:
                idx_num = int(m_sp_idx.group(1))
                for it in items:
                    if int(it.get("i", 0)) == idx_num:
                        matched_prod = it
                        break

        if matched_prod:
            # Check if user wants to change/re-search web image for this item:
            # e.g. "đổi ảnh mục 2 sang ảnh khác", "tìm lại ảnh Từ Dũ chụp cổng bệnh viện", "đổi ảnh Doomi Baby thành bộ quần áo sơ sinh"
            if re.search(r"(?:đổi\s*(?:ảnh|hình)|tìm\s*(?:lại\s*)?(?:ảnh|hình)|lấy\s*(?:ảnh|hình)\s*khác)", low):
                from media_ops import download_web_image_for_item
                from utils import slugify
                m_custom_q = re.search(r"(?:thành|sang|với\s*từ\s*khóa|theo\s*kiểu|là|:)\s+[\"']?(.+?)[\"']?$", line, flags=re.I)
                custom_q = m_custom_q.group(1).strip() if m_custom_q else ""
                if custom_q.lower() in ("ảnh khác", "hình khác", "cái khác", "khác"):
                    custom_q = ""
                item_idx = int(matched_prod.get("i", 1))
                cand_idx = 0 if custom_q else (int(matched_prod.get("web_candidate_index", 0)) + 1) % 8
                web_cache_dir = pdir / "anh" / "web_items"
                web_cache_dir.mkdir(parents=True, exist_ok=True)
                it_name = str(matched_prod.get("display_name") or matched_prod.get("ten") or f"item_{item_idx}").strip()
                out_img = web_cache_dir / f"item_{item_idx:02d}_{slugify(it_name)}_v{cand_idx}.png"
                dl = download_web_image_for_item(
                    item_name=it_name,
                    project_title=str(proj.get("title") or bang.get("tieu_de") or ""),
                    out_path=out_img,
                    candidate_index=cand_idx,
                    custom_query=custom_q or str(matched_prod.get("search_query") or ""),
                )
                if dl.get("ok") and dl.get("path"):
                    matched_prod["custom_image_path"] = dl["path"]
                    matched_prod["web_candidate_index"] = cand_idx
                    if custom_q:
                        matched_prod["search_query"] = custom_q
                    applied_changes.append(
                        f"Đã tìm & đổi ảnh mới cho mục #{item_idx} '{it_name}'"
                        + (f" (từ khóa: '{custom_q}')" if custom_q else f" (mẫu #{cand_idx + 1})")
                    )
                    continue

            # Check if adding or editing bullet points / description for this item:
            # e.g. "thêm ý cho Doomi Baby: Giao hàng nhanh", "sửa mô tả Bora Store thành Đồ bền đẹp"
            m_add_b = re.search(r"(?:thêm\s*ý|thêm\s*dòng|thêm\s*mô\s*tả).*?(?:cho\s+.+?)?(?::|là|thành)\s*[\"']?(.+?)[\"']?$", line, flags=re.I)
            if m_add_b:
                new_b = m_add_b.group(1).strip()
                if new_b:
                    b_list = list(matched_prod.get("bullets") or [])
                    b_list.append(new_b)
                    matched_prod["bullets"] = b_list
                    matched_prod["ghi_chu"] = " • ".join(b_list)
                    applied_changes.append(f"Đã thêm ý '{new_b}' vào mục '{matched_prod.get('ten')}'")
                    continue

            m_set_b = re.search(r"(?:sửa\s*mô\s*tả|đổi\s*mô\s*tả|sửa\s*ý\s*phụ|đổi\s*ghi\s*chú).*?(?:thành|là|sang|:)\s*[\"']?(.+?)[\"']?$", line, flags=re.I)
            if m_set_b:
                raw_b = m_set_b.group(1).strip()
                b_list = [x.strip(" -•*") for x in re.split(r"[\|•\n]+", raw_b) if x.strip(" -•*")]
                matched_prod["bullets"] = b_list
                matched_prod["ghi_chu"] = " • ".join(b_list)
                applied_changes.append(f"Đã cập nhật mô tả của '{matched_prod.get('ten')}'")
                continue

            # Check if deleting product
            if any(k in low for k in ("xóa món", "bỏ món", "xóa sản phẩm", "bỏ sản phẩm", "xóa mục", "bỏ mục")):
                p_name = matched_prod.get("ten")
                items.remove(matched_prod)
                for idx_re, it_re in enumerate(items, start=1):
                    it_re["i"] = idx_re
                applied_changes.append(f"Đã xóa món '{p_name}' khỏi bảng sản phẩm")
                continue

            # Check custom text price: e.g. "Kem dưỡng ẩm đổi giá thành TẶNG" or "ghi giá là Tặng"
            m_ptxt = re.search(r"(?:đổi\s*giá|giá|ghi\s*giá|hiển\s*thị\s*giá)\s*(?:thành|là|sang|:|=)\s*[\"']?([a-zA-ZÀ-ỹ\s]+)[\"']?$", line, flags=re.I)
            if m_ptxt and not re.search(r"^\d+\s*k?$", m_ptxt.group(1).strip(), flags=re.I):
                txt_val = m_ptxt.group(1).strip()
                matched_prod["gia_text"] = txt_val
                applied_changes.append(f"Đổi hiển thị giá '{matched_prod.get('ten')}' thành '{txt_val}'")

            # Check numeric price update on matched product: e.g. "145k" or "giá 145"
            m_p = re.search(r"(?:giá\s*(?:thành|là|:|=)?\s*(\d+)\s*k?|(\d+)\s*k\b)", low)
            if m_p:
                new_p = int(m_p.group(1) or m_p.group(2))
                old_p = matched_prod.get("gia")
                matched_prod["gia"] = new_p
                matched_prod.pop("gia_text", None)
                applied_changes.append(f"Đổi giá '{matched_prod.get('ten')}': {old_p}K → {new_p}K")

            # Check quantity update: e.g. "5 cái", "2 bịch", "số lượng 4"
            m_q = re.search(r"(?:số\s*lượng|sl)\s*(?:thành|là|:|=)?\s*(\d+)|(\d+)\s*(cái|bịch|chai|hộp|cặp|bình|thanh|gói|bộ|chiếc|tuýp|hũ)\b", line, flags=re.I)
            if m_q:
                if m_q.group(1):
                    matched_prod["sl"] = int(m_q.group(1))
                else:
                    matched_prod["sl"] = int(m_q.group(2))
                    matched_prod["dv"] = m_q.group(3).capitalize()
                matched_prod.pop("custom_label", None)
                base_n = (matched_prod.get("display_name") or matched_prod.get("ten") or "").strip().upper()
                matched_prod["name_and_qty"] = f"{base_n} {matched_prod['sl']} {matched_prod.get('dv', '')}".strip()
                applied_changes.append(
                    f"Đổi số lượng '{matched_prod.get('ten')}' thành {matched_prod['sl']} {matched_prod.get('dv', '')}"
                )

            # Check rename: "đổi tên ... thành ..." or "sửa thành ..."
            m_rn = re.search(r"(?:đổi\s*tên|sửa\s*tên|đổi\s*chữ|hiển\s*thị\s*là).*?(?:thành|là|sang)\s+[\"']?(.+?)[\"']?$", line, flags=re.I)
            if m_rn:
                new_dn = m_rn.group(1).strip().upper()
                # Check if user included quantity + unit in the new name (e.g. "ÁO CỘC TAY 3 CÁI")
                m_full_lbl = re.match(r"^(.+?)\s+(\d+)\s+(CÁI|BỊCH|CHAI|HỘP|CẶP|BÌNH|THANH|GÓI|BỘ|CHIẾC|TUÝP|HŨ)$", new_dn, flags=re.I)
                if m_full_lbl:
                    matched_prod["display_name"] = m_full_lbl.group(1).strip().upper()
                    matched_prod["sl"] = int(m_full_lbl.group(2))
                    matched_prod["dv"] = m_full_lbl.group(3).capitalize()
                else:
                    matched_prod["display_name"] = new_dn
                matched_prod["name_and_qty"] = f"{matched_prod['display_name']} {matched_prod.get('sl', '')} {matched_prod.get('dv', '')}".strip()
                applied_changes.append(f"Đổi tên hiển thị SP #{matched_prod.get('i')} thành '{matched_prod['name_and_qty']}'")

            # Check per-product image scale: e.g. "ảnh món #1 80%", "áo ngắn tay thu nhỏ 85%"
            if any(k in low for k in ("cỡ", "kích thước", "ảnh", "hình", "phóng to", "thu nhỏ", "%")):
                m_item_pct = re.search(r"(\d+)\s*%", low)
                if m_item_pct:
                    pct_val = max(40, min(200, int(m_item_pct.group(1))))
                    matched_prod["image_scale"] = round(pct_val / 100.0, 2)
                    applied_changes.append(f"Đổi kích thước ảnh '{matched_prod.get('ten')}' thành {pct_val}%")
                elif "thu nhỏ" in low or "nhỏ lại" in low:
                    cur_sc = float(matched_prod.get("image_scale", 1.0))
                    new_sc = round(max(0.5, cur_sc - 0.15), 2)
                    matched_prod["image_scale"] = new_sc
                    applied_changes.append(f"Thu nhỏ ảnh '{matched_prod.get('ten')}' còn {round(new_sc * 100)}%")
                elif "phóng to" in low or "to lên" in low:
                    cur_sc = float(matched_prod.get("image_scale", 1.0))
                    new_sc = round(min(1.8, cur_sc + 0.15), 2)
                    matched_prod["image_scale"] = new_sc
                    applied_changes.append(f"Phóng to ảnh '{matched_prod.get('ten')}' lên {round(new_sc * 100)}%")
            continue

        # Generic text replacement: "sửa/đổi/thay [chữ] X thành/bằng/sang Y"
        m_rep = re.search(
            r"^(?:sửa|đổi|thay)(?:\s+chữ|\s+cụm|\s+từ|\s+nội\s*dung|\s+dòng)?\s+[\"']?(.+?)[\"']?\s+(?:thành|bằng|sang|->|=>)\s+[\"']?(.+?)[\"']?$",
            line,
            flags=re.I,
        )
        if m_rep:
            old_txt = m_rep.group(1).strip()
            new_txt = m_rep.group(2).strip()
            if old_txt:
                pat = re.compile(re.escape(old_txt), flags=re.I)
                replaced_where: list[str] = []
                # 1. Check title
                for tk in ("title",):
                    cur_v = str(proj.get(tk) or "")
                    if pat.search(cur_v):
                        proj[tk] = pat.sub(new_txt, cur_v)
                        bang["tieu_de"] = proj[tk]
                        replaced_where.append(f"Tiêu đề → '{proj[tk]}'")
                # 2. Check summaryNote & summarySubtitle
                cur_sn = str(settings.get("summaryNote") or "(Săn Sell để được giá hời)")
                if pat.search(cur_sn):
                    settings["summaryNote"] = pat.sub(new_txt, cur_sn)
                    replaced_where.append(f"Chú giải → '{settings['summaryNote']}'")
                cur_ss = str(settings.get("summarySubtitle") or "ĐỦ CHO MẸ & BÉ ĐI SINH")
                if pat.search(cur_ss):
                    settings["summarySubtitle"] = pat.sub(new_txt, cur_ss)
                    replaced_where.append(f"Dòng dưới tổng → '{settings['summarySubtitle']}'")
                # 3. Check product items
                for it in items:
                    dn = str(it.get("display_name") or it.get("ten") or "")
                    full_n = f"{dn} {it.get('sl', '')} {it.get('dv', '')}".strip()
                    if pat.search(dn):
                        it["display_name"] = pat.sub(new_txt, dn).upper()
                        it["name_and_qty"] = f"{it['display_name']} {it.get('sl', '')} {it.get('dv', '')}".strip()
                        replaced_where.append(f"SP #{it.get('i')} → '{it['name_and_qty']}'")
                    elif pat.search(full_n):
                        it["custom_label"] = pat.sub(new_txt, full_n).upper()
                        it["name_and_qty"] = it["custom_label"]
                        replaced_where.append(f"SP #{it.get('i')} → '{it['custom_label']}'")
                # 4. Check Preset A chia_se_items
                cs_items = proj.get("chia_se_items") or []
                for idx_cs, cs_line in enumerate(cs_items):
                    if pat.search(str(cs_line)):
                        cs_items[idx_cs] = pat.sub(new_txt, str(cs_line))
                        replaced_where.append(f"Ý #{idx_cs + 1} → '{cs_items[idx_cs]}'")
                if replaced_where:
                    applied_changes.append(f"Đã thay '{old_txt}' thành '{new_txt}' ({', '.join(replaced_where)})")
                    continue

        # Global web image re-search for Preset Ảnh + Nhạc: e.g. "tìm lại tất cả ảnh chụp thực tế bên ngoài", "đổi toàn bộ ảnh sang ảnh khác"
        m_global_reimg = re.search(
            r"(?:tìm\s*(?:lại\s*)?(?:tất\s*cả\s*|toàn\s*bộ\s*)?(?:ảnh|hình)|đổi\s*(?:tất\s*cả\s*|toàn\s*bộ\s*)(?:ảnh|hình))\s*(?:theo\s*kiểu|với\s*từ\s*khóa|thành|sang|:)?\s*(.*)$",
            line,
            flags=re.I,
        )
        if m_global_reimg and items:
            from media_ops import build_smart_image_search_query, download_web_image_for_item
            from utils import slugify
            extra_kw = m_global_reimg.group(1).strip(" \"'")
            if extra_kw.lower() in ("khác", "ảnh khác", "hình khác", "mới"):
                extra_kw = ""
            web_cache_dir = pdir / "anh" / "web_items"
            web_cache_dir.mkdir(parents=True, exist_ok=True)
            re_count = 0
            for it in items:
                item_idx = int(it.get("i", 1))
                it_name = str(it.get("display_name") or it.get("ten") or f"item_{item_idx}").strip()
                base_q = build_smart_image_search_query(
                    str(it.get("ten") or it_name),
                    str(proj.get("title") or bang.get("tieu_de") or ""),
                    bullets=it.get("bullets") or [],
                )
                q_use = f"{base_q} {extra_kw}".strip() if extra_kw else base_q
                cand_idx = 0 if extra_kw else (int(it.get("web_candidate_index", 0)) + 1) % 8
                out_img = web_cache_dir / f"item_{item_idx:02d}_{slugify(it_name)}_v{cand_idx}.png"
                dl = download_web_image_for_item(
                    item_name=it_name,
                    project_title=str(proj.get("title") or bang.get("tieu_de") or ""),
                    out_path=out_img,
                    candidate_index=cand_idx,
                    custom_query=q_use,
                )
                if dl.get("ok") and dl.get("path"):
                    it["custom_image_path"] = dl["path"]
                    it["web_candidate_index"] = cand_idx
                    it["search_query"] = q_use
                    re_count += 1
            if re_count > 0:
                applied_changes.append(
                    f"Đã tìm & cập nhật lại {re_count}/{len(items)} hình ảnh"
                    + (f" theo yêu cầu '{extra_kw}'" if extra_kw else " (mẫu ảnh mới)")
                )
                continue

        # Standalone title line (e.g. "GIỎ ĐỒ ĐI SINH 5TR" or all-caps title phrase)
        if (
            re.match(r"^(?:giỏ\s*đồ|chia\s*sẻ|combo|mẹ\s*bầu|đi\s*sinh)\b", low)
            or (line == line.upper() and 4 <= len(line) <= 45 and not re.search(r"\b(?:giá|bỏ|xóa|sửa|đổi|tốc\s*độ)\b", low))
        ):
            new_t = line.strip("\"' ")
            proj["title"] = new_t
            bang["tieu_de"] = new_t
            applied_changes.append(f"Đổi tiêu đề video thành '{new_t}'")
            continue

    write_json(bang_path, bang)

    # 2. If use_ai is requested or no deterministic rule matched, invoke AI CLI to apply complex edits
    if use_ai or not applied_changes:
        try:
            from cli_ai import invoke_cli_agent

            provider = settings.get("step3_provider", "agy")
            ai_out = pdir / "text" / "ai_revision_summary.json"
            if ai_out.is_file():
                try:
                    ai_out.unlink()
                except Exception:
                    pass
            kb_path = pdir / "text" / "kich_ban.md"
            kb_content = kb_path.read_text(encoding="utf-8", errors="replace").strip() if kb_path.is_file() else ""
            prompt = (
                "Bạn là trợ lý chỉnh sửa dự án video của sếp Dũng.\n"
                f"Yêu cầu chỉnh sửa của sếp:\n\"\"\"\n{notes_clean}\n\"\"\"\n\n"
                f"Kịch bản gốc sếp đã gửi ({kb_path}):\n\"\"\"\n{kb_content}\n\"\"\"\n\n"
                f"Thư mục dự án: {pdir}\n"
                f"- File cấu hình & bố cục: {pdir / 'project.json'} (chứa title, settings.summaryNote, settings.summarySubtitle, settings.priceSuffix, settings.zeroPriceLabel, settings.productImageSize, settings.titleFont, settings.subFont, ...)\n"
                f"- File bảng sản phẩm / mục hiển thị: {pdir / 'text' / 'bang.json'} (mỗi item có i, ten, display_name, bullets, sl, dv, gia, gia_text, image_scale, custom_image_path)\n\n"
                "QUY TẮC BẮT BUỘC:\n"
                "1. Bám sát ĐÚNG số lượng mục và ĐÚNG tên từng mục trong Kịch bản gốc sếp đã gửi ở trên (TUYỆT ĐỐI KHÔNG tự ý bịa thêm mục mới hoặc giữ lại mục thừa không có trong kịch bản).\n"
                "2. Sửa trực tiếp file `project.json` và `text/bang.json` nhanh gọn (KHÔNG chạy script tải ảnh lâu gây timeout).\n"
                f"3. Ghi tóm tắt các thay đổi đã thực hiện vào {ai_out} theo mẫu:\n"
                '{"changes": ["Mục đã sửa 1", "Mục đã sửa 2"]}'
            )
            ai_res = invoke_cli_agent(
                project_dir=pdir,
                step_name="final_revision",
                prompt=prompt,
                preferred_provider=provider,
                expected_out_file=ai_out,
            )
            # Reload project.json in case AI CLI modified it directly on disk
            disk_proj = read_json(pdir / "project.json", {})
            if disk_proj.get("title"):
                proj["title"] = disk_proj["title"]
            if disk_proj.get("settings"):
                proj["settings"].update(disk_proj["settings"])
            if "turn_listener_overrides" in disk_proj:
                proj["turn_listener_overrides"] = disk_proj["turn_listener_overrides"]
            if "clip_aux_sources" in disk_proj:
                proj["clip_aux_sources"] = disk_proj["clip_aux_sources"]
            if ai_res.get("ok") and ai_out.is_file():
                ai_data = read_json(ai_out, {})
                for ch in ai_data.get("changes", []):
                    if ch and ch not in applied_changes:
                        applied_changes.append(str(ch))
        except Exception as ai_err:
            if not applied_changes:
                applied_changes.append(f"Đã lưu ghi chú chỉnh sửa (AI CLI: {ai_err})")

    if not applied_changes:
        applied_changes.append("Đã lưu yêu cầu chỉnh sửa và làm mới lại ảnh mẫu & Timeline.")

    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "notes": notes_clean,
        "changes": applied_changes,
    }
    history.insert(0, entry)
    proj["revision_history"] = history[:20]

    return {
        "ok": True,
        "notes": notes_clean,
        "changes": applied_changes,
        "needs_step5": needs_step5,
        "history": proj["revision_history"],
    }



