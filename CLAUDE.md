# AI CapCut Studio — Quy tắc phối hợp Claude Cloud & Agy Local (Chủ tịch Dũng)

Dự án **AI CapCut Studio**: Phần mềm dựng video giao diện kiểu CapCut nhưng **do AI dựng 100% và chỉnh sửa hoàn toàn bằng lệnh/prompt tiếng Việt**, hỗ trợ song song:
1. **9:16 Reel / Shorts (`1080x1920`, 30fps)**: Tương thích trực tiếp với cấu trúc `edit.json` / `edit_v2.json` của hệ thống Reel Nấu Ăn (`shots[]`, `captions[]`, `cards[]`, `audioFile`, `watermark`, `grade`, `zoom`, `fadeInFrames`).
2. **16:9 YouTube (`1920x1080`, 30fps)**: Tương thích trực tiếp với cấu trúc `EPISODE.py` / `shots.json` + `.srt` của hệ thống YouTube K07/K09 (`SHOTS`, `SECTIONS`, `ERAS`, `pan/zoom`, `art/map/xsec/photo/video`, `VOICE`, `MUSIC`, `WATERMARK`).

---

## 1. Phân công nhiệm vụ giữa Claude Cloud (Opus 5.5) và Agy (Local PC)

### A. Nhiệm vụ của Claude Cloud (Frontend & AI Prompt-to-Edit UI — thư mục `src/`)
Claude Cloud làm việc trên nhánh `main` (hoặc PR), tập trung 100% vào giao diện Web Studio (`Vite + React + TypeScript + Tailwind/Lucide`):
1. **Giao diện chuẩn CapCut Dark Studio (3 khu vực chính + 1 khung AI Chat):**
   - **Top Bar:** Chọn dự án có sẵn từ ổ `G:\` (hoặc tạo mới), chuyển đổi nhanh tỷ lệ khung hình **9:16 (Reel 1080×1920)** ↔ **16:9 (YouTube 1920×1080)**, nút Undo/Redo, lịch sử phiên bản (`v1`, `v2`...), nút **Render GPU NVENC (RTX 5070 Ti)**.
   - **Left Panel (Media / Script / Subtitles / Presets):**
     - Tab *Nguyên liệu (Assets)*: Danh sách clip `muse/canh*.mp4`, clip gốc `_tam_clip_goc/*`, ảnh `art/map`, audio `mix.wav`/`vo.mp3`.
     - Tab *Kịch bản & Phụ đề (Captions/SRT)*: Danh sách từng câu phụ đề kèm mốc giây, bấm vào nhảy ngay tới giây đó.
     - Tab *Kiểm tra chất lượng (QA G4)*: Hiển thị chỉ số MAD (độ chuyển động), Laplacian (độ nét tại điểm cắt), cảnh báo cảnh tĩnh `<4 MAD` hoặc gap trống.
   - **Center Panel (Instant Realtime Preview Player):**
     - Khung xem trước video thời gian thực (dùng HTML5 `<video>`/`<canvas>` đồng bộ frame-accurate ở 30fps): tự động phát nối tiếp các `shots[]`, áp dụng hiệu ứng `zoom` (`1.00 -> 1.04`), `pan` (Ken Burns cho ảnh 16:9), `fadeInFrames` (crossfade không bị tối đen), hiển thị `cards[]` (nhãn chữ), `captions[]` (phụ đề karaoke từng từ hoặc câu) và `watermark` đúng tọa độ thật.
     - Có thanh scrub thời gian, phím `Space` để Play/Pause, `J/K/L` hoặc phím mũi tên nhảy từng khung hình / từng cảnh (`S1`, `S2`...).
   - **Bottom Panel (Multi-Track Timeline kiểu CapCut):**
     - Phóng to/thu nhỏ timeline (Zoom), con trỏ Playhead đỏ kéo mượt.
     - **Track 1 — Nhãn Cảnh / Chương (`Scenes / Sections`):** `S1`, `S2`... hoặc chương YouTube.
     - **Track 2 — Thẻ Chữ / Đồ họa (`Cards / Overlays / Eras`):** Các thẻ chú thích trên màn hình.
     - **Track 3 — Video / Hình ảnh chính (`Video / Visual Shots`):** Hiển thị từng block shot (`#01 canh01.mp4`, độ dài giây, badge `AI Muse` màu tím hoặc `GỐC` màu xanh, badge `Zoom`, cảnh báo đỏ nếu bị GAP hoặc `<4 MAD`). Click vào shot sẽ highlight để lệnh AI biết đang chọn cảnh nào.
     - **Track 4 — Phụ đề (`Captions / SRT`):** Các block phụ đề theo thời gian.
     - **Track 5 — Giọng đọc & Nhạc nền (`Voice & BGM/SFX`):** Hiển thị sóng âm / dải thời gian lời đọc (`speechStart` → `speechEnd`).
   - **Right Panel (AI Prompt-to-Edit & Command Center — TRỌNG TÂM):**
     - Khung chat điều khiển bằng tiếng Việt tự nhiên + các nút lệnh nhanh (Quick Chips).
     - Khi Chủ tịch gõ lệnh (ví dụ: *"Cảnh 3 hơi tĩnh, đổi sang muse/canh04_d.mp4, cắt còn 1.8s và bật zoom"*, *"Đẩy phụ đề lên cao hơn một chút, đổi màu vàng"*, *"Thêm thẻ chữ 'Bí quyết ướp thịt mềm' từ giây 4 đến giây 6"*, *"Tự động lấp các khoảng trống GAP"*):
       - Bộ **Natural Language Command Engine** (`src/lib/promptEngine.ts` + kết nối API LLM local ở backend `/api/ai-edit`) phân tích lệnh → sinh ra bản cập nhật `TimelineProject` + giải thích rõ đã sửa những gì (Before → After) → áp dụng ngay lên Preview & Timeline (có nút **Hoàn tác / Undo** 1 chạm).

### B. Nhiệm vụ của Agy (Local Backend & GPU Engine — thư mục `server/`)
Agy chạy trực tiếp trên máy Windows của Chủ tịch, phụ trách:
1. **Local Media & Project Server (`server/index.mjs`, cổng `3001`):**
   - Quét trực tiếp các thư mục dự án thật trên ổ `G:\YouTube 2025\NAO-Dũng - 2026-09-10` (cả nhánh Reel `TH\FB AFF\1. NẤU ĂN` và nhánh YouTube `YOUTUBE\K07`, `YOUTUBE\K09`).
   - Đọc/ghi trực tiếp file `edit.json`, `edit_v2.json` (9:16) và `EPISODE.py` + `.srt` (16:9), stream video/audio/font từ ổ `G:\` lên giao diện Web qua `/api/media?path=...` (hỗ trợ HTTP Range Requests `206 Partial Content` để tua video mượt tức thì).
   - Tích hợp AI Agent (`AICoworker` / `gemini38` / `claude-sonnet` / `gpt-oss` hoặc parser nội bộ) tại `/api/ai-edit` để dịch mọi câu lệnh phức tạp của Chủ tịch thành thao tác chỉnh sửa JSON chính xác.
   - Tích hợp nút **Xuất Video GPU (`POST /api/render`)**: gọi thẳng **FFmpeg + NVIDIA RTX 5070 Ti (`h264_nvenc -preset p5 -tune hq -rc vbr -cq 15`)** hoặc Remotion / `build_video.py` kèm Auto-Fallback CPU.

---

## 2. Quy ước kỹ thuật để không xung đột code
- **Schema dùng chung:** Đặt tại `src/types/timeline.ts`. Mọi thành phần UI và Backend đều tuân thủ đúng kiểu dữ liệu trong file này.
- **API giao tiếp giữa Frontend (`src/`) và Local Server (`server/`):**
  - `GET /api/projects` → Danh sách dự án 9:16 và 16:9 trên ổ `G:\` + dự án mẫu (Demo) khi chạy trên Cloud không có ổ `G:\`.
  - `GET /api/project?id=...` → Trả về `TimelineProject` đầy đủ.
  - `POST /api/project/save` → Lưu lại `TimelineProject` (tự động đồng bộ ngược về `edit.json` hoặc `EPISODE.py`).
  - `POST /api/ai-edit` → Gửi `{ project, prompt, selectedShotId, currentTime }` → Trả về `{ updatedProject, summary, changes[] }`.
  - `POST /api/render` → Bắt đầu xuất file `.mp4` bằng GPU RTX 5070 Ti.
  - `GET /api/media?path=...` → Stream file video/audio/ảnh từ ổ cứng máy Chủ tịch.
- **Chế độ Offline/Cloud Fallback:** Khi chạy trên môi trường **Claude Cloud** (không có `server/` ở cổng 3001 hoặc không có ổ `G:\`), Frontend **BẮT BUỘC** tự động fallback sang dữ liệu mẫu (`src/data/demoProjects.ts` gồm 1 dự án Reel 9:16 Nấu Ăn và 1 dự án YouTube 16:9 Bản Đồ Địa Lý) và chạy bộ `promptEngine.ts` ngay trên trình duyệt để test được 100% tính năng!
