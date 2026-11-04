/**
 * Dữ liệu mẫu cho chế độ Cloud / Offline (không có Agy Local Server hoặc ổ G:\).
 *  1. Reel 9:16 Nấu Ăn — "Ba Chỉ Rim Nước Tương" (mô phỏng edit_v2.json)
 *  2. YouTube 16:9 K09 — "Bí Ẩn Địa Hình & Khu Dân Cư" (mô phỏng EPISODE.py + .srt)
 *
 * Cố ý cài sẵn lỗi để test lệnh AI:
 *  - Reel: S5 (muse/canh03_c.mp4) MAD 2.8 < 4 (cảnh tĩnh) + GAP 0.6s giữa S7 và S8.
 *  - YouTube: shot map/k09_delta.png nét thấp (Laplacian 0.62) + GAP 0.8s cuối chương 2.
 */
import type {
  CaptionCue,
  DemoVisual,
  MediaAsset,
  OverlayCard,
  PanDirection,
  ShotKind,
  TimelineProject,
  TimelineShot,
} from '../types/timeline';
import { makeCue, round3 } from '../lib/timelineUtils';

interface ShotSpec {
  src: string;
  kind: ShotKind;
  start: number;
  dur: number;
  visual: DemoVisual;
  mad: number;
  lap: number;
  zoom?: [number, number];
  pan?: PanDirection;
  fade?: number;
  speed?: number;
  note?: string;
  section?: string;
}

function buildShots(prefix: string, specs: ShotSpec[]): TimelineShot[] {
  return specs.map((s, i) => ({
    id: `${prefix}_s${String(i + 1).padStart(2, '0')}`,
    label: `S${i + 1}`,
    src: s.src,
    kind: s.kind,
    start: s.start,
    duration: s.dur,
    trimIn: 0,
    speed: s.speed ?? 1,
    zoom: s.zoom ? { enabled: true, from: s.zoom[0], to: s.zoom[1] } : { enabled: false, from: 1, to: 1 },
    panDirection: s.pan ?? 'none',
    fadeInFrames: s.fade ?? 0,
    qa: { madScore: s.mad, laplacianRatio: s.lap },
    note: s.note,
    sectionId: s.section,
    demoVisual: s.visual,
  }));
}

function buildCues(prefix: string, lines: [number, number, string][], karaoke: boolean): CaptionCue[] {
  return lines.map(([a, b, text], i) => makeCue(`${prefix}_c${String(i + 1).padStart(2, '0')}`, text, a, b, karaoke));
}

/* ========================================================================= */
/* 1. REEL 9:16 — BA CHỈ RIM NƯỚC TƯƠNG                                     */
/* ========================================================================= */

const reelShots = buildShots('reel', [
  { src: 'muse/canh01_a.mp4', kind: 'muse', start: 0.0, dur: 2.6, visual: 'food-hero', mad: 7.8, lap: 1.12, zoom: [1.0, 1.04], note: 'Hook: cận nồi ba chỉ bóng nước tương' },
  { src: '_tam_clip_goc/IMG_2041.MOV', kind: 'goc', start: 2.6, dur: 2.7, visual: 'food-boil', mad: 6.4, lap: 0.98, note: 'Chần thịt với gừng' },
  { src: '_tam_clip_goc/IMG_2043.MOV', kind: 'goc', start: 5.3, dur: 2.5, visual: 'food-chop', mad: 5.9, lap: 1.05, note: 'Cắt miếng vừa ăn' },
  { src: 'muse/canh02_b.mp4', kind: 'muse', start: 7.8, dur: 2.6, visual: 'food-chop', mad: 6.1, lap: 0.94, fade: 6, note: 'Muse: cận dao cắt thớ thịt' },
  { src: 'muse/canh03_c.mp4', kind: 'muse', start: 10.4, dur: 2.8, visual: 'food-marinate', mad: 2.8, lap: 0.71, note: 'Muse: tô ướp — CẢNH TĨNH (MAD < 4)' },
  { src: '_tam_clip_goc/IMG_2050.MOV', kind: 'goc', start: 13.2, dur: 2.6, visual: 'food-rest', mad: 5.2, lap: 1.01, note: 'Thịt nghỉ 20 phút' },
  { src: 'muse/canh04_a.mp4', kind: 'muse', start: 15.8, dur: 2.9, visual: 'food-sizzle', mad: 8.4, lap: 1.08, zoom: [1.0, 1.04], note: 'Muse: xém cạnh trên chảo' },
  // ── GAP 18.7 → 19.3 (0.6s) ──
  { src: '_tam_clip_goc/IMG_2057.MOV', kind: 'goc', start: 19.3, dur: 2.8, visual: 'food-sauce', mad: 6.6, lap: 0.97, note: 'Đổ nước ướp + nước dừa' },
  { src: 'muse/canh05_b.mp4', kind: 'muse', start: 22.1, dur: 3.0, visual: 'food-simmer', mad: 5.4, lap: 0.92, fade: 4, note: 'Muse: rim lửa nhỏ, nước sánh' },
  { src: 'muse/canh06_a.mp4', kind: 'muse', start: 25.1, dur: 2.5, visual: 'food-glaze', mad: 7.1, lap: 1.1, zoom: [1.0, 1.04], note: 'Muse: thịt bóng đẹp' },
  { src: '_tam_clip_goc/IMG_2063.MOV', kind: 'goc', start: 27.6, dur: 2.4, visual: 'food-plate', mad: 6.0, lap: 1.03, note: 'Bày đĩa' },
  { src: 'muse/canh07_hero.mp4', kind: 'muse', start: 30.0, dur: 2.0, visual: 'food-hero', mad: 6.8, lap: 1.15, zoom: [1.0, 1.04], fade: 6, note: 'CTA: hero shot cuối' },
]);

const reelCaptions = buildCues(
  'reel',
  [
    [0.3, 2.9, 'Ba chỉ rim nước tương làm kiểu này cả nhà tranh nhau ăn'],
    [3.0, 6.1, 'Thịt chần sơ qua nước sôi với vài lát gừng cho sạch mùi'],
    [6.2, 9.3, 'Cắt miếng vừa ăn dày khoảng hai đốt ngón tay'],
    [9.4, 12.6, 'Ướp nước tương chút đường tỏi băm và tiêu xay'],
    [12.7, 15.6, 'Để thịt nghỉ hai mươi phút cho ngấm đều'],
    [15.7, 18.8, 'Phi thơm hành tỏi rồi cho thịt vào xém cạnh'],
    [18.9, 22.0, 'Đổ nước ướp vào thêm nửa chén nước dừa tươi'],
    [22.1, 25.2, 'Rim lửa nhỏ hai lăm phút cho nước sánh lại'],
    [25.3, 28.4, 'Thịt mềm bóng đẹp vị mặn ngọt hài hòa'],
    [28.5, 31.6, 'Lưu lại công thức và nấu ngay tối nay nhé'],
  ],
  true,
);

const reelCards: OverlayCard[] = [
  { id: 'reel_k01', kind: 'label', text: 'BA CHỈ RIM NƯỚC TƯƠNG', subtext: 'Mềm – bóng – đậm vị', start: 0.2, end: 2.6, position: 'upper', color: '#FFFFFF', background: 'rgba(220,38,38,0.92)', fontSize: 66 },
  { id: 'reel_k02', kind: 'tip', text: 'Chần 3 phút + 3 lát gừng', start: 3.2, end: 5.2, position: 'top', color: '#111111', background: 'rgba(255,215,0,0.95)', fontSize: 52 },
  { id: 'reel_k03', kind: 'tip', text: 'Ướp tối thiểu 20 phút', start: 12.8, end: 15.4, position: 'top', color: '#111111', background: 'rgba(255,215,0,0.95)', fontSize: 52 },
  { id: 'reel_k04', kind: 'tip', text: 'Bí quyết: nước dừa tươi', start: 19.4, end: 21.9, position: 'top', color: '#FFFFFF', background: 'rgba(16,185,129,0.92)', fontSize: 54 },
  { id: 'reel_k05', kind: 'label', text: 'LƯU LẠI NẤU NGAY 👇', start: 29.0, end: 32.0, position: 'upper', color: '#FFFFFF', background: 'rgba(220,38,38,0.92)', fontSize: 62 },
];

const reelAssets: MediaAsset[] = [
  ...reelShots.map((s) => ({ id: `a_${s.id}`, path: s.src, type: 'video' as const, kind: s.kind, duration: 6, qa: s.qa, note: s.note, demoVisual: s.demoVisual })),
  { id: 'a_m04d', path: 'muse/canh04_d.mp4', type: 'video', kind: 'muse', duration: 5, qa: { madScore: 7.3, laplacianRatio: 1.06 }, note: 'Muse: tô ướp xoay tay, rưới nước tương (bản động)', demoVisual: 'food-marinate' },
  { id: 'a_m03e', path: 'muse/canh03_e.mp4', type: 'video', kind: 'muse', duration: 5, qa: { madScore: 6.2, laplacianRatio: 1.0 }, note: 'Muse: trộn thịt bằng đũa', demoVisual: 'food-marinate' },
  { id: 'a_m05c', path: 'muse/canh05_c.mp4', type: 'video', kind: 'muse', duration: 5, qa: { madScore: 6.9, laplacianRatio: 0.96 }, note: 'Muse: bong bóng nước rim', demoVisual: 'food-simmer' },
  { id: 'a_m08a', path: 'muse/canh08_a.mp4', type: 'video', kind: 'muse', duration: 5, qa: { madScore: 7.6, laplacianRatio: 1.09 }, note: 'Muse: gắp miếng thịt kéo sợi', demoVisual: 'food-glaze' },
  { id: 'a_g2059', path: '_tam_clip_goc/IMG_2059.MOV', type: 'video', kind: 'goc', duration: 8, qa: { madScore: 5.8, laplacianRatio: 0.99 }, note: 'Gốc: khuấy nồi', demoVisual: 'food-simmer' },
  { id: 'a_vo', path: 'vo.mp3', type: 'audio', kind: 'voice', duration: 31.8 },
  { id: 'a_mix', path: 'mix.wav', type: 'audio', kind: 'bgm', duration: 32 },
  { id: 'a_font', path: 'fonts/BeVietnamPro-ExtraBold.ttf', type: 'font' },
];

export const demoReelProject: TimelineProject = {
  id: 'demo-reel-ba-chi-rim',
  name: 'Ba Chỉ Rim Nước Tương (Reel Nấu Ăn)',
  mode: '9:16',
  width: 1080,
  height: 1920,
  fps: 30,
  duration: 32,
  sourceFormat: 'demo',
  rootDir: 'G:\\YouTube 2025\\NAO-Dũng - 2026-09-10\\TH\\FB AFF\\1. NẤU ĂN\\BA CHI RIM NUOC TUONG',
  sourceFile: 'edit_v2.json',
  version: 'v1',
  shots: reelShots,
  captions: reelCaptions,
  captionStyle: {
    mode: 'karaoke',
    fontFamily: 'Be Vietnam Pro',
    fontSize: 72,
    fontWeight: 900,
    color: '#FFFFFF',
    highlightColor: '#FFD700',
    strokeColor: '#000000',
    strokeWidth: 10,
    bottom: 360,
    maxWidth: 940,
    uppercase: true,
  },
  cards: reelCards,
  sections: [
    { id: 'reel_sec1', title: 'Hook', start: 0, end: 2.6, color: '#ef4444' },
    { id: 'reel_sec2', title: 'Sơ chế', start: 2.6, end: 10.4, color: '#f59e0b' },
    { id: 'reel_sec3', title: 'Ướp', start: 10.4, end: 15.8, color: '#a855f7' },
    { id: 'reel_sec4', title: 'Nấu & Rim', start: 15.8, end: 27.6, color: '#22d3ee' },
    { id: 'reel_sec5', title: 'Thành phẩm + CTA', start: 27.6, end: 32, color: '#10b981' },
  ],
  audio: [
    { id: 'reel_vo', kind: 'voice', label: 'Giọng đọc vo.mp3', src: 'vo.mp3', start: 0, end: 31.8, speechStart: 0.3, speechEnd: 31.6, volume: 1 },
    { id: 'reel_bgm', kind: 'bgm', label: 'Nhạc nền mix.wav', src: 'mix.wav', start: 0, end: 32, volume: 0.22 },
    { id: 'reel_sfx', kind: 'sfx', label: 'SFX xèo xèo', src: 'sfx/sizzle.wav', start: 15.9, end: 18.6, volume: 0.6 },
  ],
  watermark: { enabled: true, text: '@BepNhaDung', position: 'top-right', opacity: 0.72, fontSize: 40, margin: 56, color: '#FFFFFF' },
  grade: { name: 'Warm Food', brightness: 1.03, contrast: 1.06, saturation: 1.12, warmth: 0.25 },
  assets: reelAssets,
  updatedAt: '2026-11-03T21:00:00.000Z',
  isDemo: true,
};

/* ========================================================================= */
/* 2. YOUTUBE 16:9 — K09 BÍ ẨN ĐỊA HÌNH & KHU DÂN CƯ                         */
/* ========================================================================= */

const ytShots = buildShots('k09', [
  { src: 'art/k09_title.png', kind: 'art', start: 0, dur: 5.5, visual: 'geo-title', mad: 4.6, lap: 1.1, pan: 'in', zoom: [1.0, 1.08], section: 'k09_sec1', note: 'Intro: tiêu đề tập' },
  { src: 'map/k09_vietnam_relief.png', kind: 'map', start: 5.5, dur: 6.0, visual: 'geo-map', mad: 4.4, lap: 1.02, pan: 'right', zoom: [1.04, 1.1], fade: 12, section: 'k09_sec1', note: 'Bản đồ địa hình tổng quan' },
  { src: 'video/drone_tayBac.mp4', kind: 'video', start: 11.5, dur: 5.0, visual: 'geo-mountain', mad: 7.9, lap: 0.97, fade: 10, section: 'k09_sec1', note: 'Drone Tây Bắc' },
  { src: 'map/k09_terrain_contour.png', kind: 'map', start: 16.5, dur: 6.5, visual: 'geo-terrain', mad: 4.2, lap: 1.06, pan: 'left', zoom: [1.0, 1.06], fade: 12, section: 'k09_sec2', note: 'Đường đồng mức' },
  { src: 'xsec/k09_xsec_truongson.png', kind: 'xsec', start: 23.0, dur: 6.0, visual: 'geo-xsec', mad: 4.1, lap: 1.12, pan: 'right', zoom: [1.02, 1.06], fade: 10, section: 'k09_sec2', note: 'Lát cắt địa hình Trường Sơn' },
  { src: 'art/k09_terrace_art.png', kind: 'art', start: 29.0, dur: 5.2, visual: 'geo-village', mad: 4.3, lap: 0.95, pan: 'up', zoom: [1.0, 1.05], fade: 12, section: 'k09_sec2', note: 'Ruộng bậc thang' },
  // ── GAP 34.2 → 35.0 (0.8s) ──
  { src: 'video/river_mekong.mp4', kind: 'video', start: 35.0, dur: 5.5, visual: 'geo-river', mad: 6.8, lap: 0.99, fade: 8, section: 'k09_sec3', note: 'Sông Mê Kông' },
  { src: 'map/k09_delta.png', kind: 'map', start: 40.5, dur: 6.0, visual: 'geo-delta', mad: 4.0, lap: 0.62, pan: 'down', zoom: [1.0, 1.06], fade: 12, section: 'k09_sec3', note: 'Châu thổ — ẢNH MỜ (Laplacian thấp)' },
  { src: 'art/k09_village_stilt.png', kind: 'art', start: 46.5, dur: 5.5, visual: 'geo-village', mad: 4.5, lap: 1.04, pan: 'left', zoom: [1.02, 1.08], fade: 12, section: 'k09_sec3', note: 'Nhà sàn ven sông' },
  { src: 'xsec/k09_xsec_delta.png', kind: 'xsec', start: 52.0, dur: 5.5, visual: 'geo-xsec', mad: 4.2, lap: 1.08, pan: 'right', zoom: [1.0, 1.05], fade: 10, section: 'k09_sec4', note: 'Lát cắt trầm tích châu thổ' },
  { src: 'video/drone_coastline.mp4', kind: 'video', start: 57.5, dur: 5.0, visual: 'geo-river', mad: 8.2, lap: 0.96, fade: 8, section: 'k09_sec4', note: 'Drone bờ biển' },
  { src: 'map/k09_population_density.png', kind: 'map', start: 62.5, dur: 6.0, visual: 'geo-map', mad: 4.3, lap: 1.01, pan: 'in', zoom: [1.0, 1.1], fade: 12, section: 'k09_sec4', note: 'Mật độ dân cư' },
  { src: 'art/k09_outro.png', kind: 'art', start: 68.5, dur: 5.5, visual: 'geo-title', mad: 4.4, lap: 1.1, pan: 'out', zoom: [1.08, 1.0], fade: 15, section: 'k09_sec4', note: 'Outro + đăng ký kênh' },
]);

const ytCaptions = buildCues(
  'k09',
  [
    [0.6, 4.9, 'Vì sao người Việt lại chọn sống ở những nơi này?'],
    [5.6, 11.2, 'Ba phần tư lãnh thổ Việt Nam là đồi núi, nhưng phần lớn dân cư lại tập trung ở đồng bằng.'],
    [11.6, 16.3, 'Ở Tây Bắc, các dãy núi cao trên hai nghìn mét chia cắt từng thung lũng nhỏ.'],
    [16.7, 22.8, 'Nhìn vào đường đồng mức, ta thấy địa hình dốc dần từ tây bắc xuống đông nam.'],
    [23.2, 28.8, 'Lát cắt qua dãy Trường Sơn cho thấy sườn đông dốc đứng, sườn tây thoải hơn.'],
    [29.2, 34.0, 'Người dân vùng cao tạo nên ruộng bậc thang để giữ nước và đất.'],
    [35.2, 40.3, 'Xuôi về phía nam, sông Mê Kông bồi đắp phù sa suốt hàng nghìn năm.'],
    [40.7, 46.2, 'Châu thổ rộng gần bốn mươi nghìn ki lô mét vuông, phẳng và màu mỡ.'],
    [46.7, 51.8, 'Nhà sàn ven sông giúp cư dân thích nghi với mùa nước nổi.'],
    [52.2, 57.3, 'Bên dưới là những lớp trầm tích dày hàng trăm mét.'],
    [57.7, 62.3, 'Dải bờ biển dài hơn ba nghìn hai trăm ki lô mét mở ra kinh tế biển.'],
    [62.7, 68.2, 'Kết quả là bản đồ dân cư gần như trùng khớp với bản đồ địa hình thấp.'],
    [68.7, 73.6, 'Đăng ký kênh để cùng khám phá tập tiếp theo nhé.'],
  ],
  false,
);

const ytCards: OverlayCard[] = [
  { id: 'k09_k01', kind: 'chapter', text: 'CHƯƠNG 1', subtext: 'Đất nước của đồi núi', start: 5.6, end: 9.5, position: 'upper', color: '#FFFFFF', background: 'rgba(15,23,42,0.82)', fontSize: 54 },
  { id: 'k09_k02', kind: 'era', text: 'Dãy Hoàng Liên Sơn', subtext: 'Fansipan 3.143 m', start: 12.0, end: 16.0, position: 'lower', color: '#FDE68A', background: 'rgba(0,0,0,0.6)', fontSize: 44 },
  { id: 'k09_k03', kind: 'chapter', text: 'CHƯƠNG 2', subtext: 'Đọc địa hình qua lát cắt', start: 16.8, end: 20.5, position: 'upper', color: '#FFFFFF', background: 'rgba(15,23,42,0.82)', fontSize: 54 },
  { id: 'k09_k04', kind: 'chapter', text: 'CHƯƠNG 3', subtext: 'Phù sa & khu dân cư', start: 35.2, end: 39.0, position: 'upper', color: '#FFFFFF', background: 'rgba(15,23,42,0.82)', fontSize: 54 },
  { id: 'k09_k05', kind: 'era', text: '~ 4.000 năm trước', subtext: 'Châu thổ Mê Kông hình thành rõ nét', start: 41.0, end: 45.5, position: 'lower', color: '#FDE68A', background: 'rgba(0,0,0,0.6)', fontSize: 44 },
  { id: 'k09_k06', kind: 'chapter', text: 'CHƯƠNG 4', subtext: 'Biển & bản đồ dân cư', start: 52.2, end: 56.0, position: 'upper', color: '#FFFFFF', background: 'rgba(15,23,42,0.82)', fontSize: 54 },
  { id: 'k09_k07', kind: 'date', text: '3.260 km bờ biển', start: 58.0, end: 62.0, position: 'lower', color: '#FFFFFF', background: 'rgba(14,116,144,0.85)', fontSize: 46 },
];

const ytAssets: MediaAsset[] = [
  ...ytShots.map((s) => ({
    id: `a_${s.id}`,
    path: s.src,
    type: s.kind === 'video' ? ('video' as const) : ('image' as const),
    kind: s.kind,
    duration: s.kind === 'video' ? 12 : undefined,
    qa: s.qa,
    note: s.note,
    demoVisual: s.demoVisual,
  })),
  { id: 'a_delta_hd', path: 'map/k09_delta_4k.png', type: 'image', kind: 'map', qa: { madScore: 4.2, laplacianRatio: 1.14 }, note: 'Bản đồ châu thổ 4K (nét)', demoVisual: 'geo-delta' },
  { id: 'a_bridge', path: 'video/drone_highland_road.mp4', type: 'video', kind: 'video', duration: 10, qa: { madScore: 7.4, laplacianRatio: 1.0 }, note: 'Drone đèo cao nguyên — dùng lấp GAP', demoVisual: 'geo-mountain' },
  { id: 'a_xsec3', path: 'xsec/k09_xsec_hoangLien.png', type: 'image', kind: 'xsec', qa: { madScore: 4.1, laplacianRatio: 1.1 }, note: 'Lát cắt Hoàng Liên Sơn', demoVisual: 'geo-xsec' },
  { id: 'a_voice', path: 'VOICE/k09_voice.mp3', type: 'audio', kind: 'voice', duration: 73.8 },
  { id: 'a_music', path: 'MUSIC/ambient_discovery.mp3', type: 'audio', kind: 'bgm', duration: 74 },
  { id: 'a_srt', path: 'k09.srt', type: 'font', note: 'Phụ đề SRT' },
];

export const demoYoutubeProject: TimelineProject = {
  id: 'demo-youtube-k09',
  name: 'K09 - Bí Ẩn Địa Hình & Khu Dân Cư',
  mode: '16:9',
  width: 1920,
  height: 1080,
  fps: 30,
  duration: 74,
  sourceFormat: 'demo',
  rootDir: 'G:\\YouTube 2025\\NAO-Dũng - 2026-09-10\\YOUTUBE\\K09',
  sourceFile: 'EPISODE.py',
  version: 'v1',
  shots: ytShots,
  captions: ytCaptions,
  captionStyle: {
    mode: 'sentence',
    fontFamily: 'Be Vietnam Pro',
    fontSize: 46,
    fontWeight: 700,
    color: '#FFFFFF',
    highlightColor: '#FDE68A',
    strokeColor: '#000000',
    strokeWidth: 6,
    bottom: 90,
    maxWidth: 1500,
    uppercase: false,
    background: 'rgba(0,0,0,0.35)',
  },
  cards: ytCards,
  sections: [
    { id: 'k09_sec1', title: 'Ch.1 · Đồi núi', start: 0, end: 16.5, color: '#22d3ee' },
    { id: 'k09_sec2', title: 'Ch.2 · Lát cắt địa hình', start: 16.5, end: 35.0, color: '#f59e0b' },
    { id: 'k09_sec3', title: 'Ch.3 · Phù sa & dân cư', start: 35.0, end: 52.0, color: '#10b981' },
    { id: 'k09_sec4', title: 'Ch.4 · Biển & bản đồ dân cư', start: 52.0, end: 74.0, color: '#a855f7' },
  ],
  audio: [
    { id: 'k09_voice', kind: 'voice', label: 'VOICE k09_voice.mp3', src: 'VOICE/k09_voice.mp3', start: 0, end: 73.8, speechStart: 0.6, speechEnd: 73.6, volume: 1 },
    { id: 'k09_music', kind: 'bgm', label: 'MUSIC ambient_discovery.mp3', src: 'MUSIC/ambient_discovery.mp3', start: 0, end: 74, volume: 0.18 },
  ],
  watermark: { enabled: true, text: 'NAO • Địa Lý Việt', position: 'top-left', opacity: 0.6, fontSize: 32, margin: 48, color: '#FFFFFF' },
  grade: { name: 'Documentary Teal', brightness: 1.0, contrast: 1.08, saturation: 1.04, warmth: -0.1 },
  assets: ytAssets,
  updatedAt: '2026-11-03T21:00:00.000Z',
  isDemo: true,
};

export const demoProjects: TimelineProject[] = [demoReelProject, demoYoutubeProject];

/** Tổng hợp để kiểm tra nhanh trong console. */
export const demoStats = demoProjects.map((p) => ({
  id: p.id,
  shots: p.shots.length,
  captions: p.captions.length,
  duration: round3(p.duration),
}));
