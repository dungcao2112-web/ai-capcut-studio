# -*- coding: utf-8 -*-
"""Silent launcher for App Video Chia Sẻ Hội Thoại 2 Người.

Checks if server is already listening on localhost:8765; if not, spawns backend/server.py
hidden (CREATE_NO_WINDOW = 0x08000000) and opens the browser.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
APP_ROOT = Path(__file__).resolve().parent
SERVER_PY = APP_ROOT / "backend" / "server.py"
LOG_FILE = APP_ROOT / "server_runtime.log"
PORT = 8765
URL = f"http://127.0.0.1:{PORT}"


def is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    if is_port_open(PORT):
        webbrowser.open(URL)
        return

    py_exe = r"C:\Users\Dung\AppData\Local\Programs\Python\Python311\python.exe"
    if not Path(py_exe).is_file():
        py_exe = sys.executable

    lf = LOG_FILE.open("a", encoding="utf-8")
    subprocess.Popen(
        [py_exe, str(SERVER_PY), "--no-browser"],
        cwd=str(APP_ROOT),
        stdout=lf,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )

    for _ in range(30):
        if is_port_open(PORT):
            break
        time.sleep(0.25)

    webbrowser.open(URL)


if __name__ == "__main__":
    main()
