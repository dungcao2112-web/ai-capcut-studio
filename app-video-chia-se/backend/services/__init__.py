# -*- coding: utf-8 -*-
"""Các dịch vụ mở rộng (module nhỏ gọn) cho App Video Chia Sẻ Hội Thoại 2 Người.

- cloud_env      : Fallback đường dẫn Windows -> Linux/Cloud (Cloud Demo Mode)
- demo_seed      : Tạo sẵn 2 dự án mẫu khi chạy trên Cloud
- project_meta   : Badge số mục / preset cho danh sách dự án
- visual_prompt  : Phân tích "Yêu cầu thiết kế" (visual_prompt) -> cấu hình giao diện video
- image_enhancer : Làm nét, cân bằng sáng, nền thẻ, tách nền dự phòng & xử lý hàng loạt
- qa_validator   : Bộ kiểm định chất lượng tự động (Auto-QA) + tự sửa lỗi
- api_routes     : Đăng ký các route API mới (không đụng route cũ)
"""
