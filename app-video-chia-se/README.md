# App "Video Chia Sẻ Hội Thoại 2 Người" — Bản Cục Bộ 100% (Agy CLI / Codex CLI)

Ứng dụng đóng gói toàn bộ quy trình sản xuất video hội thoại 2 người (`1080×1080`, `30fps`, chuẩn âm `-14 LUFS`) chạy cục bộ trên máy Windows 11 của sếp Dũng, **không gọi API ngoài** mà tận dụng trực tiếp:
- `faster-whisper` (`large-v3` CUDA local qua `C:\Users\Dung\Developer\video-use\helpers\local_asr.py`)
- `ffmpeg` / `ffprobe` (mọi tiến trình con chạy ẩn `creationflags=0x08000000`, không bật cửa sổ đen)
- `Remotion` (`C:\Users\Dung\Developer\remotion-starter`)
- **Agy CLI** (`C:\Users\Dung\AppData\Local\agy\bin\agy.exe`) & **Codex CLI** (`codex.exe` Account 1 / Account 2) cho các bước AI lập danh sách cắt và nhìn ảnh contact sheet.

---

## 1. Cách mở App (1 Click)

Nhấp đúp vào một trong hai file:
- `E:\vd chia se\Chay_App.bat`
- Hoặc `H:\source\vd-chia-se-app-goi\Chay_App.bat`

App sẽ khởi động server ngầm (`pythonw.exe`, không hiện cửa sổ console) và tự động mở trình duyệt tại `http://127.0.0.1:8765`.

---

## 2. Luồng 10 Bước & 3 Điểm Dừng Duyệt

1. **Bước Nhập**: Kéo thả hoặc bấm chọn Clip HỎI (A), Clip ĐÁP (B), Clip phụ (tùy chọn, ví dụ `IMG_0138.mov`), chọn bố cục (**A. Chia sẻ** hoặc **B. Giỏ đồ**), nhập tiêu đề, kịch bản và bảng sản phẩm (`bang.json`). Có nút **⇄ Đổi bên HỎI/ĐÁP** và nút **⚡ Nạp mẫu Giỏ đồ 1TR**.
2. **Bước 1 — Chuẩn bị**: Tạo thư mục dự án (`nguon/`, `text/`, `anh/`, `media/`, `final/`, `logs/`, `reports/`), chuẩn hóa nguồn về `720×1280` CFR `30fps`.
3. **Bước 2 — Phân tích âm thanh**: Quét mức năng lượng âm thanh (`-48 dBFS`, khoảng lặng `0.25s`, cửa sổ im `≥3s`) và chạy `faster-whisper` theo từng cụm. Tự động gắn nhãn `[ẢO]` cho các câu Whisper bịa. Kèm công cụ **Quét mịn đoạn vấp (`--from --to --gap 0.06`)** ngay trên giao diện.
4. **Bước 3 — Lập danh sách cắt (`cut.json`)**: Gọi **Agy CLI** (tự fallback sang **Codex 2 CLI**) lập `cut.json` giữ take cuối hoàn chỉnh, gắn `item` lần đầu nhắc tới, trích file âm thanh nghe thử cho từng piece và `voice_preview.wav`.
   - **★ DỪNG 1**: Sếp nghe thử từng piece, xem danh sách `dropped` (kèm lý do) và `unsure`, chỉnh sửa trực tiếp nếu cần rồi bấm **Duyệt DỪNG 1**.
5. **Bước 4 — Chọn cảnh người nghe (`idle.json`)**: Dò khoảng im `< -55 dBFS` (cách tiếng nói `≥1.5s`, dài `≥2.0s`), tạo contact sheet `2 khung/giây` và gọi **Codex 2 CLI (`-i <ảnh>`)** / **Agy CLI** chấm `GOOD`/`BAD` (miệng khép, tay dưới ngực, mắt nhìn chếch về người nói, không nhìn thẳng ống kính).
   - **★ DỪNG 2**: Sếp xem contact sheet 2fps, chọn/đổi ứng viên hoặc gắn **Clip phụ** riêng cho từng lượt nghe (ví dụ Lượt 4 gắn `IMG_0138.mov` `120.87s–122.17s`), rồi bấm **Duyệt DỪNG 2**.
6. **Bước 5 — Dựng Timeline & Media**: Tạo các đoạn video `720×1280` tốc độ `1.3x`, `voice.wav`, `sfx`, `timeline.json`.
   - **Kiểm tra bắt buộc NGUYÊN TẮC SỐ 1**: Lập bảng kiểm từng lượt nói; nếu bất kỳ lượt đang nói nào bị gắn nhầm clip `idle`, hệ thống báo lỗi đỏ và dừng ngay, không cho render.
   - **Luật hòa tan (Dissolve)**: Hòa tan 4 frame giữa các đoạn cùng vai; tự động **cắt thẳng (hard cut)** ở biên chuyển giữa clip nói và cảnh người nghe để không bị bóng ma.
7. **Bước 6 — Ảnh sản phẩm & Bảng giá**: Ghép tên sản phẩm với thư viện ảnh không nền (`G:\Công Việc\Tiktok\sản phẩm không nền`), tự động crop sát biên alpha + lề trong suốt 2%, tạo `_contact.png` trên 2 nền sáng/tối, định dạng giá có khoảng trắng trước chữ `K` (`60 K` hoặc che số cuối `6x K`, giữ `5 K`, tổng `1.13x K`).
8. **Bước 7 — Ảnh mẫu Remotion (Stills)**: Render 3 khung ảnh mẫu `1080×1080` (Mở đầu, Thân bài, Bảng tổng cuối).
   - **★ DỪNG 3**: Sếp bấm phóng to kiểm tra dấu tiếng Việt (`GIỎ`), cỡ chữ, vị trí `cropA/B`, `scaleA/B`, `topA/B`; nếu cần chỉnh thì bấm **Lưu & Chụp lại Bước 7**, ưng ý thì bấm **Duyệt DỪNG 3**.
9. **Bước 8 — Render + Chuẩn âm + Bản nén**: Render Remotion `CRF 18` chạy nền có thanh tiến độ thực tế → chuẩn âm 2 lượt EBU R128 (`-14 LUFS`, `TP ≤ -1 dBTP`, `AAC 192k`) → xuất thêm bản nén `CRF 26` (`<30MB` gửi điện thoại) ra `H:\source\<tên>_vN.mp4` và `<tên>_vN_nen.mp4` (tự tăng số `v1, v2...`, không bao giờ ghi đè).
10. **Bước 9 & 10 — Tự kiểm (`checks.md`) & Xuất**: Đo `ffprobe`, đo `loudnorm`, chạy Whisper đọc lại `voice.wav` cuối, đo tương quan chuyển động vùng mặt/miệng với âm thanh, tạo contact sheet `1 khung/giây` toàn video + `2 khung/giây` người nghe, ghi rõ cái gì đã kiểm tự động và cái gì cần mắt người vào `checks.md`.
