# -*- coding: utf-8 -*-
"""Cloud Demo Mode: tự động thay các đường dẫn Windows (C:\\, E:\\, H:\\...) bằng thư mục cục bộ
khi chạy trên Linux/Claude Cloud, để server khởi động và mọi API kiểm thử được ngay.

Trên máy Windows của Chủ tịch Dũng, module này KHÔNG thay đổi gì (giữ nguyên hành vi cũ).
Biến môi trường hỗ trợ (dùng cho kiểm thử):
- VDCS_PROJECTS_ROOT : ép thư mục chứa dự án (mọi nền tảng)
- VDCS_CLOUD_MODE=1  : ép bật Cloud Demo Mode (kể cả trên Windows)
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

_WIN_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")

# key trong cfg["paths"] -> thư mục con fallback bên trong app_root
_DIR_FALLBACKS = {
    "app_root": ".",
    "projects_root": "projects",
    "export_dir": "video_xuat",
    "product_images_dir": "kho_anh_san_pham",
    "product_sample_dir": "kho_anh_san_pham/_mau",
    "sample_pack_dir": "kho_anh_san_pham/_goi_mau",
    "sfx_dir": "kho_anh_san_pham/_sfx",
    "remotion_dir": "remotion_starter_cloud",
    "video_use_helpers_dir": "remotion_starter_cloud/_helpers",
    "whisper_model_path": "models/whisper",
}
# key -> tên lệnh trong PATH
_EXE_FALLBACKS = {
    "ffmpeg_exe": "ffmpeg",
    "ffprobe_exe": "ffprobe",
    "npx_cmd": "npx",
    "agy_exe": "agy",
}
_DIRS_TO_CREATE = ("projects_root", "export_dir", "product_images_dir", "remotion_dir")


def is_windows_path(value: Any) -> bool:
    return bool(_WIN_PATH_RE.match(str(value or "")))


def is_cloud_mode() -> bool:
    """True khi đang chạy trên Linux/macOS (Cloud) hoặc bị ép bằng VDCS_CLOUD_MODE=1."""
    if os.environ.get("VDCS_CLOUD_MODE") == "1":
        return True
    if os.environ.get("VDCS_CLOUD_MODE") == "0":
        return False
    return sys.platform != "win32"


def apply_cloud_fallbacks(cfg: dict[str, Any], app_root: Path) -> dict[str, Any]:
    """Sửa cfg tại chỗ. Ghi lại giá trị gốc vào cfg['_cloud_original_paths'] để
    save_config() có thể khôi phục, tránh ghi đè đường dẫn Windows thật trong config.json."""
    paths = cfg.setdefault("paths", {})
    originals: dict[str, Any] = {}

    env_root = os.environ.get("VDCS_PROJECTS_ROOT", "").strip()
    if env_root:
        originals.setdefault("projects_root", paths.get("projects_root"))
        paths["projects_root"] = env_root
        Path(env_root).mkdir(parents=True, exist_ok=True)

    if not is_cloud_mode():
        if originals:
            cfg["_cloud_original_paths"] = originals
        return cfg

    for key, sub in _DIR_FALLBACKS.items():
        val = paths.get(key)
        if val is not None and is_windows_path(val) and not (key == "projects_root" and env_root):
            originals[key] = val
            paths[key] = str((app_root / sub).resolve())
    for key, cmd in _EXE_FALLBACKS.items():
        val = paths.get(key)
        if val is not None and is_windows_path(val):
            originals[key] = val
            paths[key] = shutil.which(cmd) or cmd
    for key in ("python_exe",):
        if is_windows_path(paths.get(key)):
            originals[key] = paths[key]
            paths[key] = sys.executable
    for key in ("run_agy_ps1", "run_codex_ps1"):
        if is_windows_path(paths.get(key)):
            originals[key] = paths[key]
            paths[key] = ""

    for key in _DIRS_TO_CREATE:
        try:
            Path(paths[key]).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    # Remotion cần thư mục src/ + public/ để ghi props/media (không cần cài Node modules để kiểm thử)
    try:
        rdir = Path(paths["remotion_dir"])
        (rdir / "src").mkdir(parents=True, exist_ok=True)
        (rdir / "public").mkdir(parents=True, exist_ok=True)
        root_tsx = rdir / "src" / "Root.tsx"
        if not root_tsx.is_file():
            root_tsx.write_text("export const RemotionRoot = () => (\n  <>\n  </>\n);\n", encoding="utf-8")
    except Exception:
        pass

    cfg["cloud_mode"] = True
    cfg["_cloud_original_paths"] = originals
    return cfg


def restore_original_paths(cfg: dict[str, Any]) -> dict[str, Any]:
    """Trả về bản sao cfg với các đường dẫn gốc (Windows) đã được khôi phục để ghi ra config.json."""
    import copy

    out = copy.deepcopy(cfg)
    originals = out.pop("_cloud_original_paths", None) or {}
    out.pop("cloud_mode", None)
    paths = out.setdefault("paths", {})
    for key, orig in originals.items():
        if orig is None:
            continue
        # Chỉ khôi phục nếu người dùng không chủ động đổi sang một đường dẫn khác
        cur = paths.get(key)
        if cur is None or not is_windows_path(cur):
            paths[key] = orig
    return out


def environment_report() -> dict[str, Any]:
    """Thông tin môi trường cho giao diện (badge Cloud Demo / Windows Local)."""
    def _has(mod: str) -> bool:
        try:
            __import__(mod)
            return True
        except Exception:
            return False

    return {
        "cloud_mode": is_cloud_mode(),
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "opencv": _has("cv2"),
        "onnxruntime": _has("onnxruntime"),
        "pillow": _has("PIL"),
        "numpy": _has("numpy"),
    }
