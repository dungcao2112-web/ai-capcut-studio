# -*- coding: utf-8 -*-
"""• Có link nguồn => Agy CLI TỰ BẬT ở mọi luồng tìm ảnh (nút, Bước 3, lưu kịch bản), AI nhận mẫu câu mô tả +
  thông tin từng mục; mô tả sếp tự viết trong kịch bản luôn được giữ.
• Cỡ ảnh ở Bước 3 (cỡ ảnh chung + % từng mục) phải tác động lên video Remotion & Live Preview."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

APP = Path(__file__).resolve().parents[1]
SCRIPT = "7 BỆNH VIỆN\n\n1. BV Từ Dũ\n2. Hùng Vương\n- Tự viết: phòng sinh gia đình\n"


def _setup(pdir, links, ai=True, template="Giá sinh: {giá}\n{địa chỉ}"):
    from pipeline import save_project_state
    from utils import read_json

    proj = read_json(pdir / "project.json")
    proj["settings"].update({"sourceLinks": links, "aiWithSources": ai, "infoTemplate": template, "collageLayout": "1"})
    save_project_state(pdir, proj)


def _fake_dl(item_name, project_title, out_path, candidate_index=0, custom_query=""):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (900, 600), (90, 120, 150)).save(out_path)
    return {"ok": True, "path": str(out_path)}


def test_agy_auto_on_with_links_and_user_bullets_kept(fresh_demo, site, monkeypatch):
    import cli_ai
    import media_ops
    from pipeline import get_project_dir
    from utils import read_json

    calls = []

    def fake_ai(project_dir, step_name, prompt, preferred_provider="agy", effort="low", **kw):
        calls.append(prompt)
        return {"json": {"items": [{"i": 1, "bullets": ["Giá sinh: 3.500.000đ", "284 Cống Quỳnh, Quận 1, TP.HCM"]},
                                   {"i": 2, "bullets": ["AI viết lại — không được dùng"]}]}}

    monkeypatch.setattr(cli_ai, "invoke_cli_agent", fake_ai)
    monkeypatch.setattr(media_ops, "download_web_image_for_item", _fake_dl)
    pdir = get_project_dir("7-benh-vien-di-sinh-demo")
    _setup(pdir, [f"{site}/list.html"])
    res = media_ops.parse_and_fetch_anh_nhac_list(pdir, SCRIPT, use_ai=False)  # luồng Bước 3 / lưu kịch bản
    assert res["ai_used"] and res["ai_forced_by_sources"] and len(calls) == 1
    assert "MẪU CÂU MÔ TẢ BẮT BUỘC" in calls[0] and "Giá sinh: {giá}" in calls[0]
    assert "1. BV Từ Dũ: Địa chỉ: 284 Cống Quỳnh" in calls[0]  # thông tin nguồn theo từng mục
    items = read_json(pdir / "text" / "bang.json")["items"]
    assert items[0]["bullets"] == ["Giá sinh: 3.500.000đ", "284 Cống Quỳnh, Quận 1, TP.HCM"] and items[0]["bullets_source"] == "ai"
    assert items[1]["bullets"] == ["Tự viết: phòng sinh gia đình"]  # mô tả sếp viết được giữ


def test_agy_not_forced_without_links_or_when_turned_off(fresh_demo, site, monkeypatch):
    import cli_ai
    import media_ops
    from pipeline import get_project_dir

    calls = []
    monkeypatch.setattr(cli_ai, "invoke_cli_agent", lambda *a, **k: calls.append(1) or {"json": None})
    monkeypatch.setattr(media_ops, "download_web_image_for_item", _fake_dl)
    pdir = get_project_dir("7-benh-vien-di-sinh-demo")
    _setup(pdir, [])
    assert not media_ops.parse_and_fetch_anh_nhac_list(pdir, SCRIPT, use_ai=False)["ai_used"]
    _setup(pdir, [f"{site}/list.html"], ai=False)
    assert not media_ops.parse_and_fetch_anh_nhac_list(pdir, SCRIPT, use_ai=False)["ai_used"]
    assert calls == []


def test_agy_missing_falls_back_to_template_fill(fresh_demo, site, monkeypatch):
    """Máy chưa cài Agy (lỗi khi gọi) => vẫn điền mô tả theo mẫu từ link."""
    import cli_ai
    import media_ops
    import services.auto_media as am
    from pipeline import get_project_dir
    from utils import read_json

    def boom(*a, **k):
        raise FileNotFoundError("agy.exe")

    monkeypatch.setattr(cli_ai, "invoke_cli_agent", boom)
    monkeypatch.setattr(media_ops, "download_web_image_for_item", _fake_dl)
    monkeypatch.setattr(am, "web_candidate", lambda *a: None)
    pdir = get_project_dir("7-benh-vien-di-sinh-demo")
    _setup(pdir, [f"{site}/list.html"])
    media_ops.parse_and_fetch_anh_nhac_list(pdir, SCRIPT, use_ai=False)
    items = read_json(pdir / "text" / "bang.json")["items"]
    assert items[0]["bullets"] == ["Giá sinh: 3.500.000đ", "284 Cống Quỳnh, Quận 1, TP.HCM"]
    assert items[1]["bullets"] == ["Tự viết: phòng sinh gia đình"]


def test_media_settings_ai_toggle(api, fresh_demo):
    st, r = api.post("/api/projects/7-benh-vien-di-sinh-demo/media-settings", {"aiWithSources": False})
    assert st == 200 and r["settings"]["aiWithSources"] is False


def test_step3_image_size_controls_reach_remotion_and_preview(api, fresh_demo):
    tsx = (APP / "remotion" / "ConvoAppDynamic.tsx").read_text(encoding="utf-8")
    hero = tsx[tsx.index("const userScale"):tsx.index("let heroFitPx")]
    assert "cfg.productImageSize" in hero and "itemScale" in hero and "heroScale" in hero
    assert "0.86 * userScale" in tsx and "measureText(k)" in tsx  # mặc định 86%, phóng to => chữ nhường chỗ
    render_js = (APP / "frontend" / "modules" / "live_preview_render.js").read_text(encoding="utf-8")
    assert "style.productImageSize" in render_js and "item.image_scale" in render_js
    pid = "7-benh-vien-di-sinh-demo"
    st, _p = api.post(f"/api/projects/{pid}/settings", {"settings": {"productImageSize": 520}})
    st, d = api.get(f"/api/projects/{pid}/preview-data")
    assert d["style"]["productImageSize"] == 520 and d["items"][0]["image_scale"] == 1.0
