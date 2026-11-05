# -*- coding: utf-8 -*-
"""Tiêu đề phụ (có / không / ghi rõ) + định dạng khối cách dòng trống — Python & JS phải ra cùng kết quả."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]

AN_DAM = """SHOP SẮM ĐỒ ĂN DẶM CHO CON

Chất lượng - Xài bền - Kinh tế

Thuyền xưa
Bánh ăn dặm + Dầu ăn dặm thêm khi chiên xào hoặc sau khi nấu xen kẽ với mỡ động vật

Anpaso
Gia vị nêm đa dạng cho con+Bánh ăn dặm

Sokfarm
Nước tương và Mật hoa dừa quốc dân
Gia vị nêm nếm nhạt, vị ngọt tự nhiên

Bear
Máy móc dùng bền + Kinh tế
"""
AN_DAM_NO_SUB = AN_DAM.replace("Chất lượng - Xài bền - Kinh tế\n\n", "")
AN_DAM_MARKER = AN_DAM.replace("Chất lượng - Xài bền - Kinh tế", "Tiêu đề phụ: Mẹ nên lưu lại")
LIST_SUB = "TOP QUÁN ĂN DẶM\n\nNgon - Sạch - Rẻ\n\nQuán A\nQuán B\nQuán C\n"
CASES = {
    "an_dam": AN_DAM,
    "an_dam_no_sub": AN_DAM_NO_SUB,
    "an_dam_marker": AN_DAM_MARKER,
    "list_sub": LIST_SUB,
    "benh_vien": "7. BỆNH VIỆN ĐI SINH\n\nTừ dũ\nHùng Vương\nĐH Y Dược\nMê Kông\n",
    "bac_si": "6 KÊNH BÁC SĨ\n\n1. BS A\n- Sản khoa\n2. BS B\n- Nhi khoa\n",
    "bullets_sub": "3 MÓN ĐỒ\nRẻ - Bền - Đẹp\n\n1. Bình sữa\n- BPA free\n2. Khăn\n- Mềm\n3. Nhiệt kế\n- Nhanh\n",
}
NAMES = ["Thuyền xưa", "Anpaso", "Sokfarm", "Bear"]


def _py(text):
    from media_ops import parse_script_outline

    return parse_script_outline(text)


def test_an_dam_with_subtitle_is_4_items():
    o = _py(AN_DAM)
    assert o["title"] == "SHOP SẮM ĐỒ ĂN DẶM CHO CON"
    assert o["subtitle"] == "Chất lượng - Xài bền - Kinh tế"
    assert [e["heading"] for e in o["entries"]] == NAMES and o["count"] == 4
    assert o["entries"][2]["bullets"] == ["Nước tương và Mật hoa dừa quốc dân", "Gia vị nêm nếm nhạt, vị ngọt tự nhiên"]
    assert o["format"] == "blocks"


def test_an_dam_without_subtitle():
    o = _py(AN_DAM_NO_SUB)
    assert o["subtitle"] == "" and [e["heading"] for e in o["entries"]] == NAMES


def test_explicit_subtitle_marker():
    o = _py(AN_DAM_MARKER)
    assert o["subtitle"] == "Mẹ nên lưu lại" and o["count"] == 4


def test_plain_list_with_subtitle_and_legacy_formats_unchanged():
    o = _py(LIST_SUB)
    assert o["subtitle"] == "Ngon - Sạch - Rẻ" and [e["heading"] for e in o["entries"]] == ["Quán A", "Quán B", "Quán C"]
    from media_ops import _parse_script_outline_legacy

    for key in ("benh_vien", "bac_si"):
        new, old = _py(CASES[key]), _parse_script_outline_legacy(CASES[key])
        assert new["entries"] == old["entries"] and new["title"] == old["title"] and new["subtitle"] == old["subtitle"]


def _js_parse_all(cases: dict[str, str]) -> dict:
    app_js = (APP / "frontend" / "app.js").read_text(encoding="utf-8")
    m = re.search(r"function parseScriptOutlineJS\(.*?\n}\n", app_js, re.S)
    assert m, "Không tìm thấy parseScriptOutlineJS trong app.js"
    mod = (APP / "frontend" / "modules" / "script_outline_js.js").read_text(encoding="utf-8")
    prog = ("const window = globalThis;\n" + m.group(0) + "window.parseScriptOutlineJS = parseScriptOutlineJS;\n" + mod +
            f"\nconst cases = {json.dumps(cases, ensure_ascii=False)};\nconst out = {{}};\n"
            "for (const k of Object.keys(cases)) { const o = window.parseScriptOutlineJS(cases[k], '');"
            " out[k] = { title: o.title, subtitle: o.subtitle, entries: o.entries, format: o.format,"
            " serialized: window.serializeStudioOutline({ prefix: window.studioFirstLineInfo(cases[k]).prefix,"
            " title: o.hasExplicitTitle ? o.title : '', subtitle: o.subtitle || '', format: o.format, entries: o.entries }) }; }\n"
            "console.log(JSON.stringify(out));\n")
    res = subprocess.run(["node", "-e", prog], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="cần Node.js để chạy bộ phân tích JS")
def test_js_and_python_parsers_agree_and_serialize_roundtrip():
    js = _js_parse_all(CASES)
    for key, text in CASES.items():
        py = _py(text)
        assert js[key]["title"] == py["title"], key
        assert js[key]["subtitle"] == py["subtitle"], key
        assert js[key]["entries"] == py["entries"], key
        # Ghi ngược từ trình sửa rồi phân tích lại (Python) => giữ nguyên tiêu đề phụ & các mục
        again = _py(js[key]["serialized"])
        assert again["subtitle"] == py["subtitle"] and again["entries"] == py["entries"], (key, js[key]["serialized"])


def test_settings_save_sets_then_clears_script_subtitle(api):
    st, proj = api.post("/api/projects", {"title": "ĂN DẶM", "preset": "anh_nhac"})
    pid = urllib.parse.quote(proj["id"])
    bang = {"tieu_de": "X", "tong": 0, "items": [{"i": k + 1, "ten": n, "display_name": n.upper()} for k, n in enumerate(NAMES)]}
    st, p1 = api.post(f"/api/projects/{pid}/settings", {"script_text": AN_DAM, "bang": bang, "settings": {"preset": "anh_nhac"}})
    assert st == 200 and p1["bang"]["subtitle"] == "Chất lượng - Xài bền - Kinh tế"
    assert p1["settings"]["summarySubtitle"] == "CHẤT LƯỢNG - XÀI BỀN - KINH TẾ"
    bang["subtitle"] = p1["bang"]["subtitle"]  # frontend gửi lại tiêu đề phụ cũ như collectBangFromTable
    st, p2 = api.post(f"/api/projects/{pid}/settings", {"script_text": AN_DAM_NO_SUB, "bang": bang, "settings": {"preset": "anh_nhac"}})
    assert st == 200 and p2["bang"]["subtitle"] == "" and p2["settings"]["summarySubtitle"] == ""
    st, a = api.post("/api/script/analyze", {"text": AN_DAM})
    assert a["outline"]["count"] == 4 and a["outline"]["subtitle"].startswith("Chất lượng")
    api.post(f"/api/projects/{pid}/delete")
