/**
 * ============================================================================
 *  AI CapCut Studio — SCHEMA DÙNG CHUNG (Frontend `src/` ⇄ Agy Local `server/`)
 * ============================================================================
 *  Mọi thời gian tính bằng GIÂY (number, có thể lẻ). Khung hình = giây × fps.
 *  Tọa độ (bottom, x, y, fontSize...) tính theo PIXEL THẬT của khung xuất
 *  (1080×1920 cho 9:16 Reel, 1920×1080 cho 16:9 YouTube).
 *
 *  Ánh xạ nguồn:
 *   - 9:16 Reel  ← edit.json / edit_v2.json:
 *       shots[]  → TimelineShot (src, dur, zoom, fadeInFrames)
 *       captions[] → CaptionCue (+ words[] karaoke)
 *       cards[]  → OverlayCard
 *       audioFile → AudioTrackItem kind 'voice' | 'bgm'
 *       watermark, grade → WatermarkConfig, ColorGrade
 *   - 16:9 YouTube ← EPISODE.py / shots.json + .srt:
 *       SHOTS    → TimelineShot (kind art/map/xsec/photo/video, panDirection)
 *       SECTIONS → TimelineSection (chương)
 *       ERAS     → OverlayCard kind 'era'
 *       .srt     → CaptionCue (mode 'sentence')
 *       VOICE / MUSIC → AudioTrackItem
 *       WATERMARK → WatermarkConfig
 * ============================================================================
 */

export type AspectMode = '9:16' | '16:9';

export const ASPECT_PRESETS: Record<AspectMode, { width: number; height: number; label: string }> = {
  '9:16': { width: 1080, height: 1920, label: '9:16 Reel / Shorts' },
  '16:9': { width: 1920, height: 1080, label: '16:9 YouTube' },
};

/** Định dạng file gốc mà Agy Local đọc/ghi ngược. */
export type ProjectSourceFormat = 'reel-edit-json' | 'youtube-episode-py' | 'demo';

/**
 * Loại nguồn của 1 shot:
 *  - muse : clip AI Muse sinh ra (muse/canh*.mp4) — badge tím
 *  - goc  : clip quay gốc (_tam_clip_goc/*)        — badge xanh
 *  - art / map / xsec / photo : ảnh tĩnh 16:9 (Ken Burns pan/zoom)
 *  - video: video stock / drone cho YouTube
 */
export type ShotKind = 'muse' | 'goc' | 'art' | 'map' | 'xsec' | 'photo' | 'video';

export type PanDirection = 'none' | 'left' | 'right' | 'up' | 'down' | 'in' | 'out';

/** Tên cảnh mô phỏng để Preview vẽ Canvas động khi chưa có file video thật. */
export type DemoVisual =
  // Nấu ăn (9:16)
  | 'food-hero'
  | 'food-boil'
  | 'food-chop'
  | 'food-marinate'
  | 'food-rest'
  | 'food-sizzle'
  | 'food-sauce'
  | 'food-simmer'
  | 'food-glaze'
  | 'food-plate'
  // Địa lý (16:9)
  | 'geo-title'
  | 'geo-map'
  | 'geo-terrain'
  | 'geo-xsec'
  | 'geo-river'
  | 'geo-village'
  | 'geo-mountain'
  | 'geo-delta';

export interface ZoomEffect {
  enabled: boolean;
  /** Hệ số phóng đầu shot, ví dụ 1.00 */
  from: number;
  /** Hệ số phóng cuối shot, ví dụ 1.04 */
  to: number;
}

/** Chỉ số kiểm định chất lượng (Cổng QA G4). */
export interface ShotQA {
  /** Mean Absolute Difference giữa các frame — độ chuyển động. < 4 ⇒ cảnh tĩnh. */
  madScore: number;
  /** Tỉ lệ Laplacian variance tại điểm cắt so với trung vị — độ nét. < 0.75 ⇒ mờ. */
  laplacianRatio: number;
  /** true nếu chỉ số là ước tính (sau khi AI sửa, chưa đo lại bằng ffmpeg). */
  estimated?: boolean;
}

export interface TimelineShot {
  id: string;
  /** Nhãn cảnh hiển thị: S1, S2... */
  label: string;
  /** Đường dẫn tương đối trong thư mục dự án, ví dụ `muse/canh01_a.mp4`. */
  src: string;
  kind: ShotKind;
  /** Thời điểm bắt đầu trên timeline (giây). */
  start: number;
  /** Độ dài trên timeline (giây). */
  duration: number;
  /** Điểm vào trong file nguồn (giây). */
  trimIn: number;
  /** Tốc độ phát (1 = bình thường). */
  speed: number;
  zoom: ZoomEffect;
  /** Ken Burns (chủ yếu cho ảnh 16:9). */
  panDirection: PanDirection;
  /** Số frame crossfade với shot trước (0 = cắt thẳng). */
  fadeInFrames: number;
  qa?: ShotQA;
  /** Chương / section chứa shot (16:9). */
  sectionId?: string;
  /** Ghi chú cảnh (prompt Muse, mô tả...). */
  note?: string;
  /** URL phát trực tiếp do server cung cấp (nếu có). */
  mediaUrl?: string;
  /** Cảnh mô phỏng cho chế độ Demo/Cloud. */
  demoVisual?: DemoVisual;
}

export interface CaptionWord {
  text: string;
  start: number;
  end: number;
}

export interface CaptionCue {
  id: string;
  start: number;
  end: number;
  text: string;
  /** Mốc từng từ cho karaoke (Reel). Không có ⇒ chia đều. */
  words?: CaptionWord[];
}

export type CaptionMode = 'karaoke' | 'sentence';

export interface CaptionStyle {
  mode: CaptionMode;
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  /** Màu chữ thường. */
  color: string;
  /** Màu từ đang đọc (karaoke). */
  highlightColor: string;
  strokeColor: string;
  strokeWidth: number;
  /** Khoảng cách từ đáy khung lên baseline phụ đề (px thật). */
  bottom: number;
  /** Chiều rộng tối đa của dòng (px thật). */
  maxWidth: number;
  uppercase: boolean;
  /** Nền mờ sau chữ (rgba) — để trống nếu không dùng. */
  background?: string;
}

export type OverlayKind = 'label' | 'era' | 'chapter' | 'date' | 'tip';
export type OverlayPosition = 'top' | 'upper' | 'center' | 'lower' | 'bottom';

export interface OverlayCard {
  id: string;
  kind: OverlayKind;
  text: string;
  /** Dòng phụ (ví dụ năm / ghi chú). */
  subtext?: string;
  start: number;
  end: number;
  position: OverlayPosition;
  color: string;
  background: string;
  fontSize: number;
}

/** Chương YouTube (SECTIONS) hoặc nhóm cảnh Reel. */
export interface TimelineSection {
  id: string;
  title: string;
  start: number;
  end: number;
  color: string;
}

export type AudioKind = 'voice' | 'bgm' | 'sfx';

export interface AudioTrackItem {
  id: string;
  kind: AudioKind;
  label: string;
  src: string;
  start: number;
  end: number;
  /** Mốc bắt đầu / kết thúc lời đọc thực tế (voice). */
  speechStart?: number;
  speechEnd?: number;
  /** 0..1.5 */
  volume: number;
  mediaUrl?: string;
}

export type WatermarkPosition = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'top-center';

export interface WatermarkConfig {
  enabled: boolean;
  text: string;
  position: WatermarkPosition;
  opacity: number;
  fontSize: number;
  /** Lề so với mép khung (px thật). */
  margin: number;
  color: string;
}

export interface ColorGrade {
  name: string;
  /** 1 = giữ nguyên */
  brightness: number;
  contrast: number;
  saturation: number;
  /** -1 (lạnh) .. +1 (ấm) */
  warmth: number;
}

export type AssetType = 'video' | 'image' | 'audio' | 'font';

export interface MediaAsset {
  id: string;
  path: string;
  type: AssetType;
  kind?: ShotKind | AudioKind;
  duration?: number;
  qa?: ShotQA;
  note?: string;
  demoVisual?: DemoVisual;
  mediaUrl?: string;
}

export interface TimelineProject {
  id: string;
  name: string;
  mode: AspectMode;
  width: number;
  height: number;
  fps: number;
  /** Tổng độ dài (giây). */
  duration: number;
  sourceFormat: ProjectSourceFormat;
  /** Thư mục dự án trên ổ G:\ (chỉ có khi Agy Local nạp). */
  rootDir?: string;
  /** File gốc: edit.json / edit_v2.json / EPISODE.py */
  sourceFile?: string;
  /** Nhãn phiên bản: v1, v2... */
  version: string;
  shots: TimelineShot[];
  captions: CaptionCue[];
  captionStyle: CaptionStyle;
  cards: OverlayCard[];
  sections: TimelineSection[];
  audio: AudioTrackItem[];
  watermark: WatermarkConfig;
  grade: ColorGrade;
  assets: MediaAsset[];
  updatedAt: string;
  /** true nếu là dữ liệu mẫu (Cloud/offline). */
  isDemo?: boolean;
}

/* ----------------------------- API contracts ----------------------------- */

export interface ProjectListItem {
  id: string;
  name: string;
  mode: AspectMode;
  sourceFormat: ProjectSourceFormat;
  path?: string;
  isDemo?: boolean;
  updatedAt?: string;
}

/** POST /api/ai-edit */
export interface AIEditRequest {
  project: TimelineProject;
  prompt: string;
  selectedShotId: string | null;
  currentTime: number;
}

export interface AIEditChange {
  /** Đối tượng bị sửa, ví dụ "S3", "Phụ đề", "Thẻ chữ #2", "Dự án". */
  target: string;
  /** Thuộc tính, ví dụ "src", "duration", "captionStyle.color". */
  field: string;
  before: string;
  after: string;
}

export interface AIEditResponse {
  updatedProject: TimelineProject;
  summary: string;
  changes: AIEditChange[];
  /** Ai đã xử lý lệnh. */
  engine?: 'agy-local' | 'browser-rules';
  warnings?: string[];
  /** Gợi ý UI nhảy tới thời điểm này (giây). */
  seekTo?: number;
  /** Gợi ý UI chọn shot này. */
  selectShotId?: string | null;
}

/** POST /api/project/save */
export interface SaveProjectResponse {
  ok: boolean;
  path?: string;
  version?: string;
  message?: string;
}

/** POST /api/render */
export interface RenderRequest {
  project: TimelineProject;
  encoder: 'h264_nvenc' | 'hevc_nvenc' | 'libx264';
  preset: string;
  cq: number;
  outputName?: string;
}

export interface RenderResponse {
  ok: boolean;
  jobId?: string;
  outputPath?: string;
  encoder?: string;
  message?: string;
}
