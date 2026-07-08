# Stock Tracker (đa mã) — Bot theo dõi cổ phiếu tự động qua Telegram

Hệ thống chạy hoàn toàn miễn phí trên GitHub Actions, theo dõi **tối đa 10 mã
cổ phiếu cùng lúc** (HOSE/HNX/UPCoM) mỗi 5 phút trong giờ giao dịch, gửi cảnh
báo khẩn khi có tín hiệu mua/breakout/stoploss, và báo cáo tổng kết cuối ngày
gộp tất cả các mã — tất cả qua Telegram.

---

## Bước 1: Tạo bot Telegram (2 phút)

1. Mở Telegram, tìm **@BotFather**, bấm Start.
2. Gõ `/newbot` → đặt tên bot → đặt username (kết thúc bằng `bot`).
3. BotFather trả về **token** dạng `1234567890:AAHxxx...`
   → copy lại, đây là **TELEGRAM_TOKEN**.
4. Tìm bot vừa tạo, bấm **Start** (bắt buộc để bot nhắn được cho bạn).

## Bước 2: Lấy Chat ID

1. Tìm bot **@userinfobot**, bấm Start.
2. Nó trả về `Id: 123456789` → copy, đây là **TELEGRAM_CHAT_ID**.

## Bước 3: Đưa code lên GitHub

1. Tạo tài khoản github.com (nếu chưa có).
2. **New repository** → đặt tên tùy ý → chọn **Public**
   (bắt buộc Public để GitHub Actions miễn phí không giới hạn) → Create.
3. Upload toàn bộ file lên repo (Add file → Upload files). Riêng file
   `.github/workflows/tracker.yml` tạo bằng **Add file → Create new file**,
   gõ đường dẫn `.github/workflows/tracker.yml` rồi dán nội dung.

## Bước 4: Cài token vào GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret**, tạo 2 cái:
- `TELEGRAM_TOKEN` = token từ Bước 1
- `TELEGRAM_CHAT_ID` = số từ Bước 2

> Secrets được mã hóa, không ai xem được kể cả khi repo Public.

## Bước 5: Bật quyền ghi cho workflow

**Settings → Actions → General → Workflow permissions** →
chọn **Read and write permissions** → Save.

## Bước 6: Chạy thử

Tab **Actions** → workflow **Stock Tracker** → **Run workflow**.
Sau đó nhắn `/status` cho bot — câu trả lời đến ở lần chạy kế tiếp
(tối đa ~5 phút trong phiên).

Từ đây hệ thống tự chạy mỗi 5 phút (9h00–14h45, thứ 2–6) và gửi báo cáo
tổng kết ~15h30 mỗi ngày.

---

## Các lệnh Telegram

| Lệnh | Chức năng |
|---|---|
| `/list` | Danh sách mã đang theo dõi và chế độ từng mã |
| `/add HQC` | Thêm mã mới (tự kiểm tra mã có tồn tại, mặc định chế độ auto) |
| `/remove HQC` | Bỏ theo dõi một mã |
| `/status` | Trạng thái tất cả mã (giá, RSI, MACD, volume, các mốc) |
| `/status NRC` | Trạng thái riêng 1 mã |
| `/config` | Xem toàn bộ cấu hình |
| `/mode NRC auto` / `/mode NRC manual` | Đổi chế độ ngưỡng của mã |
| `/set NRC buy_zone_low 5200` | Đặt ngưỡng riêng cho mã (chế độ manual) |
| `/setsignal volume_spike_ratio 3` | Đổi ngưỡng tín hiệu chung mọi mã |
| `/help` | Danh sách lệnh |

**Lưu ý:** bot xử lý lệnh ở lần chạy kế tiếp → trả lời trễ tối đa ~5 phút
trong phiên giao dịch. Ngoài giờ giao dịch bot không chạy nên lệnh sẽ được
xử lý vào lần chạy đầu tiên của phiên kế tiếp.

### Khóa dùng với /set (ngưỡng riêng từng mã)
`buy_zone_low`, `buy_zone_high`, `breakout_level`, `stoploss_level`,
`target_low`, `target_high`

### Khóa dùng với /setsignal (ngưỡng chung)
`volume_spike_ratio`, `rsi_oversold`, `rsi_overbought`

---

## Hai chế độ ngưỡng (đặt riêng cho từng mã)

- **manual**: dùng các con số bạn đặt qua `/set` hoặc file config.
  Mã NRC đang cài sẵn theo kịch bản đã phân tích: vùng mua 5.300–5.500đ,
  breakout 6.500đ, stoploss 4.800đ, mục tiêu 7.500–8.500đ.
- **auto**: hỗ trợ = đáy 30 phiên, kháng cự = đỉnh 50 phiên, vùng mua =
  hỗ trợ +3%, tự cập nhật mỗi lần chạy. Mã thêm bằng `/add` mặc định
  dùng chế độ này — tiện khi bạn chưa phân tích kỹ mã đó.

## Các loại cảnh báo tự động (áp dụng độc lập cho từng mã)

| Tín hiệu | Điều kiện |
|---|---|
| 🟢 Điểm mua | Giá vào vùng mua + RSI không quá cao |
| 🚀 Breakout xác nhận | Vượt kháng cự + volume ≥ 2,5x TB20 |
| ⚠️ Breakout yếu | Vượt kháng cự nhưng volume thấp (nghi bull trap) |
| 🔴 Stoploss | Giá thủng mức stoploss |
| 📊 Volume đột biến | Khối lượng ≥ 3,75x trung bình 20 phiên |
| 📈 MACD cắt lên | Động lượng tăng hình thành |

Mỗi loại cảnh báo có cooldown 60 phút **tính riêng cho từng mã** —
NRC vừa báo điểm mua không làm chặn cảnh báo điểm mua của HQC.

## Giới hạn & lưu ý

- Tối đa **10 mã** cùng lúc (giữ mỗi lần chạy dưới vài phút và tránh gọi
  API quá dày). Muốn nâng: sửa `MAX_SYMBOLS` trong `main.py`.
- Nếu một mã lỗi dữ liệu, các mã còn lại vẫn chạy bình thường; mã lỗi
  được ghi chú trong báo cáo cuối ngày.
- API miễn phí thỉnh thoảng chập chờn — hệ thống tự thử lại chu kỳ sau.
- Lịch GitHub Actions có thể trễ 1–3 phút so với giờ đặt (bình thường).

---

## Các giới hạn vận hành cần biết (đọc kỹ)

1. **Lịch chạy có thể trễ 1–15 phút** lúc GitHub cao điểm — bình thường
   với nền tảng miễn phí, hệ thống đã được thiết kế chịu được điều này.
2. **Lệnh Telegram gửi ngoài giờ giao dịch** sẽ được xử lý ở lần chạy
   đầu tiên của phiên kế tiếp. Telegram chỉ giữ lệnh chưa xử lý trong
   ~24 giờ — lệnh gửi tối thứ 6 có thể bị mất trước sáng thứ 2. Nên
   gửi lệnh trong ngày giao dịch.
3. **Volume trong phiên được quy đổi theo thời gian**: lúc 9h30 sáng
   volume tích lũy mới đạt một phần ngày, hệ thống tự quy đổi tương
   đương cả ngày để so với trung bình 20 phiên (có chặn dưới 20% để
   tránh phóng đại đầu phiên). Con số "x TB20" trong cảnh báo giữa
   phiên là con số đã quy đổi.
4. **Cooldown mặc định 240 phút cho mỗi (mã, loại tín hiệu)** — cùng
   một tín hiệu của cùng một mã tối đa lặp lại ~2 lần/ngày. Đổi bằng
   cách sửa "cooldown_minutes" trong config.json.
5. **Repo sẽ tích lũy nhiều commit** ("update state") theo thời gian —
   vô hại, đó là cách hệ thống lưu trạng thái miễn phí.
6. Nếu bạn **sửa config.json trên web GitHub**, hệ thống tự hợp nhất
   với trạng thái đang chạy (đã có cơ chế pull-rebase, thử lại 3 lần).
