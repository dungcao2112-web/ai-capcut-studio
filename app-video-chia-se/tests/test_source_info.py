# -*- coding: utf-8 -*-
"""📚 Thông tin từ link nguồn: rút địa chỉ/giá/hotline/giờ mở cửa theo từng mục, điền MẪU CÂU MÔ TẢ của sếp
(chỉ điền chỗ {…}, dòng thiếu thông tin thì bỏ — không thêm câu tự do), tự điền mô tả, ngữ cảnh cho AI."""
from __future__ import annotations


def test_facts_and_description_from_sources(site):
    from services.source_info import ai_context, describe, extract_facts, info_for_item
    from services.source_links import fetch_source

    facts = {f["key"]: f["text"] for f in extract_facts("Địa chỉ: 12 Lê Lợi, Q1. Hotline 0909 123 456 • Giá chỉ 150k - 200k • Giờ mở cửa: 7h - 21h")}
    assert facts == {"address": "12 Lê Lợi, Q1", "phone": "0909 123 456", "price": "150k - 200k", "hours": "7h - 21h"}
    assert extract_facts("Giá sinh dịch vụ: 8 - 12 triệu")[0]["text"] == "8 - 12 triệu"
    assert extract_facts("giá chỉ 99.000đ/hộp")[0]["text"] == "99.000đ"
    srcs = [fetch_source(f"{site}/list.html"), fetch_source(f"{site}/dhyd.html")]
    info = info_for_item("BV Từ Dũ", srcs)
    assert describe(info) == ["284 Cống Quỳnh, Quận 1, TP.HCM", "Giá: 3.500.000đ"]
    assert describe(info_for_item("Hùng Vương", srcs))[0].startswith("Phòng sinh gia đình")  # không có số liệu => 1 câu tóm tắt
    assert describe(info_for_item("BV ĐH Y Dược", srcs))[0].startswith("BV ĐH Y Dược TP.HCM có phòng sinh")
    ctx = ai_context(["BV Từ Dũ", "Vinmec"], srcs)
    assert "1. BV Từ Dũ: Địa chỉ: 284 Cống Quỳnh" in ctx and "Vinmec" not in ctx


def test_auto_fill_descriptions_only_for_items_without(api, fresh_demo, site, monkeypatch):
    import services.auto_media as am
    from pipeline import get_project_dir
    from utils import read_json, write_json

    monkeypatch.setattr(am, "web_candidate", lambda *a: None)
    pid = "7-benh-vien-di-sinh-demo"
    bp = get_project_dir(pid) / "text" / "bang.json"
    bang = read_json(bp)
    for it in bang["items"][:2]:
        it["bullets"], it["ghi_chu"] = [], ""  # BV Từ Dũ & Hùng Vương chưa có mô tả
    write_json(bp, bang)
    api.post(f"/api/projects/{pid}/media-settings", {"collageLayout": "1", "sourceLinks": [f"{site}/list.html"]})  # tự điền: mặc định bật
    st, res = api.post(f"/api/projects/{pid}/auto-media", {})
    items = {i["i"]: i for i in res["project"]["bang"]["items"]}
    assert items[1]["bullets"] == ["284 Cống Quỳnh, Quận 1, TP.HCM", "Giá: 3.500.000đ"] and items[1]["bullets_from_sources"]
    assert items[2]["bullets"][0].startswith("Phòng sinh gia đình")
    assert items[3]["bullets"] == ["Quận 5, TP.HCM"]  # đã có mô tả => giữ nguyên
    rep = {x["i"]: x for x in res["report"]["items"]}
    assert rep[1]["facts"] == 3 and rep[1]["info_added"]
    # Tắt tự điền => chỉ lưu thông tin để xem, không đổi mô tả
    bang = read_json(bp)
    bang["items"][3]["bullets"] = []
    write_json(bp, bang)
    api.post(f"/api/projects/{pid}/media-settings", {"autoInfoFromSources": False})
    st, res2 = api.post(f"/api/projects/{pid}/auto-media", {})
    assert res2["project"]["bang"]["items"][3]["bullets"] == []


def test_description_template_fills_only_known_info_and_drops_missing_lines(site):
    from services.source_info import fill_template, template_for_item
    from services.source_links import fetch_source

    srcs = [fetch_source(f"{site}/list.html")]
    tpl = "📍 {địa chỉ}\nGiá sinh thường: {giá}\nHotline: {hotline}\nGiờ khám: {giờ mở cửa}\nBác sĩ trưởng khoa: {bác sĩ trưởng khoa}"
    _info, desc = template_for_item("BV Từ Dũ", srcs, tpl)
    assert desc == ["📍 284 Cống Quỳnh, Quận 1, TP.HCM", "Giá sinh thường: 3.500.000đ", "Hotline: 028 5404 2829"]
    _info, desc2 = template_for_item("Hùng Vương", srcs, tpl)
    assert desc2 == []  # không có thông tin nào theo mẫu => không thêm câu tự do
    _i, desc3 = template_for_item("Hùng Vương", srcs, "Ưu điểm: {tóm tắt}")
    assert desc3[0].startswith("Ưu điểm: Phòng sinh gia đình")
    custom = fill_template("Trưởng khoa: {trưởng khoa}", {"facts": []}, ["Giới thiệu\nTrưởng Khoa: PGS. Lê Văn B\nKhác"])
    assert custom == ["Trưởng khoa: PGS. Lê Văn B"]


def test_template_api_preview_and_auto_fill(api, fresh_demo, site, monkeypatch):
    import services.auto_media as am
    from pipeline import get_project_dir
    from utils import read_json, write_json

    monkeypatch.setattr(am, "web_candidate", lambda *a: None)
    pid = "7-benh-vien-di-sinh-demo"
    bp = get_project_dir(pid) / "text" / "bang.json"
    bang = read_json(bp)
    bang["items"][0]["bullets"], bang["items"][0]["ghi_chu"] = [], ""
    write_json(bp, bang)
    tpl = "Giá sinh thường: {giá}\nHotline: {hotline}\n" + "\n".join(f"Dòng {k}: {{x{k}}}" for k in range(8))
    st, r = api.post(f"/api/projects/{pid}/media-settings", {"collageLayout": "1", "sourceLinks": [f"{site}/list.html"], "infoTemplate": tpl})
    assert len(r["settings"]["infoTemplate"].splitlines()) == 6  # tối đa 6 dòng
    st, prev = api.post(f"/api/projects/{pid}/source-info-preview", {})
    row = next(x for x in prev["items"] if x["i"] == 1)
    assert row["template_bullets"] == ["Giá sinh thường: 3.500.000đ", "Hotline: 028 5404 2829"] and not row["has_bullets"]
    st, prev2 = api.post(f"/api/projects/{pid}/source-info-preview", {"template": "📍 {địa chỉ}"})
    assert next(x for x in prev2["items"] if x["i"] == 1)["template_bullets"] == ["📍 284 Cống Quỳnh, Quận 1, TP.HCM"]
    st, res = api.post(f"/api/projects/{pid}/auto-media", {})
    it1 = res["project"]["bang"]["items"][0]
    assert it1["bullets"] == ["Giá sinh thường: 3.500.000đ", "Hotline: 028 5404 2829"]
    assert it1["source_info"]["template_bullets"] == it1["bullets"]


def test_ai_context_carries_template(site):
    from services.source_info import ai_context
    from services.source_links import fetch_source

    ctx = ai_context(["BV Từ Dũ"], [fetch_source(f"{site}/list.html")], template="Giá: {giá}")
    assert ctx.startswith("MẪU CÂU MÔ TẢ BẮT BUỘC") and "Giá: {giá}" in ctx and "KHÔNG thêm câu ngoài mẫu" in ctx
