# -*- coding: utf-8 -*-
"""
Native Desktop Application Launcher for 'App Video Chia Sẻ Hội Thoại 2 Người'.
Starts the local backend server in a background daemon thread (if not already running)
and opens the Studio UI in a native Windows WebView2 Desktop Window (pywebview).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from server import AppRequestHandler
from utils import load_config


def _is_server_alive(url: str, timeout: float = 0.8) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/config", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _ensure_backend_server(host: str, port: int) -> ThreadingHTTPServer | None:
    url = f"http://{host}:{port}"
    if _is_server_alive(url):
        return None

    server = ThreadingHTTPServer((host, port), AppRequestHandler)
    t = threading.Thread(target=server.serve_forever, name="BackendHTTPServer", daemon=True)
    t.start()

    for _ in range(30):
        if _is_server_alive(url, timeout=0.3):
            break
        time.sleep(0.1)
    return server


def _enable_dark_titlebar_windows() -> None:
    """Apply Windows 11 Dark Mode titlebar and custom App Icon (WM_SETICON) to the native window."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        time.sleep(0.4)
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            val = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
            ico_path = str(ROOT_DIR / "frontend" / "app_icon.ico")
            if os.path.isfile(ico_path):
                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x00000010
                WM_SETICON = 0x0080
                hicon_big = user32.LoadImageW(None, ico_path, IMAGE_ICON, 256, 256, LR_LOADFROMFILE)
                hicon_small = user32.LoadImageW(None, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
                if hicon_big:
                    user32.SendMessageW(hwnd, WM_SETICON, 1, hicon_big)
                if hicon_small:
                    user32.SendMessageW(hwnd, WM_SETICON, 0, hicon_small)
    except Exception:
        pass


def _parse_cli_args(argv: list[str]) -> dict:
    """Hỗ trợ: --server (chỉ chạy HTTP server, không mở cửa sổ), --port N, --host H, --no-demo."""
    opts = {"server": "--server" in argv, "port": None, "host": "127.0.0.1", "seed_demo": "--no-demo" not in argv}
    for flag, key in (("--port", "port"), ("--host", "host")):
        if flag in argv:
            idx = argv.index(flag)
            if idx + 1 < len(argv):
                opts[key] = argv[idx + 1]
    if opts["port"] is not None:
        opts["port"] = int(opts["port"])
    return opts


def run_headless_server(host: str, port: int, seed_demo: bool = True) -> None:
    """Chế độ Server thuần (Linux/Claude Cloud): python3 desktop_app.py --server --port 8765"""
    if seed_demo:
        try:
            from services.demo_seed import ensure_demo_projects

            seeded = ensure_demo_projects()
            if seeded.get("created"):
                print(f"Đã tạo dự án mẫu: {', '.join(seeded['created'])}", flush=True)
        except Exception as exc:  # Không bao giờ để lỗi seed chặn server
            print(f"[Cảnh báo] Không tạo được dự án mẫu: {exc}", flush=True)
    server = ThreadingHTTPServer((host, port), AppRequestHandler)
    print(f"Server running at http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    cli = _parse_cli_args(sys.argv[1:])
    if cli["server"]:
        cfg_srv = load_config()
        run_headless_server(cli["host"], cli["port"] or int(cfg_srv.get("port", 8765)), cli["seed_demo"])
        return
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Dung.AppVideoChiaSe2Nguoi.1.0")
        except Exception:
            pass
    cfg = load_config()
    port = cli["port"] or int(cfg.get("port", 8765))
    host = "127.0.0.1"
    url = f"http://{host}:{port}"

    server = _ensure_backend_server(host, port)

    title = "App Video Chia Sẻ Hội Thoại 2 Người — Studio Desktop (100% Local & CapCut)"
    try:
        import webview

        window = webview.create_window(
            title=title,
            url=url,
            width=1540,
            height=940,
            min_size=(1100, 700),
            resizable=True,
            text_select=True,
            background_color="#0b1020",
        )
        webview.start(_enable_dark_titlebar_windows)
    except Exception:
        # Fallback to Edge/Chrome native --app window if WebView2 runtime encounters any issue
        for browser_exe in (
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ):
            if os.path.isfile(browser_exe):
                subprocess.run([browser_exe, f"--app={url}", "--window-size=1540,940"])
                break
    finally:
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
