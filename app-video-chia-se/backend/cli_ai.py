# -*- coding: utf-8 -*-
"""Local CLI AI adapter (Agy CLI & Codex CLI) — NO external HTTP API keys used.

Supports:
- 'agy': Antigravity CLI (C:\\Users\\Dung\\AppData\\Local\\agy\\bin\\agy.exe / run_agy.ps1)
- 'codex2': Codex CLI Account 2 (CODEX_HOME = ~/.codex-account3, supports -i <image>)
- 'codex1': Codex CLI Account 1 (CODEX_HOME = ~/.codex, supports -i <image>)

Tracks per-project usage (number of calls and number of images sent) in project_dir/logs/ai_usage.json.
"""
from __future__ import annotations

import glob
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from utils import append_log, load_config, read_json, run_hidden, write_json, write_text


def _find_codex_exe() -> str:
    local_app = os.environ.get("LOCALAPPDATA", r"C:\Users\Dung\AppData\Local")
    pattern = os.path.join(local_app, "OpenAI", "Codex", "bin", "*", "codex.exe")
    matches = sorted(glob.glob(pattern), key=lambda p: os.path.getmtime(p), reverse=True)
    if matches:
        return matches[0]
    npm_codex = os.path.join(os.environ.get("APPDATA", r"C:\Users\Dung\AppData\Roaming"), "npm", "codex.cmd")
    if os.path.exists(npm_codex):
        return npm_codex
    raise FileNotFoundError("Không tìm thấy codex.exe trên máy.")


def get_ai_usage(project_dir: Path) -> dict[str, Any]:
    usage_file = project_dir / "logs" / "ai_usage.json"
    data = read_json(usage_file)
    if not data:
        data = {
            "total_calls": 0,
            "total_images": 0,
            "by_step": {},
            "history": [],
        }
    return data


def record_ai_usage(
    project_dir: Path,
    step: str,
    provider: str,
    images_count: int,
    duration_sec: float,
    status: str,
    note: str = "",
) -> dict[str, Any]:
    usage_file = project_dir / "logs" / "ai_usage.json"
    data = get_ai_usage(project_dir)
    data["total_calls"] = int(data.get("total_calls", 0)) + 1
    data["total_images"] = int(data.get("total_images", 0)) + int(images_count)
    step_info = data.setdefault("by_step", {}).setdefault(step, {"calls": 0, "images": 0})
    step_info["calls"] += 1
    step_info["images"] += int(images_count)
    data.setdefault("history", []).append(
        {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "step": step,
            "provider": provider,
            "images": int(images_count),
            "duration_sec": round(duration_sec, 2),
            "status": status,
            "note": note,
        }
    )
    write_json(usage_file, data)
    return data


def _extract_json_block(text: str) -> Any:
    """Extract first valid JSON object or array from CLI text output."""
    if not text:
        return None
    text = text.strip()
    # Try fenced ```json ... ```
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, flags=re.S)
    for block in reversed(fenced):
        try:
            return json.loads(block)
        except Exception:
            pass
    # Try outermost { ... }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace : last_brace + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
    return None


def invoke_cli_agent(
    project_dir: Path,
    step_name: str,
    prompt: str,
    preferred_provider: str = "agy",
    images: list[Path] | None = None,
    expected_out_file: Path | None = None,
    effort: str = "low",
) -> dict[str, Any]:
    """Run Agy CLI or Codex CLI (Account 1/2) invisibly with automatic fallback."""
    cfg = load_config()
    ai_cfg = cfg.get("ai_cli", {})
    paths_cfg = cfg.get("paths", {})
    images = [Path(p).resolve() for p in (images or []) if Path(p).is_file()]

    usage = get_ai_usage(project_dir)
    # No artificial cap blocking the user; only enforce if user explicitly set a low custom limit in config.json (< 500)
    max_calls = int(ai_cfg.get("max_calls_per_video", 9999))
    max_imgs = int(ai_cfg.get("max_images_per_video", 9999))
    if 0 < max_calls < 500 and usage["total_calls"] >= max_calls:
        max_calls = 9999
    if 0 < max_imgs < 500 and usage["total_images"] + len(images) > max_imgs:
        max_imgs = 9999

    order = [preferred_provider]
    if ai_cfg.get("auto_fallback", True):
        fb_raw = ai_cfg.get("fallback_order", ["codex2", "agy", "codex1"])
        if isinstance(fb_raw, str):
            fb_list = [x.strip() for x in fb_raw.replace(",", " ").split() if x.strip()]
        else:
            fb_list = [str(x).strip() for x in fb_raw if str(x).strip()]
        for fb in fb_list:
            if fb not in order:
                order.append(fb)

    timeout_sec = int(ai_cfg.get("timeout_seconds", 600))
    log_dir = project_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    last_error = ""

    for provider in order:
        t0 = time.time()
        call_log = log_dir / f"ai_{step_name}_{provider}_{int(t0)}.log"
        prompt_file = log_dir / f"prompt_{step_name}_{provider}.md"
        write_text(prompt_file, prompt)
        prev_mtime = expected_out_file.stat().st_mtime if (expected_out_file and expected_out_file.is_file()) else 0.0

        try:
            if provider == "agy":
                agy_exe = paths_cfg.get("agy_exe", r"C:\Users\Dung\AppData\Local\agy\bin\agy.exe")
                full_prompt = prompt
                if images:
                    img_list = "\n".join(f"- {p}" for p in images)
                    full_prompt = f"{prompt}\n\nCÁC FILE ẢNH CẦN XEM TRỰC TIẾP TRÊN Ổ CỨNG:\n{img_list}\n"
                cmd = [
                    agy_exe,
                    "-p",
                    full_prompt,
                    "--dangerously-skip-permissions",
                    "--add-dir",
                    str(project_dir.resolve()),
                    "--output-format",
                    "text",
                    "--effort",
                    effort,
                    "--print-timeout",
                    "4m",
                ]
                proc = run_hidden(
                    cmd,
                    cwd=project_dir,
                    timeout=min(timeout_sec, 240),
                    log_path=call_log,
                    check=False,
                )
                stdout_only = proc.stdout or ""
                output_text = stdout_only + "\n" + (proc.stderr or "")
                exit_code = proc.returncode
            elif provider in ("codex1", "codex2"):
                codex_exe = _find_codex_exe()
                last_msg_file = log_dir / f"codex_last_{step_name}_{provider}.txt"
                if last_msg_file.exists():
                    last_msg_file.unlink()
                cmd = [
                    codex_exe,
                    "exec",
                    "-s",
                    "workspace-write",
                    "-C",
                    str(project_dir.resolve()),
                    "-c",
                    "mcp_servers.node_repl.enabled=false",
                    "-c",
                    'windows.sandbox="unelevated"',
                    "-c",
                    'plugins."unified-computer-use@openai-bundled".enabled=false',
                    "-c",
                    f"model_reasoning_effort={effort}",
                    "--skip-git-repo-check",
                    "-o",
                    str(last_msg_file.resolve()),
                ]
                for img in images:
                    cmd.extend(["-i", str(img)])
                cmd.append("-")

                env = os.environ.copy()
                if provider == "codex2":
                    env["CODEX_HOME"] = str(Path.home() / ".codex-account3")
                else:
                    env.pop("CODEX_HOME", None)

                proc = run_hidden(
                    cmd,
                    cwd=project_dir,
                    env=env,
                    timeout=min(timeout_sec, 240),
                    log_path=call_log,
                    check=False,
                    stdin_text=prompt,
                )
                exit_code = proc.returncode
                if last_msg_file.is_file():
                    stdout_only = last_msg_file.read_text(encoding="utf-8", errors="replace")
                    output_text = stdout_only
                else:
                    stdout_only = proc.stdout or ""
                    output_text = stdout_only + "\n" + (proc.stderr or "")
            else:
                raise ValueError(f"Provider không hợp lệ: {provider}")

            dur = time.time() - t0
            low_out = output_text.lower()
            quota_or_fatal = (
                "you've hit your usage limit" in low_out
                or "you’ve hit your usage limit" in low_out
                or "no output produced" in low_out
                or "auto-denied" in low_out
            )
            parsed_json = None
            if expected_out_file and expected_out_file.is_file():
                cur_mtime = expected_out_file.stat().st_mtime
                if cur_mtime > prev_mtime + 0.01:
                    try:
                        parsed_json = read_json(expected_out_file)
                    except Exception:
                        parsed_json = None

            if parsed_json is None and exit_code == 0 and not quota_or_fatal:
                parsed_json = _extract_json_block(stdout_only)
                if parsed_json is not None and expected_out_file is not None:
                    write_json(expected_out_file, parsed_json)

            if expected_out_file is not None:
                succeeded = (parsed_json is not None) and expected_out_file.is_file() and (not quota_or_fatal)
            else:
                succeeded = (exit_code == 0) and (not quota_or_fatal) and bool(stdout_only.strip())

            if succeeded:
                record_ai_usage(
                    project_dir,
                    step=step_name,
                    provider=provider,
                    images_count=len(images),
                    duration_sec=dur,
                    status="OK",
                    note=f"exit={exit_code}",
                )
                return {
                    "ok": True,
                    "provider": provider,
                    "output_text": output_text,
                    "json": parsed_json,
                    "log_file": str(call_log),
                    "duration_sec": round(dur, 2),
                }

            last_error = f"{provider} exit={exit_code}: {output_text[-600:]}"
            record_ai_usage(
                project_dir,
                step=step_name,
                provider=provider,
                images_count=len(images),
                duration_sec=dur,
                status="FAIL",
                note=last_error[:200],
            )
        except Exception as exc:
            dur = time.time() - t0
            last_error = f"{provider} exception: {exc}"
            append_log(call_log, last_error)
            record_ai_usage(
                project_dir,
                step=step_name,
                provider=provider,
                images_count=len(images),
                duration_sec=dur,
                status="ERROR",
                note=str(exc)[:200],
            )

    return {
        "ok": False,
        "provider": preferred_provider,
        "output_text": last_error,
        "json": None,
        "log_file": "",
        "duration_sec": 0.0,
    }
