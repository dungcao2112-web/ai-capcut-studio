/**
 * Kết nối Agy Local Server (server/index.mjs, cổng 3001).
 * Dev: Vite proxy /api → http://localhost:3001. Có thể đổi bằng VITE_API_BASE.
 * Mọi hàm đều có timeout; lỗi ⇒ Frontend tự fallback sang Demo / browser engine.
 */
import type {
  AIEditRequest,
  AIEditResponse,
  ProjectListItem,
  RenderRequest,
  RenderResponse,
  SaveProjectResponse,
  TimelineProject,
} from '../types/timeline';

const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 5000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    const ct = res.headers.get('content-type') ?? '';
    if (!ct.includes('application/json')) throw new Error('Phản hồi không phải JSON (server chưa chạy?)');
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchProjects(): Promise<ProjectListItem[]> {
  const data = await request<ProjectListItem[] | { projects: ProjectListItem[] }>('/api/projects', {}, 3500);
  return Array.isArray(data) ? data : data.projects ?? [];
}

export async function fetchProject(id: string): Promise<TimelineProject> {
  const data = await request<TimelineProject | { project: TimelineProject }>(`/api/project?id=${encodeURIComponent(id)}`, {}, 15000);
  return 'project' in data && data.project ? data.project : (data as TimelineProject);
}

export function saveProject(project: TimelineProject): Promise<SaveProjectResponse> {
  return request<SaveProjectResponse>('/api/project/save', { method: 'POST', body: JSON.stringify({ project }) }, 15000);
}

export function remoteAIEdit(req: AIEditRequest): Promise<AIEditResponse> {
  return request<AIEditResponse>('/api/ai-edit', { method: 'POST', body: JSON.stringify(req) }, 60000);
}

export function startRender(req: RenderRequest): Promise<RenderResponse> {
  return request<RenderResponse>('/api/render', { method: 'POST', body: JSON.stringify(req) }, 20000);
}

/** URL stream file từ ổ cứng máy Chủ tịch (hỗ trợ Range 206). */
export function mediaUrl(project: TimelineProject, relPath: string): string | undefined {
  if (project.isDemo || !project.rootDir) return undefined;
  if (/^(https?:|blob:|data:)/.test(relPath)) return relPath;
  const abs = /^[a-zA-Z]:[\\/]/.test(relPath) ? relPath : `${project.rootDir.replace(/[\\/]+$/, '')}\\${relPath.replace(/\//g, '\\')}`;
  return `${API_BASE}/api/media?path=${encodeURIComponent(abs)}`;
}
