import type { TimelineProject } from '../types/timeline';
import { findGaps, formatTime, isStillKind, shotEnd } from './timelineUtils';

export const MAD_MIN = 4;
export const LAPLACIAN_MIN = 0.75;

export type QASeverity = 'error' | 'warning' | 'info';

export interface QAIssue {
  id: string;
  severity: QASeverity;
  code: 'GAP' | 'STATIC' | 'BLUR' | 'CAPTION_OVERLAP' | 'CAPTION_SHORT' | 'SHOT_TOO_LONG' | 'NO_FADE_STILL' | 'OUT_OF_RANGE';
  title: string;
  detail: string;
  time: number;
  shotId?: string;
  /** Lệnh AI gợi ý để sửa lỗi này. */
  fixPrompt: string;
}

export interface QAReport {
  score: number;
  passed: boolean;
  issues: QAIssue[];
  stats: { avgMad: number; avgLaplacian: number; gaps: number; staticShots: number; blurShots: number };
}

export function runQA(project: TimelineProject): QAReport {
  const issues: QAIssue[] = [];

  for (const g of findGaps(project)) {
    issues.push({
      id: `gap_${g.start}`,
      severity: 'error',
      code: 'GAP',
      title: `Khoảng trống GAP ${g.duration.toFixed(2)}s`,
      detail: `Màn hình đen từ ${formatTime(g.start)} → ${formatTime(g.end)}.`,
      time: g.start,
      shotId: g.afterShotId,
      fixPrompt: 'Tự động lấp mọi khoảng trống GAP',
    });
  }

  for (const s of project.shots) {
    const qa = s.qa;
    // Ảnh tĩnh 16:9 có Ken Burns được coi là có chuyển động hợp lệ.
    const still = isStillKind(s.kind);
    const hasMotion = s.zoom.enabled || s.panDirection !== 'none';
    if (qa && qa.madScore < MAD_MIN && !(still && hasMotion)) {
      issues.push({
        id: `static_${s.id}`,
        severity: 'error',
        code: 'STATIC',
        title: `${s.label} cảnh tĩnh — MAD ${qa.madScore.toFixed(1)} < ${MAD_MIN}`,
        detail: `${s.src} gần như không chuyển động, người xem dễ lướt qua.`,
        time: s.start,
        shotId: s.id,
        fixPrompt: `Sửa cảnh tĩnh ${s.label}`,
      });
    }
    if (qa && qa.laplacianRatio < LAPLACIAN_MIN) {
      issues.push({
        id: `blur_${s.id}`,
        severity: 'warning',
        code: 'BLUR',
        title: `${s.label} ảnh mờ — Laplacian ${qa.laplacianRatio.toFixed(2)}`,
        detail: `Độ nét tại điểm cắt thấp hơn ngưỡng ${LAPLACIAN_MIN}.`,
        time: s.start,
        shotId: s.id,
        fixPrompt: `Thay cảnh ${s.label.replace('S', '')} bằng bản nét hơn`,
      });
    }
    if (still && !hasMotion) {
      issues.push({
        id: `kb_${s.id}`,
        severity: 'warning',
        code: 'NO_FADE_STILL',
        title: `${s.label} ảnh tĩnh không có Ken Burns`,
        detail: 'Ảnh đứng yên hoàn toàn — nên bật pan/zoom.',
        time: s.start,
        shotId: s.id,
        fixPrompt: `Bật zoom và pan phải cho cảnh ${s.label.replace('S', '')}`,
      });
    }
    const maxLen = project.mode === '9:16' ? 4.5 : 9;
    if (s.duration > maxLen) {
      issues.push({
        id: `long_${s.id}`,
        severity: 'info',
        code: 'SHOT_TOO_LONG',
        title: `${s.label} dài ${s.duration.toFixed(1)}s`,
        detail: `Nhịp ${project.mode} khuyến nghị ≤ ${maxLen}s / cảnh.`,
        time: s.start,
        shotId: s.id,
        fixPrompt: `Tách cảnh ${s.label.replace('S', '')} làm đôi`,
      });
    }
    if (shotEnd(s) > project.duration + 0.05) {
      issues.push({
        id: `oor_${s.id}`,
        severity: 'warning',
        code: 'OUT_OF_RANGE',
        title: `${s.label} vượt quá độ dài video`,
        detail: `Kết thúc ở ${formatTime(shotEnd(s))} > ${formatTime(project.duration)}.`,
        time: s.start,
        shotId: s.id,
        fixPrompt: `Cắt cảnh ${s.label.replace('S', '')} còn ${(project.duration - s.start).toFixed(1)}s`,
      });
    }
  }

  const caps = [...project.captions].sort((a, b) => a.start - b.start);
  caps.forEach((c, i) => {
    const next = caps[i + 1];
    if (next && next.start < c.end - 0.02) {
      issues.push({
        id: `ovl_${c.id}`,
        severity: 'warning',
        code: 'CAPTION_OVERLAP',
        title: `Phụ đề câu ${i + 1} chồng lên câu ${i + 2}`,
        detail: `${formatTime(next.start)} < ${formatTime(c.end)}`,
        time: next.start,
        fixPrompt: 'Sửa phụ đề chồng nhau',
      });
    }
    if (c.end - c.start < 0.6) {
      issues.push({
        id: `short_${c.id}`,
        severity: 'info',
        code: 'CAPTION_SHORT',
        title: `Phụ đề câu ${i + 1} quá ngắn`,
        detail: `Chỉ hiển thị ${(c.end - c.start).toFixed(2)}s.`,
        time: c.start,
        fixPrompt: 'Sửa phụ đề chồng nhau',
      });
    }
  });

  const penalty = issues.reduce((acc, i) => acc + (i.severity === 'error' ? 1.5 : i.severity === 'warning' ? 0.6 : 0.15), 0);
  const score = Math.max(0, Math.round((10 - penalty) * 10) / 10);
  const withQa = project.shots.filter((s) => s.qa);
  const avgMad = withQa.length ? withQa.reduce((a, s) => a + (s.qa?.madScore ?? 0), 0) / withQa.length : 0;
  const avgLaplacian = withQa.length ? withQa.reduce((a, s) => a + (s.qa?.laplacianRatio ?? 0), 0) / withQa.length : 0;

  return {
    score,
    passed: score >= 8 && !issues.some((i) => i.severity === 'error'),
    issues,
    stats: {
      avgMad,
      avgLaplacian,
      gaps: issues.filter((i) => i.code === 'GAP').length,
      staticShots: issues.filter((i) => i.code === 'STATIC').length,
      blurShots: issues.filter((i) => i.code === 'BLUR').length,
    },
  };
}

export function shotIssues(report: QAReport, shotId: string): QAIssue[] {
  return report.issues.filter((i) => i.shotId === shotId && i.code !== 'GAP');
}
