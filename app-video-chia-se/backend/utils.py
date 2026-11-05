# -*- coding: utf-8 -*-
"""Common utilities: hidden process execution, UTF-8 I/O, ffprobe/ffmpeg, Recycle Bin."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

CREATE_NO_WINDOW = 0x08000000

# Monkey-patch subprocess.Popen globally so NO child process (even inside libraries like faster-whisper)
# can ever pop up a console window on Windows.
_OriginalPopen = subprocess.Popen


class HiddenPopen(_OriginalPopen):
    def __init__(self, *args, **kwargs):
        if sys.platform == "win32":
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
        super().__init__(*args, **kwargs)


subprocess.Popen = HiddenPopen


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    app_root = Path(__file__).resolve().parents[1]
    if config_path is None:
        config_path = app_root / "config.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    paths = cfg.setdefault("paths", {})

    # Safe fallback when external drive (e.g. H:\) is unplugged so no step ever crashes with [WinError 3]
    exp_raw = Path(paths.get("export_dir", r"H:\source"))
    if exp_raw.anchor and not Path(exp_raw.anchor).exists():
        fb_exp = app_root / "video_xuat"
        fb_exp.mkdir(parents=True, exist_ok=True)
        paths["export_dir"] = str(fb_exp)

    prod_raw = Path(paths.get("product_images_dir", r"H:\source\san pham"))
    if prod_raw.anchor and not Path(prod_raw.anchor).exists():
        fb_prod = app_root / "kho_anh_san_pham"
        fb_prod.mkdir(parents=True, exist_ok=True)
        paths["product_images_dir"] = str(fb_prod)

    # Cloud Demo Mode (Linux/Claude Cloud): thay đường dẫn Windows bằng thư mục cục bộ trong app
    try:
        from services.cloud_env import apply_cloud_fallbacks

        cfg = apply_cloud_fallbacks(cfg, app_root)
    except ImportError:
        pass

    return cfg


def save_config(cfg: dict[str, Any], config_path: Path | None = None) -> None:
    if config_path is None:
        config_path = Path(__file__).resolve().parents[1] / "config.json"
    # Không bao giờ ghi đè đường dẫn Windows thật bằng đường dẫn fallback của Cloud
    try:
        from services.cloud_env import restore_original_paths

        cfg = restore_original_paths(cfg)
    except ImportError:
        pass
    write_json(config_path, cfg)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_log(log_path: Path | None, msg: str) -> None:
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def run_hidden(
    args: list[ Any ],
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
    log_path: Path | None = None,
    check: bool = True,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess:
    cmd = [str(x) for x in args]
    append_log(log_path, "CMD: " + " ".join(cmd))
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    if p.stdout and log_path:
        append_log(log_path, "STDOUT:\n" + p.stdout[-4000:])
    if p.stderr and log_path:
        append_log(log_path, "STDERR:\n" + p.stderr[-4000:])
    if check and p.returncode != 0:
        err_tail = (p.stderr or p.stdout or "")[-3500:]
        raise RuntimeError(f"Lệnh thất bại (code {p.returncode}): {' '.join(cmd[:4])}...\n{err_tail}")
    return p


def ffprobe_media(ffprobe_exe: str, media_path: Path, count_frames: bool = False) -> dict[str, Any]:
    cmd = [
        ffprobe_exe,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
    ]
    if count_frames:
        cmd.append("-count_frames")
    cmd.append(str(media_path))
    p = run_hidden(cmd, check=True)
    data = json.loads(p.stdout)
    streams = data.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})

    width = int(v_stream.get("width", 0)) if v_stream else 0
    height = int(v_stream.get("height", 0)) if v_stream else 0
    duration = float(fmt.get("duration") or (v_stream.get("duration") if v_stream else 0) or 0.0)

    def _parse_rate(r_str: str) -> float:
        if not r_str or r_str == "0/0":
            return 0.0
        if "/" in r_str:
            n, d = r_str.split("/", 1)
            return float(n) / float(d) if float(d) != 0 else 0.0
        return float(r_str)

    r_fps = _parse_rate(v_stream.get("r_frame_rate", "0/0")) if v_stream else 0.0
    avg_fps = _parse_rate(v_stream.get("avg_frame_rate", "0/0")) if v_stream else 0.0
    is_vfr = abs(r_fps - avg_fps) > 0.25 if (r_fps and avg_fps) else False
    nb_frames = 0
    if v_stream:
        nb_frames = int(
            v_stream.get("nb_read_frames")
            or v_stream.get("nb_frames")
            or round(duration * (avg_fps or 30))
        )

    return {
        "path": str(media_path),
        "name": media_path.name,
        "size_bytes": media_path.stat().st_size if media_path.exists() else 0,
        "width": width,
        "height": height,
        "duration": round(duration, 3),
        "r_fps": round(r_fps, 3),
        "avg_fps": round(avg_fps, 3),
        "is_vfr": is_vfr,
        "nb_frames": nb_frames,
        "video_codec": v_stream.get("codec_name") if v_stream else None,
        "audio_codec": a_stream.get("codec_name") if a_stream else None,
        "sample_rate": int(a_stream.get("sample_rate", 0)) if a_stream else 0,
        "channels": int(a_stream.get("channels", 0)) if a_stream else 0,
        "raw": data,
    }


def measure_loudness(ffmpeg_exe: str, media_path: Path) -> dict[str, Any]:
    cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-nostats",
        "-i",
        str(media_path),
        "-vn",
        "-af",
        "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
        "-f",
        "null",
        "NUL",
    ]
    p = run_hidden(cmd, check=True)
    blocks = re.findall(r"\{[^{}]*\}", p.stderr, flags=re.S)
    stats = next((json.loads(x) for x in reversed(blocks) if '"input_i"' in x), None)
    if not stats:
        raise RuntimeError(f"Không đo được loudnorm cho {media_path}")
    return {
        "input_i": float(stats["input_i"]),
        "input_tp": float(stats["input_tp"]),
        "input_lra": float(stats["input_lra"]),
        "input_thresh": float(stats["input_thresh"]),
        "target_offset": float(stats["target_offset"]),
        "raw": stats,
    }


def move_to_recycle_bin(file_path: Path) -> bool:
    """Move a file or folder to the Windows Recycle Bin (never delete permanently)."""
    target = file_path.resolve()
    if not target.exists():
        return False
    ps_code = (
        "Add-Type -AssemblyName Microsoft.VisualBasic; "
        f"[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('{str(target)}', "
        "'OnlyErrorDialogs', 'SendToRecycleBin')"
        if target.is_file()
        else "Add-Type -AssemblyName Microsoft.VisualBasic; "
        f"[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory('{str(target)}', "
        "'OnlyErrorDialogs', 'SendToRecycleBin')"
    )
    p = run_hidden(["powershell.exe", "-NoProfile", "-Command", ps_code], check=False)
    return p.returncode == 0


def open_in_explorer(path: Path) -> None:
    target = path.resolve()
    if target.is_file():
        subprocess.Popen(["explorer.exe", f"/select,{str(target)}"], creationflags=CREATE_NO_WINDOW)
    elif target.is_dir():
        subprocess.Popen(["explorer.exe", str(target)], creationflags=CREATE_NO_WINDOW)


def pick_file_dialog(
    title: str = "Chọn file",
    filter_str: str = "Tất cả file (*.*)|*.*",
    initial_dir: str | None = None,
) -> str | None:
    """Open native Windows file dialog ALWAYS in front of the active browser window via Win32 GetOpenFileNameW."""
    try:
        import ctypes
        from ctypes import wintypes

        OFN_EXPLORER = 0x00080000
        OFN_FILEMUSTEXIST = 0x00001000
        OFN_PATHMUSTEXIST = 0x00000800
        OFN_NOCHANGEDIR = 0x00000008

        class OPENFILENAMEW(ctypes.Structure):
            _fields_ = [
                ("lStructSize", wintypes.DWORD),
                ("hwndOwner", wintypes.HWND),
                ("hInstance", wintypes.HINSTANCE),
                ("lpstrFilter", wintypes.LPCWSTR),
                ("lpstrCustomFilter", wintypes.LPWSTR),
                ("nMaxCustFilter", wintypes.DWORD),
                ("nFilterIndex", wintypes.DWORD),
                ("lpstrFile", wintypes.LPWSTR),
                ("nMaxFile", wintypes.DWORD),
                ("lpstrFileTitle", wintypes.LPWSTR),
                ("nMaxFileTitle", wintypes.DWORD),
                ("lpstrInitialDir", wintypes.LPCWSTR),
                ("lpstrTitle", wintypes.LPCWSTR),
                ("Flags", wintypes.DWORD),
                ("nFileOffset", wintypes.WORD),
                ("nFileExtension", wintypes.WORD),
                ("lpstrDefExt", wintypes.LPCWSTR),
                ("lCustData", ctypes.c_void_p),
                ("lpfnHook", ctypes.c_void_p),
                ("lpTemplateName", wintypes.LPCWSTR),
                ("pvReserved", ctypes.c_void_p),
                ("dwReserved", wintypes.DWORD),
                ("FlagsEx", wintypes.DWORD),
            ]

        user32 = ctypes.windll.user32
        comdlg32 = ctypes.windll.comdlg32
        user32.AllowSetForegroundWindow(-1)
        fg_hwnd = user32.GetForegroundWindow()

        # Convert pipe-separated filter "Desc|*.ext|Desc2|*.*" to null-separated Win32 filter
        win_filter = filter_str.replace("|", "\0") + "\0\0"
        buf = ctypes.create_unicode_buffer(4096)
        if initial_dir and Path(initial_dir).is_dir():
            init_dir = str(Path(initial_dir))
        else:
            init_dir = r"H:\source" if Path(r"H:\source").is_dir() else str(Path.home())

        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.hwndOwner = fg_hwnd
        ofn.lpstrFilter = win_filter
        ofn.nFilterIndex = 1
        ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
        ofn.nMaxFile = 4096
        ofn.lpstrInitialDir = init_dir
        ofn.lpstrTitle = title
        ofn.Flags = OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR

        if comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            return buf.value
        return None
    except Exception:
        init_dir_fallback = (
            str(Path(initial_dir))
            if (initial_dir and Path(initial_dir).is_dir())
            else r"H:\source"
        )
        # Fallback to TopMost WinForms dialog shown and activated
        ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.OpenFileDialog
$f.Title = {json.dumps(title, ensure_ascii=False)}
$f.Filter = {json.dumps(filter_str, ensure_ascii=False)}
$f.InitialDirectory = {json.dumps(init_dir_fallback, ensure_ascii=False)}
$form = New-Object System.Windows.Forms.Form
$form.TopMost = $true
$form.StartPosition = 'CenterScreen'
$form.Width = 1; $form.Height = 1; $form.Opacity = 0.01
$form.Show()
$form.Activate()
$res = $f.ShowDialog($form)
$form.Close()
if ($res -eq [System.Windows.Forms.DialogResult]::OK) {{
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $f.FileName
}}
"""
        p = run_hidden(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", ps_script],
            check=False,
        )
        out = (p.stdout or "").strip()
        return out if out else None


def list_source_videos() -> list[dict[str, Any]]:
    """List video files available in H:\\source for 1-click quick selection in the UI."""
    cfg = load_config()
    src_dir = Path(cfg.get("paths", {}).get("export_dir", r"H:\source"))
    if not src_dir.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for p in sorted(src_dir.iterdir(), key=lambda x: (0 if x.suffix.lower() == ".mov" else 1, x.name.lower())):
        if p.is_file() and p.suffix.lower() in (".mov", ".mp4", ".mkv"):
            size_mb = round(p.stat().st_size / (1024 * 1024), 1)
            items.append(
                {
                    "name": p.name,
                    "path": str(p),
                    "size_mb": size_mb,
                }
            )
    return items


def slugify(text: str) -> str:
    s = text.lower().strip()
    replacements = {
        "[àáạảãâầấậẩẫăằắặẳẵ]": "a",
        "[èéẹẻẽêềếệểễ]": "e",
        "[ìíịỉĩ]": "i",
        "[òóọỏõôồốộổỗơờớợởỡ]": "o",
        "[ùúụủũưừứựửữ]": "u",
        "[ỳýỵỷỹ]": "y",
        "đ": "d",
    }
    for pat, rep in replacements.items():
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "convo-video"
