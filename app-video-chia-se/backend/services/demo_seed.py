# -*- coding: utf-8 -*-
"""Tạo sẵn 2 dự án mẫu cho Cloud Demo Mode (Linux / Claude Cloud không có ổ E:\\, H:\\):

- 6-kenh-bac-si-demo        : 6 kênh bác sĩ (tên nhân vật hư cấu) + ảnh chân dung minh hoạ
- 7-benh-vien-di-sinh-demo  : 7 bệnh viện đi sinh tại TP.HCM + địa chỉ (cấp quận) + ảnh minh hoạ

Ảnh được vẽ bằng Pillow nên không cần mạng. Dự án dùng preset 'anh_nhac' (Ảnh + Chữ + Nhạc).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

DEMO_PROJECTS: list[dict[str, Any]] = [
    {
        "id": "6-kenh-bac-si-demo",
        "title": "6 KÊNH BÁC SĨ SẢN NHI MẸ BẦU NÊN THEO DÕI",
        "visual_prompt": "Nền màu be ấm (#F6EFE6); Khung thẻ bác sĩ chuẩn y khoa; Căn giữa địa chỉ & thông tin",
        "items": [
            ("BS. Minh Anh (Demo)", ["Sản phụ khoa • Kênh chia sẻ kiến thức mang thai"]),
            ("BS. Thảo Vy (Demo)", ["Nhi khoa • Chăm sóc trẻ sơ sinh"]),
            ("BS. Quốc Bảo (Demo)", ["Sản khoa • Giải đáp khám thai định kỳ"]),
            ("BS. Hồng Nhung (Demo)", ["Dinh dưỡng mẹ bầu & sau sinh"]),
            ("BS. Gia Huy (Demo)", ["Nhi sơ sinh • Lịch tiêm chủng cho bé"]),
            ("BS. Ngọc Lan (Demo)", ["Hiếm muộn & Hỗ trợ sinh sản"]),
        ],
        "hues": [(201, 28, 50), (28, 100, 184), (16, 138, 106), (214, 51, 108), (183, 121, 31), (112, 72, 232)],
    },
    {
        "id": "7-benh-vien-di-sinh-demo",
        "title": "7 BỆNH VIỆN ĐI SINH UY TÍN TẠI TP.HCM",
        "visual_prompt": "Nền màu be ấm (#F6EFE6); Phóng to khung ảnh chính; Căn giữa địa chỉ & thông tin",
        "items": [
            ("BV Từ Dũ", ["Quận 1, TP.HCM"]),
            ("BV Hùng Vương", ["Quận 5, TP.HCM"]),
            ("BV ĐH Y Dược", ["Quận 5, TP.HCM"]),
            ("BV Phụ Sản Mê Kông", ["Quận Tân Bình, TP.HCM"]),
            ("Vinmec Central Park", ["Quận Bình Thạnh, TP.HCM"]),
            ("BV Tâm Anh", ["Quận Tân Bình, TP.HCM"]),
            ("BV Quốc Tế Mỹ (AIH)", ["TP. Thủ Đức, TP.HCM"]),
        ],
        "hues": [(201, 28, 50), (28, 100, 184), (16, 138, 106), (214, 51, 108), (183, 121, 31), (112, 72, 232), (8, 120, 160)],
    },
]


def build_script_text(title: str, items: list[tuple[str, list[str]]]) -> str:
    lines = [title, ""]
    for idx, (name, bullets) in enumerate(items, start=1):
        lines.append(f"{idx}. {name}")
        lines.extend(f"- {b}" for b in bullets)
    return "\n".join(lines) + "\n"


def _draw_building(path: Path, label: str, hue: tuple[int, int, int]) -> Path:
    from PIL import Image, ImageDraw

    w, h = 900, 720
    im = Image.new("RGB", (w, h), (226, 238, 248))
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(h * 0.82), w, h], fill=(196, 214, 170))
    d.rectangle([int(w * 0.18), int(h * 0.25), int(w * 0.82), int(h * 0.84)], fill=(248, 246, 240), outline=hue, width=6)
    for row in range(5):
        for col in range(6):
            x = int(w * 0.23) + col * int(w * 0.095)
            y = int(h * 0.31) + row * int(h * 0.09)
            d.rectangle([x, y, x + int(w * 0.06), y + int(h * 0.055)], fill=(150, 190, 220))
    d.rectangle([int(w * 0.44), int(h * 0.68), int(w * 0.56), int(h * 0.84)], fill=hue)
    d.rectangle([int(w * 0.30), int(h * 0.15), int(w * 0.70), int(h * 0.24)], fill=hue)
    d.rectangle([int(w * 0.485), int(h * 0.165), int(w * 0.515), int(h * 0.225)], fill=(255, 255, 255))
    d.rectangle([int(w * 0.465), int(h * 0.18), int(w * 0.535), int(h * 0.21)], fill=(255, 255, 255))
    d.text((int(w * 0.31), int(h * 0.88)), label[:40], fill=(40, 40, 40))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def _create_one(spec: dict[str, Any]) -> str:
    from pipeline import create_project, get_projects_root, save_project_state
    from services.subject_fallback import draw_demo_portrait
    from utils import read_json, write_json

    pid = spec["id"]
    script = build_script_text(spec["title"], spec["items"])
    create_project({
        "id": pid,
        "title": spec["title"],
        "preset": "anh_nhac",
        "script_text": script,
        "bang": {"tieu_de": spec["title"], "tong": 0, "items": []},
    })
    pdir = get_projects_root() / pid
    is_doctor = "bac-si" in pid
    items = []
    for idx, (name, bullets) in enumerate(spec["items"], start=1):
        hue = spec["hues"][(idx - 1) % len(spec["hues"])]
        img_p = pdir / "anh" / "demo_src" / f"item_{idx:02d}.png"
        if is_doctor:
            draw_demo_portrait(img_p, name, hue)
        else:
            _draw_building(img_p, name, hue)
        items.append({
            "i": idx, "nhom": 1, "ten": name, "display_name": name.upper(), "sl": 1, "dv": "Mục",
            "gia": 0, "no_price": True, "is_scene_photo": True, "ghi_chu": " | ".join(bullets),
            "bullets": bullets, "custom_image_path": str(img_p),
        })
    write_json(pdir / "text" / "bang.json", {"tieu_de": spec["title"], "subtitle": "", "tong": 0, "items": items})
    proj = read_json(pdir / "project.json", {})
    proj["visual_prompt"] = spec["visual_prompt"]
    proj["is_demo"] = True
    proj.setdefault("settings", {}).update({"bgTheme": "beige", "summarySubtitle": "DỮ LIỆU MẪU — CLOUD DEMO"})
    save_project_state(pdir, proj)
    try:
        from services.visual_prompt import save_and_apply_visual_prompt

        save_and_apply_visual_prompt(pdir, spec["visual_prompt"], apply=True)
    except Exception:
        pass
    # Dựng sẵn Timeline (Bước 5) + Storyboard ảnh (Bước 6) để Auto-QA & Live Preview có đủ dữ liệu
    try:
        from pipeline import execute_step

        execute_step(pid, 5, force_recompute=True, auto_approve=True)
        execute_step(pid, 6, force_recompute=True, auto_approve=True)
    except Exception:
        pass
    return pid


def ensure_demo_projects(force: bool = False, require_cloud: bool = True) -> dict[str, Any]:
    """Tạo 2 dự án mẫu nếu chưa có. Trên Windows (máy thật) mặc định KHÔNG tạo gì."""
    from pipeline import get_projects_root
    from services.cloud_env import is_cloud_mode

    if require_cloud and not is_cloud_mode():
        return {"ok": True, "created": [], "skipped": "not_cloud"}
    root = get_projects_root()
    created, existing = [], []
    for spec in DEMO_PROJECTS:
        pdir = root / spec["id"]
        if pdir.is_dir() and (pdir / "project.json").is_file() and not force:
            existing.append(spec["id"])
            continue
        if pdir.is_dir():
            shutil.rmtree(pdir)
        created.append(_create_one(spec))
    return {"ok": True, "created": created, "existing": existing}
