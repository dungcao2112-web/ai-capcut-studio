import type {
  AspectMode,
  CaptionCue,
  CaptionWord,
  ShotKind,
  TimelineProject,
  TimelineShot,
} from '../types/timeline';
import { ASPECT_PRESETS } from '../types/timeline';

export const round2 = (n: number) => Math.round(n * 100) / 100;
export const round3 = (n: number) => Math.round(n * 1000) / 1000;
export const clamp = (n: number, a: number, b: number) => Math.min(b, Math.max(a, n));

let idCounter = 0;
export const uid = (prefix = 'id') =>
  `${prefix}_${Date.now().toString(36)}${(idCounter++).toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;

/** 12.345 → "00:12.34" ; 75.5 → "01:15.50" */
export function formatTime(sec: number, withFrames = false, fps = 30): string {
  const s = Math.max(0, sec);
  const m = Math.floor(s / 60);
  const rest = s - m * 60;
  if (withFrames) {
    const whole = Math.floor(rest);
    const frame = Math.floor((rest - whole) * fps + 1e-6);
    return `${String(m).padStart(2, '0')}:${String(whole).padStart(2, '0')}:${String(frame).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}:${rest.toFixed(2).padStart(5, '0')}`;
}

export const snapToFrame = (t: number, fps: number) => Math.round(t * fps) / fps;

export const shotEnd = (s: TimelineShot) => s.start + s.duration;

export function sortShots(shots: TimelineShot[]): TimelineShot[] {
  return [...shots].sort((a, b) => a.start - b.start);
}

/** Gán lại nhãn S1..Sn theo thứ tự thời gian. */
export function relabelShots(shots: TimelineShot[]): TimelineShot[] {
  return sortShots(shots).map((s, i) => ({ ...s, label: `S${i + 1}` }));
}

export function findShotAt(project: TimelineProject, t: number): TimelineShot | undefined {
  return project.shots.find((s) => t >= s.start && t < shotEnd(s) - 1e-6);
}

export interface GapInfo {
  start: number;
  end: number;
  duration: number;
  afterShotId?: string;
}

export function findGaps(project: TimelineProject, minGap = 1 / 60): GapInfo[] {
  const shots = sortShots(project.shots);
  const gaps: GapInfo[] = [];
  let cursor = 0;
  let prev: TimelineShot | undefined;
  for (const s of shots) {
    if (s.start - cursor > minGap) {
      gaps.push({ start: round3(cursor), end: round3(s.start), duration: round3(s.start - cursor), afterShotId: prev?.id });
    }
    cursor = Math.max(cursor, shotEnd(s));
    prev = s;
  }
  const total = project.duration;
  if (total - cursor > minGap) {
    gaps.push({ start: round3(cursor), end: round3(total), duration: round3(total - cursor), afterShotId: prev?.id });
  }
  return gaps;
}

/** Tổng độ dài = max(shot cuối, phụ đề cuối, audio cuối). */
export function computeDuration(project: TimelineProject): number {
  const ends = [
    ...project.shots.map(shotEnd),
    ...project.captions.map((c) => c.end),
    ...project.audio.map((a) => a.end),
  ];
  return round2(Math.max(1, ...ends));
}

export function inferKindFromPath(path: string, fallback: ShotKind = 'muse'): ShotKind {
  const p = path.toLowerCase().replace(/\\/g, '/');
  if (p.includes('muse/') || p.startsWith('muse')) return 'muse';
  if (p.includes('_tam_clip_goc') || p.includes('goc/')) return 'goc';
  if (p.includes('xsec')) return 'xsec';
  if (p.includes('map/') || p.startsWith('map')) return 'map';
  if (p.includes('art/') || p.startsWith('art')) return 'art';
  if (p.includes('photo/') || /\.(jpe?g|png|webp)$/.test(p)) return 'photo';
  if (/\.(mp4|mov|mkv|webm)$/.test(p)) return fallback === 'goc' || fallback === 'muse' ? fallback : 'video';
  return fallback;
}

export const isStillKind = (k: ShotKind) => k === 'art' || k === 'map' || k === 'xsec' || k === 'photo';

/** Chia đều mốc từng từ trong 1 câu (dùng khi không có word-timing thật). */
export function splitWords(text: string, start: number, end: number): CaptionWord[] {
  const tokens = text.trim().split(/\s+/).filter(Boolean);
  if (!tokens.length) return [];
  const weights = tokens.map((t) => Math.max(1, t.length));
  const total = weights.reduce((a, b) => a + b, 0);
  const span = Math.max(0.05, end - start);
  let cursor = start;
  return tokens.map((tok, i) => {
    const d = (weights[i] / total) * span;
    const w = { text: tok, start: round3(cursor), end: round3(cursor + d) };
    cursor += d;
    return w;
  });
}

export function makeCue(id: string, text: string, start: number, end: number, withWords: boolean): CaptionCue {
  return { id, text, start, end, words: withWords ? splitWords(text, start, end) : undefined };
}

/** Chuyển đổi tỷ lệ khung hình, tự điều chỉnh cỡ chữ / vị trí phụ đề / watermark cho hợp. */
export function convertAspect(project: TimelineProject, mode: AspectMode): TimelineProject {
  if (project.mode === mode) return project;
  const preset = ASPECT_PRESETS[mode];
  const toWide = mode === '16:9';
  const cs = project.captionStyle;
  return {
    ...project,
    mode,
    width: preset.width,
    height: preset.height,
    captionStyle: {
      ...cs,
      fontSize: Math.round(toWide ? cs.fontSize * 0.82 : cs.fontSize / 0.82),
      bottom: Math.round(toWide ? cs.bottom * 0.42 : cs.bottom / 0.42),
      maxWidth: Math.round(toWide ? 1500 : 940),
    },
    watermark: {
      ...project.watermark,
      fontSize: Math.round(toWide ? project.watermark.fontSize * 0.85 : project.watermark.fontSize / 0.85),
    },
    cards: project.cards.map((c) => ({
      ...c,
      fontSize: Math.round(toWide ? c.fontSize * 0.85 : c.fontSize / 0.85),
    })),
  };
}

export function cloneProject(p: TimelineProject): TimelineProject {
  return typeof structuredClone === 'function' ? structuredClone(p) : JSON.parse(JSON.stringify(p));
}

export function bumpVersion(v: string): string {
  const m = /^v(\d+)$/i.exec(v.trim());
  return m ? `v${Number(m[1]) + 1}` : 'v2';
}

/** Hash chuỗi → số [0,1) ổn định, dùng cho sóng âm / mô phỏng. */
export function hash01(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 100000) / 100000;
}
