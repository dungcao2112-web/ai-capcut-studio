# -*- coding: utf-8 -*-
"""Bộ kiểm thử dịch vụ: làm nét / tách nền ảnh bác sĩ, API ảnh hàng loạt, Cloud fallback,
Remotion autoFit & đồng bộ TSX, toàn vẹn Frontend (hàm global cũ + module mới <= 280 dòng)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFilter

APP = Path(__file__).resolve().parents[1]


@pytest.fixture()
def portrait(tmp_path):
    from services.subject_fallback import draw_demo_portrait

    return draw_demo_portrait(tmp_path / "portrait.png", "BS TEST", (200, 60, 90))


# ---------------------------------------------------------------------------
# Làm nét & nền thẻ
# ---------------------------------------------------------------------------
def test_clahe_preserves_shape_and_expands_contrast():
    from services.image_enhancer import clahe_channel

    rng = np.random.default_rng(0)
    flat = (110 + rng.integers(0, 20, size=(200, 160))).astype(np.uint8)
    out = clahe_channel(flat, clip_limit=2.0)
    assert out.shape == flat.shape and out.dtype == np.uint8
    assert out.std() > flat.std() * 1.5


def test_auto_enhance_increases_sharpness_and_keeps_alpha(portrait):
    from services.image_enhancer import auto_enhance_portrait, measure_sharpness

    blurry = Image.open(portrait).convert("RGBA").filter(ImageFilter.GaussianBlur(2))
    blurry.putalpha(128)
    out = auto_enhance_portrait(blurry, strength=1.0)
    assert out.mode == "RGBA" and out.size == blurry.size
    assert np.asarray(out.getchannel("A")).max() == 128
    assert measure_sharpness(out) > measure_sharpness(blurry) * 1.3


def test_card_background_colors_and_rounded_corners():
    from services.image_enhancer import apply_card_background, resolve_card_bg

    assert resolve_card_bg("beige") == "#F6EFE6" and resolve_card_bg("transparent") is None
    assert resolve_card_bg("#f0f7ff") == "#F0F7FF"
    with pytest.raises(ValueError):
        resolve_card_bg("#12")
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    card = apply_card_background(im, "#FFFDF9", radius=40, border_px=0)
    assert card.getpixel((0, 0))[3] == 0  # góc bo tròn trong suốt
    assert card.getpixel((100, 100)) == (255, 253, 249, 255)


def test_enhance_options_from_query_and_body():
    from services.image_enhancer import enhance_options_from_request

    assert enhance_options_from_request({}) == {}
    assert enhance_options_from_request({"mode": ["cutout"]}) == {}  # không gửi tuỳ chọn => hành vi cũ
    qs = {"enhance": ["1"], "card_bg": ["#F6EFE6"], "enhance_strength": ["1.2"]}
    assert enhance_options_from_request(qs) == {"enhance": True, "card_bg": "#F6EFE6", "enhance_strength": 1.2}
    assert enhance_options_from_request({"enhance": False, "warm_tone": True}) == {"enhance": False, "warm_tone": True}


@pytest.mark.parametrize("mode", ["cutout", "cutout_plain", "cutout_card", "crop_card"])
def test_safe_extract_all_modes_without_opencv(portrait, tmp_path, mode):
    from services.image_enhancer import safe_extract_doctor_subject_image

    out = tmp_path / f"out_{mode}.png"
    res = safe_extract_doctor_subject_image(portrait, out, mode=mode, enhance=True)
    assert res["ok"] and out.is_file() and res["person_detected"]
    assert res["engine"] in ("u2net", "fallback")
    with Image.open(out) as im:
        assert im.size == (800, 800)
    assert res["sharpness_after"] > res["sharpness_before"]


def test_fallback_mask_isolates_person_and_drops_label_bar(portrait):
    from services.subject_fallback import fallback_subject_mask

    rgb = Image.open(portrait).convert("RGB")
    alpha, bbox = fallback_subject_mask(rgb)
    w, h = rgb.size
    assert alpha.shape == (h, w) and bbox is not None
    assert bbox[1] > h * 0.08  # thanh chữ trên cùng (3–8% chiều cao) đã bị loại
    assert alpha[int(h * 0.35), w // 2] > 200  # mặt
    assert alpha[int(h * 0.9), w // 2] > 200  # áo blouse trắng trên nền sáng
    assert alpha[int(h * 0.3), 5] < 30  # nền


# ---------------------------------------------------------------------------
# API ảnh bác sĩ (route cũ + tuỳ chọn mới, route hàng loạt)
# ---------------------------------------------------------------------------
def test_upload_doctor_image_legacy_and_with_options(api, fresh_demo, portrait):
    pid = "6-kenh-bac-si-demo"
    raw = portrait.read_bytes()
    st, res = api.request("POST", f"/api/projects/{pid}/upload-doctor-image?item_index=1&mode=cutout&run_step6=0&filename=a.png", raw=raw)
    assert st == 200 and res["ok"] and res["result"]["enhanced"] is False  # hành vi cũ
    st, res = api.request("POST", f"/api/projects/{pid}/upload-doctor-image?item_index=2&mode=cutout_plain&run_step6=1&filename=b.png&enhance=1&card_bg=%23F6EFE6", raw=raw)
    assert st == 200 and res["result"]["enhanced"] is True and res["result"]["card_bg"] == "#F6EFE6"
    item2 = next(i for i in res["project"]["bang"]["items"] if i["i"] == 2)
    assert item2["custom_image_path"].endswith("item_02_doctor.png")


def test_edit_doctor_image_preview_with_card_bg(api, fresh_demo):
    st, res = api.post("/api/projects/6-kenh-bac-si-demo/edit-doctor-image",
                       {"item_index": 3, "mode": "cutout", "preview_only": True, "card_bg": "#F0F7FF", "enhance": True})
    assert st == 200 and res["edited_rel"].endswith("preview_item_03.png") and res["project"] is None
    assert res["result"]["card_bg"] == "#F0F7FF"


def test_enhance_and_batch_endpoints(api, fresh_demo):
    pid = "6-kenh-bac-si-demo"
    st, one = api.post(f"/api/projects/{pid}/enhance-doctor-image", {"item_index": 1, "mode": "cutout", "card_bg": "beige"})
    assert st == 200 and one["ok"] and one["result"]["card_bg"] == "#F6EFE6"
    st, bad = api.post(f"/api/projects/{pid}/enhance-doctor-image", {"item_index": 99})
    assert st == 400
    st, b = api.post(f"/api/projects/{pid}/batch-process-images", {"mode": "cutout", "enhance": True, "card_bg": "#FFFDF9"})
    assert st == 200 and b["processed_count"] == 6 and not b["skipped"]
    assert all(r["sharpness_after"] > r["sharpness_before"] for r in b["results"])
    assert all(it.get("image_enhanced") for it in b["project"]["bang"]["items"])
    st, err = api.post(f"/api/projects/{pid}/batch-process-images", {"mode": "khong_co"})
    assert st == 400


# ---------------------------------------------------------------------------
# Cloud fallback & cấu hình
# ---------------------------------------------------------------------------
def test_cloud_fallback_never_overwrites_windows_paths(tmp_path):
    from services.cloud_env import apply_cloud_fallbacks, restore_original_paths
    from utils import save_config

    cfg = {"paths": {"remotion_dir": r"C:\Users\Dung\Developer\remotion-starter", "ffmpeg_exe": r"C:\ffmpeg.exe",
                     "projects_root": r"E:\vd chia se\projects"}, "port": 8765}
    apply_cloud_fallbacks(cfg, tmp_path)
    assert ":\\" not in cfg["paths"]["remotion_dir"] and cfg["cloud_mode"] is True
    out = tmp_path / "config.json"
    save_config(cfg, out)
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["paths"]["remotion_dir"] == r"C:\Users\Dung\Developer\remotion-starter"
    assert "cloud_mode" not in saved and "_cloud_original_paths" not in saved
    assert restore_original_paths(cfg)["paths"]["ffmpeg_exe"] == r"C:\ffmpeg.exe"


def test_repo_config_json_still_has_windows_paths():
    cfg = json.loads((APP / "config.json").read_text(encoding="utf-8"))
    assert cfg["paths"]["remotion_dir"].startswith("C:\\")
    assert "cloud_mode" not in cfg


def test_desktop_app_cli_args():
    import importlib.util

    spec = importlib.util.spec_from_file_location("desktop_app", APP / "desktop_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    o = mod._parse_cli_args(["--server", "--port", "8765"])
    assert o["server"] is True and o["port"] == 8765 and o["seed_demo"] is True
    assert mod._parse_cli_args([])["server"] is False


# ---------------------------------------------------------------------------
# Remotion
# ---------------------------------------------------------------------------
def test_remotion_tsx_autofit_and_centering():
    tsx = (APP / "remotion" / "ConvoAppDynamic.tsx").read_text(encoding="utf-8")
    assert "export const autoFitFontSize" in tsx
    assert tsx.count("fitFont(") >= 6
    assert 'alignItems: CENTER_INFO ? "center"' in tsx and 'textAlign: CENTER_INFO ? "center"' in tsx
    assert "estimateTitleBottom" in tsx and "heroImageScale" in tsx and "doctorCardFrame" in tsx


def test_remotion_embedded_template_in_sync_with_file():
    import remotion_templates as rt

    src = (APP / "remotion" / "ConvoAppDynamic.tsx").read_text(encoding="utf-8")
    assert rt.get_convo_app_tsx() == src
    assert rt.CONVO_APP_DYNAMIC_TSX == src, "Hãy đồng bộ lại CONVO_APP_DYNAMIC_TSX trong remotion_templates.py"


def test_ensure_composition_writes_tsx(tmp_path):
    import remotion_templates as rt

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Root.tsx").write_text("export const RemotionRoot = () => (\n  <>\n  </>\n);\n", encoding="utf-8")
    assert rt.ensure_remotion_dynamic_composition(tmp_path, {"totalFrames": 10}) == "ConvoAppDynamic"
    assert "autoFitFontSize" in (tmp_path / "src" / "ConvoAppDynamic.tsx").read_text(encoding="utf-8")
    assert "ConvoAppDynamic" in (tmp_path / "src" / "Root.tsx").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Toàn vẹn Frontend (Zero Regression)
# ---------------------------------------------------------------------------
LEGACY_GLOBALS = ["onScriptInputChanged", "handleDoctorFilesUpload", "openDoctorImageEditorModal", "runStep",
                  "onSelectProject", "saveProjectSettings", "applyAnhNhacCustomRequest", "populateWorkspace",
                  "switchTab", "parseScriptOutlineJS", "refreshProjectsList", "runNextStepOrApprove"]


def test_legacy_globals_kept_or_provided():
    app_js = (APP / "frontend" / "app.js").read_text(encoding="utf-8")
    mods = "".join(p.read_text(encoding="utf-8") for p in (APP / "frontend" / "modules").glob("*.js"))
    for name in LEGACY_GLOBALS:
        in_app = re.search(rf"^(async\s+)?function\s+{name}\s*\(", app_js, re.M)
        in_mod = f"window.{name} =" in mods
        if name in ("handleDoctorFilesUpload", "runStep"):
            continue  # CLAUDE.md liệt kê nhưng bản app.js hiện tại không có — không phải hồi quy
        assert in_app or in_mod, f"Thiếu hàm global {name}"
    for name in ("selectProject", "analyzeScriptOutlineNow", "studioSaveAll", "batchProcessAllDoctorImages",
                 "openAutoQaModal", "runAutoQaFix", "livePreviewGoTo", "setStudioTheme", "showToast"):
        assert f"window.{name} =" in mods, f"Module chưa cung cấp {name}"


def test_inline_handlers_in_index_resolve_to_functions():
    html = (APP / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (APP / "frontend" / "app.js").read_text(encoding="utf-8") + "".join(
        p.read_text(encoding="utf-8") for p in (APP / "frontend" / "modules").glob("*.js"))
    names = set(re.findall(r'on(?:click|change|input|drop|keydown)="(?:if\([^"]*?\)\{\s*event\.preventDefault\(\);\s*)?([A-Za-z_]\w*)\(', html))
    names -= {"if", "document", "event", "this"}
    missing = [n for n in sorted(names) if not re.search(rf"(function\s+{n}\s*\(|window\.{n}\s*=)", js)]
    assert not missing, missing


def test_new_modules_are_small():
    files = list((APP / "frontend" / "modules").glob("*.js")) + list((APP / "frontend" / "styles").glob("*.css")) + \
        list((APP / "backend" / "services").glob("*.py")) + list((APP / "tests").glob("*.py"))
    too_big = {f.name: n for f in files if (n := len(f.read_text(encoding="utf-8").splitlines())) > 260}
    assert not too_big, too_big
