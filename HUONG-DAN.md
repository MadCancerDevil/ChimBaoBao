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

---

# PHIÊN BẢN 3 — Các tính năng mới

## Phân tích nâng cao (tự động, không cần cài gì thêm)

- **Mô hình nến** (~10 mẫu kinh điển: Búa, Sao Băng, Nhấn chìm, Sao Mai/Hôm,
  Doji, Marubozu, 3 chàng lính/3 con quạ...) kèm **chấm điểm hợp lưu 0-5**
  (mô hình + vị trí hỗ trợ/kháng cự + RSI + volume + xu hướng tuần).
  Chỉ cảnh báo khi đạt từ 3/5 điểm — tránh nhiễu. Tín hiệu trong phiên
  gắn nhãn "⏳ nến chưa đóng - chờ xác nhận".
- **Xu hướng đa khung**: 1 tuần / 1 tháng / 3 tháng / 9 tháng, hiển thị
  trong /status và báo cáo cuối ngày.
- **Swing đỉnh-đáy gần nhất** (kèm ngày) + **phân kỳ RSI/MACD** trên cả
  khung ngày và khung tuần.
- **Vùng Fibonacci**: cản trên / đỡ dưới gần nhất theo con sóng chính.
- **Mô hình cụm giá**: hình chữ nhật tích lũy, 2-3 đỉnh/đáy, hội tụ
  (tam giác/nêm), Vai-Đầu-Vai. Theo dõi ngầm trong /status; chỉ bắn
  cảnh báo khẩn khi **phá vỡ kèm volume đạt chuẩn**, kèm giá mục tiêu
  đo từ chiều cao mẫu hình.

## Danh mục cá nhân (tính riêng từng người trong group)

| Lệnh | Chức năng |
|---|---|
| `/avg NRC 5400` | Đặt giá vốn NRC của BẠN (ai gõ tính người đó) |
| `/avg NRC 5400 2000` | Kèm số lượng để tính lãi/lỗ theo tiền |
| `/avg NRC 5150` (gõ lại) | Ghi đè giá vốn mới sau khi trung bình giá |
| `/unavg NRC` | Xóa khỏi danh mục của bạn |
| `/pl` | Lời/lỗ của bạn + gợi ý chốt lời/hòa vốn/cắt lỗ theo mốc kỹ thuật |
| `/plall` | Tổng hợp cả nhóm |

Cảnh báo tự động: **từ lời thành lỗ** (từng lời ≥5% nay âm — báo 1 lần,
tự kích hoạt lại khi hồi phục) và **chạm ngưỡng lỗ** -5%, -10% (đổi trong
config.json → mục "portfolio"). Gợi ý vị thế là máy ghép giá vốn với mốc
kỹ thuật, mang tính tham khảo — không phải khuyến nghị đầu tư.

Lệnh `/setsignal` đã bỏ; các ngưỡng tín hiệu chung vẫn chỉnh được trong
`config.json` → mục "signals".

## Dùng trong group Telegram

1. Tạo group, thêm bot + các thành viên vào.
2. Tắt chế độ riêng tư của bot để bot đọc được lệnh trong group:
   chat với @BotFather → /mybots → chọn bot → Bot Settings →
   Group Privacy → **Turn off**.
3. Lấy chat_id group: nhắn 1 tin trong group rồi mở
   `https://api.telegram.org/bot<TOKEN>/getUpdates`, tìm
   `"chat":{"id":-100...}` (số âm).
4. Sửa secret `TELEGRAM_CHAT_ID` trên GitHub thành số âm này.
Mọi thành viên group đều dùng được toàn bộ lệnh; riêng /avg /pl tính
theo từng người. Bot hiểu cả dạng lệnh `/status@TenBot`.

## Phản hồi tức thời (tùy chọn — Cloudflare Worker)

Không bắt buộc: thiếu bước này bot vẫn chạy đủ tính năng, lệnh được trả
lời ở chu kỳ 5 phút kế tiếp. Cài Worker để lệnh đọc (/status /pl /list
/help /config) được trả lời **ngay lập tức** từ dữ liệu lần quét gần
nhất, còn lệnh ghi (/add /set /avg...) được xác nhận ngay + kích hoạt
bot chạy sớm (~1-2 phút thay vì chờ 5 phút).

1. Tạo tài khoản miễn phí tại dash.cloudflare.com.
2. Workers & Pages → Create → Create Worker → đặt tên → Deploy →
   Edit code → xóa code mẫu, dán toàn bộ nội dung file `worker.js`
   → Deploy. Ghi lại URL dạng `https://tên.tài-khoản.workers.dev`.
3. Tạo GitHub token cho Worker: github.com → Settings (avatar) →
   Developer settings → Fine-grained tokens → Generate:
   chọn đúng repo này, Permissions: **Contents: Read and write** và
   **Actions: Read and write** → tạo và copy token.
4. Trong Worker: Settings → Variables and Secrets, thêm:
   - `TELEGRAM_TOKEN` (secret) — token bot
   - `GITHUB_TOKEN` (secret) — token vừa tạo
   - `REPO` (text) — vd `MadCancerDevil/ChimBaoBao`
   - `BRANCH` (text) — `main`
   - `CHAT_ID` (text) — chat id group (số âm) hoặc cá nhân
5. Trỏ webhook Telegram về Worker — mở URL sau trên trình duyệt
   (thay TOKEN và URL_WORKER):
   `https://api.telegram.org/botTOKEN/setWebhook?url=URL_WORKER`
   Thấy `"ok":true` là xong. (Muốn quay về chế độ không Worker:
   mở `https://api.telegram.org/botTOKEN/deleteWebhook`.)

Lưu ý: khi webhook bật, bot chính tự chuyển sang đọc lệnh từ hàng đợi
do Worker ghi (thư mục `queue/`), không còn qua getUpdates — lệnh gửi
ngoài giờ giao dịch cũng không bao giờ bị mất nữa.

---

## Bản vá: lỗi "ConnectionError" / "RetryError" khi lấy dữ liệu

**Triệu chứng:** Actions chạy báo đỏ, log hiện `[ERR] MÃ: RetryError[...
raised ConnectionError]` cho TẤT CẢ các mã cùng lúc.

**Nguyên nhân:** nguồn dữ liệu VCI giới hạn số lượng truy cập từ các IP
dùng chung của máy chủ cloud (GitHub Actions, Kaggle, Colab đều thuộc
nhóm này) — đây là giới hạn của gói miễn phí phía nhà cung cấp dữ liệu,
không phải lỗi cấu hình của bạn. Càng nhiều mã theo dõi và gọi càng dồn
dập thì càng dễ bị chặn tạm thời.

**Đã khắc phục trong bản này:**
- Tự động thử lại tối đa 4 lần với độ trễ tăng dần khi gặp lỗi kết nối,
  trước khi thực sự báo lỗi.
- Giãn cách ngẫu nhiên 1,5–3 giây giữa các mã khi tải dữ liệu, tránh dồn
  request cùng lúc.
- Cảnh báo lỗi toàn bộ mã chỉ gửi tối đa 1 lần/giờ (không bị spam liên
  tục mỗi 5 phút nếu bị chặn kéo dài).

**Nếu vẫn còn gặp thường xuyên sau bản vá này:**
- Giảm số mã theo dõi cùng lúc (mỗi mã thêm là thêm 1 lần gọi API).
- Giãn lịch chạy thưa hơn: sửa `*/5` thành `*/10` hoặc `*/15` trong
  `.github/workflows/tracker.yml` (dòng cron đầu tiên).
- Cân nhắc gói trả phí của vnstock (banner "Insiders Program" hiện trong
  log) nếu cần độ ổn định cao hơn — đây là quyết định của bạn, không bắt
  buộc để hệ thống chạy được.

---

## Bản vá: lịch chạy không chính xác (GitHub tự trễ 15-90 phút)

**Triệu chứng:** cấu hình chạy mỗi 5 phút nhưng thực tế Actions chỉ chạy
rải rác ~1 tiếng/lần; có ngày mất hẳn báo cáo cuối ngày dù mọi thứ vẫn
cấu hình đúng.

**Nguyên nhân:** đây là giới hạn đã biết của chính GitHub Actions — lịch
chạy tự động (`schedule:`) không được đảm bảo đúng giờ, có thể trễ
15-90 phút hoặc bị bỏ qua hoàn toàn khi hệ thống GitHub tải cao, đặc
biệt với lịch chạy dày như mỗi 5 phút. Không có cách nào sửa từ phía
code để khắc phục hoàn toàn — đây là hành vi của nền tảng.

**Cách khắc phục:** dùng chính Cloudflare Worker đã cài (mục 8) để
**chủ động gọi GitHub chạy đúng giờ**, thay vì để GitHub tự quyết định.
Cloudflare Cron Trigger đáng tin cậy hơn nhiều so với lịch cron của
GitHub. Lịch `schedule:` gốc trong GitHub vẫn được giữ lại làm dự
phòng — nếu Cloudflare gặp sự cố, GitHub vẫn tự chạy được (dù có thể
trễ), hệ thống không phụ thuộc hoàn toàn vào 1 phía.

### Thêm Cron Trigger trên Cloudflare (bắt buộc để có bản vá này)

1. Vào trang Worker của bạn trên Cloudflare Dashboard.
2. Vào tab **Settings** → mục **Triggers**.
3. Tìm phần **Cron Triggers** → bấm **Add Cron Trigger**.
4. Thêm lần lượt **2 lịch** (mỗi lần bấm Add Cron Trigger là 1 lịch):
   - `*/5 2-7 * * 1-5` — kiểm tra tín hiệu mỗi 5 phút trong phiên
     (9h00–14h45 giờ VN, thứ 2–6)
   - `30 8 * * 1-5` — báo cáo tổng kết cuối ngày (15h30 giờ VN)
5. Bấm **Save** / **Add trigger** để lưu (tùy giao diện, tên nút có thể
   khác đôi chút).

**Không cần làm gì thêm** — `worker.js` trong bản vá này đã có sẵn hàm
`scheduled()` tự nhận diện đúng lịch nào vừa kích hoạt và gọi GitHub
chạy đúng chế độ (kiểm tra / báo cáo) tương ứng.

**Kiểm tra hoạt động:** sau khi thêm Cron Trigger, đợi tới đúng phút kế
tiếp chia hết cho 5 trong giờ giao dịch, vào tab Actions trên GitHub xem
có lượt chạy mới xuất hiện đúng giờ không (thay vì rải rác như trước).

---

## Bản vá: lỗi "cannot access local variable 'hosting_service'"

**Triệu chứng:** log hiện lỗi Python nằm ngay bên trong thư viện
`vnstock`, thử lại 4 lần vẫn lỗi y hệt (khác với ConnectionError ở bản
vá trước — lỗi này không phải do mạng, thử lại không giúp được gì).

**Nguyên nhân:** code đang dùng lớp `Vnstock()` kiểu cũ
(`Vnstock().stock(symbol=..., source="VCI")`) — lớp này đã **chính thức
hết hạn hỗ trợ từ 31/08/2025** theo thông báo của chính thư viện, và
đường code nội bộ xử lý lớp cũ này hiện có lỗi thật (không phải do bạn
cấu hình sai).

**Đã khắc phục:** chuyển sang lớp `Quote` mới
(`from vnstock import Quote; Quote(symbol=..., source="VCI")`) — đúng
theo hướng dẫn migration chính thức của vnstock, không còn phụ thuộc
đường code cũ đã lỗi thời.

**Bạn chỉ cần thay lại file `main.py`** bằng bản trong gói này, không
cần đổi gì thêm ở `requirements.txt` hay các file khác.

---

## Bản vá: lỗi "hosting_service" vẫn còn dù đã đổi sang lớp Quote

**Nguyên nhân thật sự:** không phải do cách gọi API (`Vnstock()` hay
`Quote()`), mà do **phiên bản thư viện**. `requirements.txt` trước đó
ghi `vnstock>=3.2.0` không giới hạn trên, nên mỗi lần workflow chạy sẽ
tự lấy bản **mới nhất tuyệt đối**. Vnstock bản 4.0.0 (phát hành
28/04/2026) giới thiệu một lớp "smart manager" mới tự động quản lý
request/rate-limit — và chính lớp mới này chứa lỗi `hosting_service`,
ảnh hưởng đến cả cách gọi cũ lẫn mới.

**Đã khắc phục:** ghim `requirements.txt` ở dòng phiên bản **3.x**
(`vnstock>=3.2.0,<4.0.0`) — vẫn nhận các bản vá lỗi trong dòng 3.x,
nhưng không bao giờ tự nhảy sang dòng 4.x cho đến khi bạn chủ động đổi.
Đã kiểm tra: với bản 3.5.1, khi mạng bị chặn chỉ trả về lỗi
`ConnectionError` thông thường (cơ chế thử-lại đã xử lý tốt), không
còn lỗi `hosting_service` nữa.

**Bạn cần thay 2 file:** `main.py` (bản dùng lớp `Quote`, đã gửi ở bản
vá trước) và `requirements.txt` (bản ghim phiên bản này).

**Nếu về sau muốn nâng lên dòng 4.x** (khi vnstock đã sửa lỗi này):
sửa lại `vnstock>=3.2.0,<4.0.0` thành `vnstock>=4.0.0` trong
`requirements.txt`, thử chạy lại — nếu ổn định thì giữ, nếu lỗi thì
quay lại ghim 3.x như cũ.
