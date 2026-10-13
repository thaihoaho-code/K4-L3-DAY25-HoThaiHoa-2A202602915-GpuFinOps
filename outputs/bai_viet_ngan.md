# Tối ưu chi phí GPU cho NimbusAI

## 1. Baseline và phương án tối ưu

Theo báo cáo M5, chi phí mô phỏng giảm từ **$27.133/tháng** xuống **$14.626/tháng**, tiết kiệm **$12.507 (46,1%)**. Riêng inference, M2 xử lý 2.400 request với tổng 7.533.027 token: chi phí giảm từ **$48,87/ngày** xuống **$8,48/ngày**, tương đương từ **$6,488 xuống $1,126 cho mỗi triệu token**. Mức giảm inference là **82,6%**.

Baseline inference giả định mọi request chạy model lớn, không cache và không batch. Phương án tối ưu dùng cascade theo `route_tier`, tính giá thấp hơn cho input đã cache và giảm 50% giá request batch. Đây là kết quả mô phỏng theo giá trong catalog tháng 6/2026, không phải hóa đơn thực tế.

## 2. Đòn bẩy tiết kiệm

| Đòn bẩy | Tiết kiệm/tháng |
|---|---:|
| Mua GPU bằng spot/reserved | **$10.040** |
| Cascade, cache và batch cho inference | $1.212 |
| Right-size GPU bị Util Lie | $655 |
| Tắt GPU nhàn rỗi | $600 |
| **Tổng** | **$12.507** |

Đòn bẩy mua GPU đóng góp nhiều nhất, khoảng **80% tổng khoản tiết kiệm**. M3 đưa workload chạy liên tục sang reserved và workload có thể gián đoạn sang spot có checkpoint; nhờ vậy giá mỗi GPU-giờ thấp hơn on-demand. Đây là nơi nên ưu tiên kiểm tra hợp đồng, mức sử dụng thực tế và khả năng chịu gián đoạn trước khi cam kết.

Inference giảm 82,6% trên đơn vị `$/1M-token` nhờ kết hợp ba thay đổi. Batch giảm một nửa phần giá được áp dụng; cache giảm giá input cache còn 10%; cascade chuyển request phù hợp sang model nhỏ hơn. Các mức giảm nhân với nhau ở phần chi phí liên quan, vì vậy cần nhìn chi phí/token sau khi ghép các đòn bẩy, không cộng phần trăm giảm một cách đơn giản.

## 3. GPU-Util Lie và tác động tài chính

M1 gắn cờ hai GPU theo điều kiện GPU-Util trung bình từ 90% nhưng MFU dưới 30%:

- `gpu-h100-4`: GPU-Util **98,2%**, MFU **19,4%**, MBU **20,7%**.
- `gpu-a10g-1`: GPU-Util **96,9%**, MFU **26,8%**, MBU **30,2%**.

GPU-Util cho biết GPU bận trong bao lâu; MFU cho biết tốc độ tính toán đạt được so với mức tối đa. Vì thế Util cao tự nó không chứng minh GPU đang làm việc hiệu quả. Báo cáo M5 ước tính chuyển mỗi GPU xuống một loại nhỏ hơn tiết kiệm **$655/tháng**: H100 sang A100 và A10G sang L4, giả định chạy 24 giờ/ngày trong 30 ngày. M1 còn ghi nhận 8 giờ nhàn rỗi trên `gpu-h100-5`; theo giá H100 $2,50/giờ, phần này là **$20/ngày**, hay **$600/tháng** nếu lặp lại mỗi ngày. Cần benchmark latency và chất lượng trước khi áp dụng right-sizing cho production.

## 4. Phân tích mở rộng đã đo

**Ngân sách reasoning.** M2 hiện phân tách chi phí và năng lượng theo `is_reasoning`. Trong 2.400 request, có 201 request reasoning (**8,4%**) với 1.241.156 token (**16,5%** tổng token). Theo giả định trong `sustainability.py` — 0,30 Wh/1.000 token và reasoning dùng năng lượng gấp 80 lần — nhóm này chiếm **$1,40/ngày (16,5% chi phí inference tối ưu)** và khoảng **29.788 Wh**, tương đương **94,0% năng lượng** ước tính của toàn bộ traffic (31.675 Wh). Nếu nhóm reasoning dùng mức năng lượng thường, phần tăng thêm là khoảng **29,4 kWh**. Insight: 8,4% số request chiếm 94% năng lượng; NimbusAI nên chỉ bật reasoning khi độ phức tạp task vượt ngưỡng đã định và theo dõi giới hạn theo team. Phần mở rộng được tính trực tiếp trong `missions/m2_inference_levers.py`.

**Lịch carbon cho job có thể gián đoạn.** M3 hiện tính theo từng workload `interruptible=1`. Tổng năng lượng theo công suất GPU trong catalog và lịch chạy là **1.789 kWh**. Chuyển giả định các job này từ `us-east-1` sang vùng sạch nhất trong catalog, `europe-north1`, giảm phát thải ước tính từ **679,8 xuống 53,7 kg CO₂e**, tiết kiệm **626,2 kg (92,1%)**. Đây là phép tính theo công suất định mức và giả định toàn bộ workload chuyển vùng; chưa tính PUE, mức tải thực, độ trễ mạng hay giới hạn vị trí dữ liệu. Insight: job training có thể checkpoint là ứng viên tốt để xếp lịch theo vùng có điện sạch hơn. Phần mở rộng được triển khai trong `missions/m3_purchasing.py`.

## 5. Ba hành động đầu tiên cho NimbusAI

1. **Đo lại hiệu quả và right-size hai GPU bị gắn cờ.** Thu thập latency, throughput, MFU/MBU và mức sử dụng bộ nhớ; thử A100 thay H100 và L4 thay A10G trên workload đại diện trước khi chuyển tải.
2. **Chuyển job có thể gián đoạn sang spot có checkpoint; dành reserved cho tải ổn định.** Theo dõi interruption, tỷ lệ hoàn tất và mức sử dụng để xác nhận khoản tiết kiệm M3 có đạt được trong thực tế.
3. **Đưa chi phí/token và năng lượng vào chính sách routing.** Bật batch/cache khi phù hợp, dùng cascade sang model nhỏ cho request đơn giản, đặt giới hạn cho reasoning và đánh giá vùng chạy theo cả giá điện lẫn carbon.
