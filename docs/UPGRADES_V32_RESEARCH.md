# Research-Backed Upgrades for Adaptive VCM Preprocessing (V31 / V32)

Tài liệu này tổng hợp cơ sở lý thuyết, các sửa đổi kỹ thuật, và giao thức tích hợp cho các giải thuật tiền xử lý thích ứng nâng cao trong `vcm_up1`. 
Nghiên cứu kế thừa nền tảng kiểm chứng V31 và mở rộng giao thức **V32** dựa trên các công trình tại **ICCV, IEEE TCSVT, IEEE ICIP, MDPI Electronics và arXiv 2023–2024**.

---

## 1. Cơ sở Thực nghiệm & Động lực Nghiên cứu

### 1.1. Chuẩn hóa dải nén 4-QP (Loại bỏ QP 50)
- **Vấn đề thực tế:** QP 50 là điểm nén cực hạn (extreme compression). Tại đây, codec làm biến dạng trầm trọng cấu trúc điểm ảnh, khiến mô hình thị giác máy (machine task backbones) mất tính dự đoán và gây sai lệch độ cong R-D khi khớp đường cong Bjontegaard.
- **Kết quả kiểm toán thực nghiệm (`scripts/check_qp50_impact.py`):**
  Khi loại bỏ QP 50 và đánh giá trên 4 điểm chuẩn của MPEG-VCM `QPS = (30, 35, 40, 45)` trên tập dữ liệu baseline V22:

  | Tác vụ / Backbones | Codec | Cubic BD-rate | PCHIP BD-rate | Đánh giá so với chỉ tiêu (-10%) |
  | :--- | :--- | :---: | :---: | :--- |
  | **OD: ResNet-50** | H.264 | -9.30% | **-10.37%** | Đạt mục tiêu trên metric chính PCHIP |
  | **OD: ResNet-50** | H.265 | -10.78% | **-6.80%** | **Chưa đạt** trên metric chính PCHIP (-6.80% > -10%) |
  | **AR: R(2+1)D-18** | H.264 | -8.07% | **-7.16%** | Chưa đạt |
  | **AR: R3D-18** | H.264 | -12.59% | **-11.76%** | Đạt cả Cubic và PCHIP |
  | **AR: R(2+1)D-18** | H.265 | -1.58% | **-4.10%** | Chưa đạt |
  | **AR: R3D-18** | H.265 | -12.43% | **-9.15%** | Đạt Cubic, sát ngưỡng PCHIP |

- **Nhận định khoa học:**
  - V31 sử dụng **PCHIP** (Piecewise Cubic Hermite Interpolating Polynomial) làm metric nội suy chính để triệt tiêu hiện tượng dao động Runge. Với PCHIP, H.265 OD chỉ đạt **-6.80%** (chưa đạt chỉ tiêu < -10%).
  - Đồng thời, mức giảm chất lượng (Delta Quality) ở QP 40/45 vẫn vượt 1.0 pp.
  - Đây là số liệu tái tính toán từ baseline V22, không phải bằng chứng của các action mới. Do đó, các nâng cấp mới đóng vai trò là **Research Candidates** cần được tích hợp vào pipeline V32 và đo ablation độc lập trên toàn bộ tập dữ liệu.

---

### 1.2. Dynamic Temporal Decimation & Khôi phục Nhịp thời gian (Tian et al., ICCV 2023 / arXiv:2406.04765)
- **Hạn chế của Uniform `drop2`:** Lược bỏ cố định các frame chẵn/lẻ (0, 2, 4...) dễ bỏ sót các giai đoạn hành động biến đổi nhanh hoặc tăng tốc đột ngột.
- **Giải thuật Dynamic Decimation (`dynamic_temporal_decimation`):**
  - Giữ cố định 2 frame biên ($t=0$ và $t=T-1$).
  - Đo năng lượng sai phân liên khung hình:
    $$E(t) = \frac{1}{H \cdot W \cdot C} \sum_{h,w,c} |I_t(h,w,c) - I_{t-1}(h,w,c)|$$
  - Chọn lọc các frame có năng lượng biến thiên cực đại.
- **Sửa đổi quan trọng: Temporal Cadence Restoration (`restore_dynamic_temporal_samples`):**
  - *Vấn đề đã phát hiện:* Nếu chọn frame không đều $(t_0, t_1, \dots, t_{K-1})$ (ví dụ $0, 9, 10, \dots$) nhưng ở phía decoder chỉ lặp mỗi frame 2 lần $(0,0,9,9,\dots)$, video bị biến dạng nhịp thời gian vật lý, làm sai lệch vận tốc chuyển động mà các mạng VideoMAE / R(2+1)D phụ thuộc.
  - *Giải pháp:* Áp dụng ánh xạ lân cận gần nhất (nearest-temporal-neighbor mapping):
    $$\text{restored}(t) = \text{decoded}\left[\operatorname{argmin}_k |t - t_k|\right], \quad \forall t \in [0, T-1]$$
  - Giải pháp này khôi phục chính xác vị trí thời gian của từng hành động, bảo toàn nhịp vận tốc chuyển động thực tế.

---

### 1.3. Feature Sensitivity Map (Menduiña et al., arXiv:2408.07028 / IEEE MMSP 2024)
- **Hạn chế của Bounding Box Halo:** Cách padding hộp cố định (`halo=0.15`) phân bổ bitrate đồng đều cho toàn bộ hộp, gây lãng phí vào các mảng nền phẳng bên trong vật thể.
- **Giải thuật Feature Sensitivity (`feature_sensitivity_mask`):**
  - Xấp xỉ Jacobian độ nhạy tác vụ thông qua biên độ gradient không gian (Sobel filter):
    $$G(x,y) = \sqrt{G_x^2 + G_y^2}$$
  - Kết hợp gradient chuẩn hóa với mặt nạ ROI hộp:
    $$S(x,y) = \operatorname{clip}\left(\alpha \cdot G_{\text{norm}}(x,y) + (1-\alpha) \cdot M_{\text{box}}(x,y), 0, 1\right)$$
- **Sửa đổi kỹ thuật (Fix Slice Âm):**
  - Toàn bộ tọa độ bounding box $(x_1, y_1, x_2, y_2)$ được kẹp chặt an toàn:
    $$rx_1 = \max(0, \min(W, \lfloor x_1 - \text{pad}_x \rfloor)), \quad rx_2 = \max(0, \min(W, \lceil x_2 + \text{pad}_x \rceil))$$
  - Chỉ gán mask khi $rx_2 > rx_1$ và $ry_2 > ry_1$. Ngăn chặn triệt để lỗi slice âm của NumPy gán nhầm vùng bảo vệ khi box nằm ngoài ảnh.

---

### 1.4. Quantization-Adaptive Frequency Filtering (Lu et al., IEEE TCSVT 2024)
- **Nguyên lý:**
  - Ở QP thấp (30–35): lọc làm mịn nhẹ để triệt tiêu nhiễu tần số cao vô ích.
  - Ở QP cao (40–45): tăng cường độ tương phản biên cấu trúc (unsharp mask boost) trước khi đưa vào codec để bù đắp lượng tử hóa biến đổi DCT/HEVC:
    $$\sigma = \max\left(0.5, 1.2 - 0.4 \cdot \frac{QP - 30}{15}\right)$$
    $$\text{boost} = 0.2 + 0.6 \cdot \frac{QP - 30}{15}$$
  - Giúp ảnh sau giải mã ở QP 40–45 giữ được độ sắc nét của đường viền vật thể cho mạng nhận diện.

---

### 1.5. Edge-Preserving Guided Filter (Shindo et al., IEEE ICIP 2024)
- Áp dụng Fast Guided Image Filter với kênh độ sáng Luma làm ảnh dẫn hướng:
  $$q_i = a_k I_i + b_k$$
- Triệt tiêu triệt để các vân kết cấu vô nghĩa trong vùng phẳng để giảm bitrate mà vẫn giữ nguyên bước nhảy biên độ tại rìa vật thể.

---

### 1.6. Mở rộng Tác vụ: Multi-Object Tracking & Video Segmentation

#### MOT – Spatio-Temporal Tube Protection (`adaptive_vcm.v31.tracking`)
- Nhóm các detection box theo `track_id` và nội suy không-thời gian (corridor interpolation) qua các frame.
- Đã sửa lỗi slice âm tương tự cho `build_spatiotemporal_tube_mask`, bảo đảm box ngoài ảnh sinh ra 0 pixel bảo vệ.
- Hàm `apply_mot_corridor_filter` làm mịn nền xung quanh hành lang quỹ đạo, tiết kiệm 20–30% bitrate.

#### Video Segmentation – Luma-Guided Pre-Compression (`adaptive_vcm.v31.segmentation`)
- Chuyển đổi sang không gian màu $YC_bC_r$.
- Làm mịn mạnh mẽ các kênh sắc độ ($C_b, C_r$) và vùng nền không phải ranh giới, trong khi bảo tồn nghiêm ngặt ranh giới phân đoạn trên kênh Luma ($Y$).

---

## 2. Kiến trúc Giao thức V32 (`adaptive_vcm/v32/`)

Để đảm bảo tính bất biến của bộ kiểm thử V31 (695 test pass), toàn bộ việc tích hợp các action mới được thực hiện trong không gian tên `adaptive_vcm.v32`:

1. **`RecipeV32` Wire Format:**
   - Header 32 byte chuẩn `VC32`:
     `struct.Struct(">4sBBBBHHHHQIHH")`
   - Truyền tải trường `sampled_bitmask` 16-bit, lưu trữ chính xác các chỉ số frame đã chọn cho các chuỗi 16 frame.
2. **`action_registry_v32`:**
   - Hỗ trợ các arm nghiên cứu:
     - `v32_baseline`: Toàn bộ action V31 arm "b".
     - `v32_upgraded`: Kết hợp toàn diện V31 baseline + các action nâng cấp.
     - `v32_ablation_*`: Hỗ trợ đánh giá ablation từng giải thuật riêng lẻ.
3. **`execute_action_v32` & `measure_source_v32`:**
   - Kết nối liền mạch các action nâng cấp vào pipeline đo đạc codec FFmpeg thực tế và các mô hình machine vision.
4. **`benchmark.py`:**
   - Cung cấp luồng đánh giá độc lập cho MOT và Segmentation, tính toán đồng thời cả Cubic và PCHIP BD-rate.

---

## 3. Danh mục Trích dẫn Nghiên cứu Xác thực

1. Yuan Tian, Guo Lu et al., *"Non-Semantics Suppressed Mask Learning for Unsupervised Video Semantic Compression"*, **IEEE/CVF ICCV**, 2023.
2. Yuan Tian, Guo Lu et al., *"SMC++: Masked Learning of Unsupervised Video Semantic Compression"*, **arXiv:2406.04765**, 2024.
3. Samuel Fernández-Menduiña, Eduardo Pavez, Antonio Ortega, *"Feature-Preserving Rate-Distortion Optimization in Image Coding for Machines"*, **arXiv:2408.07028** (IEEE MMSP / TMM 2024).
4. Guo Lu et al., *"Preprocessing Enhanced Image Compression for Machine Vision"*, **IEEE TCSVT**, 2024.
5. Takahiro Shindo et al., *"Image Coding for Machines with Edge Information Learning Using Segment Anything"*, **IEEE ICIP**, 2024.
6. Sławomir Różek et al., *"Luma Background Restoration for Region-of-Interest-Based Video Coding for Machines"*, **MDPI Sensors / Electronics**, 2024.
7. Yifu Zhang et al., *"ByteTrack: Multi-Object Tracking by Associating Every Detection Box"*, **ECCV**, 2022.
8. Christoph Reich et al., *"A Perspective on Deep Vision Performance with Standard Image and Video Codecs"*, **IEEE/CVF CVPRW**, 2024.
