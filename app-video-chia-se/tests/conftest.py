# -*- coding: utf-8 -*-
"""Cấu hình pytest: chạy server thật (ThreadingHTTPServer) trên cổng ngẫu nhiên với thư mục dự án tạm,
bật Cloud Demo Mode và tạo sẵn 2 dự án mẫu. Không đụng tới thư mục projects/ thật của app."""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND = APP_ROOT / "backend"


@pytest.fixture(scope="session", autouse=True)
def _isolated_env(tmp_path_factory):
    root = tmp_path_factory.mktemp("projects")
    os.environ["VDCS_PROJECTS_ROOT"] = str(root)
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
