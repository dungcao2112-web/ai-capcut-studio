# -*- coding: utf-8 -*-
"""Mẫu ghép chung (chọn ở Bước 1) + Link nguồn: nhận diện link, đọc trang, khớp ảnh/thông tin theo mục,
tự ghép cho tất cả mục. Dùng 1 web server cục bộ giả lập nên không cần Internet."""
from __future__ import annotations

import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    colors = {"tu-du": (200, 40, 60), "hung-vuong": (30, 90, 200), "dh-y-duoc": (20, 140, 90), "logo": (0, 0, 0)}
    for name, c in colors.items():
        size = (64, 64) if name == "logo" else (900, 650)
        Image.new("RGB", size, c).save(root / f"{name}.jpg")
    (root / "list.html").write_text("""<html><head><title>Top bệnh viện đi sinh</title>
      <meta property="og:description" content="Danh sách bệnh viện"></head><body>
      <img src="logo.jpg" alt="logo">
      <h2>BV Từ Dũ</h2><p>BV Từ Dũ là bệnh viện phụ sản lớn nhất phía Nam, nằm ở Quận 1.</p>
      <img src="tu-du.jpg" alt="Sảnh BV Từ Dũ">
      <h2>Hùng Vương</h2><p>Bệnh viện Hùng Vương có khoa sinh dịch vụ rất đông mẹ bầu chọn.</p>
      <img data-src="/hung-vuong.jpg" alt="BV Hùng Vương mặt tiền">
      <script>var x = "BV Từ Dũ không phải chữ";</script></body></html>""", encoding="utf-8")
    (root / "dhyd.html").write_text("""<html><head><title>BV ĐH Y Dược</title>
      <meta property="og:title" content="BV ĐH Y Dược"><meta property="og:image" content="/dh-y-duoc.jpg">
      <meta property="og:description" content="BV ĐH Y Dược TP.HCM có phòng sinh gia đình hiện đại."></head><body>Trang chủ</body></html>""",
                                  encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_extract_links_from_messy_paste():
    from services.source_links import extract_links, link_kind

    text = "Xem https://shopee.vn/a-b?x=1, và (https://www.tiktok.com/@bs.demo/video/1). Ảnh: https://x.vn/a.jpg… https://shopee.vn/a-b?x=1"
    links = extract_links(text)
    assert links == ["https://shopee.vn/a-b?x=1", "https://www.tiktok.com/@bs.demo/video/1", "https://x.vn/a.jpg"]
    assert [link_kind(u) for u in links] == ["shopee", "tiktok", "image"]


def test_fetch_source_reads_title_images_text(site):
    from services.source_links import fetch_source

    s = fetch_source(f"{site}/list.html")
    assert s["ok"] and s["title"] == "Top bệnh viện đi sinh"
    urls = [i["url"] for i in s["images"]]
    assert f"{site}/tu-du.jpg" in urls and f"{site}/hung-vuong.jpg" in urls
    assert not any("logo" in u for u in urls)  # bỏ logo/icon
    assert "không phải chữ" not in s["text"]  # bỏ nội dung <script>
    og = fetch_source(f"{site}/dhyd.html")
    assert og["images"][0]["url"] == f"{site}/dh-y-duoc.jpg" and og["description"].startswith("BV ĐH Y Dược")
    img = fetch_source(f"{site}/tu-du.jpg")
    assert img["ok"] and img["kind"] == "image"
    bad = fetch_source(f"{site}/khong-co.html")
    assert not bad["ok"] and bad["error"]


def test_match_images_and_info_per_item(site):
    from services.source_links import fetch_source, images_for_item, info_for_item

    srcs = [fetch_source(f"{site}/list.html"), fetch_source(f"{site}/dhyd.html")]
    assert images_for_item("BV Từ Dũ", 0, 3, srcs)[0]["url"].endswith("tu-du.jpg")
    assert images_for_item("Hùng Vương", 1, 3, srcs)[0]["url"].endswith("hung-vuong.jpg")
    assert images_for_item("BV ĐH Y Dược", 2, 3, srcs)[0]["url"].endswith("dh-y-duoc.jpg")
    assert images_for_item("Vinmec", 3, 3, srcs) == []
    info = info_for_item("BV Từ Dũ", srcs)
    assert info and "phụ sản lớn nhất" in info[0]["text"]
    # Mỗi mục 1 link theo thứ tự => không khớp tên vẫn lấy ảnh đại diện của link cùng thứ tự
    assert images_for_item("Tên lạ", 1, 2, srcs)[0]["url"].endswith("dh-y-duoc.jpg")


def test_media_settings_api_and_inspect(api, fresh_demo, site):
    pid = "7-benh-vien-di-sinh-demo"
    st, r = api.post(f"/api/projects/{pid}/media-settings", {"collageLayout": "4-luoi", "collageStyle": {"bg": "beige", "border": "brown"},
                                                             "sourceLinks": [f"{site}/list.html  {site}/dhyd.html", f"{site}/list.html"],
                                                             "autoInfoFromSources": True})
    assert st == 200 and r["settings"]["collageLayout"] == "4-luoi"
    assert r["settings"]["sourceLinks"] == [f"{site}/list.html", f"{site}/dhyd.html"]
    st, bad = api.post(f"/api/projects/{pid}/media-settings", {"collageLayout": "9-luoi"})
    assert st == 400
    st, ins = api.post("/api/sources/inspect", {"links": [f"{site}/list.html", f"{site}/khong-co.html"], "project_id": pid})
    assert [s["ok"] for s in ins["sources"]] == [True, False] and ins["sources"][0]["images"] == 2
    st, ex = api.post("/api/sources/extract", {"text": f"a {site}/list.html b"})
    assert ex["links"][0]["kind"] == "web"


def test_auto_media_collage_for_all_items_from_sources(api, fresh_demo, site, monkeypatch, tmp_path):
    import services.auto_media as am

    web_img = tmp_path / "web.png"
    Image.new("RGB", (800, 600), (120, 120, 120)).save(web_img)
    calls = []
    monkeypatch.setattr(am, "web_candidate", lambda name, title, out, cand: calls.append(name) or web_img)
    pid = "7-benh-vien-di-sinh-demo"
    api.post(f"/api/projects/{pid}/media-settings", {"collageLayout": "2-ngang", "sourceLinks": [f"{site}/list.html", f"{site}/dhyd.html"],
                                                     "autoInfoFromSources": True})
    st, res = api.post(f"/api/projects/{pid}/auto-media", {})
    assert st == 200, res
    rep = {x["i"]: x for x in res["report"]["items"]}
    assert len(rep) == 7 and all(x["status"].startswith("Ghép 2/2") for x in rep.values())
    assert rep[1]["from_sources"] == 1 and rep[2]["from_sources"] == 1 and rep[3]["from_sources"] == 1
    assert rep[5]["from_sources"] == 0  # Vinmec không có trong nguồn => ảnh hiện tại + ảnh web
    items = {i["i"]: i for i in res["project"]["bang"]["items"]}
    assert items[1]["collage_layout"] == "2-ngang" and len(items[1]["gallery"]) == 2
    assert items[1]["gallery"][0]["path"].endswith("item_01_src0.png")  # ảnh từ nguồn đứng ô đầu
    assert "/framed/" in items[1]["custom_image_path"]
    assert items[1]["source_info"] and "phụ sản" in items[1]["source_info"][0]["text"]
    assert items[1]["bullets"] == ["Quận 1, TP.HCM"]  # đã có mô tả => không ghi đè
    assert all(p["image_file"] for p in res["project"]["products_prepared"]["items"])


def test_single_layout_uses_source_image_and_skips_web(api, fresh_demo, site, monkeypatch):
    import services.auto_media as am

    monkeypatch.setattr(am, "web_candidate", lambda *a: pytest.fail("không được tìm web khi đã có ảnh"))
    pid = "7-benh-vien-di-sinh-demo"
    api.post(f"/api/projects/{pid}/media-settings", {"collageLayout": "1", "sourceLinks": [f"{site}/list.html"]})
    st, res = api.post(f"/api/projects/{pid}/auto-media", {})
    items = {i["i"]: i for i in res["project"]["bang"]["items"]}
    assert items[1]["custom_image_path"].endswith("item_01_src0.png") and items[1]["image_source_urls"][0].endswith("tu-du.jpg")
    assert items[5]["custom_image_path"].endswith("item_05.png")  # không khớp nguồn => giữ ảnh hiện tại


def test_fetch_flow_applies_template_automatically(fresh_demo, monkeypatch, tmp_path):
    """Bấm 'Tự tìm & Gắn Hình Ảnh' => ảnh của mọi mục được tự ghép theo mẫu đã chọn ở Bước 1."""
    import media_ops
    import services.auto_media as am
    from pipeline import get_project_dir, save_project_state
    from utils import read_json

    def fake_dl(item_name, project_title, out_path, candidate_index=0, custom_query=""):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (900, 600), (40 + candidate_index * 30, 90, 120)).save(out_path)
        return {"ok": True, "path": str(out_path)}

    monkeypatch.setattr(media_ops, "download_web_image_for_item", fake_dl)
    monkeypatch.setattr(am, "web_candidate", lambda name, title, out, cand: (fake_dl(name, title, out, cand), out)[1])
    pdir = get_project_dir("6-kenh-bac-si-demo")
    proj = read_json(pdir / "project.json")
    proj["settings"].update({"collageLayout": "3-1lon2nho", "sourceLinks": []})
    save_project_state(pdir, proj)
    res = media_ops.parse_and_fetch_anh_nhac_list(pdir, (pdir / "text" / "kich_ban.md").read_text(encoding="utf-8"))
    assert res["auto_media"]["layout"] == "3-1lon2nho" and len(res["auto_media"]["items"]) == 6
    bang = read_json(pdir / "text" / "bang.json")
    assert all(it.get("collage_layout") == "3-1lon2nho" and len(it["gallery"]) == 3 for it in bang["items"])


def test_not_enough_images_switches_to_smaller_layout(api, fresh_demo, monkeypatch):
    import services.auto_media as am

    monkeypatch.setattr(am, "web_candidate", lambda *a: None)  # không có mạng => chỉ có ảnh hiện tại
    pid = "7-benh-vien-di-sinh-demo"
    api.post(f"/api/projects/{pid}/media-settings", {"collageLayout": "4-luoi", "sourceLinks": []})
    st, res = api.post(f"/api/projects/{pid}/auto-media", {})
    rep = res["report"]["items"][0]
    assert rep["layout"] == "1" and "1/4" in rep["note"]
    it = res["project"]["bang"]["items"][0]
    assert it["collage_layout"] == "1" and "/framed/" not in it["custom_image_path"]


def test_reapplying_template_is_stable(api, fresh_demo, monkeypatch):
    import services.auto_media as am

    monkeypatch.setattr(am, "web_candidate", lambda *a: None)
    pid = "7-benh-vien-di-sinh-demo"
    api.post(f"/api/projects/{pid}/media-settings", {"collageLayout": "2-ngang", "sourceLinks": []})
    first = api.post(f"/api/projects/{pid}/auto-media", {})[1]["project"]["bang"]["items"][0]
    second = api.post(f"/api/projects/{pid}/auto-media", {})[1]["project"]["bang"]["items"][0]
    assert first["base_image_path"].endswith("item_01.png") and second["base_image_path"] == first["base_image_path"]
    assert second["collage_layout"] == first["collage_layout"] == "1"
