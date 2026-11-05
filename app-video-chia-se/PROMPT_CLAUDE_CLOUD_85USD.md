# 🚀 MEGA-PROMPT DÀNH CHO CLAUDE CLOUD (ĐỐT $85 CREDIT TỐI ƯU TOÀN DIỆN APP)

> **Hướng dẫn cho Sếp Dũng:**
> 1. Mở trình duyệt vào **https://claude.ai/code** (hoặc mở **Claude Desktop** -> tab **Code** -> chọn môi trường **Cloud**).
> 2. Chọn model **Claude Opus 4.6 / Opus 5.5** + chế độ **Max Effort (hoặc Extended Thinking)**.
> 3. Chọn repo GitHub của dự án này (`dungcao2112-web/app-video-chia-se`).
> 4. Copy toàn bộ đoạn Prompt trong khung bên dưới và dán vào ô chat của Claude Cloud (Sếp có thể bật song song **2 đến 3 phiên Cloud** cùng lúc với cùng Prompt này hoặc chia từng Phase để đốt hết $85 credit nhanh nhất và thu về các nhánh PR chất lượng nhất!).

---

## 📋 NỘI DUNG PROMPT (COPY TỪ ĐÂY DÁN VÀO CLAUDE CLOUD)

```text
Đọc kỹ file `CLAUDE.md` và toàn bộ mã nguồn hiện có trong repo (`desktop_app.py`, `backend/`, `frontend/`, `remotion/ConvoAppDynamic.tsx`).

Tôi đang cần sử dụng tối đa năng lực tính toán của Claude Cloud (Opus Max Effort) để **tối ưu hóa toàn diện cả Chức Năng (Backend/AI/Media/Remotion) lẫn Giao Diện Trải Nghiệm Người Dùng (Frontend Studio UI/UX)** cho ứng dụng **App Video Chia Sẻ Hội Thoại 2 Người**.

### YÊU CẦU QUAN TRỌNG:
1. **Bảo toàn 100% tính năng & tương thích ngược**:
   - Giữ nguyên mọi API route hiện có trong `backend/server.py` và mọi hàm global trong `frontend/app.js` đang gắn với `frontend/index.html`.
   - Ngôn ngữ giao diện: **100% Tiếng Việt rõ ràng, trực quan, chuẩn phong cách Studio chuyên nghiệp**.
2. **Kiến trúc Module hóa thông minh (giữ mỗi file mới <= 280 dòng để ghi file nhanh và dễ bảo trì)**:
   - Tạo các module Frontend mới trong `frontend/modules/` và `frontend/styles/`, sau đó nhúng vào `frontend/index.html`.
   - Tạo các dịch vụ Backend mới trong `backend/services/` và đăng ký blueprint / route vào `backend/server.py`.
3. **Thực hiện đầy đủ, sâu sắc và hoàn chỉnh cả 5 Hạng Mục lớn trong `CLAUDE.md` (không làm sơ sài, không viết code giả lập/TODO)**:

   - **HẠNG MỤC 1 — Giao diện Studio Pro & Theme Sáng Màu Be / Tối (`frontend/styles/studio_pro.css`, `frontend/modules/ui_enhancements.js`)**:
     - Làm mới toàn diện giao diện với hệ thống Design Token hiện đại, bo góc tinh tế, hiệu ứng chuyển cảnh mượt, thanh tiến trình 6 bước sắc nét.
     - Thêm công tắc chuyển đổi nhanh **Dark Studio Mode** <-> **Warm Beige Mode (`#F6EFE6` / `#FFFDF9`)** trên Header.
     - Thêm hệ thống phím tắt (`Ctrl+Enter`, `Ctrl+S`), bộ lọc tìm kiếm dự án tức thì, badge hiển thị số lượng mục & preset trên từng dự án, và thông báo Toast hiện đại.

   - **HẠNG MỤC 2 — Trình Xem Trước Bố Cục Video 9:16 Thời Gian Thực (`frontend/modules/live_preview_9x16.js`)**:
     - Xây dựng khung **Interactive 9:16 Storyboard & Summary Board Live Canvas** ngay ở cột phải.
     - Khi người dùng nhập kịch bản vào `#scriptInput`, gõ yêu cầu thiết kế vào `#visualPromptInput` (ví dụ: "nền màu be, ảnh bác sĩ to rõ, căn giữa địa chỉ"), hoặc tải ảnh bác sĩ lên, Canvas 9:16 phải vẽ ngay lập tức:
       1. Từng Slide mục (`1..N`) với nền màu be/tối tương ứng, tiêu đề trên cùng, khung ảnh lớn ở giữa (hiển thị ảnh thật đã tách nền/cắt), tên mục nổi bật và các pill thông tin/địa chỉ căn giữa tuyệt đối.
       2. Slide **Bảng Tổng Hợp Cuối Video (Summary Card)** hiển thị đúng số lượng mục (`TOP N ...`) để người dùng kiểm tra ngay lập tức trước khi bấm Render Remotion.
     - Có thanh điều hướng chuyển qua lại giữa các Slide (`Slide 1..N` và `Bảng Tổng Hợp`) + nút xuất ảnh chụp nhanh Slide hiện tại ra PNG.

   - **HẠNG MỤC 3 — Nâng Cấp Bộ Phân Tích Kịch Bản Trước & Kho Thẻ Yêu Cầu Thông Minh (`frontend/modules/script_inspector_pro.js`)**:
     - Nâng cấp khung `#scriptPreAnalysisBox`: cho phép sửa trực tiếp tiêu đề chính, tên từng mục, các dòng mô tả/địa chỉ ngay trên các thẻ phân tích, đổi thứ tự mục (`↑`/`↓`), thêm/xóa mục và tự động cập nhật ngược lại vào ô `#scriptInput`.
     - Tự động phát hiện và cảnh báo nếu tiêu đề ghi "6 KÊNH..." nhưng danh sách thực tế có số mục khác 6, kèm nút **"Tự động chuẩn hóa kịch bản"** 1 chạm.
     - Thêm thanh **Quick Chips Yêu Cầu Thiết Kế** ngay dưới ô `#visualPromptInput` (Nền màu be ấm `#F6EFE6`, Ảnh to rõ kịch khung, Căn giữa địa chỉ, Phong cách Bác sĩ Y khoa, Phong cách Mẹ & Bé Hồng phấn, Chữ vàng viền đậm) + lưu lịch sử các yêu cầu hay dùng vào `localStorage`.

   - **HẠNG MỤC 4 — Nâng Cấp Trình Tách Nền & Chỉnh Sửa Ảnh Bác Sĩ / Sản Phẩm Pro (`frontend/modules/doctor_editor_pro.js`, `backend/services/image_enhancer.py`)**:
     - Bổ sung tính năng **Tự động làm nét & cân bằng sáng ảnh chân dung bác sĩ (`auto_enhance_portrait`)** bằng OpenCV/Pillow (CLAHE + Unsharp Mask + khử nhiễu nhẹ + bo khung thẻ).
     - Cho phép chọn màu nền thẻ trực tiếp (Trắng kem `#FFFDF9`, Be ấm `#F6EFE6`, Xanh y khoa `#F0F7FF`, Trong suốt) và độ bo góc/viền.
     - Thêm nút **"⚡ Tách nền & Làm nét Hàng Loạt (Batch Process All)"** để xử lý tự động toàn bộ ảnh đã tải lên trong 1 lần bấm.

   - **HẠNG MỤC 5 — Bộ Kiểm Định Chất Lượng Tự Động (Auto-QA Engine), Cloud Demo Fallback & Tối Ưu Remotion (`backend/services/qa_validator.py`, `remotion/ConvoAppDynamic.tsx`, `tests/`)**:
     - Xây dựng `backend/services/qa_validator.py` với các route `/api/projects/<pid>/qa-check` và `/api/projects/<pid>/qa-autofix` + nút **"🛡️ Kiểm tra & Tự sửa lỗi bố cục (Auto-QA)"** trên giao diện.
     - Tự động đối chiếu số lượng mục giữa kịch bản gốc, `script_outline`, `storyboard.json`, thư mục `anh/products/` và bảng tổng hợp cuối video; tự động sửa nếu lệch.
     - Tinh chỉnh `remotion/ConvoAppDynamic.tsx`: bổ sung cơ chế tự động co chữ thông minh (`autoFitFontSize`) khi tên mục hoặc địa chỉ dài, căn giữa hoàn hảo các pill địa chỉ trong chế độ `chia_se`, tối ưu hiệu ứng chuyển cảnh mượt mà.
     - Tạo dữ liệu mẫu tự động (`backend/services/demo_seed.py`) khi chạy trên môi trường Cloud và viết bộ kiểm thử toàn diện `tests/test_suite.py` (chạy `pytest` xanh 100%).

4. **Quy trình Kiểm thử & Bàn giao trên Cloud**:
   - Sau mỗi hạng mục, chạy `git add . && git commit -m "..." && git push -u origin HEAD`.
   - Khởi chạy server kiểm thử (`python3 desktop_app.py --server --port 8765`), chạy toàn bộ `pytest`, kiểm tra mọi API hoạt động hoàn hảo và tổng hợp báo cáo chi tiết những gì đã nâng cấp.
```
