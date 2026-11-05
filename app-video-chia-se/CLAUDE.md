# App Video Chia Sẻ Hội Thoại 2 Người — Kiến Trúc & Quy Chuẩn Tối Ưu Toàn Diện (Claude Cloud)

Dự án **App Video Chia Sẻ Hội Thoại 2 Người (`app-video-chia-se`)** của Chủ tịch Dũng (chạy tại `http://127.0.0.1:8765`, Desktop App `pywebview` + Flask Backend + Vanilla JS Studio UI + Remotion 9:16 Video Renderer).

---

## 1. Cấu Trúc Thư Mục & Các Thành Phần Cốt Lõi

```text
app-video-chia-se/
├── desktop_app.py                  # Entrypoint mở cửa sổ Desktop (pywebview) hoặc chạy Flask server (--server --port 8765)
├── launch_app.py                   # Script khởi động nhanh
├── config.json                     # Cấu hình đường dẫn mặc định, preset, cổng server
├── backend/
│   ├── server.py                   # Flask REST API chính (/api/projects, /api/script/analyze, /api/projects/<id>/...)
│   ├── pipeline.py                 # Luồng xử lý 6 bước: Kịch bản -> Giọng đọc -> Ảnh/Storyboard -> Nhạc -> Xuất Video
│   ├── media_ops.py                # Xử lý ảnh, tìm kiếm ảnh, phân tích dàn ý kịch bản (parse_script_outline), AI tách nền bác sĩ (extract_doctor_subject_image)
│   ├── remotion_templates.py       # Đồng bộ dữ liệu sang Remotion & gọi render video 9:16 (1080x1920, 30fps)
│   ├── capcut_export.py            # Xuất bản nháp CapCut / JianyingPro
│   ├── cli_ai.py                   # Kết nối AI CLI (Claude / Gemini / Codex) để phân tích kịch bản & storyboard
│   └── utils.py                    # Tiện ích đọc/ghi JSON, chuẩn hóa slug, quản lý tiến trình
├── frontend/
│   ├── index.html                  # Giao diện chính của ứng dụng (6 bước + Bảng quy trình bên trái + Preview phải)
│   ├── app.js                      # Logic điều khiển Frontend (quản lý dự án, phân tích kịch bản, tải/cắt ảnh bác sĩ, render)
│   └── styles.css                  # Hệ thống giao diện CSS của ứng dụng
└── remotion/
    └── ConvoAppDynamic.tsx         # Component Remotion chính để render video 9:16 (đồng bộ với C:\Users\Dung\Developer\remotion-starter\src\ConvoAppDynamic.tsx)
```

---

## 2. Quy Tắc Bắt Buộc Khi Tối Ưu Trên Claude Cloud (Opus 5.5)

1. **Giữ Tương Thích Ngược 100% (Zero Regression)**:
   - **KHÔNG** xóa hoặc đổi tên các API endpoint hiện có trong `backend/server.py` (như `/api/projects`, `/api/script/analyze`, `/api/projects/<pid>/upload-doctor-image`, `/api/projects/<pid>/edit-doctor-image`, `/api/projects/<pid>/step/1..6`).
   - **KHÔNG** xóa các hàm global được gọi từ `onclick` / `oninput` trong `frontend/index.html` (như `onScriptInputChanged`, `analyzeScriptOutlineNow`, `handleDoctorFilesUpload`, `openDoctorImageEditorModal`, `runStep`, `selectProject`).
2. **Chiến Lược Chia Module Nhỏ Gọn (`<= 280 dòng/file`)**:
   - Để công cụ `Write` / `Edit` trên Claude Cloud chạy tức thì, không bị nghẽn với các file lớn (`frontend/app.js` ~159KB, `backend/media_ops.py` ~114KB, `backend/pipeline.py` ~108KB), hãy **tạo các module mở rộng độc lập** trong:
     - `frontend/modules/*.js` và `frontend/styles/*.css` (nhúng thêm vào cuối `frontend/index.html`)
     - `backend/services/*.py` (import vào `backend/server.py` và `backend/pipeline.py`)
     - `tests/*.py` (bộ kiểm thử tự động `pytest`)
3. **Hỗ Trợ Chạy Độc Lập Trên Môi Trường Linux/Cloud (`Cloud Demo Mode`)**:
   - Trên máy thật của Chủ tịch Dũng (Windows), app dùng `C:\Users\Dung\Developer\remotion-starter` và `E:\vd chia se\models\u2net_human_seg.onnx`.
   - Khi chạy trên môi trường **Claude Cloud (Linux VM)**, backend phải tự động fallback mượt mà nếu thiếu model ONNX hoặc thư mục Windows, đồng thời cung cấp sẵn 2 dự án mẫu (`6-kenh-bac-si-demo` và `7-benh-vien-di-sinh-demo`) để có thể bật server `python3 desktop_app.py --server --port 8765` và kiểm thử trực tiếp mọi API + giao diện!
4. **Commit & Push Liên Tục Sau Mỗi Hạng Mục**:
   - Sau khi hoàn thành từng hạng mục, luôn chạy:
     ```bash
     git add . && git commit -m "feat: <mô tả hạng mục>" && git push -u origin HEAD
     ```

---

## 3. Danh Sách 5 Hạng Mục Tối Ưu Chức Năng & Giao Diện Trọng Tâm

### Hạng mục 1: Nâng Cấp Giao Diện Studio Pro & Theme Sáng/Beige — Tối (`frontend/styles/studio_pro.css` & `frontend/modules/ui_enhancements.js`)
- Thiết kế hệ thống giao diện **Studio Pro** hiện đại, sắc nét, độ tương phản cao, chữ tiếng Việt rõ ràng dễ đọc.
- Hỗ trợ nút chuyển đổi nhanh **Chế độ Tối (Dark Studio)** và **Chế độ Sáng Màu Be Ấm (Warm Beige Studio `#F6EFE6` / `#FFFDF9`)** ngay trên thanh Header.
- Thêm thanh **Quick Action Bar & Phím tắt thông minh**:
  - `Ctrl + Enter`: Phân tích kịch bản & Chạy bước hiện tại
  - `Ctrl + S`: Lưu kịch bản & yêu cầu thiết kế (`visual_prompt`)
  - Toast Notification mượt mà, bộ lọc tìm kiếm nhanh danh sách dự án ở cột trái, hiển thị badge số mục (`6 mục`, `7 mục`) và preset (`Chia sẻ`, `2 người`) ngay trên từng thẻ dự án.

### Hạng mục 2: Trình Xem Trước Bố Cục Video 9:16 Thời Gian Thực (`frontend/modules/live_preview_9x16.js`)
- Tạo khung **Live Storyboard Canvas 9:16** tương tác ngay trên giao diện Bước 1 & Bước 3 để Chủ tịch xem trước ngay lập tức kết quả thiết kế **mà chưa cần chờ Remotion xuất MP4**:
  - Hiển thị trực quan từng Slide (`1..N`) và **Bảng Tổng Hợp Cuối Video (Summary Board)** theo thời gian thực khi gõ kịch bản hoặc chọn tông màu trong ô Yêu cầu thêm (`#visualPromptInput`).
  - Phản ánh chính xác: nền màu be (`#F6EFE6`), thẻ trắng kem (`#FFFDF9`), tiêu đề chính trên cùng, khung ảnh lớn ở giữa (hiển thị đúng ảnh bác sĩ/sản phẩm đã tách nền hoặc tải lên), tên mục chữ vàng/nâu nổi bật, và các pill thông tin/địa chỉ **căn giữa tuyệt đối (`text-align: center`)**.
  - Cho phép bấm nút `< Trước` / `Sau >` hoặc click vào từng mục trong khung Phân tích kịch bản để nhảy tới đúng Slide đó trên Canvas 9:16.

### Hạng mục 3: Nâng Cấp Bộ Phân Tích Kịch Bản & Kho Thẻ Yêu Cầu Thông Minh (`frontend/modules/script_inspector_pro.js`)
- Nâng cấp khung **Phân tích kịch bản trước (`#scriptPreAnalysisBox`)**:
  - Cho phép **click sửa trực tiếp** tên mục (ví dụ sửa nhanh `1. BS Dương M. Tuấn`) hoặc nội dung bullet ngay trong bảng phác thảo và tự động đồng bộ ngược lại vào ô kịch bản `#scriptInput`.
  - Hỗ trợ kéo-thả hoặc nút `↑` / `↓` để đổi thứ tự các mục, nút `+ Thêm mục` hoặc `× Xóa mục`.
  - Cảnh báo tự động nếu có mục bị thiếu mô tả/địa chỉ hoặc tiêu đề số lượng mục (`6 KÊNH...`) lệch với số mục thực tế.
- Thêm **Thanh Quick Chips cho ô Yêu cầu thêm (`#visualPromptInput`)**:
  - Các nút bấm 1 chạm tạo sẵn yêu cầu chuẩn:
    - `🎨 Nền màu be ấm (#F6EFE6)`
    - `🖼️ Phóng to khung ảnh chính`
    - `📐 Căn giữa địa chỉ & thông tin`
    - `👨‍⚕️ Khung thẻ bác sĩ chuẩn y khoa`
    - `🌸 Tông hồng phấn Mẹ & Bé`
    - `✨ Bảng tổng hợp chữ to rõ`

### Hạng mục 4: Nâng Cấp Trình Cắt & Tách Nền Ảnh Bác Sĩ / Sản Phẩm Pro (`frontend/modules/doctor_editor_pro.js` & `backend/services/image_enhancer.py`)
- Bổ sung các tính năng cao cấp cho Modal chỉnh sửa ảnh bác sĩ và API xử lý ảnh:
  - Hỗ trợ **Zoom lăn chuột & Kéo dịch chuyển ảnh (Pan/Zoom)** mượt mà trong khung cắt.
  - Tuỳ chọn **Màu nền thẻ sau khi tách nền**: Trắng kem (`#FFFDF9`), Be ấm (`#F6EFE6`), Xanh y khoa nhạt (`#F0F7FF`), hoặc Trong suốt (`PNG Transparent`).
  - Tuỳ chọn **Tự động làm nét khuôn mặt & Cân bằng sáng (Auto Face/Subject Enhance + Warm Tone)** trong `backend/services/image_enhancer.py` để ảnh bác sĩ tải từ Facebook/TikTok về luôn sáng rõ, sắc nét khi lên video 1080x1920.
  - Tính năng **Áp dụng hàng loạt (Batch Process All Images)**: Tự động tách nền + đóng khung đồng bộ cho cả 6–10 ảnh chỉ với 1 nút bấm.

### Hạng mục 5: Bộ Kiểm Định Chất Lượng Tự Động (Auto-QA), Hàng Đợi Batch & Tối Ưu Remotion (`backend/services/qa_validator.py`, `remotion/ConvoAppDynamic.tsx`, `tests/`)
- Xây dựng `backend/services/qa_validator.py` (kèm endpoint `GET /api/projects/<pid>/qa-check` và `POST /api/projects/<pid>/qa-autofix`):
  - Kiểm tra tự động 10 tiêu chí trước khi xuất video:
    1. Số mục trong kịch bản (`expected_item_count`) == Số mục trong `storyboard.json` == Số dòng trên Bảng Tổng Hợp.
    2. Tất cả các mục đều có file ảnh hợp lệ, độ phân giải tối thiểu đạt chuẩn, không bị ảnh rỗng/lỗi.
    3. Các dòng địa chỉ / bullet không bị tràn khung hoặc lệch bố cục.
    4. Cấu hình màu nền (`bgTheme` / `customBgColor`) khớp với yêu cầu trong `visual_prompt`.
  - Tự động sửa lỗi (`qa-autofix`) chỉ với 1 cú click.
- Tối ưu `remotion/ConvoAppDynamic.tsx`:
  - Tự động co giãn cỡ chữ thông minh (Auto-Fit Text Scaling) khi tên bệnh viện/bác sĩ hoặc địa chỉ quá dài, đảm bảo không bao giờ bị cắt chữ hay lệch lề.
  - Căn giữa tuyệt đối (`justifyContent: 'center'`, `textAlign: 'center'`) các thẻ thông tin phụ/địa chỉ trong chế độ `chia_se`.
- Viết bộ kiểm thử tự động `tests/test_app_comprehensive.py` kiểm tra toàn bộ luồng phân tích kịch bản (6 kênh bác sĩ, 7 bệnh viện đi sinh, 3 đồ xài cho bé), API server, tách nền ảnh và QA Validator.
