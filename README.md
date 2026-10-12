# Video Coding for Machines (VCM) - Adaptive Preprocessing Engine (V31 / V32)

Repository nghiên cứu và phát triển hệ thống tiền xử lý thích ứng (Adaptive Preprocessing) cho **Video Coding for Machines (VCM)**. 
Dự án kế thừa nền tảng kiểm chứng kỹ thuật nghiêm ngặt từ nhánh `v31-actions` (phân lập FIT/CAL/TUNE/DEV, mã hóa H.264/H.265 thực tế với FFmpeg, tính toán byte metadata trên wire, kiểm tra hash phục hồi khi resume, chốt guard và bootstrap), đồng thời xây dựng giao thức **V32** để tích hợp và đánh giá độc lập các giải thuật tiền xử lý tiên tiến từ các hội nghị và tạp chí hàng đầu (**ICCV, IEEE TCSVT, IEEE ICIP, MDPI Electronics, arXiv 2023–2024**).

---

## 🔬 Kiểm toán Thực nghiệm: Dải nén 4-QP (Bỏ QP 50)

Trước đây, việc đưa điểm nén cực hạn **QP 50** vào tính toán BD-rate gây sai lệch lớn do cấu trúc điểm ảnh bị phá vỡ nặng nề và mAP sụt giảm nghiêm trọng.

Kết quả kiểm toán thực nghiệm trực tiếp khi loại bỏ QP 50 bằng script [`scripts/check_qp50_impact.py`](file:///C:/Users/Wagur1/vcm_up1/scripts/check_qp50_impact.py) trên dải 4 QP chuẩn `QPS = (30, 35, 40, 45)`:

| Tác vụ / Mô hình | Codec | 5-QP BD-rate (Cubic / PCHIP) | 4-QP BD-rate (Cubic / PCHIP) | Độ lệch chất lượng tối đa tại 4-QP | Trạng thái chỉ tiêu (-10%) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **OD: ResNet-50** | H.264 | -9.66% / -9.79% | **-9.30% / -10.37%** | QP 45: -1.02 pp | Đạt với PCHIP (-10.37%) |
| **OD: ResNet-50** | H.265 | -6.57% / -6.77% | **-10.78% / -6.80%** | QP 40: -1.05 pp | **Chưa đạt** với PCHIP (-6.80%) |
| **AR: R(2+1)D-18** | H.264 | -5.92% / -4.84% | **-8.07% / -7.16%** | QP 35: -3.12 pp | Chưa đạt |
| **AR: R3D-18** | H.264 | -10.55% / -10.27% | **-12.59% / -11.76%** | QP 35: -0.78 pp | Đạt cả 2 metric |
| **AR: R(2+1)D-18** | H.265 | -3.98% / -4.45% | **-1.58% / -4.10%** | QP 40: -3.91 pp | Chưa đạt |
| **AR: R3D-18** | H.265 | -6.46% / -6.15% | **-12.43% / -9.15%** | QP 30: +0.78 pp | Đạt với Cubic, sát ngưỡng PCHIP |

### 📌 Ghi chú Khoa học & Minh bạch Kết quả:
1. **PCHIP là metric nội suy chính của V31:** Trên H.265 Object Detection, nội suy Cubic cho kết quả -10.78%, nhưng nội suy đơn điệu PCHIP (tránh dao động Runge) chỉ đạt **-6.80%**. Do đó, mục tiêu BD-rate < -10% trên H.265 OD **chưa đạt**.
2. **Nguồn gốc dữ liệu:** Bảng số liệu trên là kết quả tính toán lại từ baseline V22 khi bỏ điểm QP 50. Đây **chưa phải là bằng chứng thực nghiệm của các hành động nâng cấp mới**.
3. **Mức suy giảm chất lượng tác vụ:** Tại một số điểm nén cao (QP 40/45), mức giảm chất lượng mAP/Top-1 vẫn vượt ngưỡng biên 1.0 điểm phần trăm (-1.02 pp ở QP 45 H.264; -1.05 pp ở QP 40 H.265).
4. **Định vị các nâng cấp mới:** Các giải thuật tiền xử lý mới (Dynamic Decimation, Feature Sensitivity, Quant-Adaptive Filtering...) hiện đóng vai trò là **các giả thuyết và phương án cải tiến nghiên cứu (Research Candidates)** trong giao thức V32, cần được đánh giá ablation toàn diện trên tập dữ liệu đầy đủ.

---

## 🛠 Kiến trúc Giao thức: V31 Frozen và V32 Protocol

Hệ thống được tổ chức thành 2 tầng giao thức độc lập nhằm bảo đảm tính toàn vẹn nghiên cứu:

```text
vcm_up1/
├── adaptive_vcm/
│   ├── v31/                     # GIAO THỨC V31 (ĐÃ KHÓA / FROZEN)
│   │   ├── actions.py           # Bộ action V31 bất biến (identity, drop2, background, area)
│   │   ├── transport.py         # Wire format 32-byte chuẩn VC31
│   │   ├── protocol.py          # Khóa tập QPS = (30, 35, 40, 45) và quy tắc guard
│   │   ├── measure.py           # Đo đạc codec thật với cache hash bất biến
│   │   ├── tracking.py          # Module hỗ trợ MOT: Spatio-temporal tube protection
│   │   ├── segmentation.py      # Module hỗ trợ Segmentation: Luma-guided boundary preservation
│   │   └── upgrades.py          # Các hàm thuật toán nâng cấp (đã fix negative-slice & task check)
│   ├── v32/                     # GIAO THỨC V32 (MỞ RỘNG & TÍCH HỢP TOÀN DIỆN)
│   │   ├── protocol.py          # Định nghĩa các arm V32: v32_baseline, v32_upgraded, v32_ablation_*
│   │   ├── transport.py         # RecipeV32 wire format (VC32) truyền bitmask sample_indices
│   │   ├── actions.py           # Bộ action registry V32 kết nối liền mạch action mới
│   │   ├── measure.py           # Pipeline đo đạc codec thật cho action V32
│   │   └── benchmark.py         # Công cụ đo lường ablation độc lập (MOT, Segmentation, BD-rate)
│   └── codec.py                 # Bộ mã hóa/giải mã H.264 & H.265 tiêu chuẩn qua FFmpeg
├── docs/
│   └── UPGRADES_V32_RESEARCH.md # Cơ sở toán học và đối sánh chi tiết
├── scripts/
│   ├── check_qp50_impact.py     # Script kiểm toán 4-QP vs 5-QP
│   └── monitor_and_shard.py     # Quản lý phân tán tác vụ Kaggle GPU
└── tests/
    ├── test_v31_upgrades.py     # Kiểm thử đơn vị chuyên sâu (OOB boxes, cadence, task check)
    └── test_v32_protocol.py     # Kiểm thử giao thức V32, wire format VC32 và benchmark
```

### Các lỗi kỹ thuật đã được xử lý triệt để:
- **Khôi phục nhịp thời gian (Temporal Cadence Restoration):** Thêm hàm `restore_dynamic_temporal_samples` thực hiện ánh xạ lân cận gần nhất (nearest-temporal-neighbor mapping) $k^*(t) = \operatorname{argmin}_k |t - t_k|$. Khung hình được phục hồi đúng tọa độ thời gian thực thay vì nhân đôi đồng đều (`repeat_factor=2`), bảo toàn nhịp chuyển động cho các mô hình Action Recognition.
- **Xử lý triệt để lỗi Negative Slices:** Toàn bộ tọa độ hộp trong `feature_sensitivity_mask` ([`upgrades.py`](file:///C:/Users/Wagur1/vcm_up1/adaptive_vcm/v31/upgrades.py)) và `build_spatiotemporal_tube_mask` ([`tracking.py`](file:///C:/Users/Wagur1/vcm_up1/adaptive_vcm/v31/tracking.py)) được kẹp chặt trong khoảng $[0, W]$ và $[0, H]$. Kiểm tra `rx2 > rx1 and ry2 > ry1` ngăn chặn tình trạng slice âm của NumPy gán nhầm giá trị bảo vệ cho toàn khung hình khi box nằm ngoài ảnh.
- **Kiểm tra tương thích đầu vào:** `execute_upgraded_action` kiểm tra nghiêm ngặt `action.task == source["task"]`, lập tức báo lỗi `ValueError` nếu truyền chéo dữ liệu (ví dụ source OD truyền vào action AR).

---

## 🚀 Các Phương pháp Tiền xử lý Khoa học (V32 Candidates)

| Module | Tác vụ | Phương pháp nâng cấp | Nghiên cứu nền tảng |
| :--- | :--- | :--- | :--- |
| `adaptive_vcm.v31.upgrades` | **Action Recognition** | **Dynamic Temporal Decimation & Cadence Restoration:** Chọn lọc keyframe theo năng lượng sai phân chuyển động $E(t) = \frac{1}{HW}\sum\|I_t - I_{t-1}\|$ và khôi phục nhịp thời gian nearest-neighbor. | *Tian et al., ICCV 2023 (SMC) & arXiv:2406.04765 (SMC++)* |
| `adaptive_vcm.v31.upgrades` | **Object Detection** | **Feature Sensitivity Map:** Xấp xỉ Jacobian độ nhạy tác vụ qua biên độ gradient không gian kết hợp ROI box an toàn, thay thế halo thô. | *Menduiña et al., arXiv:2408.07028 (FPRDO / IEEE MMSP 2024)* |
| `adaptive_vcm.v31.upgrades` | **AR & OD** | **Quantization-Adaptive Filtering:** Tự động điều chỉnh cân bằng giữa làm mịn nhiễu và tăng cường độ tương phản biên cấu trúc theo QP. | *Lu et al., IEEE TCSVT 2024* |
| `adaptive_vcm.v31.upgrades` | **Tất cả tác vụ** | **Edge-Preserving Guided Filter:** Làm phẳng vân kết cấu nền để giảm bitrate mà không làm suy giảm gradient biên vật thể. | *Shindo et al., IEEE ICIP 2024* |
| `adaptive_vcm.v31.tracking` | **MOT** | **Spatio-Temporal Tube Protection:** Bảo vệ hành lang không-thời gian liên tục của các tracklet, chống đứt gãy trajectory. | *Zhang et al., ECCV 2022 (ByteTrack)* |
| `adaptive_vcm.v31.segmentation` | **Segmentation** | **Luma-Guided Pre-Compression:** Bảo tồn độ phân giải biên độ sáng Luma ($Y$), làm mịn mạnh các kênh màu ($C_b, C_r$). | *Różek et al., MDPI Sensors / Electronics 2024* |

---

## 🛠 Hướng dẫn Cài đặt & Chạy Kiểm thử

### Cài đặt môi trường
Yêu cầu Python 3.10+ và FFmpeg (hỗ trợ libx264, libx265):
```bash
pip install -e .
```

### Chạy kiểm thử tự động
Chạy toàn bộ các bài test nâng cấp và giao thức V32:
```bash
python -m pytest tests/test_v31_upgrades.py tests/test_v32_protocol.py -v
```

Chạy kiểm thử nền tảng V31:
```bash
python -m pytest tests/test_v31_protocol.py tests/test_v31_codec.py tests/test_v31_actions.py -v
```

Kiểm tra số liệu 4-QP vs 5-QP:
```bash
python scripts/check_qp50_impact.py
```

---

## 📖 Danh mục Trích dẫn Nghiên cứu Khoa học Xác thực

1. Yuan Tian, Guo Lu et al., *"Non-Semantics Suppressed Mask Learning for Unsupervised Video Semantic Compression"*, **IEEE/CVF International Conference on Computer Vision (ICCV)**, 2023, pp. 13622-13631.
2. Yuan Tian, Guo Lu et al., *"SMC++: Masked Learning of Unsupervised Video Semantic Compression"*, **arXiv:2406.04765**, 2024.
3. Samuel Fernández-Menduiña, Eduardo Pavez, Antonio Ortega, *"Feature-Preserving Rate-Distortion Optimization in Image Coding for Machines"*, **arXiv:2408.07028** / **IEEE 26th International Workshop on Multimedia Signal Processing (MMSP)**, 2024.
4. Guo Lu et al., *"Preprocessing Enhanced Image Compression for Machine Vision"*, **IEEE Transactions on Circuits and Systems for Video Technology (TCSVT)**, 2024.
5. Takahiro Shindo et al., *"Image Coding for Machines with Edge Information Learning Using Segment Anything"*, **IEEE International Conference on Image Processing (ICIP)**, 2024.
6. Sławomir Różek et al., *"Luma Background Restoration for Region-of-Interest-Based Video Coding for Machines"*, **MDPI Sensors / Electronics**, 2024.
7. Christoph Reich et al., *"A Perspective on Deep Vision Performance with Standard Image and Video Codecs"*, **IEEE/CVF CVPRW**, 2024.
8. Marc Windsheimer et al., *"On Annotation-Free Optimization of Video Coding for Machines"*, **arXiv:2407.21327**, 2024.
9. Yifu Zhang et al., *"ByteTrack: Multi-Object Tracking by Associating Every Detection Box"*, **European Conference on Computer Vision (ECCV)**, 2022.
