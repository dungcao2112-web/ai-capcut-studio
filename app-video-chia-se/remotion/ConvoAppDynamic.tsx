import React from "react";
import {
  AbsoluteFill,
  Audio,
  Html5Video,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useRemotionEnvironment,
  useVideoConfig,
} from "remotion";
import { loadFont as loadAnton } from "@remotion/google-fonts/Anton";
import { loadFont as loadBarlowCondensed } from "@remotion/google-fonts/BarlowCondensed";
import { loadFont as loadBeVietnamPro } from "@remotion/google-fonts/BeVietnamPro";
import { loadFont as loadMontserrat } from "@remotion/google-fonts/Montserrat";
import { loadFont as loadOswald } from "@remotion/google-fonts/Oswald";
import { loadFont as loadBaloo2 } from "@remotion/google-fonts/Baloo2";
import { loadFont as loadPaytoneOne } from "@remotion/google-fonts/PaytoneOne";
import { loadFont as loadBangers } from "@remotion/google-fonts/Bangers";
import { loadFont as loadPhudu } from "@remotion/google-fonts/Phudu";
import { loadFont as loadCoiny } from "@remotion/google-fonts/Coiny";
import { loadFont as loadKanit } from "@remotion/google-fonts/Kanit";
import { loadFont as loadChakraPetch } from "@remotion/google-fonts/ChakraPetch";
import { loadFont as loadMali } from "@remotion/google-fonts/Mali";
import { loadFont as loadPatrickHand } from "@remotion/google-fonts/PatrickHand";
import { loadFont as loadLexend } from "@remotion/google-fonts/Lexend";
import activeData from "./convo_app_active.json";

const FONT_LOADERS: Record<string, (style?: any, opts?: any) => { fontFamily: string }> = {
  Anton: loadAnton,
  BarlowCondensed: loadBarlowCondensed,
  BeVietnamPro: loadBeVietnamPro,
  Montserrat: loadMontserrat,
  Oswald: loadOswald,
  Baloo2: loadBaloo2,
  PaytoneOne: loadPaytoneOne,
  Bangers: loadBangers,
  Phudu: loadPhudu,
  Coiny: loadCoiny,
  Kanit: loadKanit,
  ChakraPetch: loadChakraPetch,
  Mali: loadMali,
  PatrickHand: loadPatrickHand,
  Lexend: loadLexend,
};

const loadSelectedFont = (fontKey: string | undefined, fallbackKey = "Anton"): string => {
  const key = fontKey && FONT_LOADERS[fontKey] ? fontKey : fallbackKey;
  const loader = FONT_LOADERS[key] || loadAnton;
  try {
    return loader("normal", { subsets: ["vietnamese", "latin", "latin-ext"] }).fontFamily;
  } catch {
    return loader().fontFamily;
  }
};

const activeCfg = (activeData.config || {}) as Record<string, any>;
const titleFontFamily = loadSelectedFont(activeCfg.titleFont, "Anton");
const subFontFamily = loadSelectedFont(activeCfg.subFont, "Anton");
const antonFont = subFontFamily;
const barlowFont = subFontFamily;

const SIZE = 1080;
const FEATHER = 80;
const DEFAULT_DISSOLVE = 4;

type Word = { t: string; red: boolean };
type CaptionData = {
  words: Word[];
  from: number;
  to: number;
  who: "A" | "B";
  sourceText?: string;
};
type Segment = {
  file: string;
  still: string;
  from: number;
  frames: number;
  kind?: "speak" | "idle" | "hold";
  noDissolve?: boolean;
};
type TimelineData = {
  fps: number;
  frames: number;
  turns: { who: "A" | "B"; from: number; frames: number }[];
  itemMarks: Record<string, number>;
  redTickFrames: number[];
  captions: CaptionData[];
  pieces: CaptionData[];
  visualTracks: Record<"A" | "B", Segment[]>;
  dissolveFrames?: number;
};

type ProductItem = {
  i: number;
  ten: string;
  display_name?: string;
  sl: number | string;
  dv: string;
  gia: number | string;
  gia_text?: string;
  no_price?: boolean;
  bullets?: string[];
  image_file: string;
  name_and_qty?: string;
  image_scale?: number;
};

export const formatVNPrice = (
  rawGia: number | string,
  maskPrice: boolean,
  giaText?: string
): string => {
  if (giaText && String(giaText).trim()) {
    return String(giaText).trim();
  }
  if (typeof rawGia === "string" && rawGia.trim() && isNaN(Number(rawGia.trim()))) {
    return rawGia.trim();
  }
  const sfx = (activeData.config as any)?.priceSuffix ?? " K";
  const num = typeof rawGia === "number" ? rawGia : Number(String(rawGia).replace(/[^0-9]/g, ""));
  if (!num || isNaN(num)) {
    const zeroLabel = (activeData.config as any)?.zeroPriceLabel;
    if (zeroLabel !== undefined && String(zeroLabel).trim() !== "") {
      return String(zeroLabel).trim();
    }
    return String(rawGia);
  }
  if (maskPrice) {
    if (num < 10) return `${num}${sfx}`;
    if (num >= 1000) {
      const s = String(num);
      const head = s.slice(0, -3);
      const mid = s.slice(-3, -1);
      return `${head}.${mid}x${sfx}`;
    }
    return `${String(num).slice(0, -1)}x${sfx}`;
  } else {
    if (num >= 1000) {
      return `${num.toLocaleString("vi-VN")}${sfx}`;
    }
    return `${num}${sfx}`;
  }
};

const Dissolve: React.FC<{
  src: string;
  box: React.CSSProperties;
  inner: React.CSSProperties;
  dissolveFrames: number;
}> = ({ src, box, inner, dissolveFrames }) => {
  const f = useCurrentFrame();
  return (
    <div
      style={{
        ...box,
        opacity: interpolate(f, [0, Math.max(1, dissolveFrames - 1)], [1, 0], {
          extrapolateRight: "clamp",
        }),
      }}
    >
      <Img src={src} style={{ ...inner, objectFit: "fill" }} />
    </div>
  );
};

const shouldDissolveJoin = (
  prev: Segment,
  curr: Segment,
  who: "A" | "B",
  turns: { who: "A" | "B"; from: number; frames: number }[]
): boolean => {
  if (prev.noDissolve || curr.noDissolve) return false;
  if (prev.file.endsWith(".jpg") || curr.file.endsWith(".jpg")) return false;
  if (prev.file.includes("idle") !== curr.file.includes("idle")) return false;
  // Rule from Brief Step 9: No dissolve at boundary where speaker switches between real speech and idle listener shot
  if (prev.kind && curr.kind && prev.kind !== curr.kind) return false;
  // Also check turn boundaries: if this exact frame is where speaker 'who' starts or stops speaking, hard cut!
  const boundaryTurnChange = turns.some((t) => {
    const tStart = t.from;
    const tEnd = t.from + t.frames;
    return curr.from === tStart || curr.from === tEnd;
  });
  if (boundaryTurnChange) {
    const prevSpeaking = turns.some(
      (t) => t.who === who && prev.from >= t.from && prev.from < t.from + t.frames
    );
    const currSpeaking = turns.some(
      (t) => t.who === who && curr.from >= t.from && curr.from < t.from + t.frames
    );
    if (prevSpeaking !== currSpeaking) return false;
  }
  return true;
};

const Track: React.FC<{
  who: "A" | "B";
  entries: Segment[];
  mediaDir: string;
  turns: { who: "A" | "B"; from: number; frames: number }[];
  cfg: typeof activeData.config;
}> = ({ who, entries, mediaDir, turns, cfg }) => {
  const { isStudio } = useRemotionEnvironment();
  const Video = isStudio ? Html5Video : OffthreadVideo;

  const askerOnRight = cfg.askerSide !== "left";
  const isRightSide = (who === "A" && askerOnRight) || (who === "B" && !askerOnRight);
  const faceX = isRightSide ? 810 : 270;
  const s = who === "A" ? (cfg.scaleA ?? 1) : (cfg.scaleB ?? 1.06);
  const cropVal = who === "A" ? (cfg.cropA ?? 329) : (cfg.cropB ?? 325);
  const topVal = who === "A" ? (cfg.topA ?? 180) : (cfg.topB ?? 215);
  const faceCenter = cropVal * s;
  const left = faceX - faceCenter;

  const box: React.CSSProperties = {
    position: "absolute",
    left,
    top: 0,
    width: isRightSide ? SIZE - left : 720,
    height: SIZE,
    overflow: "hidden",
    WebkitMaskImage: isRightSide
      ? `linear-gradient(to right, transparent 0, #000 ${FEATHER}px)`
      : undefined,
  };
  const inner: React.CSSProperties = {
    position: "absolute",
    width: 720 * s,
    height: 1280 * s,
    left: 0,
    top: -topVal,
    objectFit: "fill",
  };
  const dissolveFrames = activeData.timeline.dissolveFrames ?? DEFAULT_DISSOLVE;

  return (
    <>
      {entries.map((e, idx) => {
        const isStillHold = e.file.toLowerCase().endsWith(".jpg") || e.file.toLowerCase().endsWith(".png");
        return (
          <Sequence key={`${who}-${idx}-${e.file}-${e.from}`} from={e.from} durationInFrames={e.frames} layout="none">
            <div style={box}>
              {isStillHold ? (
                <Img src={staticFile(`${mediaDir}/${e.file}`)} style={inner} />
              ) : (
                <Video
                  src={staticFile(`${mediaDir}/${e.file}`)}
                  muted
                  startFrom={0}
                  endAt={e.frames}
                  style={inner}
                />
              )}
            </div>
          </Sequence>
        );
      })}
      {entries.slice(1).map((e, i) => {
        const prev = entries[i];
        if (!shouldDissolveJoin(prev, e, who, turns)) return null;
        return (
          <Sequence
            key={`xf-${who}-${i}-${e.file}-${e.from}`}
            from={e.from}
            durationInFrames={dissolveFrames}
            layout="none"
          >
            <Dissolve
              src={staticFile(`${mediaDir}/${prev.still}`)}
              box={box}
              inner={inner}
              dissolveFrames={dissolveFrames}
            />
          </Sequence>
        );
      })}
    </>
  );
};

const punctuated = (text: string) =>
  text.replace(/\[[^\]]*\]/g, (match) => match.slice(1, -1)).replace(/[.,!?;:]/g, "");

const captionWords = (cap: CaptionData) => {
  if (!cap.sourceText) return cap.words;
  const source = punctuated(cap.sourceText).trim().split(/\s+/);
  let offset = 0;
  return cap.words.map((word) => {
    if (!word.t) return word;
    const match = source
      .slice(offset)
      .findIndex((token) => token.toLocaleLowerCase("vi") === word.t.toLocaleLowerCase("vi"));
    if (match < 0) return word;
    offset += match + 1;
    return { ...word, t: source[offset - 1] };
  });
};

const ChiaSeNotes: React.FC<{ marks: Record<string, number>; rows: string[] }> = ({ marks, rows }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const visible = rows
    .map((label, index) => ({ label, index, at: marks[String(index + 1)] }))
    .filter((x) => x.at !== undefined && frame >= x.at);
  if (!visible.length) return null;
  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        top: 610,
        width: 600,
        maxWidth: 600,
        transform: "translateX(-50%)",
        boxSizing: "border-box",
        padding: 0,
        fontFamily: antonFont,
        background: "transparent",
        zIndex: 5,
      }}
    >
      {visible.map(({ label, index, at }) => {
        const p = spring({ frame: frame - at!, fps, config: { damping: 16, stiffness: 180 } });
        return (
          <div
            key={index}
            style={{
              height: 50,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "0 2px",
              color: "#000",
              fontSize: 38,
              letterSpacing: 0,
              whiteSpace: "nowrap",
              textAlign: "center",
              lineHeight: "50px",
              textTransform: "uppercase",
              WebkitTextStroke: "2px #fff",
              paintOrder: "stroke fill",
              transform: `translateY(${interpolate(p, [0, 1], [8, 0])}px)`,
              opacity: p,
            }}
          >
            {label}
          </div>
        );
      })}
    </div>
  );
};

const ChiaSeCaption: React.FC<{ cap: CaptionData }> = ({ cap }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({
    frame: frame - cap.from,
    fps,
    config: { damping: 13, stiffness: 200 },
    durationInFrames: 9,
  });
  const words = captionWords(cap);
  let split = words.length;
  if (words.length > 8) {
    const candidates = Array.from({ length: words.length - 1 }, (_, i) => i + 1).filter(
      (i) => !(words[i - 1]?.red && words[i]?.red)
    );
    if (candidates.length) {
      split = candidates.sort(
        (a, b) => Math.abs(words.length - 2 * a) - Math.abs(words.length - 2 * b) || a - b
      )[0];
    }
  }
  const lines = split < words.length ? [words.slice(0, split), words.slice(split)] : [words];
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 66, zIndex: 6 }}>
      <div
        style={{
          fontFamily: antonFont,
          fontWeight: 700,
          fontSize: 36,
          lineHeight: 1.35,
          textAlign: "center",
          width: 900,
          maxWidth: 900,
          padding: "0 8px",
          letterSpacing: 0,
          transform: `scale(${interpolate(pop, [0, 1], [0.92, 1])})`,
          opacity: Math.min(1, pop * 2),
        }}
      >
        {lines.map((line, li) => (
          <div key={li} style={{ whiteSpace: "nowrap" }}>
            {line.map((w, i) => (
              <React.Fragment key={`${li}-${i}-${w.t}`}>
                {i > 0 ? " " : null}
                <span
                  style={{
                    color: w.red ? "#ff2b2b" : "#fff",
                    WebkitTextStroke: "2px #000",
                    paintOrder: "stroke fill",
                  }}
                >
                  {w.t}
                </span>
              </React.Fragment>
            ))}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

const GioDoItemCard: React.FC<{
  item: ProductItem;
  at: number;
  mediaDir: string;
  maskPrice: boolean;
}> = ({ item, at, mediaDir, maskPrice }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({
    frame: f - at,
    fps,
    config: { damping: 14, stiffness: 180 },
    durationInFrames: 9,
  });
  const baseName = (item.display_name || item.ten || "").trim();
  const qtyText = item.sl ? `${item.sl} ${item.dv || ""}`.trim() : "";
  const fullLabel = (item.name_and_qty || `${baseName} ${qtyText}`).toLocaleUpperCase("vi");
  const priceStr = formatVNPrice(item.gia, maskPrice, item.gia_text);
  const hasImg = Boolean(item.image_file);
  const cfg = (activeData.config || {}) as Record<string, any>;
  const hidePrice = Boolean(cfg.preset === "anh_nhac" || item.no_price);
  const hasPeopleVideo = Boolean(
    (activeData.timeline?.visualTracks?.A?.length || 0) +
      (activeData.timeline?.visualTracks?.B?.length || 0)
  );
  const baseProdImgSize = Number(cfg.productImageSize || (hidePrice ? 450 : 400));
  const itemScale = Number(item.image_scale || 1.0);
  const prodImgSize = Math.round(baseProdImgSize * (isNaN(itemScale) || itemScale <= 0 ? 1.0 : itemScale));
  const prodNameFontSize = Number(cfg.productNameFontSize || (hidePrice ? 60 : 50));
  const prodPriceFontSize = Number(cfg.productPriceFontSize || 105);
  const leftCenterX = Number(cfg.productLeftCenterX || 270);
  const rightCenterX = Number(cfg.productRightCenterX || 810);
  const cardTop = Number(cfg.productCardTop || (hidePrice && !hasPeopleVideo ? 215 : 610));

  if (hidePrice && !hasPeopleVideo) {
    const bullets = Array.isArray(item.bullets) ? item.bullets.filter(Boolean) : [];
    const hasBullets = bullets.length > 0;
    const isSingleBullet = bullets.length === 1;
    const bgTheme = String(cfg.bgTheme || "beige").toLowerCase();
    const isLightBg = Boolean(
      cfg.backgroundColor || bgTheme === "beige" || bgTheme === "light" || bgTheme !== "dark"
    );
    const heroImgPx = Math.round(
      bullets.length >= 2
        ? Math.min(720, Math.max(520, prodImgSize * 1.35))
        : Math.min(880, Math.max(560, prodImgSize * 1.48))
    );
    const heroBoxH = Math.round(heroImgPx * 0.72);
    const effTop = Number(cfg.productCardTop || (bullets.length >= 2 ? 172 : hasBullets ? 176 : 185));
    return (
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: effTop,
          bottom: 24,
          opacity: p,
          transform: `translateY(${interpolate(p, [0, 1], [14, 0])}px) scale(${interpolate(
            p,
            [0, 1],
            [0.95, 1]
          )})`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 4,
        }}
      >
        {hasImg ? (
          <div
            style={{
              width: heroImgPx,
              height: heroBoxH,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <Img
              src={staticFile(`${mediaDir}/products/${item.image_file}`)}
              style={{
                width: heroImgPx,
                height: heroImgPx,
                maxWidth: "none",
                maxHeight: "none",
                objectFit: "contain",
                filter: isLightBg
                  ? "drop-shadow(0 16px 30px rgba(90,65,45,.26))"
                  : "drop-shadow(0 14px 28px rgba(0,0,0,.48))",
              }}
            />
          </div>
        ) : null}
        <div
          style={{
            marginTop: bullets.length >= 2 ? 18 : 28,
            maxWidth: 960,
            padding: "2px 24px",
            textAlign: "center",
            fontFamily: barlowFont,
            color: isLightBg ? "#C91C32" : "#FFD54F",
            fontSize: bullets.length >= 2 ? Math.min(62, Math.max(prodNameFontSize, 56)) : Math.max(prodNameFontSize, 66),
            lineHeight: 1.06,
            fontWeight: 700,
            WebkitTextStroke: isLightBg ? "4px #fff" : "4px #000",
            paintOrder: "stroke fill",
            textShadow: isLightBg ? "0 4px 12px rgba(0,0,0,.18)" : "0 6px 16px rgba(0,0,0,.85)",
          }}
        >
          {`${item.i}. ${fullLabel}`}
        </div>
        {hasBullets ? (
          isSingleBullet ? (
            <div
              style={{
                marginTop: 18,
                width: "fit-content",
                maxWidth: 960,
                background: isLightBg ? "rgba(255, 252, 245, 0.96)" : "rgba(15, 23, 42, 0.78)",
                border: isLightBg ? "2.5px solid #decbb1" : "2px solid rgba(255, 255, 255, 0.22)",
                borderRadius: 999,
                padding: "12px 38px",
                boxShadow: isLightBg ? "0 8px 22px rgba(110, 82, 55, 0.15)" : "0 12px 30px rgba(0,0,0,0.45)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <div
                style={{
                  fontFamily: barlowFont,
                  fontSize: 33,
                  lineHeight: 1.22,
                  color: isLightBg ? "#3b281e" : "#f8fafc",
                  WebkitTextStroke: isLightBg ? "0px transparent" : "1.5px #000",
                  paintOrder: "stroke fill",
                  textAlign: "center",
                }}
              >
                {`📍 ${bullets[0]}`}
              </div>
            </div>
          ) : (
            <div
              style={{
                marginTop: 10,
                width: "fit-content",
                minWidth: 720,
                maxWidth: 940,
                background: isLightBg ? "rgba(255, 252, 245, 0.95)" : "rgba(15, 23, 42, 0.74)",
                border: isLightBg ? "2.5px solid #decbb1" : "2px solid rgba(255, 255, 255, 0.22)",
                borderRadius: 24,
                padding: "14px 32px",
                boxShadow: isLightBg ? "0 8px 24px rgba(110, 82, 55, 0.16)" : "0 12px 30px rgba(0,0,0,0.45)",
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-start",
                gap: 6,
              }}
            >
              {bullets.map((b, bi) => (
                <div
                  key={bi}
                  style={{
                    fontFamily: barlowFont,
                    fontSize: bullets.length >= 3 ? 29 : 32,
                    lineHeight: 1.25,
                    color: isLightBg ? "#3b281e" : "#f8fafc",
                    WebkitTextStroke: isLightBg ? "0px transparent" : "1.5px #000",
                    paintOrder: "stroke fill",
                    textAlign: "left",
                  }}
                >
                  {`• ${b}`}
                </div>
              ))}
            </div>
          )
        ) : null}
      </div>
    );
  }

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: cardTop,
        bottom: 35,
        opacity: p,
        transform: `translateY(${interpolate(p, [0, 1], [10, 0])}px) scale(${interpolate(
          p,
          [0, 1],
          [0.96, 1]
        )})`,
        zIndex: 4,
      }}
    >
      {hasImg ? (
        <div
          style={{
            position: "absolute",
            left: leftCenterX - prodImgSize / 2,
            top: "50%",
            width: prodImgSize,
            height: prodImgSize,
            transform: "translateY(-50%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Img
            src={staticFile(`${mediaDir}/products/${item.image_file}`)}
            style={{
              width: prodImgSize,
              height: prodImgSize,
              objectFit: "contain",
              filter: "drop-shadow(0 5px 8px rgba(0,0,0,.30))",
            }}
          />
        </div>
      ) : null}
      <div
        style={{
          position: "absolute",
          left: hasImg ? rightCenterX - 260 : 130,
          top: "50%",
          width: hasImg ? 520 : 820,
          transform: "translateY(-50%)",
          textAlign: "center",
          fontFamily: barlowFont,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 14,
        }}
      >
        <div
          style={{
            maxWidth: "100%",
            color: hidePrice ? "#E5121F" : "#111",
            fontSize: prodNameFontSize,
            lineHeight: 1.08,
            fontWeight: 700,
            WebkitTextStroke: hidePrice ? "4px #fff" : "3.5px #fff",
            paintOrder: "stroke fill",
            textShadow: "0 2px 5px rgba(255,255,255,.85)",
          }}
        >
          {fullLabel}
        </div>
        {!hidePrice ? (
          <div
            style={{
              color: "#E5121F",
              fontSize: prodPriceFontSize,
              lineHeight: 1,
              fontWeight: 700,
              WebkitTextStroke: "4px #fff",
              paintOrder: "stroke fill",
              textShadow: "0 2px 4px rgba(255,255,255,.8)",
            }}
          >
            {priceStr}
          </div>
        ) : null}
      </div>
    </div>
  );
};

const GioDoBatch5Table: React.FC<{
  items: ProductItem[];
  marks: [string, number][];
  maskPrice: boolean;
}> = ({ items, marks, maskPrice }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const activeMarks = marks.filter(([, at]) => f >= at);
  if (!activeMarks.length) return null;
  const latestIdx = Number(activeMarks[activeMarks.length - 1][0]) - 1;
  const pageStart = Math.floor(latestIdx / 5) * 5;
  const pageItems = items.slice(pageStart, pageStart + 5);

  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        top: 610,
        width: 780,
        transform: "translateX(-50%)",
        fontFamily: barlowFont,
        zIndex: 4,
      }}
    >
      {pageItems.map((it) => {
        const at = activeData.timeline.itemMarks[String(it.i)];
        if (at === undefined || f < at) return null;
        const p = spring({ frame: f - at, fps, config: { damping: 16, stiffness: 180 } });
        const baseName = (it.display_name || it.ten || "").trim();
        const qtyText = it.sl ? `${it.sl} ${it.dv || ""}`.trim() : "";
        const label = (it.name_and_qty || `${baseName} ${qtyText}`).toLocaleUpperCase("vi");
        return (
          <div
            key={it.i}
            style={{
              height: 52,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 14,
              fontSize: 38,
              fontWeight: 700,
              color: "#000",
              WebkitTextStroke: "2.5px #fff",
              paintOrder: "stroke fill",
              opacity: p,
              transform: `translateY(${interpolate(p, [0, 1], [8, 0])}px)`,
            }}
          >
            <span>{label} – </span>
            <span style={{ color: "#E5121F" }}>{formatVNPrice(it.gia, maskPrice, it.gia_text)}</span>
          </div>
        );
      })}
    </div>
  );
};

const GioDoTotalCard: React.FC<{
  at: number;
  lastItem: ProductItem | undefined;
  totalPriceStr: string;
  mediaDir: string;
}> = ({ at, lastItem, totalPriceStr, mediaDir }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({
    frame: f - at,
    fps,
    config: { damping: 11, stiffness: 190 },
    durationInFrames: 12,
  });
  const cfg = (activeData.config || {}) as Record<string, any>;
  const baseProdImgSize = Number(cfg.productImageSize || 400);
  const lastScale = Number(lastItem?.image_scale || 1.0);
  const prodImgSize = Math.round(baseProdImgSize * (isNaN(lastScale) || lastScale <= 0 ? 1.0 : lastScale));
  const leftCenterX = Number(cfg.productLeftCenterX || 270);
  const rightCenterX = Number(cfg.productRightCenterX || 810);
  const cardTop = Number(cfg.productCardTop || 610);
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: cardTop,
        bottom: 35,
        zIndex: 5,
      }}
    >
      {lastItem?.image_file ? (
        <div
          style={{
            position: "absolute",
            left: leftCenterX - prodImgSize / 2,
            top: "50%",
            width: prodImgSize,
            height: prodImgSize,
            transform: "translateY(-50%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Img
            src={staticFile(`${mediaDir}/products/${lastItem.image_file}`)}
            style={{
              width: prodImgSize,
              height: prodImgSize,
              objectFit: "contain",
              filter: "drop-shadow(0 5px 8px rgba(0,0,0,.30))",
            }}
          />
        </div>
      ) : null}
      <div
        style={{
          position: "absolute",
          left: rightCenterX - 260,
          top: "50%",
          width: 520,
          textAlign: "center",
          fontFamily: barlowFont,
          color: "#E5121F",
          fontSize: 84,
          lineHeight: 1,
          fontWeight: 700,
          WebkitTextStroke: "4px #fff",
          paintOrder: "stroke fill",
          textShadow: "0 2px 4px rgba(255,255,255,.8)",
          opacity: p,
          transform: `translateY(-50%) scale(${interpolate(p, [0, 1], [0.86, 1])})`,
        }}
      >
        TỔNG {totalPriceStr}
      </div>
    </div>
  );
};

const GioDoSummaryRow: React.FC<{
  item: ProductItem;
  index: number;
  rowsPerCol: number;
  singleCol?: boolean;
  mediaDir: string;
  maskPrice: boolean;
}> = ({ item, index, rowsPerCol, singleCol, mediaDir, maskPrice }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = index * 4;
  const p = spring({
    frame: f - at,
    fps,
    config: { damping: 14, stiffness: 210 },
    durationInFrames: 10,
  });
  const col = singleCol ? 0 : index < rowsPerCol ? 0 : 1;
  const row = singleCol ? index : index % rowsPerCol;
  const baseName = (item.display_name || item.ten || "").trim();
  const qtyText = item.sl ? `${item.sl} ${item.dv || ""}`.trim() : "";
  const name = (item.name_and_qty || `${baseName} ${qtyText}`).toLocaleUpperCase("vi");
  const hidePrice = Boolean((activeData.config as any)?.preset === "anh_nhac" || item.no_price);
  const bullets = Array.isArray(item.bullets) ? item.bullets.filter(Boolean) : [];

  if (singleCol) {
    const rowHeight = rowsPerCol <= 3 ? 190 : Math.floor(600 / rowsPerCol);
    const rowStride = rowsPerCol <= 3 ? 202 : Math.floor(625 / rowsPerCol);
    const thumbW = rowsPerCol <= 3 ? 185 : 140;
    const thumbH = rowsPerCol <= 3 ? 156 : 118;
    return (
      <div
        style={{
          position: "absolute",
          left: 72,
          top: 172 + row * rowStride,
          width: 936,
          height: rowHeight,
          display: "flex",
          alignItems: "center",
          gap: 20,
          padding: "8px 14px",
          boxSizing: "border-box",
          borderBottom: "1.5px solid #f1dfe4",
          opacity: p,
          transform: `translateY(${interpolate(p, [0, 1], [8, 0])}px) scale(${interpolate(
            p,
            [0, 1],
            [0.97, 1]
          )})`,
        }}
      >
        {item.image_file ? (
          <Img
            src={staticFile(`${mediaDir}/products/${item.image_file}`)}
            style={{
              width: thumbW,
              height: thumbH,
              objectFit: "contain",
              flexShrink: 0,
              filter: "drop-shadow(0 4px 8px rgba(76,48,50,.20))",
            }}
          />
        ) : (
          <div style={{ width: thumbW, height: thumbH, flexShrink: 0 }} />
        )}
        <div
          style={{
            flex: 1,
            minWidth: 0,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: 5,
            textAlign: "left",
          }}
        >
          <div
            style={{
              color: "#c92a42",
              fontFamily: barlowFont,
              fontSize: 34,
              lineHeight: 1.1,
              fontWeight: 800,
            }}
          >
            {`${item.i}. ${name}`}
          </div>
          {bullets.map((b, bi) => (
            <div
              key={bi}
              style={{
                color: "#383238",
                fontFamily: barlowFont,
                fontSize: 22,
                lineHeight: 1.24,
                fontWeight: 700,
              }}
            >
              {`• ${b}`}
            </div>
          ))}
        </div>
      </div>
    );
  }

  const rowHeight = rowsPerCol <= 5 ? 105 : rowsPerCol <= 7 ? 80 : Math.floor(560 / rowsPerCol);
  const rowStride = rowsPerCol <= 5 ? 118 : rowsPerCol <= 7 ? 90 : Math.floor(630 / rowsPerCol);
  const thumbW = hidePrice ? (rowsPerCol <= 5 ? 110 : 82) : 60;
  const thumbH = hidePrice ? (rowsPerCol <= 5 ? 92 : 70) : 68;

  return (
    <div
      style={{
        position: "absolute",
        left: col === 0 ? 72 : 548,
        top: 174 + row * rowStride,
        width: 460,
        height: rowHeight,
        display: "flex",
        alignItems: "center",
        gap: hidePrice ? 20 : 8,
        padding: "0 8px",
        boxSizing: "border-box",
        borderBottom: "1px solid #f1dfe4",
        opacity: p,
        transform: `translateY(${interpolate(p, [0, 1], [8, 0])}px) scale(${interpolate(
          p,
          [0, 1],
          [0.97, 1]
        )})`,
      }}
    >
      {item.image_file ? (
        <Img
          src={staticFile(`${mediaDir}/products/${item.image_file}`)}
          style={{
            width: thumbW,
            height: thumbH,
            objectFit: "contain",
            flexShrink: 0,
            filter: "drop-shadow(0 2px 3px rgba(76,48,50,.16))",
          }}
        />
      ) : (
        <div style={{ width: thumbW, height: thumbH, flexShrink: 0 }} />
      )}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 6,
          overflow: "hidden",
          textAlign: "left",
        }}
      >
        <div
          style={{
            color: "#383238",
            fontFamily: barlowFont,
            fontSize: hidePrice ? (rowsPerCol <= 5 ? (bullets.length ? 25 : 27) : 23) : 21,
            lineHeight: 1.12,
            fontWeight: 700,
          }}
        >
          {hidePrice ? `${item.i}. ${name}` : name}
        </div>
        {hidePrice && bullets.length > 0 ? (
          <div
            style={{
              color: "#6b584c",
              fontFamily: barlowFont,
              fontSize: 16.5,
              lineHeight: 1.15,
              fontWeight: 600,
              whiteSpace: "normal",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {bullets[0]}
          </div>
        ) : null}
      </div>
      {!hidePrice ? (
        <div
          style={{
            minWidth: 75,
            flexShrink: 0,
            textAlign: "right",
            color: "#d92f48",
            fontFamily: barlowFont,
            fontSize: formatVNPrice(item.gia, maskPrice, item.gia_text).length >= 7 ? 26 : 31,
            lineHeight: 1,
            fontWeight: 800,
            whiteSpace: "nowrap",
          }}
        >
          {formatVNPrice(item.gia, maskPrice, item.gia_text)}
        </div>
      ) : null}
    </div>
  );
};

const GioDoSummary: React.FC<{
  title: string;
  items: ProductItem[];
  totalPriceStr: string;
  summaryNote: string;
  summarySubtitle: string;
  mediaDir: string;
  maskPrice: boolean;
}> = ({ title, items, totalPriceStr, summaryNote, summarySubtitle, mediaDir, maskPrice }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fade = interpolate(f, [0, 3], [0, 1], { extrapolateRight: "clamp" });
  const totalAt = 68;
  const totalPop = spring({
    frame: f - totalAt,
    fps,
    config: { damping: 12, stiffness: 180 },
    durationInFrames: 14,
  });
  const hasAnyBullets = items.some((it) => Array.isArray(it.bullets) && it.bullets.length > 0);
  const singleCol = hasAnyBullets && items.length <= 5;
  const rowsPerCol = singleCol ? Math.max(1, items.length) : Math.max(1, Math.ceil(items.length / 2));
  const isAnhNhac = (activeData.config as any)?.preset === "anh_nhac";
  const topSubtitle = String((activeData as any)?.subtitle || "").trim();
  const effNote = isAnhNhac && summaryNote === "(Săn Sell để được giá hời)"
    ? "(Lưu lại ngay để tham khảo khi cần nhé!)"
    : summaryNote;
  const cleanNote = effNote.trim().startsWith("(")
    ? effNote.trim()
    : `(${effNote.trim()})`;
  const effTotalText = (activeData.config as any)?.totalTextOverride
    || (isAnhNhac ? `TOP ${items.length} ${title}` : `TỔNG ${totalPriceStr}`);
  const effSubtitle = topSubtitle
    ? topSubtitle.toLocaleUpperCase("vi")
    : isAnhNhac && (!summarySubtitle || summarySubtitle === "ĐỦ CHO MẸ & BÉ ĐI SINH")
    ? "DANH SÁCH TỔNG HỢP CHI TIẾT"
    : (summarySubtitle || "ĐỦ CHO MẸ & BÉ ĐI SINH");

  return (
    <AbsoluteFill
      style={{
        opacity: fade,
        zIndex: 6,
        background: "radial-gradient(ellipse at 50% 42%, #fffaf5 0%, #f9e9e9 56%, #f2dfe3 100%)",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 38,
          top: 42,
          width: 1004,
          height: 996,
          borderRadius: 42,
          background: "linear-gradient(145deg,#ffffff 0%,#fffefd 70%,#fff8f4 100%)",
          boxShadow: "0 20px 70px rgba(98,54,67,.22), 0 3px 12px rgba(100,60,65,.10)",
          overflow: "hidden",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 74,
          left: 70,
          right: 70,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          color: "#4b3640",
          fontFamily: titleFontFamily,
          zIndex: 1,
        }}
      >
        <div
          style={{
            fontSize: 54,
            lineHeight: 1.08,
            fontWeight: 700,
            letterSpacing: 1,
            textAlign: "center",
            textTransform: "uppercase",
          }}
        >
          {title}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, width: 400, marginTop: 13 }}>
          <div style={{ height: 2, flex: 1, background: "linear-gradient(90deg,transparent,#dfadb5)" }} />
          <div
            style={{
              width: 9,
              height: 9,
              borderRadius: 9,
              background: "#d99ca8",
              boxShadow: "0 0 0 4px #f9edf0",
            }}
          />
          <div style={{ height: 2, flex: 1, background: "linear-gradient(90deg,#dfadb5,transparent)" }} />
        </div>
      </div>
      {items.map((item, index) => (
        <GioDoSummaryRow
          key={item.i}
          item={item}
          index={index}
          rowsPerCol={rowsPerCol}
          singleCol={singleCol}
          mediaDir={mediaDir}
          maskPrice={maskPrice}
        />
      ))}
      {effNote ? (
        <div
          style={{
            position: "absolute",
            left: 170,
            top: 797,
            width: 740,
            height: 36,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: barlowFont,
            fontSize: 27,
            lineHeight: 1,
            fontWeight: 700,
            color: "#c93652",
            letterSpacing: 0.3,
            zIndex: 2,
          }}
        >
          {cleanNote}
        </div>
      ) : null}
      <div
        style={{
          position: "absolute",
          left: 200,
          top: 849,
          width: 680,
          height: 106,
          borderRadius: 54,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
          background: "linear-gradient(105deg,#d84c61 0%,#bb2949 50%,#e87579 100%)",
          boxShadow: "0 10px 22px rgba(185,48,72,.25), inset 0 2px 0 rgba(255,255,255,.30)",
          color: "#fff8e8",
          fontFamily: barlowFont,
          opacity: totalPop,
          transform: `scale(${interpolate(totalPop, [0, 1], [0.82, 1])})`,
          zIndex: 2,
        }}
      >
        <div style={{ fontSize: effTotalText.length > 22 ? 34 : 42, lineHeight: 1, fontWeight: 700, letterSpacing: 1, padding: "0 18px", textAlign: "center" }}>
          {effTotalText}
        </div>
        <div style={{ fontSize: 19, lineHeight: 1.2, marginTop: 6, letterSpacing: 1 }}>
          {effSubtitle}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const ConvoAppDynamic: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const timeline = activeData.timeline as unknown as TimelineData;
  const cfg = activeData.config;
  const mediaDir = activeData.mediaDir;
  const preset = cfg.preset || "giodo";
  const titlePop = spring({ frame, fps, config: { damping: 15, stiffness: 140 } });

  const sfx = (file: string, at: number, key: string, volume = 0.25) =>
    at >= durationInFrames || at < 0 ? null : (
      <Sequence
        key={key}
        from={at}
        durationInFrames={Math.min(180, durationInFrames - at)}
        layout="none"
      >
        <Audio src={staticFile(`${mediaDir}/sfx/${file}`)} volume={volume} />
      </Sequence>
    );

  const marks = Object.entries(timeline.itemMarks || {}).sort((a, b) => a[1] - b[1]);
  const titleFont = titleFontFamily;
  const titleSize = cfg.titleFontSize || 75;
  const titleTop = cfg.titleTop ?? 110;

  // Render order: left side track first, right side track second (with feather mask)
  const askerOnRight = cfg.askerSide !== "left";
  const leftWho: "A" | "B" = askerOnRight ? "B" : "A";
  const rightWho: "A" | "B" = askerOnRight ? "A" : "B";

  if (preset === "chiase") {
    const cap = (timeline.pieces || []).find((c) => frame >= c.from && frame < c.to);
    const noteRows: string[] = activeData.chiaSeItems || [];
    return (
      <AbsoluteFill style={{ backgroundColor: "#e9e9e9" }}>
        <Track
          who={leftWho}
          entries={timeline.visualTracks[leftWho] || []}
          mediaDir={mediaDir}
          turns={timeline.turns || []}
          cfg={cfg}
        />
        <Track
          who={rightWho}
          entries={timeline.visualTracks[rightWho] || []}
          mediaDir={mediaDir}
          turns={timeline.turns || []}
          cfg={cfg}
        />
        <div
          style={{
            position: "absolute",
            top: titleTop,
            width: "100%",
            display: "flex",
            justifyContent: "center",
            zIndex: 9,
          }}
        >
          <div
            style={{
              maxWidth: 1000,
              color: "#fff",
              fontFamily: titleFont,
              fontWeight: 700,
              fontSize: titleSize,
              lineHeight: 1.05,
              textAlign: "center",
              textTransform: "uppercase",
              WebkitTextStroke: "5px #000",
              paintOrder: "stroke fill",
              textShadow: "0 5px 14px rgba(0,0,0,.9)",
              transform: `scale(${interpolate(titlePop, [0, 1], [0.94, 1])})`,
            }}
          >
            {activeData.title}
          </div>
        </div>
        <ChiaSeNotes marks={timeline.itemMarks || {}} rows={noteRows} />
        {cap ? <ChiaSeCaption key={cap.from} cap={cap} /> : null}
        {sfx("04_whoosh.wav", 0, "title-whoosh", 0.55)}
        {marks.map(([item, at], index) => (
          <React.Fragment key={item}>
            {sfx("02_soft_pop.wav", at, `pop-${item}`, 0.55)}
            {index === marks.length - 1 ? sfx("05_sparkle.wav", at, "sparkle", 0.55) : null}
          </React.Fragment>
        ))}
        {(timeline.redTickFrames || []).map((at, i) => sfx("07_tick.wav", at, `tick-${i}`, 0.55))}
        <Audio src={staticFile(`${mediaDir}/voice.wav`)} />
      </AbsoluteFill>
    );
  }

  // Preset B: "giodo" or Preset C: "anh_nhac"
  const isAnhNhac = preset === "anh_nhac";
  const hasPeopleVideo = Boolean(
    (timeline.visualTracks?.[leftWho]?.length || 0) +
      (timeline.visualTracks?.[rightWho]?.length || 0)
  );
  const products: ProductItem[] = activeData.products || [];
  const summaryStart = timeline.frames - 4;
  const lastMarkFrame = marks.length ? marks[marks.length - 1][1] : timeline.frames - 94;
  const totalAt = isAnhNhac ? summaryStart : Math.min(timeline.frames - 45, lastMarkFrame + 49);
  const current = marks.filter(([, at]) => frame >= at).at(-1);
  const currentItem =
    current && frame < totalAt ? products[Number(current[0]) - 1] || null : null;
  const maskPrice = cfg.maskPrice ?? true;
  const rawTotal =
    activeData.totalPrice ||
    products.reduce((acc, it) => acc + (Number(it.gia) || 0), 0);
  const totalPriceStr = formatVNPrice(rawTotal, maskPrice);
  const summarySounds = products.map((_, i) =>
    sfx("02_soft_pop.wav", summaryStart + i * 4, `summary-pop-${i}`, 0.12)
  );

  const customBg = String((cfg as any).backgroundColor || "").trim();
  const isBeigeTheme = (cfg as any).bgTheme !== "dark";
  const mainBg = customBg
    ? customBg
    : hasPeopleVideo
    ? "#e9e9e9"
    : isBeigeTheme
    ? "radial-gradient(circle at 50% 35%, #fffdf9 0%, #f5ebe0 58%, #e6d5c3 100%)"
    : "radial-gradient(circle at 50% 32%, #2e1d3a 0%, #161329 58%, #090a12 100%)";

  return (
    <AbsoluteFill
      style={{
        background: mainBg,
      }}
    >
      <Track
        who={leftWho}
        entries={timeline.visualTracks[leftWho] || []}
        mediaDir={mediaDir}
        turns={timeline.turns || []}
        cfg={cfg}
      />
      <Track
        who={rightWho}
        entries={timeline.visualTracks[rightWho] || []}
        mediaDir={mediaDir}
        turns={timeline.turns || []}
        cfg={cfg}
      />
      {frame < summaryStart ? (
        <div
          style={{
            position: "absolute",
            top: (activeData as any).subtitle ? Math.max(58, titleTop - 28) : titleTop,
            width: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9,
          }}
        >
          <div
            style={{
              maxWidth: 1000,
              color: isBeigeTheme ? "#4a2c1d" : "#fff",
              fontFamily: titleFontFamily,
              fontWeight: 700,
              fontSize: titleSize,
              lineHeight: 1.05,
              textAlign: "center",
              textTransform: "uppercase",
              WebkitTextStroke: isBeigeTheme ? "5px #fff" : "5px #000",
              paintOrder: "stroke fill",
              textShadow: isBeigeTheme ? "0 5px 14px rgba(90,60,40,.28)" : "0 5px 14px rgba(0,0,0,.9)",
              transform: `scale(${interpolate(titlePop, [0, 1], [0.94, 1])})`,
            }}
          >
            {activeData.title}
          </div>
          {(activeData as any).subtitle ? (
            <div
              style={{
                marginTop: 8,
                padding: "4px 24px",
                borderRadius: 30,
                background: isBeigeTheme ? "rgba(74, 44, 29, 0.10)" : "rgba(0,0,0,0.45)",
                border: isBeigeTheme ? "1.5px solid rgba(74, 44, 29, 0.22)" : "none",
                color: isBeigeTheme ? "#5c3724" : "#fde68a",
                fontFamily: barlowFont,
                fontSize: 30,
                fontWeight: 700,
                letterSpacing: 0.6,
                textTransform: "uppercase",
                WebkitTextStroke: isBeigeTheme ? "0px transparent" : "1.5px #000",
                paintOrder: "stroke fill",
              }}
            >
              {(activeData as any).subtitle}
            </div>
          ) : null}
        </div>
      ) : null}

      {cfg.productDisplayMode === "batch5" && frame < totalAt ? (
        <GioDoBatch5Table items={products} marks={marks} maskPrice={maskPrice} />
      ) : currentItem ? (
        <GioDoItemCard
          key={currentItem.i}
          item={currentItem}
          at={current?.[1] ?? 0}
          mediaDir={mediaDir}
          maskPrice={maskPrice}
        />
      ) : null}

      {!isAnhNhac && frame >= totalAt && frame < timeline.frames ? (
        <GioDoTotalCard
          at={totalAt}
          lastItem={products[products.length - 1]}
          totalPriceStr={totalPriceStr}
          mediaDir={mediaDir}
        />
      ) : null}

      {frame >= summaryStart ? (
        <Sequence from={summaryStart} durationInFrames={durationInFrames - summaryStart} layout="none">
          <GioDoSummary
            title={activeData.title}
            items={products}
            totalPriceStr={totalPriceStr}
            summaryNote={cfg.summaryNote ?? "(Săn Sell để được giá hời)"}
            summarySubtitle={cfg.summarySubtitle ?? "ĐỦ CHO MẸ & BÉ ĐI SINH"}
            mediaDir={mediaDir}
            maskPrice={maskPrice}
          />
        </Sequence>
      ) : null}

      {sfx("04_whoosh.wav", 0, "title-whoosh", 0.2)}
      {marks.map(([n, at]) => sfx("02_soft_pop.wav", at, `pop-${n}`, 0.2))}
      {frame < summaryStart ? sfx("05_sparkle.wav", totalAt, "total-sparkle", 0.2) : null}
      {summarySounds}
      {sfx("05_sparkle.wav", summaryStart + 68, "summary-sparkle", 0.16)}
      <Audio src={staticFile(`${mediaDir}/voice.wav`)} />
    </AbsoluteFill>
  );
};
