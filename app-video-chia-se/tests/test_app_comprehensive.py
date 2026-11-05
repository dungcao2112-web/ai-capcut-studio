# -*- coding: utf-8 -*-
"""Kiểm thử toàn diện: phân tích kịch bản (6 kênh bác sĩ, 7 bệnh viện đi sinh, 3 đồ xài cho bé),
API server (route cũ + route mới), Yêu cầu thiết kế, Live Preview data và Auto-QA."""
from __future__ import annotations

import urllib.parse

SCRIPT_6_KENH = """6 KÊNH BÁC SĨ SẢN NHI MẸ BẦU NÊN THEO DÕI

1. BS Dương M. Tuấn
- Sản phụ khoa
2. BS Thảo Vy
- Nhi khoa
3. BS Quốc Bảo
- Sản khoa
4. BS Hồng Nhung
- Dinh dưỡng
5. BS Gia Huy
- Nhi sơ sinh
6. BS Ngọc Lan
- Hiếm muộn
"""

# Mẫu của chính app (loadSampleBenhVienList): "7." là số thứ tự series, danh sách có 8 bệnh viện
SCRIPT_7_BENH_VIEN = "7. BỆNH VIỆN ĐI SINH\n\nTừ dũ\nHùng Vương\nĐH Y Dược\nMê Kông\nVinmec\nTâm Anh\nHạnh Phúc\nBV Quốc Tế Mỹ (AIH)\n"

SCRIPT_3_DO_XAI = """3 ĐỒ XÀI CHO BÉ SƠ SINH MẸ NÊN SẮM

1. Bình sữa thuỷ tinh
- Dễ vệ sinh, không chứa BPA
2. Khăn sữa sợi tre
- Mềm, thấm hút tốt
3. Nhiệt kế điện tử
- Đo nhanh 1 giây
"""


def _outline(text, title=""):
    from media_ops import parse_script_outline
    from services.qa_validator import outline_warnings

    o = parse_script_outline(text, current_title=title)
    o["warnings"] = outline_warnings(o)
    return o


# ---------------------------------------------------------------------------
# 1. Phân tích kịch bản
# ---------------------------------------------------------------------------
def test_outline_6_kenh_bac_si_keeps_number_and_bullets():
    o = _outline(SCRIPT_6_KENH)
    assert o["title"] == "6 KÊNH BÁC SĨ SẢN NHI MẸ BẦU NÊN THEO DÕI"
    assert o["count"] == 6
    assert o["entries"][0] == {"heading": "BS Dương M. Tuấn", "bullets": ["Sản phụ khoa"]}
    assert o["warnings"] == []


def test_outline_7_benh_vien_series_prefix_is_not_a_count():
    o = _outline(SCRIPT_7_BENH_VIEN)
    assert o["title"] == "BỆNH VIỆN ĐI SINH"
    assert o["count"] == 8
    assert [e["heading"] for e in o["entries"]][:2] == ["Từ dũ", "Hùng Vương"]
    assert not [w for w in o["warnings"] if w["code"] == "title_count"]


def test_outline_3_do_xai_cho_be():
    o = _outline(SCRIPT_3_DO_XAI)
    assert o["count"] == 3 and o["title"].startswith("3 ĐỒ XÀI")
    assert all(e["bullets"] for e in o["entries"])


def test_outline_warnings_detect_mismatch_missing_and_duplicates():
    text = SCRIPT_6_KENH + "7. BS Thảo Vy\n"
    o = _outline(text)
    codes = {w["code"] for w in o["warnings"]}
    assert {"title_count", "missing_bullets", "duplicate"} <= codes
    assert next(w for w in o["warnings"] if w["code"] == "title_count")["fixable"] is True


# ---------------------------------------------------------------------------
# 2. API server — route cũ vẫn hoạt động, route mới hoạt động
# ---------------------------------------------------------------------------
def test_config_reports_cloud_mode_and_local_paths(api):
    st, data = api.get("/api/config")
    assert st == 200 and data["config"]["cloud_mode"] is True
    assert ":\\" not in data["config"]["paths"]["projects_root"]
    assert len(data["steps_meta"]) == 10


def test_projects_list_has_badges(api):
    st, data = api.get("/api/projects")
    assert st == 200
    by_id = {p["id"]: p for p in data["projects"]}
    assert by_id["6-kenh-bac-si-demo"]["item_count"] == 6
    assert by_id["7-benh-vien-di-sinh-demo"]["item_count"] == 7
    assert by_id["7-benh-vien-di-sinh-demo"]["preset_label"] == "Ảnh + Nhạc"
    for key in ("id", "title", "preset", "pipeline_status", "current_step"):  # trường cũ giữ nguyên
        assert key in by_id["6-kenh-bac-si-demo"]


def test_legacy_routes_still_work(api):
    st, proj = api.post("/api/projects", {"title": "TEST CŨ", "preset": "anh_nhac", "script_text": SCRIPT_3_DO_XAI})
    assert st == 200 and proj["title"] == "TEST CŨ"
    pid = urllib.parse.quote(proj["id"])
    st, loaded = api.get(f"/api/projects/{pid}")
    assert st == 200 and loaded["id"] == proj["id"]
    st, saved = api.post(f"/api/projects/{pid}/settings", {"title": "TEST ĐÃ SỬA", "settings": {"itemDurationSec": 3.0}})
    assert st == 200 and saved["title"] == "TEST ĐÃ SỬA" and saved["settings"]["itemDurationSec"] == 3.0
    st, f = api.get(f"/api/projects/{pid}/file?path=text/kich_ban.md")
    assert st == 200 and "Bình sữa" in f.decode("utf-8")
    st, lg = api.get(f"/api/projects/{pid}/logs/1")
    assert st == 200 and lg["step"] == 1
    st, _ = api.post(f"/api/projects/{pid}/delete")
    assert st == 200


def test_script_analyze_endpoint(api):
    st, data = api.post("/api/script/analyze", {"text": SCRIPT_6_KENH + "7. BS Mới\n- Nhi\n"})
    assert st == 200
    assert data["outline"]["count"] == 7
    assert any(w["code"] == "title_count" for w in data["outline"]["warnings"])


def test_environment_endpoint(api):
    st, env = api.get("/api/system/environment")
    assert st == 200 and env["cloud_mode"] is True and env["pillow"] is True


def test_static_frontend_and_modules_served(api):
    st, html = api.get("/")
    assert st == 200
    html = html.decode("utf-8")
    for mod in ("ui_enhancements", "project_browser", "theme_adapter", "live_preview_9x16", "live_preview_render",
                "script_inspector_pro", "visual_prompt_chips", "doctor_editor_pro", "qa_panel"):
        assert f"modules/{mod}.js" in html
        st, js = api.get(f"/modules/{mod}.js")
        assert st == 200 and len(js) > 500
    for css in ("studio_pro", "studio_components"):
        st, body = api.get(f"/styles/{css}.css")
        assert st == 200 and (b"data-theme" in body or b"lp-dock" in body)


def test_unknown_route_404(api):
    st, data = api.get("/api/khong-ton-tai")
    assert st == 404


# ---------------------------------------------------------------------------
# 3. Yêu cầu thiết kế & Live Preview
# ---------------------------------------------------------------------------
def test_visual_prompt_parse_rules():
    from services.visual_prompt import parse_visual_prompt

    st = parse_visual_prompt("Nền màu be ấm (#F6EFE6); Phóng to khung ảnh chính 120%; Căn giữa địa chỉ & thông tin")
    assert st["bgColor"] == "#F6EFE6" and st["cardColor"] == "#FFFDF9"
    assert st["heroImageScale"] == 1.2 and st["centerInfoPills"] is True
    pink = parse_visual_prompt("Nền hồng phấn Mẹ & Bé")
    assert pink["bgColor"] == "#FCE8EC"
    assert parse_visual_prompt("nền tối")["bgTheme"] == "dark"
    assert parse_visual_prompt("")["matched"] == []


def test_visual_prompt_api_applies_settings(api, fresh_demo):
    pid = "6-kenh-bac-si-demo"
    st, res = api.post(f"/api/projects/{pid}/visual-prompt", {"text": "Nền hồng phấn Mẹ & Bé; Bảng tổng hợp chữ to rõ"})
    assert st == 200
    s = res["project"]["settings"]
    assert s["customBgColor"] == "#FCE8EC" and s["summaryLargeText"] is True and "fce8ec" in s["backgroundColor"]
    st, got = api.get(f"/api/projects/{pid}/visual-prompt")
    assert got["visual_prompt"].startswith("Nền hồng phấn")


def test_preview_data_has_images_and_style(api, fresh_demo):
    st, d = api.get("/api/projects/7-benh-vien-di-sinh-demo/preview-data")
    assert st == 200 and d["outline_count"] == 7 and len(d["items"]) == 7
    assert all(it["image_url"].startswith("/api/projects/") for it in d["items"])
    st, img = api.get(d["items"][0]["image_url"])
    assert st == 200 and img[:8] == b"\x89PNG\r\n\x1a\n"
    assert d["style"]["bgColor"] == "#F6EFE6"


# ---------------------------------------------------------------------------
# 4. Auto-QA
# ---------------------------------------------------------------------------
def test_qa_check_demo_is_perfect(api, fresh_demo):
    st, r = api.get("/api/projects/7-benh-vien-di-sinh-demo/qa-check")
    assert st == 200 and r["total"] == 10
    assert r["score"] == 100, [c for c in r["checks"] if c["status"] != "pass"]
    assert set(r["counts"].values()) == {7}


def test_qa_autofix_resyncs_counts_and_title(api, fresh_demo):
    from pipeline import get_project_dir

    pid = "7-benh-vien-di-sinh-demo"
    sp = get_project_dir(pid) / "text" / "kich_ban.md"
    sp.write_text(sp.read_text(encoding="utf-8") + "8. BV Nhân Dân Gia Định\n- Quận Bình Thạnh, TP.HCM\n", encoding="utf-8")
    st, before = api.get(f"/api/projects/{pid}/qa-check")
    failed = {c["id"] for c in before["checks"] if c["status"] == "fail"}
    assert {"count_consistency", "title_count", "names_match"} <= failed
    st, res = api.post(f"/api/projects/{pid}/qa-autofix", {"rerun_steps": True})
    assert st == 200
    after = res["after"]
    assert set(after["counts"].values()) == {8}
    assert res["project"]["title"].startswith("8 BỆNH VIỆN")
    assert sp.read_text(encoding="utf-8").splitlines()[0].startswith("8 BỆNH VIỆN")
    # Mục mới chưa có ảnh: QA phải báo đúng & không giả vờ đã sửa
    assert next(c for c in after["checks"] if c["id"] == "images_present")["status"] == "fail"
    assert any("ảnh" in w for w in res["warnings"])
    # Ảnh của các mục cũ được giữ nguyên theo tên
    items = res["project"]["bang"]["items"]
    assert items[0]["custom_image_path"].endswith("item_01.png")


def test_qa_detects_visual_prompt_mismatch_and_fixes(api, fresh_demo):
    from pipeline import get_project_dir, save_project_state
    from utils import read_json

    pid = "6-kenh-bac-si-demo"
    pdir = get_project_dir(pid)
    proj = read_json(pdir / "project.json")
    proj["settings"]["customBgColor"] = "#000000"
    proj["settings"]["centerInfoPills"] = False
    save_project_state(pdir, proj)
    st, r = api.get(f"/api/projects/{pid}/qa-check")
    bg = next(c for c in r["checks"] if c["id"] == "bg_theme_match")
    assert bg["status"] == "fail" and "customBgColor" in bg["detail"]
    st, res = api.post(f"/api/projects/{pid}/qa-autofix", {"rerun_steps": False})
    assert next(c for c in res["after"]["checks"] if c["id"] == "bg_theme_match")["status"] == "pass"
    assert res["project"]["settings"]["centerInfoPills"] is True


def test_qa_detects_bullet_drift_and_restores_from_script(api, fresh_demo):
    from pipeline import get_project_dir
    from utils import read_json, write_json

    pid = "7-benh-vien-di-sinh-demo"
    bp = get_project_dir(pid) / "text" / "bang.json"
    bang = read_json(bp)
    bang["items"][2]["bullets"] = []
    write_json(bp, bang)
    st, r = api.get(f"/api/projects/{pid}/qa-check")
    nm = next(c for c in r["checks"] if c["id"] == "names_match")
    assert nm["status"] == "warn" and "3" in nm["detail"]
    assert next(c for c in r["checks"] if c["id"] == "images_present")["fixable"] is False
    st, res = api.post(f"/api/projects/{pid}/qa-autofix", {"rerun_steps": True})
    assert res["project"]["bang"]["items"][2]["bullets"] == ["Quận 5, TP.HCM"]
    assert res["after"]["score"] == 100
