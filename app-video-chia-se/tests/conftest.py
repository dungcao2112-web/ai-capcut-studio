# -*- coding: utf-8 -*-
"""Cấu hình pytest: chạy server thật (ThreadingHTTPServer) trên cổng ngẫu nhiên với thư mục dự án tạm,
bật Cloud Demo Mode và tạo sẵn 2 dự án mẫu. Không đụng tới thư mục projects/ thật của app."""
from __future__ import annotations

import functools
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND = APP_ROOT / "backend"


@pytest.fixture(scope="session", autouse=True)
def _isolated_env(tmp_path_factory):
    root = tmp_path_factory.mktemp("projects")
    os.environ["VDCS_PROJECTS_ROOT"] = str(root)
    os.environ["VDCS_PRODUCT_IMAGES_DIR"] = str(tmp_path_factory.mktemp("kho_anh"))
    os.environ["VDCS_EXPORT_DIR"] = str(tmp_path_factory.mktemp("video_xuat"))
    os.environ["VDCS_CLOUD_MODE"] = "1"
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    yield root


@pytest.fixture(scope="session")
def demo(_isolated_env):
    from services.demo_seed import ensure_demo_projects

    res = ensure_demo_projects(force=True)
    assert sorted(res["created"]) == ["6-kenh-bac-si-demo", "7-benh-vien-di-sinh-demo"]
    return res


class Api:
    def __init__(self, base: str):
        self.base = base

    def request(self, method: str, path: str, body=None, raw: bytes | None = None, headers=None):
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        hdrs = {"Content-Type": "application/json; charset=utf-8"} if raw is None else {"Content-Type": "application/octet-stream"}
        hdrs.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = resp.read()
                status = resp.status
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as err:
            payload, status, ctype = err.read(), err.code, err.headers.get("Content-Type", "")
        if "application/json" in ctype:
            return status, json.loads(payload.decode("utf-8"))
        return status, payload

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body=body if body is not None else {}, **kw)


@pytest.fixture(scope="session")
def api(demo):
    from server import AppRequestHandler

    srv = ThreadingHTTPServer(("127.0.0.1", 0), AppRequestHandler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield Api(f"http://127.0.0.1:{srv.server_address[1]}")
    srv.shutdown()
    srv.server_close()


@pytest.fixture()
def fresh_demo(demo):
    """Tạo lại 2 dự án mẫu trước test có sửa dữ liệu."""
    from services.demo_seed import ensure_demo_projects

    ensure_demo_projects(force=True)
    return True


@pytest.fixture(scope="session")
def site(tmp_path_factory):
    """Web server cục bộ giả lập các link nguồn (trang danh sách, trang 1 mục, ảnh) — không cần Internet."""
    root = tmp_path_factory.mktemp("site")
    colors = {"tu-du": (200, 40, 60), "hung-vuong": (30, 90, 200), "dh-y-duoc": (20, 140, 90), "logo": (0, 0, 0)}
    for name, c in colors.items():
        size = (64, 64) if name == "logo" else (900, 650)
        Image.new("RGB", size, c).save(root / f"{name}.jpg")
    (root / "list.html").write_text("""<html><head><title>Top bệnh viện đi sinh</title>
      <meta property="og:description" content="Danh sách bệnh viện"></head><body>
      <img src="logo.jpg" alt="logo">
      <h2>1. BV Từ Dũ</h2><p>BV Từ Dũ là bệnh viện phụ sản lớn nhất phía Nam, nằm ở Quận 1.</p>
      <ul><li>Địa chỉ: 284 Cống Quỳnh, Quận 1, TP.HCM</li><li>Giá sinh thường từ 3.500.000đ</li><li>Hotline: 028 5404 2829</li></ul>
      <img src="tu-du.jpg" alt="Sảnh BV Từ Dũ">
      <h2>2. Hùng Vương</h2><p>Phòng sinh gia đình rộng rãi, mẹ được người thân ở cạnh suốt ca sinh.</p>
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
