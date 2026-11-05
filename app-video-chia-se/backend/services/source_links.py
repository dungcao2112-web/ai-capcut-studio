# -*- coding: utf-8 -*-
"""🔗 Link nguồn do sếp dán: tự nhận diện link, đọc trang (tiêu đề, mô tả, ảnh + chú thích, đoạn chữ, các
mục con theo tiêu đề nhỏ), rồi khớp ẢNH với từng mục theo tên. THÔNG TIN theo mục: services/source_info.py. Không dán link => app tự tìm web như bình thường.

Kết quả đọc được lưu cache ở text/sources.json (không phải tải lại mỗi lần bấm).
"""
from __future__ import annotations

import io
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.I)
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
SKIP_IMG = re.compile(r"(logo|icon|sprite|avatar|emoji|pixel|blank|spacer|badge|banner-ads|\.svg|\.gif)", re.I)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MAX_BYTES = 4 * 1024 * 1024


def extract_links(text: str, limit: int = 60) -> list[str]:
    out: list[str] = []
    for m in URL_RE.finditer(text or ""):
        u = m.group(0).rstrip(".,;:!?)]}>…")
        if u not in out:
            out.append(u)
    return out[:limit]


def link_kind(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    path = urllib.parse.urlparse(url).path.lower()
    for key in ("facebook", "tiktok", "shopee", "lazada", "youtube", "instagram", "tiki"):
        if key in host:
            return key
    return "image" if path.endswith(IMG_EXT) else "web"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower()).replace("đ", "d")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


class _PageParser(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.title, self.meta, self.images, self.text = base, "", {}, [], []
        self.sections: list[dict[str, Any]] = []  # [{heading, text[]}] — bài dạng danh sách: mỗi mục 1 tiêu đề nhỏ
        self._in_title = False
        self._heading: list[str] | None = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in ("h1", "h2", "h3", "h4", "dt"):
            self._heading = []
        elif tag in ("p", "li", "div", "br", "td") and self.sections:
            self.sections[-1]["text"].append("\n")
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.meta[key] = a["content"]
        elif tag == "img":
            src = a.get("data-src") or a.get("data-original") or a.get("src") or ""
            if not src and a.get("srcset"):
                src = a["srcset"].split(",")[-1].strip().split(" ")[0]
            if src and not src.startswith("data:"):
                ctx = " ".join(self.text[-2:])[-160:]  # chỉ đoạn chữ liền trước ảnh
                self.images.append({"url": urllib.parse.urljoin(self.base, src), "alt": a.get("alt", "") or a.get("title", ""), "ctx": ctx})

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in ("h1", "h2", "h3", "h4", "dt") and self._heading is not None:
            head = " ".join(self._heading).strip()
            self._heading = None
            if head:
                self.sections.append({"heading": head[:160], "text": []})

    def handle_data(self, data):
        t = " ".join(data.split())
        if not t or self._skip:
            return
        if self._in_title:
            self.title += t
        elif self._heading is not None:
            self._heading.append(t)
            self.text.append(t)
        else:
            self.text.append(t)
            if self.sections:
                self.sections[-1]["text"].append(t)


def _get(url: str, timeout: float = 10.0) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "vi,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(MAX_BYTES), (resp.headers.get("Content-Type") or "").lower()


def fetch_source(url: str, timeout: float = 10.0) -> dict[str, Any]:
    info: dict[str, Any] = {"url": url, "kind": link_kind(url), "ok": False, "title": "", "description": "",
                            "images": [], "text": "", "fetched_at": int(time.time())}
    try:
        raw, ctype = _get(url, timeout)
    except Exception as exc:
        info["error"] = f"Không đọc được link: {exc}"[:200]
        return info
    if ctype.startswith("image/") or url.lower().split("?")[0].endswith(IMG_EXT):
        name = Path(urllib.parse.urlparse(url).path).stem.replace("-", " ").replace("_", " ")
        info.update(ok=True, kind="image", title=name, images=[{"url": url, "alt": name, "ctx": ""}])
        return info
    html = raw.decode("utf-8", errors="replace")
    p = _PageParser(url)
    try:
        p.feed(html)
    except Exception:
        pass
    imgs = []
    for key in ("og:image", "twitter:image", "og:image:url"):
        if p.meta.get(key):
            imgs.append({"url": urllib.parse.urljoin(url, p.meta[key]), "alt": p.meta.get("og:title", p.title), "ctx": "og"})
    seen = set()
    for im in imgs + p.images:
        if im["url"] in seen or SKIP_IMG.search(im["url"]):
            continue
        seen.add(im["url"])
        info["images"].append(im)
    info.update(ok=True, title=(p.meta.get("og:title") or p.title).strip()[:200],
                description=(p.meta.get("og:description") or p.meta.get("description") or "").strip()[:400],
                text=" ".join(p.text)[:20000],
                sections=[{"heading": sec["heading"], "text": re.sub(r"\s*\n\s*", "\n", " ".join(sec["text"])).strip()[:2000]}
                          for sec in p.sections[:120]])
    info["images"] = info["images"][:60]
    return info


def load_sources(pdir: Path, links: list[str], refresh: bool = False) -> list[dict[str, Any]]:
    from utils import read_json, write_json

    cache_p = pdir / "text" / "sources.json"
    cache = read_json(cache_p, {}) or {}
    out = []
    for url in links:
        rec = cache.get(url)
        if refresh or not rec or not rec.get("ok") or "sections" not in rec:  # bản cache cũ chưa chia mục => đọc lại
            rec = fetch_source(url)
            cache[url] = rec
        out.append(rec)
    write_json(cache_p, {u: cache[u] for u in links if u in cache})
    return out


def match_score(name: str, text: str) -> float:
    n, t = norm(name), norm(text)
    if not n or not t:
        return 0.0
    if f" {n} " in f" {t} ":
        return 1.0
    toks = [w for w in n.split() if len(w) >= 2]
    tset = set(t.split())
    return sum(1 for w in toks if w in tset) / max(1, len(toks))


def images_for_item(name: str, idx0: int, n_items: int, sources: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """Ảnh hợp với mục: chú thích/tên file/ngữ cảnh/tiêu đề trang khớp tên mục. Nếu số link = số mục
    và không khớp được tên thì dùng ảnh đại diện của link cùng thứ tự (sếp dán mỗi mục 1 link)."""
    scored: list[dict[str, Any]] = []
    for s in sources:
        if not s.get("ok"):
            continue
        page_hit = match_score(name, f"{s.get('title', '')} {s.get('description', '')}")
        for k, im in enumerate(s.get("images") or []):
            fname = Path(urllib.parse.urlparse(im["url"]).path).stem.replace("-", " ").replace("_", " ")
            sc = max(match_score(name, im.get("alt", "")), match_score(name, fname))
            if not im.get("alt") and sc < 0.6 and im.get("ctx") != "og":  # ảnh không chú thích => dựa chữ liền trước
                sc = 0.75 * match_score(name, im.get("ctx", ""))
            if page_hit >= 0.99 and (im.get("ctx") == "og" or k < 4):
                sc = max(sc, 0.85 if im.get("ctx") == "og" else 0.7)
            if sc >= 0.6:
                scored.append({"url": im["url"], "score": round(sc, 3), "source": s["url"]})
    scored.sort(key=lambda x: -x["score"])
    if not scored:
        pages = [s for s in sources if s.get("ok") and s.get("images")]
        if len(pages) == n_items and idx0 < len(pages):
            scored = [{"url": im["url"], "score": 0.5, "source": pages[idx0]["url"]} for im in pages[idx0]["images"][:limit]]
    uniq, seen = [], set()
    for x in scored:
        if x["url"] not in seen:
            seen.add(x["url"])
            uniq.append(x)
    return uniq[:limit]


def download_image(url: str, out_path: Path, min_side: int = 300) -> Path | None:
    from PIL import Image

    try:
        raw, _ctype = _get(url, 12)
        with Image.open(io.BytesIO(raw)) as im:
            if min(im.size) < min_side:
                return None
            out_path.parent.mkdir(parents=True, exist_ok=True)
            im.convert("RGB").save(out_path)
        return out_path
    except Exception:
        return None
