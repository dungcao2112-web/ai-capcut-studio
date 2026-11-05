# -*- coding: utf-8 -*-
"""Core media processing operations for the 2-person conversation video app.

Implements:
- Step 2: Energy RMS segmentation (-48 dBFS, gap 0.25s) + Whisper ASR per segment + hallucination [ẢO] tagging
- Step 2b: Fine-grain sub-segment analysis (--from --to --gap 0.06)
- Step 3: Audio preview extraction for cut pieces + ASR verification on joined voice
- Step 4: Silence detection (-55 dBFS, >=1.5s from voice, >=2.0s duration, trim 1s ends) + 2fps contact sheets
- Step 5: Timeline & media builder + Principle #1 turn-by-turn verification
- Step 6: Product no-bg image matching, alpha bbox crop + 2% margin, 3-bg contact sheet
- Step 9: Mouth-motion vs Audio RMS correlation check + 1fps/2fps verification contact sheets
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from utils import CREATE_NO_WINDOW, append_log, ffprobe_media, load_config, read_json, run_hidden, write_json, write_text

FPS = 30
PAD_IN = 0.08
PAD_OUT = 0.12
DISSOLVE_FRAMES = 4
SFX_NAMES = ("04_whoosh.wav", "02_soft_pop.wav", "05_sparkle.wav", "07_tick.wav")

HALLUCINATION_PATTERNS = [
    r"hãy\s+subscribe",
    r"đăng\s+ký\s+kênh",
    r"cảm\s+ơn\s+các\s+bạn\s+đã\s+xem",
    r"cảm\s+ơn\s+đã\s+xem",
    r"hẹn\s+gặp\s+lại\s+các\s+bạn\s+trong\s+những\s+video\s+tiếp\s+theo",
    r"like\s+và\s+subscribe",
    r"ghiền\s+mì\s+gõ",
    r"la\s+la\s+school",
    r"subtitles\s+by",
    r"amara\.org",
]


def is_whisper_hallucination(text: str) -> bool:
    low = text.lower().strip()
    if not low:
        return True
    for pat in HALLUCINATION_PATTERNS:
        if re.search(pat, low):
            return True
    return False


def _init_local_whisper(cfg: dict[str, Any]):
    paths = cfg.get("paths", {})
    helpers_dir = paths.get("video_use_helpers_dir", r"C:\Users\Dung\Developer\video-use\helpers")
    whisper_path = paths.get(
        "whisper_model_path",
        r"E:\VoiceStudioData\models\hub\models--Systran--faster-whisper-large-v3\snapshots\edaa852ec7e145841d8ffdb056a99866b5f0a478",
    )
    if helpers_dir not in sys.path:
        sys.path.insert(0, helpers_dir)
    if os.path.isdir(whisper_path):
        os.environ["VIDEO_USE_WHISPER_MODEL"] = whisper_path
        os.environ["HF_HUB_OFFLINE"] = "1"
    import local_asr

    local_asr._add_cuda_dll_dirs()
    return local_asr._get_model()


def analyze_clip_energy_and_asr(
    clip_path: Path,
    who: str,
    project_dir: Path,
    thr_db: float = -48.0,
    gap_sec: float = 0.25,
    t0: float = 0.0,
    t1: float = 1e9,
    log_path: Path | None = None,
    write_project_files: bool = True,
) -> dict[str, Any]:
    """Run energy segmentation + faster-whisper per segment (Step 2 & fine-grain re-analyze)."""
    cfg = load_config()
    ffmpeg_exe = cfg["paths"]["ffmpeg_exe"]

    with tempfile.TemporaryDirectory(prefix=f"analyze_{who}_") as tmp:
        raw_path = Path(tmp) / "audio.raw"
        run_hidden(
            [
                ffmpeg_exe,
                "-v",
                "error",
                "-y",
                "-i",
                str(clip_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "s16le",
                str(raw_path),
            ],
            log_path=log_path,
        )
        x = np.fromfile(raw_path, dtype=np.int16).astype(float) / 32768.0
        f_win = 160  # 10ms at 16kHz
        k = len(x) // f_win
        r = 20.0 * np.log10(np.sqrt((x[: k * f_win].reshape(k, f_win) ** 2).mean(1)) + 1e-9)

        segs: list[tuple[float, float]] = []
        cur = None
        last = None
        start_idx = max(0, int(t0 * 100))
        end_idx = min(k, int(t1 * 100))
        for i in range(start_idx, end_idx):
            if r[i] > thr_db:
                cur = i if cur is None else cur
                last = i
            elif cur is not None and (i - last) > gap_sec * 100:
                segs.append((cur / 100.0, (last + 1) / 100.0))
                cur = None
        if cur is not None and last is not None:
            segs.append((cur / 100.0, (last + 1) / 100.0))

        model = _init_local_whisper(cfg)
        transcript_lines: list[str] = []
        segments_detail: list[dict[str, Any]] = []

        for s, e in segs:
            dur = round(e - s, 2)
            vals = r[max(0, round(s * 100)) : min(k, max(round(s * 100) + 1, round(e * 100)))]
            peak_rms = float(np.max(vals)) if len(vals) else -99.0
            if e - s < 0.3:
                line = f"{s:.2f}-{e:.2f} | (ngắn, bỏ qua)"
                transcript_lines.append(line)
                segments_detail.append(
                    {
                        "start": round(s, 2),
                        "end": round(e, 2),
                        "duration": dur,
                        "peak_rms": round(peak_rms, 2),
                        "short": True,
                        "hallucination": False,
                        "text": "(ngắn, bỏ qua)",
                    }
                )
                continue

            wav_path = Path(tmp) / "seg.wav"
            run_hidden(
                [
                    ffmpeg_exe,
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    f"{max(0.0, s - 0.2):.2f}",
                    "-to",
                    f"{e + 0.2:.2f}",
                    "-i",
                    str(clip_path),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(wav_path),
                ],
                log_path=log_path,
            )
            out_segs, _ = model.transcribe(
                str(wav_path),
                language="vi",
                vad_filter=False,
                condition_on_previous_text=False,
                beam_size=5,
                temperature=0,
            )
            raw_text = " ".join(t.text.strip() for t in out_segs).strip()
            is_ao = is_whisper_hallucination(raw_text)
            if is_ao and raw_text:
                display_text = f"[ẢO] {raw_text}"
            elif not raw_text:
                display_text = "(im lặng)"
            else:
                display_text = raw_text

            line = f"{s:.2f}-{e:.2f} | {display_text}"
            transcript_lines.append(line)
            segments_detail.append(
                {
                    "start": round(s, 2),
                    "end": round(e, 2),
                    "duration": dur,
                    "peak_rms": round(peak_rms, 2),
                    "short": False,
                    "hallucination": is_ao,
                    "text": display_text,
                }
            )

        audio_total_dur = len(x) / 16000.0
        quiet_windows: list[tuple[float, float]] = []
        cursor = 0.0
        for s, e in segs:
            if s - cursor >= 3.0:
                quiet_windows.append((round(cursor, 2), round(s, 2)))
            cursor = e
        if audio_total_dur - cursor >= 3.0:
            quiet_windows.append((round(cursor, 2), round(audio_total_dur, 2)))

        energy_lines = [
            f"# {clip_path.name}; mono 16000 Hz; RMS window 10 ms; VOICE > {thr_db:.0f} dBFS; gap {gap_sec:.2f} s",
            "# VOICE = energy interval, includes noises and short intervals; not a speech/VAD verdict.",
        ]
        for seg_info in segments_detail:
            s_val, e_val = seg_info["start"], seg_info["end"]
            is_sh = "true" if seg_info["short"] else "false"
            energy_lines.append(
                f"{s_val:.2f}-{e_val:.2f} | VOICE | duration={e_val - s_val:.2f}s | "
                f"peak_window_RMS={seg_info['peak_rms']:.2f} dBFS | short={is_sh}"
            )
        energy_lines.append("# Quiet windows >= 3s (complement of merged VOICE intervals)")
        for qs, qe in quiet_windows:
            energy_lines.append(f"{qs:.2f}-{qe:.2f} | QUIET | duration={qe - qs:.2f}s")
        long_cnt = sum(1 for d in segments_detail if not d["short"])
        short_cnt = sum(1 for d in segments_detail if d["short"])
        energy_lines.append(
            f"# TOTAL: {len(segments_detail)} VOICE; {long_cnt} >=0.30s; {short_cnt} short; {len(quiet_windows)} QUIET >=3s"
        )

        phien_am_text = "\n".join(transcript_lines) + "\n"
        energy_text = "\n".join(energy_lines) + "\n"

        if write_project_files:
            write_text(project_dir / "text" / f"phien_am_{who}.txt", phien_am_text)
            write_text(project_dir / "text" / f"energy_{who}.txt", energy_text)
            write_json(
                project_dir / "reports" / f"energy_metrics_{who}.json",
                {
                    "who": who,
                    "clip": str(clip_path),
                    "duration_audio": round(audio_total_dur, 3),
                    "segments": segments_detail,
                    "quiet_3s": quiet_windows,
                },
            )

        return {
            "who": who,
            "duration_audio": round(audio_total_dur, 3),
            "segments": segments_detail,
            "quiet_3s": quiet_windows,
            "phien_am_text": phien_am_text,
            "energy_text": energy_text,
        }


def extract_piece_audio_previews(project_dir: Path, cut_data: dict[str, Any]) -> dict[str, Any]:
    """Generate individual WAV preview files for every piece anddropped item, plus joined voice_preview.wav."""
    cfg = load_config()
    ffmpeg_exe = cfg["paths"]["ffmpeg_exe"]
    speed = float(project_dir_config(project_dir).get("speed", 1.3))

    preview_dir = project_dir / "media" / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    for old in preview_dir.glob("*.wav"):
        old.unlink()

    sources = {
        "A": project_dir / "nguon" / "A_hoi.mp4",
        "B": project_dir / "nguon" / "B_dap.mp4",
    }
    concat_wavs: list[Path] = []
    piece_previews: list[dict[str, Any]] = []

    for ti, turn in enumerate(cut_data.get("turns", [])):
        who = turn.get("who", "A")
        src = sources.get(who)
        if not src or not src.is_file():
            continue
        pieces = turn.get("pieces", [])
        for pi, piece in enumerate(pieces):
            start = float(piece["start"])
            end = float(piece["end"])
            pad_in = float(piece["pad_in"]) if piece.get("custom_pad") and "pad_in" in piece else PAD_IN
            pad_out = float(piece["pad_out"]) if piece.get("custom_pad") and "pad_out" in piece else PAD_OUT
            cut_start = max(0.0, start - pad_in)
            cut_end = end + pad_out
            if pi > 0:
                cut_start = max(cut_start, float(pieces[pi - 1]["end"]) + 0.02)
            if pi + 1 < len(pieces):
                cut_end = min(cut_end, float(pieces[pi + 1]["start"]) - 0.02)
            dur = max(0.05, cut_end - cut_start)
            nf = max(1, round(dur / speed * FPS))
            play_dur = nf / FPS

            wav_name = f"turn_{ti:02d}_piece_{pi:02d}_{who}.wav"
            wav_path = preview_dir / wav_name
            run_hidden(
                [
                    ffmpeg_exe,
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    f"{cut_start:.3f}",
                    "-t",
                    f"{dur:.3f}",
                    "-i",
                    str(src),
                    "-vn",
                    "-af",
                    f"afade=t=in:d=0.02,atempo={speed},afade=t=out:st={max(0, play_dur - 0.04):.3f}:d=0.04,apad=whole_dur={play_dur:.4f}",
                    "-t",
                    f"{play_dur:.4f}",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    str(wav_path),
                ]
            )
            concat_wavs.append(wav_path)
            piece["preview_wav"] = f"media/previews/{wav_name}"
            piece_previews.append(
                {
                    "turn_index": ti,
                    "piece_index": pi,
                    "who": who,
                    "start": start,
                    "end": end,
                    "preview_wav": f"media/previews/{wav_name}",
                }
            )

    # Also extract previews for dropped segments (normalize string entries if needed)
    norm_dropped: list[dict[str, Any]] = []
    for di, drop in enumerate(cut_data.get("dropped", [])):
        if isinstance(drop, str):
            m_d = re.search(r"\b([AB])\b.*?(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*:?\s*(.*)", drop)
            if m_d:
                drop = {
                    "who": m_d.group(1),
                    "start": float(m_d.group(2)),
                    "end": float(m_d.group(3)),
                    "why": m_d.group(4).strip() or drop,
                }
            else:
                drop = {"who": "B", "start": 0.0, "end": 0.0, "why": drop}
        norm_dropped.append(drop)
        who = drop.get("who", "A")
        src = sources.get(who)
        if not src or not src.is_file():
            continue
        s = float(drop.get("start", 0))
        e = float(drop.get("end", 0))
        if e > s + 0.05:
            wav_name = f"dropped_{di:02d}_{who}.wav"
            wav_path = preview_dir / wav_name
            run_hidden(
                [
                    ffmpeg_exe,
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    f"{s:.3f}",
                    "-t",
                    f"{e - s:.3f}",
                    "-i",
                    str(src),
                    "-vn",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    str(wav_path),
                ],
                check=False,
            )
            if wav_path.is_file():
                drop["preview_wav"] = f"media/previews/{wav_name}"
    cut_data["dropped"] = norm_dropped

    joined_wav = project_dir / "media" / "voice_preview.wav"
    if concat_wavs:
        list_txt = preview_dir / "concat_list.txt"
        write_text(list_txt, "".join(f"file '{p.as_posix()}'\n" for p in concat_wavs))
        run_hidden(
            [
                ffmpeg_exe,
                "-v",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_txt),
                "-c",
                "copy",
                str(joined_wav),
            ]
        )

    return {
        "piece_previews": piece_previews,
        "joined_voice_wav": "media/voice_preview.wav" if joined_wav.is_file() else None,
    }


def transcribe_joined_voice(project_dir: Path, wav_path: Path) -> dict[str, Any]:
    """Run local Whisper ASR on joined voice.wav to verify fluency and check for stutters/repeats."""
    cfg = load_config()
    model = _init_local_whisper(cfg)
    segs, info = model.transcribe(
        str(wav_path),
        language="vi",
        vad_filter=False,
        condition_on_previous_text=False,
        beam_size=5,
        temperature=0,
    )
    rows = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs]
    full_text = " ".join(r["text"] for r in rows)
    result = {
        "language": info.language,
        "full_text": full_text,
        "segments": rows,
    }
    write_json(project_dir / "reports" / "voice_asr_check.json", result)
    return result


_VN_NUM_MAP = {
    "0": "khong",
    "1": "mot",
    "2": "hai",
    "3": "ba",
    "4": "bon",
    "5": "nam",
    "6": "sau",
    "7": "bay",
    "8": "tam",
    "9": "chin",
    "10": "muoi",
}


def _norm_vn_word(w: str) -> str:
    s = (w or "").lower().strip()
    s = re.sub(r"[\[\].,!?;:\"'()\-–—_]", "", s).strip()
    if s in _VN_NUM_MAP:
        return _VN_NUM_MAP[s]
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").replace("đ", "d")
    return s


def _vn_words_match(w1: str, w2: str) -> bool:
    if not w1 or not w2:
        return False
    if w1 == w2:
        return True
    if len(w1) >= 3 and len(w2) >= 3 and w1[-2:] == w2[-2:]:
        return True
    return False


def align_piece_text_to_audio(
    project_dir: Path,
    who: str,
    target_text: str,
    cur_start: float = 0.0,
    cur_end: float = 0.0,
) -> dict[str, Any]:
    """Align edited piece text to exact word-level start/end timestamps using faster-whisper word_timestamps + 10ms RMS valley snapping."""
    cfg = load_config()
    ffmpeg_exe = cfg["paths"]["ffmpeg_exe"]
    who_clean = "A" if str(who).upper() == "A" else "B"
    clip_path = project_dir / "nguon" / ("A_hoi.mp4" if who_clean == "A" else "B_dap.mp4")
    if not clip_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy clip nguồn cho {who_clean}: {clip_path}")

    raw_clean = re.sub(r"\[([^\]]*)\]", r"\1", target_text or "")
    raw_clean = re.sub(r"[.,!?;:\"'()\-–—]", " ", raw_clean)
    raw_words_display = [t for t in (target_text or "").split() if _norm_vn_word(t)]
    target_toks = [_norm_vn_word(t) for t in raw_clean.split() if _norm_vn_word(t)]
    if len(raw_words_display) != len(target_toks):
        raw_words_display = [t for t in raw_clean.split() if _norm_vn_word(t)]
    if not target_toks:
        raise ValueError("Nội dung chữ trống, không thể dò giây.")

    # 1. Parse phien_am_{who}.txt to find the best candidate window [span_start, span_end]
    pa_path = project_dir / "text" / f"phien_am_{who_clean}.txt"
    lines: list[dict[str, Any]] = []
    if pa_path.is_file():
        for raw_line in pa_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*\|\s*(.+)$", raw_line)
            if m:
                txt = m.group(3).strip()
                if "(ngắn, bỏ qua)" not in txt and "[ẢO]" not in txt:
                    lines.append({"start": float(m.group(1)), "end": float(m.group(2)), "text": txt})

    best_span = None
    best_span_score = -1e9
    for i in range(len(lines)):
        comb_txt = ""
        s_start = lines[i]["start"]
        s_end = lines[i]["end"]
        for j in range(i, min(len(lines), i + 6)):
            if j > i and lines[j]["start"] - lines[j - 1]["end"] > 2.8:
                break
            comb_txt = (comb_txt + " " + lines[j]["text"]).strip()
            s_end = lines[j]["end"]
            c_toks = [_norm_vn_word(t) for t in re.sub(r"[.,!?;:\"'()\-–—]", " ", comb_txt).split() if _norm_vn_word(t)]
            if not c_toks:
                continue
            t_hits = sum(1 for tw in target_toks if any(_vn_words_match(tw, cw) for cw in c_toks))
            c_hits = sum(1 for cw in c_toks if any(_vn_words_match(tw, cw) for tw in target_toks))
            recall = t_hits / max(len(target_toks), 1)
            prec = c_hits / max(len(c_toks), 1)
            f1 = (2 * recall * prec / (recall + prec)) if (recall + prec) > 0 else 0.0
            prox = 0.25 if (cur_start > 0 and abs(s_start - cur_start) < 2.2) else 0.0
            overlap_bonus = 0.20 if (cur_end > cur_start and s_start <= cur_end + 1.0 and s_end >= cur_start - 1.0) else 0.0
            sc = f1 + recall * 0.35 + prox + overlap_bonus
            if sc > best_span_score and (t_hits >= 1 and recall >= 0.35):
                best_span_score = sc
                best_span = {"start": s_start, "end": s_end, "text": comb_txt}

    if best_span:
        span_start = float(best_span["start"])
        span_end = float(best_span["end"])
    elif cur_end > cur_start:
        span_start = max(0.0, cur_start - 1.0)
        span_end = cur_end + 1.5
    else:
        raise ValueError("Không tìm thấy câu khớp trong bản phiên âm.")

    win_start = max(0.0, round(span_start - 0.20, 2))
    win_end = round(span_end + 0.20, 2)
    win_dur = max(0.5, round(win_end - win_start, 2))

    # 2. Extract 16kHz mono WAV and run Whisper with word_timestamps=True
    with tempfile.TemporaryDirectory(prefix="align_piece_") as tmp_dir:
        tmp_wav = Path(tmp_dir) / "slice.wav"
        run_hidden(
            [
                ffmpeg_exe,
                "-v",
                "error",
                "-y",
                "-ss",
                f"{win_start:.3f}",
                "-t",
                f"{win_dur:.3f}",
                "-i",
                str(clip_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "wav",
                str(tmp_wav),
            ]
        )
        # Also read raw s16le samples for 10ms RMS valley snapping
        proc = subprocess.run(
            [
                ffmpeg_exe,
                "-v",
                "error",
                "-ss",
                f"{win_start:.3f}",
                "-t",
                f"{win_dur:.3f}",
                "-i",
                str(clip_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "s16le",
                "-",
            ],
            capture_output=True,
            check=True,
            creationflags=CREATE_NO_WINDOW,
        )
        pcm = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0

        model = _init_local_whisper(cfg)
        segs, _ = model.transcribe(
            str(tmp_wav),
            language="vi",
            vad_filter=False,
            condition_on_previous_text=False,
            word_timestamps=True,
            beam_size=5,
            temperature=0,
        )
        spoken: list[dict[str, Any]] = []
        for s in segs:
            for w in getattr(s, "words", []) or []:
                norm_w = _norm_vn_word(w.word)
                if not norm_w:
                    continue
                spoken.append(
                    {
                        "w": w.word.strip(),
                        "norm": norm_w,
                        "start": round(win_start + float(w.start), 3),
                        "end": round(win_start + float(w.end), 3),
                    }
                )

    if not spoken:
        return {
            "start": round(span_start, 2),
            "end": round(span_end, 2),
            "custom_pad": False,
            "pad_in": PAD_IN,
            "pad_out": PAD_OUT,
            "matched_words": best_span["text"] if best_span else target_text,
        }

    # 3. True 1-to-1 Ordered Sequence Alignment (Dynamic Programming)
    # Each target token k (0..n_tg-1) aligns to at most ONE spoken word s (0..n_sp-1) in strictly increasing order.
    # Repeated stutters in spoken CANNOT match the same target token twice!
    n_sp = len(spoken)
    n_tg = len(target_toks)

    def _find_rms_valley(t_left: float, t_right: float, fallback_t: float) -> float:
        """Find the quietest 10ms point in [t_left, t_right] from 16kHz PCM."""
        if pcm.size < 320 or t_right <= t_left:
            return fallback_t
        idx_l = max(0, int((t_left - win_start) * 16000))
        idx_r = min(pcm.size - 160, int((t_right - win_start) * 16000))
        if idx_r <= idx_l:
            return fallback_t
        best_idx = idx_l
        min_rms = 1e9
        for idx in range(idx_l, idx_r + 1, 80):  # 5ms step, 15ms window
            chunk = pcm[idx : min(pcm.size, idx + 240)]
            if chunk.size == 0:
                continue
            rms = float(np.sqrt(np.mean(chunk * chunk)))
            if rms < min_rms:
                min_rms = rms
                best_idx = idx + chunk.size // 2
        return win_start + (best_idx / 16000.0)

    def _word_sim(tw: str, sw: str) -> float:
        if tw == sw:
            return 2.2
        if _vn_words_match(tw, sw):
            return 1.5
        return -0.8

    # DP state: dp[k][s] = best score aligning target_toks[0..k] ending with target_toks[k] matched to spoken[s]
    dp = np.full((n_tg, n_sp), -1e9, dtype=np.float64)
    parent_s = np.full((n_tg, n_sp), -1, dtype=np.int32)

    for s in range(n_sp):
        sim0 = _word_sim(target_toks[0], spoken[s]["norm"])
        # Slight preference for later take if a stutter repeat occurs at the very beginning (e.g. "bà mua, bà mua 3 thanh")
        pos_bias = 0.008 * s
        prox0 = 0.15 if (cur_start > 0 and abs(spoken[s]["start"] - cur_start) < 0.9) else 0.0
        dp[0, s] = sim0 + pos_bias + prox0

    for k in range(1, n_tg):
        tw = target_toks[k]
        for s in range(k, n_sp):
            sim = _word_sim(tw, spoken[s]["norm"])
            best_prev_score = -1e9
            best_p = -1
            for s_prev in range(k - 1, s):
                skipped_sp = s - s_prev - 1
                if skipped_sp == 0:
                    # Contiguous spoken words! Strong bonus so contiguous takes stay together
                    trans = 1.15
                elif skipped_sp == 1:
                    # 1 extra Whisper syllable
                    trans = -0.25
                else:
                    # A multi-word phrase in spoken was deleted by user in the middle!
                    # Constant gap-open penalty + tiny per-word penalty so one clean skip beats scattered matches
                    trans = -0.85 - 0.02 * skipped_sp
                cand_sc = dp[k - 1, s_prev] + trans
                if cand_sc >= best_prev_score:
                    best_prev_score = cand_sc
                    best_p = s_prev
            if best_p != -1:
                dp[k, s] = best_prev_score + sim + (0.005 * s)
                parent_s[k, s] = best_p

    # Backtrack from the best ending spoken index s for target_toks[n_tg - 1]
    if n_sp >= n_tg:
        best_last_s = int(np.argmax(dp[n_tg - 1]))
        mapped_s = [0] * n_tg
        cur_s = best_last_s
        for k in range(n_tg - 1, -1, -1):
            mapped_s[k] = cur_s
            cur_s = int(parent_s[k, cur_s])
    else:
        mapped_s = [min(k, n_sp - 1) for k in range(n_tg)]

    # Group aligned target words into contiguous spoken chunks (split when >= 2 spoken words were deleted in the middle)
    chunks: list[dict[str, Any]] = []
    chunk_tg_start = 0
    for k in range(1, n_tg):
        s_prev = mapped_s[k - 1]
        s_cur = mapped_s[k]
        skipped_words = s_cur - s_prev - 1
        time_gap = spoken[s_cur]["start"] - spoken[s_prev]["end"]
        if skipped_words >= 2 and time_gap >= 0.35:
            chunks.append(
                {
                    "tg_start": chunk_tg_start,
                    "tg_end": k - 1,
                    "s_start": mapped_s[chunk_tg_start],
                    "s_end": s_prev,
                }
            )
            chunk_tg_start = k
    chunks.append(
        {
            "tg_start": chunk_tg_start,
            "tg_end": n_tg - 1,
            "s_start": mapped_s[chunk_tg_start],
            "s_end": mapped_s[n_tg - 1],
        }
    )

    def _compute_chunk_bounds(s_idx_start: int, s_idx_end: int) -> tuple[float, float, bool, float, float]:
        t_start_trimmed = s_idx_start > 0
        t_end_trimmed = s_idx_end < (n_sp - 1)

        if t_start_trimmed:
            prev_end = spoken[s_idx_start - 1]["end"]
            cur_w_start = spoken[s_idx_start]["start"]
            mid_t = 0.5 * (prev_end + cur_w_start)
            c_start = _find_rms_valley(prev_end - 0.03, cur_w_start + 0.03, max(prev_end, mid_t))
            p_in = 0.01
        else:
            c_start = span_start if abs(spoken[0]["start"] - span_start) <= 0.40 else spoken[0]["start"]
            p_in = PAD_IN

        if t_end_trimmed:
            cur_w_end = spoken[s_idx_end]["end"]
            next_start = spoken[s_idx_end + 1]["start"]
            mid_t = 0.5 * (cur_w_end + next_start)
            c_end = _find_rms_valley(cur_w_end - 0.04, next_start + 0.02, min(cur_w_end, mid_t))
            p_out = 0.01
        else:
            c_end = span_end if abs(spoken[-1]["end"] - span_end) <= 0.40 else spoken[-1]["end"]
            p_out = PAD_OUT

        if c_end <= c_start + 0.12:
            c_end = c_start + 0.25
        return round(c_start, 2), round(c_end, 2), bool(t_start_trimmed or t_end_trimmed), round(p_in, 3), round(p_out, 3)

    sub_pieces: list[dict[str, Any]] = []
    for ch in chunks:
        c_start, c_end, c_custom, p_in, p_out = _compute_chunk_bounds(ch["s_start"], ch["s_end"])
        ch_text = " ".join(raw_words_display[ch["tg_start"] : ch["tg_end"] + 1]).strip()
        ch_matched = " ".join(x["w"] for x in spoken[ch["s_start"] : ch["s_end"] + 1])
        sub_pieces.append(
            {
                "start": c_start,
                "end": c_end,
                "text": ch_text,
                "custom_pad": c_custom,
                "pad_in": p_in,
                "pad_out": p_out,
                "matched_words": ch_matched,
            }
        )

    first_p = sub_pieces[0]
    return {
        "start": first_p["start"],
        "end": first_p["end"],
        "custom_pad": first_p["custom_pad"],
        "pad_in": first_p["pad_in"],
        "pad_out": first_p["pad_out"],
        "trimmed_start": chunks[0]["s_start"] > 0,
        "trimmed_end": chunks[-1]["s_end"] < (n_sp - 1),
        "matched_words": " | ".join(sp["matched_words"] for sp in sub_pieces),
        "sub_pieces": sub_pieces,
    }


def project_dir_config(project_dir: Path) -> dict[str, Any]:
    proj = read_json(project_dir / "project.json", {})
    cfg = load_config()
    merged = dict(cfg.get("defaults", {}))
    merged.update(proj.get("settings", {}))
    return merged


def generate_listener_candidates(
    clip_path: Path,
    energy_path: Path,
    out_dir: Path,
    who: str,
    source_label: str = "main",
) -> list[dict[str, Any]]:
    """Find quiet listener-shot candidates (<-55 dBFS, >=1.5s from voice, >=2.0s, trim 1s ends) and create 2fps sheets."""
    cfg = load_config()
    ffmpeg_exe = cfg["paths"]["ffmpeg_exe"]
    ffprobe_exe = cfg["paths"]["ffprobe_exe"]

    out_dir.mkdir(parents=True, exist_ok=True)
    probe = ffprobe_media(ffprobe_exe, clip_path)
    duration = float(probe["duration"])

    # Parse VOICE intervals from energy file if provided; otherwise detect directly
    voices: list[tuple[float, float]] = []
    if energy_path.is_file():
        for line in energy_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*\|\s*VOICE\b", line, re.I)
            if m:
                voices.append((float(m.group(1)), float(m.group(2))))

    def _merge(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for s, e in sorted(intervals):
            if out and s <= out[-1][1]:
                out[-1] = (out[-1][0], max(e, out[-1][1]))
            else:
                out.append((s, e))
        return out

    voices = _merge(voices)

    # Measure silence <-55 dBFS via ffmpeg silencedetect
    p = run_hidden(
        [
            ffmpeg_exe,
            "-hide_banner",
            "-i",
            str(clip_path),
            "-vn",
            "-af",
            "silencedetect=noise=-55dB:d=0.10",
            "-f",
            "null",
            "-",
        ]
    )
    starts: list[float] = []
    quiet: list[tuple[float, float]] = []
    for line in p.stderr.splitlines():
        sm = re.search(r"silence_start:\s*([0-9.]+)", line)
        if sm:
            starts.append(float(sm.group(1)))
        em = re.search(r"silence_end:\s*([0-9.]+)", line)
        if em:
            end = float(em.group(1))
            start = starts.pop(0) if starts else 0.0
            quiet.append((start, end))
    if starts:
        quiet.append((starts[-1], duration))
    quiet = _merge(quiet)

    raw_candidates: list[tuple[float, float]] = []
    for start, end in quiet:
        parts = [(max(1.0, start), min(duration - 1.0, end))]
        for vs, ve in voices:
            bs, be = vs - 1.5, ve + 1.5
            next_parts: list[tuple[float, float]] = []
            for a, b in parts:
                if be <= a or bs >= b:
                    next_parts.append((a, b))
                else:
                    if bs > a:
                        next_parts.append((a, min(bs, b)))
                    if be < b:
                        next_parts.append((max(be, a), b))
            parts = next_parts
        raw_candidates.extend((round(a, 2), round(b, 2)) for a, b in parts if b - a >= 2.0)

    font = ImageFont.load_default()
    candidate_list: list[dict[str, Any]] = []

    for index, (start, end) in enumerate(raw_candidates, 1):
        cand_id = f"{who}_{source_label}_{index:02d}"
        frames_dir = out_dir / f"{cand_id}_frames"
        frames_dir.mkdir(exist_ok=True)
        times: list[float] = []
        t = math.ceil(start * 2) / 2.0
        while t <= end + 1e-6:
            times.append(round(t, 2))
            t += 0.5
        if not times:
            times = [round((start + end) / 2.0, 2)]

        thumbs: list[tuple[Image.Image, float]] = []
        frame_arrays: list[np.ndarray] = []
        for fi, ts in enumerate(times):
            img_path = frames_dir / f"frame_{fi:03d}.jpg"
            run_hidden(
                [
                    ffmpeg_exe,
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    f"{ts:.3f}",
                    "-i",
                    str(clip_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=240:-1",
                    "-q:v",
                    "3",
                    str(img_path),
                ]
            )
            with Image.open(img_path) as im:
                rgb = im.convert("RGB").copy()
                thumbs.append((rgb, ts))
                frame_arrays.append(np.asarray(rgb, dtype=np.float32))

        cell_w, cell_h, label_h, cols = 240, 160, 24, 4
        rows = max(1, (len(thumbs) + cols - 1) // cols)
        sheet = Image.new("RGB", (cols * cell_w, rows * (cell_h + label_h)), "#202020")
        draw = ImageDraw.Draw(sheet)
        for i, (im, ts) in enumerate(thumbs):
            x = (i % cols) * cell_w
            y = (i // cols) * (cell_h + label_h)
            im_copy = im.copy()
            im_copy.thumbnail((cell_w, cell_h))
            sheet.paste(im_copy, (x, y))
            draw.text((x + 5, y + cell_h + 3), f"{ts:.1f}s", font=font, fill="white")

        sheet_name = f"candidate_{cand_id}_{start:.2f}-{end:.2f}.jpg"
        sheet_path = out_dir / sheet_name
        sheet.save(sheet_path, quality=90)

        # Compute local motion stability metric across frames (helps detect large hand/head gestures)
        motion_scores: list[float] = []
        if len(frame_arrays) >= 2:
            for i in range(len(frame_arrays) - 1):
                diff = float(np.mean(np.abs(frame_arrays[i + 1] - frame_arrays[i])))
                motion_scores.append(round(diff, 2))
        avg_motion = round(float(np.mean(motion_scores)), 2) if motion_scores else 0.0

        candidate_list.append(
            {
                "id": cand_id,
                "who": who,
                "source_label": source_label,
                "source_clip": str(clip_path),
                "start": start,
                "end": end,
                "duration": round(end - start, 2),
                "sheet_path": str(sheet_path),
                "avg_motion": avg_motion,
                "verdict": "GOOD" if avg_motion < 12.0 else "BAD",
                "reason": (
                    "Đoạn im < -55 dBFS, chuyển động ổn định, chờ AI/sếp xác nhận mắt & miệng."
                    if avg_motion < 12.0
                    else "Có chuyển động lớn (tay/đầu), nên kiểm tra kỹ hoặc loại."
                ),
            }
        )

    return candidate_list


def token_data(text: str) -> list[dict[str, Any]]:
    red = False
    words: list[dict[str, Any]] = []
    for token in re.findall(r"\[|\]|[^\s\[\]]+", text):
        if token == "[":
            red = True
        elif token == "]":
            red = False
        else:
            words.append({"t": re.sub(r"[,?!.;:]$", "", token.strip()), "red": red})
    return words


def word_chunks(text: str, start: float, end: float) -> list[list[tuple[str, bool, float, float]]]:
    toks: list[tuple[str, bool]] = []
    red = False
    for token in re.findall(r"\[|\]|[^\s\[\]]+", text):
        if token == "[":
            red = True
        elif token == "]":
            red = False
        else:
            toks.append((token, red))
    if not toks:
        return []
    weights = [len(re.sub(r"\W", "", word)) + 1.5 for word, _ in toks]
    total = sum(weights) or 1.0
    acc = 0.0
    out: list[list[tuple[str, bool, float, float]]] = []
    cur: list[tuple[str, bool, float, float]] = []
    for (word, is_red), weight in zip(toks, weights):
        a = start + (end - start) * acc / total
        b = start + (end - start) * (acc + weight) / total
        acc += weight
        cur.append((word, is_red, a, b))
        if len(cur) >= 4 or (len(cur) >= 3 and re.search(r"[,?.!]$", word)):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def subtract_intervals(
    intervals: list[tuple[float, float, str, str]],
    blocked: list[tuple[float, float]],
) -> list[tuple[float, float, str, str]]:
    available = list(intervals)
    for bs, be in blocked:
        next_available: list[tuple[float, float, str, str]] = []
        for start, end, reason, clip_src in available:
            if be <= start or bs >= end:
                next_available.append((start, end, reason, clip_src))
            else:
                if bs > start + 1e-6:
                    next_available.append((start, min(bs, end), reason, clip_src))
                if be < end - 1e-6:
                    next_available.append((max(be, start), end, reason, clip_src))
        available = next_available
    return [(a, b, r, c) for a, b, r, c in available if b - a > 1e-5]


def allocate_listener_range(
    intervals: list[tuple[float, float, str, str]],
    needed: float,
    blocked: list[tuple[float, float]],
) -> list[tuple[float, float, str, str]]:
    available = subtract_intervals(intervals, blocked)
    fitting = [(b - a, a, b, r, c) for a, b, r, c in available if b - a + 1e-6 >= needed]
    if fitting:
        _, a, b, r, c = min(fitting, key=lambda x: (x[0] - needed, x[1]))
        return [(a, a + needed, r, c)]
    ranked = sorted(available, key=lambda x: (-(x[1] - x[0]), x[0]))
    chosen: list[tuple[float, float, str, str]] = []
    remaining = needed
    for start, end, r, c in ranked:
        take = min(end - start, remaining)
        if take > 1e-5:
            chosen.append((start, start + take, r, c))
            remaining -= take
        if remaining <= 1e-5:
            break
    return chosen


def extract_video_segment(
    ffmpeg_exe: str,
    src: Path,
    start: float,
    end: float,
    frames: int,
    dst: Path,
    speed: float,
) -> Path:
    duration = max(0.04, end - start)
    run_hidden(
        [
            ffmpeg_exe,
            "-v",
            "error",
            "-y",
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{duration:.6f}",
            "-i",
            str(src),
            "-vf",
            f"setpts=PTS/{speed},fps={FPS},scale=720:1280,setsar=1",
            "-frames:v",
            str(frames),
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "14",
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
            str(dst),
        ]
    )
    still = dst.with_suffix(".jpg")
    run_hidden(
        [
            ffmpeg_exe,
            "-v",
            "error",
            "-y",
            "-sseof",
            "-0.1",
            "-i",
            str(dst),
            "-frames:v",
            "1",
            "-vf",
            "format=yuvj420p",
            "-q:v",
            "2",
            str(still),
        ]
    )
    if not still.exists() or still.stat().st_size == 0:
        run_hidden(
            [
                ffmpeg_exe,
                "-v",
                "error",
                "-y",
                "-i",
                str(dst),
                "-frames:v",
                "1",
                "-vf",
                "format=yuvj420p",
                "-q:v",
                "2",
                str(still),
            ]
        )
    return still


def extract_pingpong_segment(
    ffmpeg_exe: str,
    src: Path,
    start: float,
    end: float,
    frames: int,
    dst: Path,
    speed: float,
) -> Path:
    single_dur = max(0.2, (end - start) / speed)
    needed_dur = max(0.1, frames / FPS)
    loops = max(1, math.ceil(needed_dur / max(0.2, single_dur * 1.9)))
    stream_loop_args = ["-stream_loop", str(loops)] if loops > 0 else []
    run_hidden(
        [
            ffmpeg_exe,
            "-v",
            "error",
            "-y",
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{max(0.1, end - start):.6f}",
            "-i",
            str(src),
            "-filter_complex",
            (
                f"[0:v]setpts=PTS/{speed},fps={FPS},split=2[f][r];"
                f"[r]reverse[rev];"
                f"[f][rev]concat=n=2:v=1:a=0,loop=loop={loops}:size=32767:start=0,scale=720:1280,setsar=1[v]"
            ),
            "-map",
            "[v]",
            "-frames:v",
            str(frames),
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "14",
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
            str(dst),
        ]
    )
    still = dst.with_suffix(".jpg")
    run_hidden(
        [
            ffmpeg_exe,
            "-v",
            "error",
            "-y",
            "-sseof",
            "-0.1",
            "-i",
            str(dst),
            "-frames:v",
            "1",
            "-vf",
            "format=yuvj420p",
            "-q:v",
            "2",
            str(still),
        ]
    )
    return still


def verify_principle_one(timeline: dict[str, Any]) -> dict[str, Any]:
    """NGUYÊN TẮC SỐ 1: Người đang NÓI luôn dùng clip GỐC có miệng cử động đúng tiếng.
    Chỉ người NGHE mới được thay bằng cảnh yên lặng.
    Returns verification table and raises/reports if any speaking turn uses an idle clip.
    """
    turns = timeline.get("turns", [])
    tracks = timeline.get("visualTracks", {"A": [], "B": []})
    rows: list[dict[str, Any]] = []
    passed_all = True

    for ti, turn in enumerate(turns):
        speaker = turn["who"]
        listener = "B" if speaker == "A" else "A"
        t_from = int(turn["from"])
        t_to = t_from + int(turn["frames"])

        speaker_segs = [
            s
            for s in tracks.get(speaker, [])
            if int(s["from"]) < t_to and (int(s["from"]) + int(s["frames"])) > t_from
        ]
        listener_segs = [
            s
            for s in tracks.get(listener, [])
            if int(s["from"]) < t_to and (int(s["from"]) + int(s["frames"])) > t_from
        ]

        speaker_Violations = []
        for s in speaker_segs:
            fname = str(s.get("file", "")).lower()
            kind = s.get("kind", "speak")
            if kind == "idle" or "idle" in fname or fname.endswith(".jpg"):
                speaker_Violations.append(s.get("file"))

        verdict = "PASS" if (speaker_segs and not speaker_Violations) else "FAIL"
        if verdict != "PASS":
            passed_all = False

        rows.append(
            {
                "turn": ti + 1,
                "speaker": speaker,
                "listener": listener,
                "from_frame": t_from,
                "to_frame": t_to,
                "duration_sec": round((t_to - t_from) / FPS, 2),
                "speaker_clips": [s.get("file") for s in speaker_segs],
                "speaker_kinds": [s.get("kind", "speak") for s in speaker_segs],
                "listener_clips": [s.get("file") for s in listener_segs],
                "verdict": verdict,
                "violations": speaker_Violations,
            }
        )

    return {
        "passed": passed_all,
        "turns_checked": len(rows),
        "rows": rows,
    }


def check_mouth_audio_correlation(
    project_dir: Path,
    media_out_dir: Path,
    timeline: dict[str, Any],
) -> dict[str, Any]:
    """Step 9: Measure mouth/lower-face frame-to-frame motion on speaking clips vs audio presence."""
    cfg = load_config()
    ffmpeg_exe = cfg["paths"]["ffmpeg_exe"]
    turns = timeline.get("turns", [])
    tracks = timeline.get("visualTracks", {"A": [], "B": []})
    results: list[dict[str, Any]] = []
    all_pass = True

    with tempfile.TemporaryDirectory(prefix="mouth_check_") as tmp:
        for ti, turn in enumerate(turns):
            speaker = turn["who"]
            t_from = int(turn["from"])
            t_to = t_from + int(turn["frames"])
            speaker_segs = [
                s
                for s in tracks.get(speaker, [])
                if int(s["from"]) < t_to and (int(s["from"]) + int(s["frames"])) > t_from
            ]
            seg_motions: list[float] = []
            for s in speaker_segs:
                clip_file = media_out_dir / s["file"]
                if not clip_file.is_file() or clip_file.suffix.lower() in (".jpg", ".png"):
                    seg_motions.append(0.0)
                    continue
                # Extract 6fps grayscale frames cropped to upper-body/face region (720x1280 -> center 360x400 around face)
                raw_frames = Path(tmp) / f"t{ti}_{s['file']}.raw"
                run_hidden(
                    [
                        ffmpeg_exe,
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(clip_file),
                        "-vf",
                        "fps=6,crop=280:280:220:260,format=gray",
                        "-f",
                        "rawvideo",
                        str(raw_frames),
                    ],
                    check=False,
                )
                if raw_frames.is_file() and raw_frames.stat().st_size >= 280 * 280 * 2:
                    buf = np.fromfile(raw_frames, dtype=np.uint8)
                    n_f = len(buf) // (280 * 280)
                    arr = buf[: n_f * 280 * 280].reshape(n_f, 280, 280).astype(np.float32)
                    diffs = np.mean(np.abs(arr[1:] - arr[:-1]), axis=(1, 2))
                    seg_motions.append(float(np.mean(diffs)))

            mean_motion = round(float(np.mean(seg_motions)), 2) if seg_motions else 0.0
            # Speaking clips at 6fps have mean grayscale pixel diff > 1.2 when mouth/head moves naturally
            status = "PASS" if mean_motion >= 1.0 else "REVIEW_HUMAN"
            if status != "PASS":
                all_pass = False
            results.append(
                {
                    "turn": ti + 1,
                    "speaker": speaker,
                    "from_frame": t_from,
                    "to_frame": t_to,
                    "mean_face_motion": mean_motion,
                    "status": status,
                    "note": (
                        "Cử động vùng mặt/miệng khớp đoạn có tiếng"
                        if status == "PASS"
                        else "Chuyển động thấp, cần mắt người xem kỹ"
                    ),
                }
            )

    return {
        "all_pass": all_pass,
        "turns": results,
    }


def _strip_accents(s: str) -> str:
    s = s.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def match_and_prepare_products(
    project_dir: Path,
    bang_data: dict[str, Any],
    remotion_media_dir: Path,
) -> dict[str, Any]:
    """Step 6: Match product names in bang.json to no-background PNGs, crop alpha bbox + 2% margin,
    and build a 3-background contact sheet (_contact.png).
    """
    cfg = load_config()
    lib_dir = Path(cfg["paths"].get("product_images_dir", r"H:\source\san pham"))
    sample_dir = Path(cfg["paths"].get("product_sample_dir", r"H:\source\vd-chia-se-app-goi\mau\anh_sp_mau"))

    prod_out_dir = remotion_media_dir / "products"
    prod_out_dir.mkdir(parents=True, exist_ok=True)
    proj_prod_dir = project_dir / "anh" / "products"
    proj_prod_dir.mkdir(parents=True, exist_ok=True)

    # Known curated mapping for standard maternity items (1TR & 5TR) + keyword matcher for new items
    KEYWORD_MAP = [
        (["ao ngan tay", "ao coc"], "01_ao_ngan_tay.png", "ao_ngan_tay"),
        (["ao dai tay"], "02_ao_dai_tay.png", "ao_dai_tay"),
        (["bim", "ta dan", "ta quan"], "03_bim.png", "bim"),
        (["tam lot", "lot chong tham"], "04_tam_lot.png", "tam_lot"),
        (["khan sua"], "05_khan_sua.png", "khan_sua"),
        (["khan tam"], "06_khan_tam.png", "khan_tam_be"),
        (["nuoc muoi"], "07_nuoc_muoi.png", "nuoc_muoi"),
        (["tam bong"], "08_tam_bong.png", "tam_bong"),
        (["dau gio", "dau khuynh diep", "khuynh diep"], "09_dau_gio.png", "dau_khuynh_diep"),
        (["sua tam"], "10_sua_tam.png", "sua_tam"),
        (["kem duong am", "duong am"], "11_kem_duong_am.png", "kem_duong_am"),
        (["kem ho tro ngua ham", "kem ham", "ngua ham"], "12_kem_ham.png", "kem_ham"),
        (["may hut sua"], "13_may_hut_sua.png", "may_hut_sua"),
        (["ao hut sua"], "14_ao_hut_sua.png", "ao_hut_sua"),
        (["binh sua"], "11_binh_sua.png", "binh_sua"),
        (["meji", "meiji", "sua thanh"], "12_meji.png", "meji"),
        (["co rua binh"], "17_co_rua_binh.png", "co_rua_binh"),
        (["nuoc rua binh", "rua binh"], "13_nuoc_rua_binh.png", "nuoc_rua_binh"),
        (["nuoc giat", "omo"], "19_nuoc_giat.png", "nuoc_giat"),
        (["bang ve sinh", "bvs"], "14_bvs_quan.png", "bvs_quan"),
    ]

    lib_files = sorted(lib_dir.glob("*.png")) if lib_dir.is_dir() else []
    sample_files = sorted(sample_dir.glob("*.png")) if sample_dir.is_dir() else []
    sp_5tr_dir = Path(r"C:\Users\Dung\Developer\gio-do-di-sinh\anh\sp_png")

    items = bang_data.get("items", [])
    prepared_items: list[dict[str, Any]] = []
    missing_items: list[str] = []

    for idx, item in enumerate(items, 1):
        item_num = int(item.get("i", idx))
        raw_name = str(item.get("ten", "")).strip()
        display_name = str(item.get("display_name") or raw_name).strip()
        # Special rule from Brief Step 6: "dầu gió" -> "DẦU KHUYNH DIỆP" if not yet customized
        if _strip_accents(raw_name) == "dau gio" and not item.get("display_name"):
            display_name = "Dầu khuynh diệp"

        norm_name = _strip_accents(raw_name)
        chosen_src: Path | None = None
        slug = re.sub(r"[^a-z0-9]+", "_", norm_name).strip("_") or f"sp_{item_num:02d}"

        # 1. Check if user already specified custom_image_path (auto-redirect old paths to H:\source\san pham if present)
        custom_path = item.get("custom_image_path")
        if custom_path:
            cp = Path(custom_path)
            lib_cand = lib_dir / cp.name
            if lib_cand.is_file():
                chosen_src = lib_cand
                item["custom_image_path"] = str(lib_cand)
            elif cp.is_file():
                chosen_src = cp

        # 2. Check H:\source\san pham (lib_dir) first, then curated sample directory, 5TR sp_png dir, & V7 remotion products
        if chosen_src is None:
            v7_prod_dir = Path(cfg["paths"]["remotion_dir"]) / "public" / "convo_gio1tr_v7" / "products"
            for keys, sample_fname, canonical_slug in KEYWORD_MAP:
                if any(k in norm_name for k in keys):
                    slug = canonical_slug
                    for cand in (
                        lib_dir / sample_fname,
                        v7_prod_dir / f"{item_num:02d}_{canonical_slug}.png",
                        sample_dir / sample_fname,
                        sp_5tr_dir / sample_fname,
                    ):
                        if cand.is_file():
                            chosen_src = cand
                            break
                    if chosen_src is not None:
                        break

        # 3. Search in H:\source\san pham by filename keywords (avoiding single generic prefix words like 'nuoc', 'kem', 'ao')
        if chosen_src is None and lib_files:
            generic_words = {"nuoc", "kem", "ao", "khan", "sua", "binh", "co", "tam", "dau"}
            tokens = [t for t in norm_name.split() if len(t) >= 2]
            specific_tokens = [t for t in tokens if t not in generic_words]
            best_score = 0
            for lf in lib_files:
                lf_norm = _strip_accents(lf.stem)
                if specific_tokens and not any(st in lf_norm for st in specific_tokens):
                    continue
                score = sum(1 for t in tokens if t in lf_norm)
                if score > best_score:
                    best_score = score
                    chosen_src = lf

        # 4. If still not found in H:\source\san pham, automatically search & download from Web!
        if chosen_src is None:
            web_save_path = lib_dir / f"{slug}.png"
            dl_info = download_web_image_for_item(
                item_name=raw_name,
                project_title=str(bang_data.get("tieu_de") or ""),
                out_path=web_save_path,
                candidate_index=int(item.get("web_candidate_idx") or 0),
                custom_query=str(item.get("search_query") or ""),
            )
            if dl_info.get("ok") and web_save_path.is_file():
                chosen_src = web_save_path
                item["custom_image_path"] = str(web_save_path)
                if dl_info.get("candidates"):
                    item["web_candidates"] = dl_info["candidates"]

        out_fname = f"{item_num:02d}_{slug}.png"
        out_remotion = prod_out_dir / out_fname
        out_proj = proj_prod_dir / out_fname

        alpha_ok = False
        img_size = (0, 0)
        item_scale = float(item.get("image_scale", 1.0))
        if chosen_src and chosen_src.is_file():
            with Image.open(chosen_src) as im:
                rgba = im.convert("RGBA")
                a_raw = np.asarray(rgba.getchannel("A"))
                is_opaque_photo = float(np.mean(a_raw < 245)) < 0.02
                if is_opaque_photo:
                    canvas = frame_scene_photo_as_card(rgba, target_box=800)
                elif rgba.size == (800, 800) and (
                    bool(item.get("is_scene_photo"))
                    or bool(item.get("is_doctor_cutout"))
                    or "doctor_edited" in str(chosen_src)
                    or "web_items" in str(chosen_src)
                ):
                    canvas = rgba
                else:
                    alpha = rgba.getchannel("A")
                    bbox = alpha.point(lambda p: 255 if p > 12 else 0).getbbox()
                    if bbox:
                        rgba = rgba.crop(bbox)
                    # Normalize all product cutouts onto a uniform 800x800 square canvas
                    target_box = 800
                    pad = 40
                    max_inner = target_box - 2 * pad  # 720px max dimension
                    aspect = max(rgba.width, rgba.height) / max(1, min(rgba.width, rgba.height))
                    scale_limit = max_inner if aspect <= 1.35 else round(max_inner * min(1.0, (1.35 / aspect) ** 0.22))
                    sc = scale_limit / max(1, max(rgba.size))
                    new_w = max(1, round(rgba.width * sc))
                    new_h = max(1, round(rgba.height * sc))
                    rgba = rgba.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    canvas = Image.new("RGBA", (target_box, target_box), (0, 0, 0, 0))
                    ox = (target_box - new_w) // 2
                    oy = (target_box - new_h) // 2
                    canvas.alpha_composite(rgba, (ox, oy))
                canvas.save(out_remotion)
                canvas.save(out_proj)
                img_size = canvas.size
                a_arr = np.asarray(canvas.getchannel("A"))
                transparent_ratio = float(np.mean(a_arr < 16))
                alpha_ok = transparent_ratio > 0.08
        else:
            missing_items.append(raw_name)

        sl = item.get("sl", 0 if item.get("no_price") else 1)
        dv = item.get("dv", "")
        gia = item.get("gia", 0)
        if item.get("no_price") or (not sl and not dv):
            name_and_qty = display_name.strip()
        else:
            name_and_qty = f"{display_name} {sl} {dv}".strip()

        prepared_items.append(
            {
                "i": item_num,
                "nhom": item.get("nhom", 1),
                "ten": raw_name,
                "display_name": display_name,
                "sl": sl,
                "dv": dv,
                "gia": gia,
                "no_price": bool(item.get("no_price")),
                "bullets": item.get("bullets") or [],
                "ghi_chu": item.get("ghi_chu", ""),
                "name_and_qty": name_and_qty,
                "image_file": out_fname if chosen_src else "",
                "source_image": str(chosen_src) if chosen_src else "",
                "image_scale": item_scale,
                "alpha_ok": alpha_ok,
                "width": img_size[0],
                "height": img_size[1],
            }
        )

    # Create contact sheet showing all product cutouts on dark/light/pink backgrounds
    contact_path = proj_prod_dir / "_contact.png"
    _build_products_contact_sheet(prepared_items, proj_prod_dir, contact_path)
    shutil.copy2(contact_path, prod_out_dir / "_contact.png")

    return {
        "items": prepared_items,
        "missing": missing_items,
        "contact_sheet": str(contact_path),
    }


def _build_products_contact_sheet(
    items: list[dict[str, Any]],
    prod_dir: Path,
    out_path: Path,
) -> None:
    cols = 4
    rows = max(1, (len(items) + cols - 1) // cols)
    cell_w, cell_h = 260, 220
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "#2a2a2a")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for idx, it in enumerate(items):
        cx = (idx % cols) * cell_w
        cy = (idx // cols) * cell_h
        # Draw split background (left dark #222, right warm light #f6e8ea) to inspect cutout edges
        draw.rectangle([cx, cy, cx + cell_w // 2, cy + cell_h - 32], fill="#242424")
        draw.rectangle([cx + cell_w // 2, cy, cx + cell_w - 2, cy + cell_h - 32], fill="#f8eaec")
        fname = it.get("image_file")
        if fname and (prod_dir / fname).is_file():
            with Image.open(prod_dir / fname) as im:
                rgba = im.convert("RGBA")
                rgba.thumbnail((cell_w - 24, cell_h - 48))
                px = cx + (cell_w - rgba.width) // 2
                py = cy + (cell_h - 32 - rgba.height) // 2
                sheet.paste(rgba, (px, py), rgba)
        label = f"#{it['i']:02d} { _strip_accents(it.get('display_name') or it.get('ten', ''))[:20] } ({it.get('gia')}K)"
        draw.text((cx + 6, cy + cell_h - 24), label, font=font, fill="white")

    sheet.save(out_path)


def generate_video_qa_sheets(
    video_path: Path,
    timeline: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    """Step 9: Create 1fps full-video contact sheet and 2fps listener-turn contact sheets."""
    cfg = load_config()
    ffmpeg_exe = cfg["paths"]["ffmpeg_exe"]
    ffprobe_exe = cfg["paths"]["ffprobe_exe"]

    out_dir.mkdir(parents=True, exist_ok=True)
    probe = ffprobe_media(ffprobe_exe, video_path)
    duration = float(probe["duration"])
    font = ImageFont.load_default()

    # 1. Full video 1fps contact sheet
    frames_1fps_dir = out_dir / "qa_1fps_frames"
    frames_1fps_dir.mkdir(exist_ok=True)
    sec_list = [float(s) for s in range(int(math.ceil(duration)))]
    thumbs: list[tuple[Image.Image, float]] = []
    for i, sec in enumerate(sec_list):
        if sec >= duration:
            break
        fp = frames_1fps_dir / f"f_{i:03d}.jpg"
        run_hidden(
            [
                ffmpeg_exe,
                "-v",
                "error",
                "-y",
                "-ss",
                f"{sec:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-vf",
                "scale=240:240",
                "-q:v",
                "3",
                str(fp),
            ]
        )
        with Image.open(fp) as im:
            thumbs.append((im.convert("RGB").copy(), sec))

    cols = 6
    cell_w, cell_h, label_h = 240, 240, 22
    rows = max(1, (len(thumbs) + cols - 1) // cols)
    sheet_1fps = Image.new("RGB", (cols * cell_w, rows * (cell_h + label_h)), "#1a1a1a")
    draw = ImageDraw.Draw(sheet_1fps)
    for i, (im, sec) in enumerate(thumbs):
        x = (i % cols) * cell_w
        y = (i // cols) * (cell_h + label_h)
        sheet_1fps.paste(im, (x, y))
        draw.text((x + 6, y + cell_h + 4), f"t={sec:.1f}s (f={int(sec*30)})", font=font, fill="white")

    sheet_1fps_path = out_dir / "sheet_1fps_full.jpg"
    sheet_1fps.save(sheet_1fps_path, quality=90)

    # 2. Listener turns 2fps sheet
    listen_thumbs: list[tuple[Image.Image, str]] = []
    frames_listen_dir = out_dir / "qa_listen_2fps_frames"
    frames_listen_dir.mkdir(exist_ok=True)
    for ti, turn in enumerate(timeline.get("turns", [])):
        speaker = turn["who"]
        listener = "B" if speaker == "A" else "A"
        t_start = float(turn["from"]) / FPS
        t_end = float(turn["from"] + turn["frames"]) / FPS
        t = t_start + 0.1
        while t < min(duration - 0.05, t_end):
            fp = frames_listen_dir / f"turn_{ti + 1}_{int(t * 100):05d}.jpg"
            run_hidden(
                [
                    ffmpeg_exe,
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    f"{t:.3f}",
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=240:240",
                    "-q:v",
                    "3",
                    str(fp),
                ]
            )
            with Image.open(fp) as im:
                im_rgb = im.convert("RGB").copy()
                d_box = ImageDraw.Draw(im_rgb)
                # By default in ConvoAppDynamic (Brief Step 7): B (người đáp) is on LEFT, A (người hỏi) is on RIGHT
                asker_on_right = timeline.get("askerSide", "right") != "left"
                listener_on_left = (listener == "B" and asker_on_right) or (listener == "A" and not asker_on_right)
                if listener_on_left:
                    d_box.rectangle([2, 2, 118, 237], outline="#22c55e", width=3)
                    side_lbl = f"{listener}-Trai nghe"
                else:
                    d_box.rectangle([122, 2, 237, 237], outline="#22c55e", width=3)
                    side_lbl = f"{listener}-Phai nghe"
                listen_thumbs.append((im_rgb, f"T{ti+1}({side_lbl}) {t:.1f}s"))
            t += 0.5

    rows_l = max(1, (len(listen_thumbs) + cols - 1) // cols)
    sheet_listen = Image.new("RGB", (cols * cell_w, rows_l * (cell_h + label_h)), "#1a1a1a")
    draw_l = ImageDraw.Draw(sheet_listen)
    for i, (im, lbl) in enumerate(listen_thumbs):
        x = (i % cols) * cell_w
        y = (i // cols) * (cell_h + label_h)
        sheet_listen.paste(im, (x, y))
        draw_l.text((x + 6, y + cell_h + 4), lbl, font=font, fill="white")

    sheet_listen_path = out_dir / "sheet_2fps_listeners.jpg"
    sheet_listen.save(sheet_listen_path, quality=90)

    return {
        "sheet_1fps_full": str(sheet_1fps_path),
        "sheet_2fps_listeners": str(sheet_listen_path),
        "frames_1fps_count": len(thumbs),
        "frames_listen_count": len(listen_thumbs),
    }


def _build_script_from_bang(bang: dict[str, Any]) -> str:
    """Generate a structured kich_ban.md from bang.json so Step 3 AI has full context."""
    title = bang.get("tieu_de") or "GIỎ ĐỒ ĐI SINH"
    tong = bang.get("tong") or 0
    items = bang.get("items", [])
    lines = [
        f"# Kịch bản: {title}",
        f"- Tổng ngân sách bảng giá: {tong} K",
        "- Vai A (Người hỏi): Hỏi kinh nghiệm soạn đồ / tư vấn danh sách các món cần mua.",
        "- Vai B (Người đáp): Tư vấn chi tiết từng món theo thứ tự bảng dưới đây:",
        "",
        "## Danh sách các món trong bảng:",
    ]
    for it in items:
        i_num = it.get("i", 1)
        ten = it.get("ten", "")
        disp = it.get("display_name") or ten.upper()
        sl = it.get("sl", 1)
        dv = it.get("dv", "Cái")
        gia = it.get("gia", 0)
        note = it.get("ghi_chu") or it.get("brand") or ""
        note_str = f" ({note})" if note else ""
        price_str = f"{gia}K" if gia > 0 else "TẶNG / 0K"
        lines.append(f"{i_num}. **{ten}** (Hiển thị: `{disp}`) — Số lượng: {sl} {dv} — Giá: {price_str}{note_str}")
    return "\n".join(lines) + "\n"


def parse_table_image_with_ai(
    project_dir: Path,
    image_path: Path,
    preferred_provider: str = "agy",
) -> dict[str, Any]:
    """Read an uploaded/pasted image of an Excel product table or 5-point script using local CLI AI (Codex 2 / Agy)."""
    from cli_ai import invoke_cli_agent

    anh_dir = project_dir / "anh"
    anh_dir.mkdir(parents=True, exist_ok=True)
    saved_img = anh_dir / "bang_nguon.jpg"
    with Image.open(image_path) as im:
        im.convert("RGB").save(saved_img, quality=95)

    out_json_path = project_dir / "text" / "ai_parsed_table.json"
    if out_json_path.is_file():
        out_json_path.unlink()

    prompt = (
        "Hãy đọc kỹ ảnh chụp bảng sản phẩm / kịch bản đính kèm và trích xuất chính xác 100% sang JSON hợp lệ.\n"
        f"Ghi kết quả JSON vào đúng file: {out_json_path} VÀ in nguyên khối ```json ... ``` ở câu trả lời.\n"
        "Cấu trúc JSON bắt buộc:\n"
        "{\n"
        '  "tieu_de": "TIÊU ĐỀ IN HOA Ở ĐẦU BẢNG (VD: GIỎ ĐỒ ĐI SINH 5 TR)",\n'
        '  "preset": "giodo",\n'
        '  "tong": 5036,\n'
        '  "items": [\n'
        "    {\n"
        '      "i": 1,\n'
        '      "nhom": 1,\n'
        '      "ten": "Áo ngắn tay",\n'
        '      "display_name": "ÁO NGẮN TAY",\n'
        '      "sl": 3,\n'
        '      "dv": "Cái",\n'
        '      "gia": 60,\n'
        '      "brand": "",\n'
        '      "ghi_chu": ""\n'
        "    }\n"
        "  ],\n"
        '  "chia_se_items": []\n'
        "}\n"
        "Quy tắc bắt buộc:\n"
        "1. Đọc đúng từng dòng từ trên xuống dưới, giữ chính xác dấu tiếng Việt.\n"
        "2. Tách cột số lượng + đơn vị (VD: '3 Cái' -> sl=3, dv='Cái'; '1 Bịch' -> sl=1, dv='Bịch'; '1 Cặp' -> sl=1, dv='Cặp'; '3 Thanh' -> sl=3, dv='Thanh').\n"
        "3. Cột giá: lấy số nguyên (VD: 60, 40, 150, 3320). Nếu ô giá trống (như món được tặng kèm) thì để gia=0.\n"
        "4. Cột bên phải ngoài cùng (nếu có chữ như 'Khuynh diệp', 'Centaphil', 'Được tặng khi mua Sữa tắm', 'Pigoen', 'Wesser', 'Bzu', 'Omo', 'Sofit diana') -> ghi vào 'ghi_chu' và 'brand'. Riêng dòng 'Dầu gió' có ghi 'Khuynh diệp' thì đặt 'display_name': 'DẦU KHUYNH DIỆP', các dòng khác đặt 'display_name' là tên món IN HOA.\n"
        "5. Dòng số tổng ở cuối bảng (VD: 5036) ghi vào 'tong'.\n"
    )

    ai_res = invoke_cli_agent(
        project_dir=project_dir,
        step_name="step0_parse_table_image",
        prompt=prompt,
        preferred_provider=preferred_provider,
        images=[saved_img],
        expected_out_file=out_json_path,
        effort="low",
    )
    parsed = ai_res.get("json")
    if not parsed or not isinstance(parsed, dict):
        raise RuntimeError(
            f"AI CLI ({ai_res.get('provider')}) không đọc được bảng từ ảnh. Chi tiết: {ai_res.get('output_text', '')[-400:]}"
        )

    norm_items: list[dict[str, Any]] = []
    for idx, it in enumerate(parsed.get("items", []), 1):
        ten = str(it.get("ten") or it.get("name") or f"Món {idx}").strip()
        ghi_chu = str(it.get("ghi_chu") or it.get("brand") or it.get("note") or "").strip()
        disp = str(it.get("display_name") or "").strip().upper()
        if not disp:
            disp = "DẦU KHUYNH DIỆP" if ("dầu gió" in ten.lower() and "khuynh diệp" in ghi_chu.lower()) else ten.upper()
        elif "dầu gió" in ten.lower() and "khuynh diệp" in ghi_chu.lower():
            disp = "DẦU KHUYNH DIỆP"

        sl_raw = it.get("sl", 1)
        dv_raw = str(it.get("dv") or "Cái").strip()
        if isinstance(sl_raw, str):
            m_q = re.match(r"^(\d+)\s*(.*)$", sl_raw.strip())
            sl = int(m_q.group(1)) if m_q else 1
            if m_q and m_q.group(2).strip():
                dv_raw = m_q.group(2).strip()
        else:
            sl = int(sl_raw) if sl_raw is not None else 1

        gia_raw = it.get("gia")
        try:
            gia = int(float(str(gia_raw).replace(",", "").replace(".", "").strip())) if gia_raw not in (None, "") else 0
        except Exception:
            gia = 0

        norm_items.append(
            {
                "i": idx,
                "nhom": int(it.get("nhom") or 1),
                "ten": ten,
                "display_name": disp,
                "sl": sl,
                "dv": dv_raw.capitalize() if dv_raw else "Cái",
                "gia": gia,
                "ghi_chu": ghi_chu,
            }
        )

    calc_total = sum(x["gia"] for x in norm_items)
    tong_val = parsed.get("tong")
    try:
        tong = int(tong_val) if tong_val else calc_total
    except Exception:
        tong = calc_total

    title = str(parsed.get("tieu_de") or "").strip().upper()
    bang_data = {
        "tieu_de": title,
        "tong": tong,
        "items": norm_items,
    }
    script_md = _build_script_from_bang(bang_data)
    return {
        "provider": ai_res.get("provider"),
        "title": title,
        "preset": parsed.get("preset", "giodo"),
        "bang": bang_data,
        "chia_se_items": parsed.get("chia_se_items") or [],
        "script_text": script_md,
        "table_image_rel": "anh/bang_nguon.jpg",
    }


def parse_table_tsv_text(raw_text: str, default_title: str = "") -> dict[str, Any]:
    """Instant parser for rows copied directly from Excel (TSV / lines) into bang.json."""
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    title = default_title
    items: list[dict[str, Any]] = []
    tong = 0

    for ln in lines:
        cols = [c.strip() for c in re.split(r"\t+|\s{2,}|\|", ln) if c.strip()]
        if not cols:
            continue
        # Single number at the end = total row (e.g. "5036")
        if len(cols) == 1 and re.match(r"^\d{3,6}$", cols[0]):
            tong = int(cols[0])
            continue
        # Header title row (e.g. "GIỎ ĐỒ ĐI SINH 5 TR")
        if len(cols) == 1 and not re.search(r"\d+\s*(cái|bịch|chai|hộp|cặp|bình|thanh)", cols[0], re.I):
            if not items and len(cols[0]) >= 5:
                title = cols[0].upper()
            continue

        ten = cols[0]
        sl, dv, gia, ghi_chu = 1, "Cái", 0, ""
        if len(cols) >= 2:
            m_q = re.match(r"^(\d+)\s*(.*)$", cols[1])
            if m_q:
                sl = int(m_q.group(1))
                dv = m_q.group(2).strip().capitalize() or "Cái"
        if len(cols) >= 3:
            if re.match(r"^\d+$", cols[2]):
                gia = int(cols[2])
                if len(cols) >= 4:
                    ghi_chu = " ".join(cols[3:])
            else:
                ghi_chu = " ".join(cols[2:])

        idx = len(items) + 1
        disp = "DẦU KHUYNH DIỆP" if ("dầu gió" in ten.lower() and "khuynh diệp" in ghi_chu.lower()) else ten.upper()
        items.append(
            {
                "i": idx,
                "nhom": 1,
                "ten": ten,
                "display_name": disp,
                "sl": sl,
                "dv": dv,
                "gia": gia,
                "ghi_chu": ghi_chu,
            }
        )

    if not tong:
        tong = sum(x["gia"] for x in items)
    bang = {"tieu_de": title, "tong": tong, "items": items}
    return {
        "title": title,
        "bang": bang,
        "script_text": _build_script_from_bang(bang),
    }


def build_smart_image_search_query(
    item_name: str,
    project_title: str = "",
    bullets: list[str] | None = None,
) -> str:
    """Build an accurate Vietnamese web image search query from an item name, project title, and optional bullets."""
    raw = (item_name or "").strip()
    title_clean = re.sub(r"^\s*\d+[\.\)\-:]\s*", "", (project_title or "").strip())

    # Expand common Vietnamese abbreviations
    expanded = re.sub(r"\bbv\b", "Bệnh viện", raw, flags=re.I)
    expanded = re.sub(r"\bđh\b", "Đại học", expanded, flags=re.I)
    expanded = re.sub(r"\bđhyd\b", "Đại học Y Dược", expanded, flags=re.I)

    # Curated hospital / maternity / baby brand queries for instant 100% precision
    curated_map = {
        "tu du": "Bệnh viện Từ Dũ TPHCM",
        "hung vuong": "Bệnh viện Phụ sản Hùng Vương TPHCM",
        "dh y duoc": "Bệnh viện Đại học Y Dược TPHCM",
        "dai hoc y duoc": "Bệnh viện Đại học Y Dược TPHCM",
        "me kong": "Bệnh viện Phụ sản Mê Kông TPHCM",
        "mekong": "Bệnh viện Phụ sản Mê Kông TPHCM",
        "vinmec": "Bệnh viện Đa khoa Quốc tế Vinmec",
        "tam anh": "Bệnh viện Đa khoa Tâm Anh",
        "hanh phuc": "Bệnh viện Quốc tế Hạnh Phúc",
        "aih": "Bệnh viện Quốc tế Mỹ AIH",
        "quoc te my": "Bệnh viện Quốc tế Mỹ AIH",
        "doomi baby": "Doomi Baby đồ sơ sinh khăn sữa tấm lót cho bé",
        "bora store": "Bora Store đồ dùng cho bé cọ rửa bình sữa ăn dặm",
        "hai anh family": "Hải Anh Family đồ sơ sinh mẹ và bé",
    }
    stripped_item = _strip_accents(raw)
    for k, q_val in curated_map.items():
        if k in stripped_item:
            return q_val

    if "benh vien" in _strip_accents(title_clean) or "bv" in stripped_item:
        if "benh vien" not in _strip_accents(expanded):
            return f"Bệnh viện {expanded}"
        return expanded

    # If the item has descriptive bullets, extract concrete product nouns to enrich the image query
    bullet_hint = ""
    if bullets:
        joined_b = " ".join(bullets)
        # Look for concrete nouns after "từ ..."
        m_tu = re.search(r"(?:đa dạng từ|từ)\s+([^.;]+)", joined_b, flags=re.I)
        if m_tu:
            phrases = [p.strip() for p in m_tu.group(1).split(",") if p.strip()]
            bullet_hint = " ".join(phrases[:3])
        if len(bullet_hint) > 45:
            bullet_hint = bullet_hint[:45].rsplit(" ", 1)[0]

    if bullet_hint:
        return f"{expanded} {bullet_hint} {title_clean}".strip()

    if title_clean and _strip_accents(title_clean) not in stripped_item:
        return f"{expanded} {title_clean}".strip()
    return expanded


def search_web_images(query: str, max_results: int = 8) -> list[dict[str, str]]:
    """Search Bing Images Async (mkt=vi-VN) and return a list of {murl, turl, title} dicts."""
    import urllib.parse
    import urllib.request

    q_str = (query or "").strip()
    if not q_str:
        return []
    url = (
        "https://www.bing.com/images/async?q="
        + urllib.parse.quote(q_str.encode("utf-8"))
        + "&first=0&count=20&adlt=off&mkt=vi-VN"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
            "Referer": "https://www.bing.com/images/search",
        },
    )
    try:
        raw_html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", errors="ignore")
    except Exception:
        return []

    blobs = re.findall(r'm="(\{[^"]+\})"', raw_html)
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for b in blobs:
        try:
            unesc = (
                b.replace("&quot;", '"')
                .replace("&amp;", "&")
                .replace("&#39;", "'")
            )
            data = json.loads(unesc)
            murl = str(data.get("murl") or "").strip()
            turl = str(data.get("turl") or "").strip()
            title = str(data.get("t") or "").strip()
            if not murl and not turl:
                continue
            key = murl or turl
            if key in seen_urls:
                continue
            seen_urls.add(key)
            results.append({"murl": murl, "turl": turl, "title": title})
            if len(results) >= max_results:
                break
        except Exception:
            continue
    return results


def frame_scene_photo_as_card(im: Image.Image, target_box: int = 800) -> Image.Image:
    """Frame an opaque rectangular photo (e.g., hospital building / place photo) into an 800x800
    transparent RGBA canvas with a rounded 4:3 card, crisp white border, and soft drop shadow.
    """
    from PIL import ImageFilter

    rgb = im.convert("RGB")
    card_w, card_h = 720, 540
    # Center-crop to 4:3 aspect ratio
    src_w, src_h = rgb.size
    target_ratio = card_w / card_h
    src_ratio = src_w / max(1, src_h)
    if src_ratio > target_ratio:
        new_w = int(round(src_h * target_ratio))
        left = (src_w - new_w) // 2
        rgb = rgb.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(round(src_w / target_ratio))
        top = (src_h - new_h) // 2
        rgb = rgb.crop((0, top, src_w, top + new_h))

    rgb = rgb.resize((card_w, card_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (target_box, target_box), (0, 0, 0, 0))
    ox = (target_box - card_w) // 2
    oy = (target_box - card_h) // 2
    radius = 38
    border = 12

    # Soft shadow layer
    shadow = Image.new("RGBA", (target_box, target_box), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle(
        [ox - border + 4, oy - border + 10, ox + card_w + border + 4, oy + card_h + border + 10],
        radius=radius + border,
        fill=(0, 0, 0, 120),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    canvas.alpha_composite(shadow)

    # White frame layer
    frame_layer = Image.new("RGBA", (target_box, target_box), (0, 0, 0, 0))
    f_draw = ImageDraw.Draw(frame_layer)
    f_draw.rounded_rectangle(
        [ox - border, oy - border, ox + card_w + border, oy + card_h + border],
        radius=radius + border,
        fill=(255, 255, 255, 255),
    )
    canvas.alpha_composite(frame_layer)

    # Rounded photo mask
    mask = Image.new("L", (card_w, card_h), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle([0, 0, card_w, card_h], radius=radius, fill=255)
    photo_rgba = rgb.convert("RGBA")
    photo_rgba.putalpha(mask)
    canvas.alpha_composite(photo_rgba, (ox, oy))
    return canvas


def download_web_image_for_item(
    item_name: str,
    project_title: str,
    out_path: Path,
    candidate_index: int = 0,
    custom_query: str = "",
) -> dict[str, Any]:
    """Search Bing Images for `item_name` + `project_title`, download candidate image, and save as framed PNG."""
    import urllib.request

    query = (custom_query or "").strip() or build_smart_image_search_query(item_name, project_title)
    candidates = search_web_images(query, max_results=8)
    if not candidates:
        return {"ok": False, "query": query, "error": f"Không tìm thấy ảnh cho '{query}'", "candidates": []}

    start_idx = candidate_index % len(candidates)
    ordered = candidates[start_idx:] + candidates[:start_idx]

    for cand in ordered:
        for url_try in (cand.get("murl", ""), cand.get("turl", "")):
            if not url_try:
                continue
            try:
                # Request high-res thumbnail if using Bing turl
                if "tse" in url_try and "bing.net" in url_try and "w=" not in url_try:
                    url_try = url_try + "&w=800&h=600&c=7"
                req = urllib.request.Request(
                    url_try,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "Referer": "https://www.bing.com/",
                    },
                )
                raw_bytes = urllib.request.urlopen(req, timeout=8).read()
                with Image.open(io.BytesIO(raw_bytes)) as im:
                    if im.width < 120 or im.height < 100:
                        continue
                    framed = frame_scene_photo_as_card(im, target_box=800)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    framed.save(out_path)
                    return {
                        "ok": True,
                        "query": query,
                        "path": str(out_path),
                        "saved_path": str(out_path),
                        "chosen_url": url_try,
                        "chosen_title": cand.get("title", ""),
                        "source_title": cand.get("title", ""),
                        "candidates": candidates,
                        "candidate_index": start_idx,
                    }
            except Exception:
                continue

    return {"ok": False, "query": query, "error": "Không tải được ảnh từ các URL ứng viên", "candidates": candidates}


def parse_script_outline(raw_text: str, current_title: str = "") -> dict[str, Any]:
    """Deterministically analyze raw script text to extract title, subtitle, and exact item entries
    before any pipeline step or AI call runs.
    """
    raw_lines = (raw_text or "").strip().splitlines()
    lines = [ln.strip() for ln in raw_lines if ln.strip()]
    if not lines:
        return {
            "title": (current_title or "DANH SÁCH CHIA SẺ").strip().upper(),
            "subtitle": "",
            "entries": [],
            "count": 0,
        }

    def _is_bullet_line(s: str) -> bool:
        return bool(re.match(r"^[\-\*\•\+]\s+", s))

    title = (current_title or "").strip().upper()
    body_lines: list[str] = []

    first_ln = lines[0]
    m_head = re.match(r"^\s*(\d+)[\.\)\-:]\s*(.+)$", first_ln)
    second_ln = lines[1] if len(lines) > 1 else ""
    second_is_num2 = bool(re.match(r"^\s*2[\.\)\-:]\s+", second_ln))
    followed_by_blank = len(raw_lines) > 1 and not raw_lines[1].strip()
    is_all_caps = (first_ln.upper() == first_ln) and any(c.isalpha() for c in first_ln)

    if m_head and (is_all_caps or int(m_head.group(1)) != 1 or followed_by_blank or not second_is_num2):
        title = m_head.group(2).strip().upper()
        body_lines = lines[1:]
    elif len(lines) >= 2 and (is_all_caps or followed_by_blank) and not _is_bullet_line(first_ln) and not second_is_num2:
        title = first_ln.strip().upper()
        body_lines = lines[1:]
    else:
        body_lines = lines

    if not title:
        title = "DANH SÁCH CHIA SẺ"

    has_bullets = any(_is_bullet_line(ln) for ln in body_lines)
    subtitle = ""
    grouped_entries: list[dict[str, Any]] = []

    if has_bullets:
        blocks: list[dict[str, Any]] = []
        for ln in body_lines:
            if _is_bullet_line(ln):
                b_txt = re.sub(r"^[\-\*\•\+]\s*", "", ln).strip()
                if b_txt:
                    if not blocks:
                        blocks.append({"heading": title, "bullets": [b_txt]})
                    else:
                        blocks[-1]["bullets"].append(b_txt)
            else:
                clean_h = re.sub(r"^\s*\d+[\.\)\-:]\s*", "", ln).strip()
                blocks.append({"heading": clean_h, "bullets": []})

        seen_bulleted_item = False
        for blk in blocks:
            if blk["bullets"]:
                seen_bulleted_item = True
                grouped_entries.append(blk)
            elif not seen_bulleted_item:
                subtitle = f"{subtitle} | {blk['heading']}".strip(" |") if subtitle else blk["heading"]
            else:
                grouped_entries.append(blk)
    else:
        for idx_b, ln in enumerate(body_lines):
            if idx_b == 0 and len(body_lines) >= 3 and ("•" in ln or " - " in ln) and not re.match(r"^\s*\d+[\.\)\-:]", ln):
                subtitle = ln.strip()
                continue
            clean_ln = re.sub(r"^\s*[\-\*\•\+]?\s*(?:\d+[\.\)\-:]\s*)?", "", ln).strip()
            if clean_ln:
                grouped_entries.append({"heading": clean_ln, "bullets": []})

    return {
        "title": title,
        "subtitle": subtitle,
        "entries": grouped_entries,
        "count": len(grouped_entries),
    }


def parse_and_fetch_anh_nhac_list(
    project_dir: Path,
    raw_text: str,
    current_title: str = "",
    use_ai: bool = False,
    custom_request: str = "",
) -> dict[str, Any]:
    """Parse a plain list of items (e.g., '7. BỆNH VIỆN ĐI SINH\\n\\nTừ dũ\\nHùng Vương...')
    and automatically search & download web images for every item in parallel.
    """
    from concurrent.futures import ThreadPoolExecutor

    cfg = load_config()
    lib_dir = Path(cfg["paths"].get("product_images_dir", r"H:\source\san pham"))
    lib_dir.mkdir(parents=True, exist_ok=True)

    outline = parse_script_outline(raw_text, current_title=current_title)
    grouped_entries = outline["entries"]
    if not grouped_entries:
        raise ValueError("Danh sách trống! Sếp hãy nhập tiêu đề và danh sách các mục.")

    title = outline["title"]
    subtitle = outline["subtitle"]

    # Optional Agy CLI query & bullet enrichment (fast 1-turn JSON output, ~12-15s)
    ai_queries: dict[int, str] = {}
    ai_display_names: dict[int, str] = {}
    ai_bullets: dict[int, list[str]] = {}
    req_clean = (custom_request or "").strip()
    needs_ai_enrichment = use_ai or bool(
        req_clean
        and re.search(
            r"(?:họ\s*tên|kinh\s*nghiệm|chuyên\s*ngành|chuyên\s*nghành|tiktok|facebook|địa\s*chỉ|thông\s*tin|mô\s*tả|chi\s*tiết|review|đánh\s*giá)",
            req_clean,
            flags=re.I,
        )
    )
    if needs_ai_enrichment and grouped_entries:
        try:
            from cli_ai import invoke_cli_agent
            extra_req_txt = f"\nYêu cầu thêm của sếp Dũng cho từng mục:\n{req_clean}\n" if req_clean else ""
            prompt = (
                "KHÔNG dùng tool đọc/ghi file hay chạy lệnh terminal. Hãy trả lời NGAY LẬP TỨC bằng duy nhất 1 khối ```json ... ```.\n"
                f"Chủ đề video: {title}\n"
                f"{extra_req_txt}"
                f"Danh sách ĐÚNG {len(grouped_entries)} mục từ kịch bản của sếp (BẮT BUỘC giữ đúng {len(grouped_entries)} mục theo thứ tự 1..{len(grouped_entries)}, TUYỆT ĐỐI KHÔNG thêm mục thứ {len(grouped_entries) + 1} và KHÔNG bớt mục):\n"
                + "\n".join(
                    f"{idx}. {g['heading']}" + (f" ({'; '.join(g['bullets'])})" if g.get("bullets") else "")
                    for idx, g in enumerate(grouped_entries, 1)
                )
                + '\n\nHãy trả về JSON chuẩn UTF-8: {"title": "TIÊU ĐỀ IN HOA", "subtitle": "PHỤ ĐỀ TÓM TẮT (NẾU CÓ)", "items": [{"i": 1, "display_name": "TÊN HIỂN THỊ IN HOA CHUẨN XÁC", "bullets": ["Dòng thông tin 1 (nếu sếp yêu cầu thêm địa chỉ/kinh nghiệm/chuyên ngành/kênh...)", "Dòng 2..."], "search_query": "Từ khóa tìm ảnh thực tế chính xác nhất bằng tiếng Việt"}]}'
            )
            ai_res = invoke_cli_agent(
                project_dir=project_dir,
                step_name="anh_nhac_queries",
                prompt=prompt,
                preferred_provider="agy",
                effort="low",
            )
            parsed_ai = ai_res.get("json")
            if isinstance(parsed_ai, dict):
                if parsed_ai.get("title"):
                    title = str(parsed_ai["title"]).strip().upper()
                if parsed_ai.get("subtitle") and not subtitle:
                    subtitle = str(parsed_ai["subtitle"]).strip()
                for it_ai in parsed_ai.get("items") or []:
                    idx_ai = int(it_ai.get("i") or 0)
                    if 1 <= idx_ai <= len(grouped_entries):
                        if it_ai.get("search_query"):
                            ai_queries[idx_ai] = str(it_ai["search_query"]).strip()
                        if it_ai.get("display_name"):
                            ai_display_names[idx_ai] = str(it_ai["display_name"]).strip().upper()
                        if isinstance(it_ai.get("bullets"), list) and it_ai["bullets"]:
                            ai_bullets[idx_ai] = [str(b).strip() for b in it_ai["bullets"] if str(b).strip()]
        except Exception:
            pass

    # Extract optional global image search hint from custom_request (e.g., "tìm ảnh chụp mặt tiền bên ngoài", "tìm ảnh tông hồng pastel")
    global_img_hint = ""
    if req_clean:
        m_hint = re.search(
            r"(?:tìm\s+ảnh|hình\s+ảnh\s+theo\s+kiểu|phong\s+cách\s+ảnh|kiểu\s+ảnh)\s*(?:là|:)?\s*([^;\n]+)",
            req_clean,
            flags=re.I,
        )
        if m_hint:
            global_img_hint = m_hint.group(1).strip()

    raw_items: list[dict[str, Any]] = []
    for idx, grp in enumerate(grouped_entries, 1):
        clean_ln = grp["heading"].strip()
        bullets_list = ai_bullets.get(idx) or grp.get("bullets") or []
        if not clean_ln:
            continue
        disp = ai_display_names.get(idx) or clean_ln.upper()
        q_str = ai_queries.get(idx) or build_smart_image_search_query(clean_ln, title, bullets=bullets_list)
        if global_img_hint and global_img_hint.lower() not in q_str.lower():
            q_str = f"{q_str} {global_img_hint}".strip()
        slug = re.sub(r"[^a-z0-9]+", "_", _strip_accents(clean_ln)).strip("_") or f"item_{idx:02d}"
        note_str = " • ".join(bullets_list) if bullets_list else q_str
        raw_items.append(
            {
                "i": len(raw_items) + 1,
                "nhom": 1,
                "ten": clean_ln,
                "display_name": disp,
                "bullets": bullets_list,
                "sl": 0,
                "dv": "",
                "gia": 0,
                "ghi_chu": note_str,
                "search_query": q_str,
                "no_price": True,
                "is_scene_photo": True,
                "image_scale": 1.0,
                "slug": slug,
            }
        )

    def _fetch_one(it_obj: dict[str, Any]) -> dict[str, Any]:
        slug = it_obj.pop("slug", f"item_{it_obj['i']:02d}")
        save_p = lib_dir / f"web_{slug}.png"
        dl = download_web_image_for_item(
            item_name=it_obj["ten"],
            project_title=title,
            out_path=save_p,
            candidate_index=0,
            custom_query=it_obj.get("search_query", ""),
        )
        if (dl.get("ok") or save_p.is_file()) and save_p.is_file():
            it_obj["custom_image_path"] = str(save_p)
            it_obj["web_candidates"] = dl.get("candidates", [])
            it_obj["web_candidate_idx"] = 0
        return it_obj

    with ThreadPoolExecutor(max_workers=4) as ex:
        final_items = list(ex.map(_fetch_one, raw_items))

    bang = {
        "tieu_de": title,
        "subtitle": subtitle,
        "tong": 0,
        "items": final_items,
    }
    (project_dir / "text").mkdir(parents=True, exist_ok=True)
    write_json(project_dir / "text" / "bang.json", bang)
    write_text(project_dir / "text" / "kich_ban.md", raw_text.strip() + "\n")
    dl_count = sum(1 for x in final_items if x.get("custom_image_path"))
    return {
        "title": title,
        "subtitle": subtitle,
        "bang": bang,
        "script_text": raw_text.strip(),
        "count": len(final_items),
        "downloaded_count": dl_count,
        "fetched_count": dl_count,
    }


def generate_pleasant_bgm_wav(out_path: Path, duration_sec: float = 25.0, sr: int = 48000) -> Path:
    """Synthesize a warm, pleasant acoustic/lofi background music track (Cmaj7 - Am7 - Fmaj7 - G6)
    so 'Preset: Ảnh + Nhạc (Không Voice)' has cheerful royalty-free music out of the box.
    """
    import wave

    dur = max(4.0, float(duration_sec))
    n_samples = int(round(dur * sr))
    t = np.arange(n_samples, dtype=np.float32) / sr

    # Chord progression every 2.0 seconds: Cmaj7 -> Am7 -> Fmaj7 -> G6
    chords = [
        [261.63, 329.63, 392.00, 493.88],  # Cmaj7
        [220.00, 261.63, 329.63, 392.00],  # Am7
        [174.61, 220.00, 261.63, 349.23],  # Fmaj7
        [196.00, 246.94, 293.66, 329.63],  # G6
    ]
    beat_sec = 0.5  # 120 BPM
    bar_sec = 2.0

    audio = np.zeros(n_samples, dtype=np.float32)

    # 1. Warm electric piano chords + gentle arpeggio pluck
    total_beats = int(math.ceil(dur / beat_sec))
    for b_idx in range(total_beats):
        start_s = b_idx * beat_sec
        i0 = int(round(start_s * sr))
        if i0 >= n_samples:
            break
        chord = chords[(b_idx // 4) % len(chords)]
        # Arpeggio note on every eighth/quarter
        note_freq = chord[b_idx % len(chord)] * 2.0
        note_len = min(int(sr * 0.48), n_samples - i0)
        lt = np.arange(note_len, dtype=np.float32) / sr
        env = np.exp(-lt * 6.5) * (1.0 - np.exp(-lt * 120.0))
        pluck = (
            0.55 * np.sin(2 * np.pi * note_freq * lt)
            + 0.20 * np.sin(2 * np.pi * (note_freq * 2.0) * lt) * np.exp(-lt * 12.0)
        ) * env
        audio[i0 : i0 + note_len] += 0.16 * pluck

        # Sustained warm pad on beat 0 of each bar
        if b_idx % 4 == 0:
            bar_len = min(int(sr * bar_sec), n_samples - i0)
            bt = np.arange(bar_len, dtype=np.float32) / sr
            pad_env = np.sin(np.pi * bt / bar_sec) ** 0.6
            pad_wave = np.zeros(bar_len, dtype=np.float32)
            for cf in chord:
                pad_wave += np.sin(2 * np.pi * cf * bt)
            # Root bass note
            bass_freq = chord[0] * 0.5
            bass_env = np.exp(-bt * 2.2)
            pad_wave += 1.4 * np.sin(2 * np.pi * bass_freq * bt) * bass_env
            audio[i0 : i0 + bar_len] += 0.075 * pad_wave * pad_env

    # Fade in first 0.4s and fade out last 1.2s
    fade_in = min(int(0.4 * sr), n_samples // 4)
    fade_out = min(int(1.2 * sr), n_samples // 3)
    if fade_in > 0:
        audio[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
    if fade_out > 0:
        audio[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)

    peak = float(np.max(np.abs(audio))) or 1.0
    audio = np.clip(audio / peak * 0.45, -0.95, 0.95)
    pcm16 = (audio * 32767.0).astype(np.int16)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        stereo = np.column_stack((pcm16, pcm16)).ravel()
        wf.writeframes(stereo.tobytes())
    return out_path


def build_timeline_and_media_anh_nhac(
    project_dir: Path,
    remotion_media_dir: Path,
    item_duration_sec: float = 2.4,
    bgm_path: str = "",
    asker_side: str = "right",
) -> dict[str, Any]:
    """Step 5 for 'Preset: Ảnh + Nhạc (Không Voice)' (preset == 'anh_nhac'):
    Builds timeline.json timed to the items in bang.json, prepares silent visual tracks if Clip A/B exist,
    and prepares the background music track (media/voice_1.3x.wav -> remotion voice.wav).
    """
    cfg = load_config()
    ffmpeg_exe = cfg["paths"]["ffmpeg_exe"]
    ffprobe_exe = cfg["paths"]["ffprobe_exe"]
    sfx_src_dir = Path(cfg["paths"]["sfx_dir"])

    media_dir = project_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    remotion_media_dir.mkdir(parents=True, exist_ok=True)

    bang_path = project_dir / "text" / "bang.json"
    bang = read_json(bang_path) if bang_path.is_file() else {"items": []}
    items = bang.get("items") or []
    n_items = max(1, len(items))

    intro_frames = int(round(1.2 * FPS))  # 36 frames (1.2s)
    per_item_frames = max(30, int(round(float(item_duration_sec or 2.4) * FPS)))
    outro_frames = 151  # 151 frames (5.03s summary board, matches Remotion giodo/anh_nhac summary length)

    item_marks: dict[str, int] = {}
    cur_f = intro_frames
    for idx, it in enumerate(items, 1):
        key = str(it.get("i") or idx)
        item_marks[key] = cur_f
        cur_f += per_item_frames

    timeline_frames = cur_f + 15
    total_frames = timeline_frames + outro_frames
    total_dur_sec = round(total_frames / FPS, 3)

    # Check if Clip A / Clip B exist for background 2-person visual tracks
    cfr_a = project_dir / "nguon" / "A_hoi.mp4"
    cfr_b = project_dir / "nguon" / "B_dap.mp4"
    visual_tracks: dict[str, list[dict[str, Any]]] = {"A": [], "B": []}

    for who, cfr_p in (("A", cfr_a), ("B", cfr_b)):
        if cfr_p.is_file():
            try:
                pr = ffprobe_media(ffprobe_exe, cfr_p)
                clip_dur = float(pr.get("duration") or 10.0)
                start_s = min(2.0, max(0.0, clip_dur * 0.15))
                avail_s = max(2.0, clip_dur - start_s - 0.5)
                seg_s = min(avail_s, total_dur_sec)
                out_name = f"idle_{who}_anh_nhac.mp4"
                out_still = f"idle_{who}_anh_nhac.jpg"
                out_local = media_dir / out_name
                still_local = media_dir / out_still
                run_hidden(
                    [
                        ffmpeg_exe,
                        "-v",
                        "error",
                        "-y",
                        "-ss",
                        f"{start_s:.3f}",
                        "-t",
                        f"{seg_s:.3f}",
                        "-i",
                        str(cfr_p),
                        "-an",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "fast",
                        "-crf",
                        "18",
                        "-r",
                        str(FPS),
                        "-pix_fmt",
                        "yuv420p",
                        str(out_local),
                    ]
                )
                run_hidden(
                    [
                        ffmpeg_exe,
                        "-v",
                        "error",
                        "-y",
                        "-ss",
                        f"{start_s:.3f}",
                        "-i",
                        str(cfr_p),
                        "-frames:v",
                        "1",
                        str(still_local),
                    ]
                )
                shutil.copy2(out_local, remotion_media_dir / out_name)
                if still_local.is_file():
                    shutil.copy2(still_local, remotion_media_dir / out_still)
                seg_frames = max(30, int(round(seg_s * FPS)))
                f_cursor = 0
                while f_cursor < timeline_frames:
                    take_f = min(seg_frames, timeline_frames - f_cursor)
                    visual_tracks[who].append(
                        {
                            "from": f_cursor,
                            "frames": take_f,
                            "file": out_name,
                            "still": out_still,
                            "kind": "idle",
                            "noDissolve": True,
                        }
                    )
                    f_cursor += take_f
            except Exception:
                pass

    # Prepare Background Music (custom file or auto-synthesized pleasant BGM)
    voice_out = media_dir / "voice.wav"
    bgm_custom = Path(bgm_path) if bgm_path and Path(bgm_path).is_file() else None
    if bgm_custom:
        run_hidden(
            [
                ffmpeg_exe,
                "-v",
                "error",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(bgm_custom),
                "-t",
                f"{total_dur_sec:.3f}",
                "-af",
                f"afade=t=in:st=0:d=0.5,afade=t=out:st={max(0.5, total_dur_sec - 1.2):.3f}:d=1.2,volume=0.55",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(voice_out),
            ]
        )
    else:
        generate_pleasant_bgm_wav(voice_out, duration_sec=total_dur_sec, sr=48000)

    shutil.copy2(voice_out, media_dir / "voice_1.3x.wav")
    shutil.copy2(voice_out, media_dir / "voice_preview.wav")
    shutil.copy2(voice_out, remotion_media_dir / "voice.wav")

    # Copy SFX files
    sfx_dst = remotion_media_dir / "sfx"
    sfx_dst.mkdir(parents=True, exist_ok=True)
    for sname in SFX_NAMES:
        sp = sfx_src_dir / sname
        if sp.is_file():
            shutil.copy2(sp, sfx_dst / sname)

    timeline = {
        "fps": FPS,
        "speed": 1.0,
        "askerSide": asker_side,
        "frames": timeline_frames,
        "totalFrames": total_frames,
        "durationSec": total_dur_sec,
        "turns": [],
        "pieces": [],
        "visualTracks": visual_tracks,
        "itemMarks": item_marks,
        "redTickFrames": [],
        "principle1_check": {
            "passed": True,
            "all_pass": True,
            "turns_checked": 0,
            "rows": [],
            "note": "Chế độ Ảnh + Nhạc (Không có Voice)",
        },
    }
    write_json(media_dir / "timeline.json", timeline)
    write_json(remotion_media_dir / "timeline.json", timeline)
    (project_dir / "reports").mkdir(parents=True, exist_ok=True)
    write_json(project_dir / "reports" / "principle1_check.json", timeline["principle1_check"])
    return timeline


_HUMAN_SEG_SESSION = None


def _get_human_seg_session():
    """Lazy-load u2net_human_seg.onnx via onnxruntime (auto-downloads if missing)."""
    global _HUMAN_SEG_SESSION
    if _HUMAN_SEG_SESSION is not None:
        return _HUMAN_SEG_SESSION
    import urllib.request
    import onnxruntime as ort

    model_dir = Path(__file__).resolve().parent.parent / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "u2net_human_seg.onnx"
    if not model_path.is_file() or model_path.stat().st_size < 10_000_000:
        url = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx"
        urllib.request.urlretrieve(url, model_path)
    _HUMAN_SEG_SESSION = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    return _HUMAN_SEG_SESSION


def compute_human_segmentation_mask(rgb_im: Image.Image) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
    """Run u2net_human_seg on an RGB PIL image and return (alpha_uint8_HxW, main_person_bbox_xyxy).
    Automatically filters out tiny disconnected avatars/icons so only the main doctor/person remains.
    """
    import cv2

    w, h = rgb_im.size
    sess = _get_human_seg_session()
    in_name = sess.get_inputs()[0].name

    im_320 = rgb_im.resize((320, 320), Image.Resampling.BILINEAR)
    arr = np.asarray(im_320, dtype=np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std
    tensor = np.transpose(arr, (2, 0, 1))[None, ...]

    pred = sess.run(None, {in_name: tensor})[0][0, 0]
    p_min, p_max = float(pred.min()), float(pred.max())
    pred_norm = (pred - p_min) / max(1e-6, p_max - p_min)
    mask_320 = (pred_norm * 255.0).astype(np.uint8)
    mask_full = cv2.resize(mask_320, (w, h), interpolation=cv2.INTER_CUBIC)

    # Keep main human component(s) and discard small stray avatars/UI elements
    binary = (mask_full > 85).astype(np.uint8)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num_labels > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        max_idx = int(np.argmax(areas)) + 1
        max_area = int(stats[max_idx, cv2.CC_STAT_AREA])
        if max_area > (w * h * 0.008):
            keep = np.zeros_like(mask_full, dtype=np.uint8)
            for lbl in range(1, num_labels):
                area = int(stats[lbl, cv2.CC_STAT_AREA])
                if lbl == max_idx or area >= max_area * 0.22:
                    keep[labels == lbl] = 255
            # Soften keep mask edges so hair/shoulders stay smooth
            keep_blur = cv2.GaussianBlur(keep, (15, 15), 0)
            mask_full = np.minimum(mask_full, keep_blur)

    # Soft contrast stretch on alpha edge to remove faint halo
    alpha_f = np.clip((mask_full.astype(np.float32) - 28.0) / (235.0 - 28.0), 0.0, 1.0)
    alpha_u8 = (alpha_f * 255.0).astype(np.uint8)

    ys, xs = np.where(alpha_u8 > 75)
    if len(xs) > 20 and len(ys) > 20:
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    else:
        bbox = None
    return alpha_u8, bbox


def extract_doctor_subject_image(
    src_path: Path,
    out_path: Path,
    mode: str = "cutout",
    crop_box: list[float] | None = None,
    target_box: int = 800,
) -> dict[str, Any]:
    """Process a user-uploaded image (e.g. screenshot or portrait) to isolate ONLY the doctor/person:
    - mode == 'cutout': AI human segmentation -> transparent background + crisp white sticker outline & soft shadow
    - mode == 'cutout_plain': AI human segmentation -> transparent background + soft shadow (no white stroke)
    - mode == 'cutout_card': AI human segmentation -> placed on a clean warm studio card with rounded white frame
    - mode == 'crop_card': Auto-detects doctor bbox (or uses manual crop_box) -> crops tightly to the doctor & frames as card
    crop_box (optional): [x_norm, y_norm, w_norm, h_norm] in 0.0..1.0 coordinates relative to the original image.
    """
    import cv2
    from PIL import ImageFilter

    with Image.open(src_path) as raw_im:
        orig_rgba = raw_im.convert("RGBA")
        orig_w, orig_h = orig_rgba.size

        # Composite onto white for RGB analysis if input had transparency
        bg_white = Image.new("RGBA", orig_rgba.size, (255, 255, 255, 255))
        bg_white.alpha_composite(orig_rgba)
        work_rgb = bg_white.convert("RGB")

        # Apply manual crop_box first if provided by the user in the interactive editor
        manual_cropped = False
        if crop_box and len(crop_box) == 4:
            cx, cy, cw, ch = [float(v) for v in crop_box]
            if cw > 0.03 and ch > 0.03:
                x1 = max(0, min(orig_w - 10, int(round(cx * orig_w))))
                y1 = max(0, min(orig_h - 10, int(round(cy * orig_h))))
                x2 = max(x1 + 10, min(orig_w, int(round((cx + cw) * orig_w))))
                y2 = max(y1 + 10, min(orig_h, int(round((cy + ch) * orig_h))))
                if not (x1 == 0 and y1 == 0 and x2 == orig_w and y2 == orig_h):
                    work_rgb = work_rgb.crop((x1, y1, x2, y2))
                    manual_cropped = True

        alpha_u8, person_bbox = compute_human_segmentation_mask(work_rgb)
        w, h = work_rgb.size

        if mode == "crop_card":
            # If user didn't manually crop, auto-crop around the detected doctor with comfortable portrait padding
            if not manual_cropped and person_bbox is not None:
                bx1, by1, bx2, by2 = person_bbox
                bw = bx2 - bx1
                bh = by2 - by1
                pad_x = int(round(bw * 0.22))
                pad_top = int(round(bh * 0.14))
                pad_bot = int(round(bh * 0.08))
                cx1 = max(0, bx1 - pad_x)
                cy1 = max(0, by1 - pad_top)
                cx2 = min(w, bx2 + pad_x)
                cy2 = min(h, by2 + pad_bot)
                cropped_portrait = work_rgb.crop((cx1, cy1, cx2, cy2))
            else:
                cropped_portrait = work_rgb
            canvas = frame_scene_photo_as_card(cropped_portrait, target_box=target_box)
        else:
            # Cutout modes: 'cutout', 'cutout_plain', 'cutout_card'
            rgba_cut = work_rgb.convert("RGBA")
            rgba_cut.putalpha(Image.fromarray(alpha_u8))
            if person_bbox is not None:
                bx1, by1, bx2, by2 = person_bbox
                pad = 6
                cx1 = max(0, bx1 - pad)
                cy1 = max(0, by1 - pad)
                cx2 = min(w, bx2 + pad)
                cy2 = min(h, by2 + pad)
                rgba_cut = rgba_cut.crop((cx1, cy1, cx2, cy2))

            if mode == "cutout_card":
                # Place the doctor cutout onto a clean warm studio card (720x540) so no clutter remains
                card_w, card_h = 720, 540
                bg_card = Image.new("RGB", (card_w, card_h), (244, 238, 228))
                bg_draw = ImageDraw.Draw(bg_card)
                # Subtle studio radial highlight
                for r_step in range(260, 10, -15):
                    t_r = (260 - r_step) / 260.0
                    c_val = (
                        int(244 + 10 * t_r),
                        int(238 + 12 * t_r),
                        int(228 + 16 * t_r),
                    )
                    bg_draw.ellipse(
                        [card_w // 2 - r_step, card_h // 2 - r_step, card_w // 2 + r_step, card_h // 2 + r_step],
                        fill=c_val,
                    )
                bg_rgba = bg_card.convert("RGBA")
                # Scale doctor cutout to fit height 505px (bottom-aligned like a portrait studio shot)
                sc = min((card_w - 60) / max(1, rgba_cut.width), 510 / max(1, rgba_cut.height))
                nw = max(1, int(round(rgba_cut.width * sc)))
                nh = max(1, int(round(rgba_cut.height * sc)))
                doc_resized = rgba_cut.resize((nw, nh), Image.Resampling.LANCZOS)
                dx = (card_w - nw) // 2
                dy = card_h - nh  # bottom-align doctor portrait on card
                bg_rgba.alpha_composite(doc_resized, (dx, dy))
                canvas = frame_scene_photo_as_card(bg_rgba.convert("RGB"), target_box=target_box)
            else:
                # Transparent cutout ('cutout' with white sticker stroke or 'cutout_plain')
                max_inner = target_box - 88  # 712px
                sc = min(max_inner / max(1, rgba_cut.width), max_inner / max(1, rgba_cut.height))
                nw = max(1, int(round(rgba_cut.width * sc)))
                nh = max(1, int(round(rgba_cut.height * sc)))
                doc_resized = rgba_cut.resize((nw, nh), Image.Resampling.LANCZOS)

                canvas = Image.new("RGBA", (target_box, target_box), (0, 0, 0, 0))
                ox = (target_box - nw) // 2
                oy = (target_box - nh) // 2

                doc_alpha = np.asarray(doc_resized.getchannel("A"))
                # Soft drop shadow
                shadow_layer = Image.new("RGBA", (target_box, target_box), (0, 0, 0, 0))
                sh_mask = Image.fromarray((doc_alpha * 0.48).astype(np.uint8))
                sh_solid = Image.new("RGBA", (nw, nh), (0, 0, 0, 255))
                sh_solid.putalpha(sh_mask)
                shadow_layer.alpha_composite(sh_solid, (ox + 4, oy + 10))
                shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(12))
                canvas.alpha_composite(shadow_layer)

                if mode == "cutout":
                    # Add crisp white sticker border around the doctor cutout
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
                    dilated = cv2.dilate(doc_alpha, kernel, iterations=1)
                    dilated_blur = cv2.GaussianBlur(dilated, (5, 5), 0)
                    stroke_layer = Image.new("RGBA", (nw, nh), (255, 255, 255, 255))
                    stroke_layer.putalpha(Image.fromarray(dilated_blur))
                    canvas.alpha_composite(stroke_layer, (ox, oy))

                canvas.alpha_composite(doc_resized, (ox, oy))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path)

        # Compute normalized suggested bbox on original image so UI crop editor can show it
        norm_bbox = [0.05, 0.05, 0.90, 0.90]
        if not manual_cropped and person_bbox is not None:
            bx1, by1, bx2, by2 = person_bbox
            bw, bh = bx2 - bx1, by2 - by1
            px1 = max(0, bx1 - int(bw * 0.12))
            py1 = max(0, by1 - int(bh * 0.10))
            px2 = min(orig_w, bx2 + int(bw * 0.12))
            py2 = min(orig_h, by2 + int(bh * 0.06))
            norm_bbox = [
                round(px1 / max(1, orig_w), 4),
                round(py1 / max(1, orig_h), 4),
                round((px2 - px1) / max(1, orig_w), 4),
                round((py2 - py1) / max(1, orig_h), 4),
            ]

        return {
            "ok": True,
            "out_path": str(out_path),
            "mode": mode,
            "person_detected": person_bbox is not None,
            "suggested_crop_box": norm_bbox,
            "orig_size": [orig_w, orig_h],
        }


