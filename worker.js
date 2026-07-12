// Cloudflare Worker - "Le tan truc 24/7" cho Stock Tracker (muc 8)
// Lenh doc (/help /list /config /status /pl /plall): tra loi NGAY tu
//   du lieu lan quet gan nhat (state.json, config.json, portfolio.json
//   doc qua raw.githubusercontent.com - repo public).
// Lenh ghi (/add /remove /set /mode /avg /unavg): xac nhan ngay, ghi
//   file vao thu muc queue/ cua repo va kich hoat workflow chay som.
//
// Bien moi truong can cai (Settings > Variables and Secrets):
//   TELEGRAM_TOKEN  (secret) - token bot
//   GITHUB_TOKEN    (secret) - fine-grained token: Contents RW + Actions RW
//   REPO            (text)   - vd: MadCancerDevil/ChimBaoBao
//   BRANCH          (text)   - vd: main
//   CHAT_ID         (text)   - chat id group (so am) hoac ca nhan

const WRITE_CMDS = ["/add", "/remove", "/set", "/mode", "/avg", "/unavg"];

const HELP_TEXT = `📖 Các lệnh hỗ trợ
— Theo dõi mã —
/list — danh sách mã đang theo dõi
/add MÃ — thêm mã (mặc định auto)
/remove MÃ — bỏ theo dõi
/status [MÃ] — trạng thái (kèm xu hướng đa khung, mẫu hình)
/config — xem cấu hình
/mode MÃ auto|manual — đổi chế độ ngưỡng
— Ngưỡng giá (chế độ manual) —
/set MÃ khóa giá_trị — vd: /set NRC buy_zone_low 5200
Khóa: buy_zone_low (cận dưới vùng mua), buy_zone_high (cận trên vùng mua), breakout_level (kháng cự), stoploss_level (cắt lỗ), target_low / target_high (mục tiêu giá)
— Danh mục cá nhân —
/avg MÃ giá_vốn [số_lượng] — đặt/cập nhật giá vốn
/unavg MÃ — xóa khỏi danh mục
/pl — lời/lỗ của bạn | /plall — cả nhóm`;

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Stock Tracker Worker OK");
    }
    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("bad request", { status: 400 });
    }
    const msg = update.message;
    if (!msg || !msg.text) return new Response("ok");
    if (String(msg.chat.id) !== String(env.CHAT_ID)) {
      return new Response("ok"); // bo qua chat la
    }

    let text = msg.text.trim();
    if (!text.startsWith("/")) return new Response("ok");
    // Cat duoi @botname (muc 7)
    const parts = text.split(/\s+/);
    parts[0] = parts[0].split("@")[0].toLowerCase();
    const cmd = parts[0];

    const reply = (t) => sendTelegram(env, msg.chat.id, t);

    try {
      if (cmd === "/help") {
        await reply(HELP_TEXT);
      } else if (cmd === "/list") {
        const cfg = await rawJson(env, "config.json");
        const lines = Object.entries(cfg.symbols).map(
          ([s, c]) => `• ${s} (${c.mode || "auto"})`);
        await reply(`Đang theo dõi ${lines.length} mã:\n` +
                    lines.join("\n"));
      } else if (cmd === "/config") {
        const cfg = await rawJson(env, "config.json");
        await reply("Cấu hình hiện tại:\n" +
                    JSON.stringify(cfg, null, 1).slice(0, 3800));
      } else if (cmd === "/status") {
        const st = await rawJson(env, "state.json");
        await reply(formatStatus(st, parts[1]));
      } else if (cmd === "/pl" || cmd === "/plall") {
        const [st, pf] = await Promise.all([
          rawJson(env, "state.json"), rawJson(env, "portfolio.json")]);
        await reply(formatPL(st, pf, cmd === "/plall"
                             ? null : String(msg.from.id),
                             msg.from.first_name));
      } else if (WRITE_CMDS.includes(cmd)) {
        await queueCommand(env, msg);
        await triggerWorkflow(env);
        await reply(`✅ Đã ghi nhận lệnh ${text}\n` +
          `Sẽ áp dụng ở lần cập nhật dữ liệu tiếp theo (~1-2 phút).`);
      } else {
        await reply("Lệnh không hợp lệ.\n\n" + HELP_TEXT);
      }
    } catch (e) {
      await reply(`❌ Lỗi xử lý: ${e.message}`);
    }
    return new Response("ok");
  },
};

// ----------------- Telegram -----------------
async function sendTelegram(env, chatId, text) {
  await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/sendMessage`,
    { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text }) });
}

// ----------------- Doc du lieu tu repo public -----------------
async function rawJson(env, path) {
  const url = `https://raw.githubusercontent.com/${env.REPO}/` +
              `${env.BRANCH}/${path}?t=${Date.now()}`;
  const r = await fetch(url, { headers: { "Cache-Control": "no-cache" } });
  if (!r.ok) throw new Error(`không đọc được ${path}`);
  return r.json();
}

// ----------------- Dinh dang tra loi -----------------
function fmt(n) {
  return n == null ? "?" : Math.round(n).toLocaleString("vi-VN");
}

function formatStatus(st, wantSym) {
  const snap = st.snapshot || {};
  const syms = Object.keys(snap).filter(
    (s) => !wantSym || s === wantSym.toUpperCase());
  if (!syms.length) return "Chưa có dữ liệu (hệ thống chưa chạy lần nào?)";
  const when = st.snapshot_time
    ? new Date(st.snapshot_time).toLocaleString("vi-VN",
        { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit",
          minute: "2-digit", day: "2-digit", month: "2-digit" })
    : "?";
  const blocks = syms.map((s) => {
    const d = snap[s];
    const lv = d.levels || {};
    const lines = [
      `[${s}] ${fmt(d.price)}đ (${d.chg_pct >= 0 ? "+" : ""}${d.chg_pct}%)`,
      `RSI ${d.rsi ?? "?"} | Vol ${d.vol_ratio}x | ` +
      `MA ${d.ma_ok ? "✅" : "⚠️"} | MACD ${d.macd_ok ? "✅" : "⚠️"}`,
      "Xu hướng: " + Object.entries(d.trends || {})
        .map(([k, v]) => `${k}: ${v.split(" (")[0]}`).join(" | "),
      `Mua ${fmt(lv.buy_zone_low)}-${fmt(lv.buy_zone_high)} | ` +
      `KC ${fmt(lv.breakout_level)} | SL ${fmt(lv.stoploss_level)}`,
    ];
    if (d.tracked_patterns) lines.push("Mẫu hình: " + d.tracked_patterns);
    if (d.candles && d.candles.length)
      lines.push("Nến: " + d.candles.join(", "));
    return lines.join("\n");
  });
  return `📋 Trạng thái (dữ liệu cập nhật lúc ${when})\n` +
         blocks.join("\n— — —\n");
}

function formatPL(st, pf, onlyUserId, askerName) {
  const snap = st.snapshot || {};
  const users = (pf && pf.users) || {};
  const blocks = [];
  for (const [uid, u] of Object.entries(users)) {
    if (onlyUserId && uid !== onlyUserId) continue;
    const lines = [];
    for (const [sym, pos] of Object.entries(u.positions || {})) {
      const d = snap[sym];
      if (!d) { lines.push(`${sym}: chưa có dữ liệu giá`); continue; }
      const pnl = (d.price / pos.avg - 1) * 100;
      const icon = pnl > 0.5 ? "🟢" : pnl < -0.5 ? "🔴" : "⚪";
      let line = `${icon} ${sym}: vốn ${fmt(pos.avg)} → ${fmt(d.price)}đ ` +
                 `(${pnl >= 0 ? "+" : ""}${pnl.toFixed(1)}%)`;
      if (pos.qty) {
        const money = (d.price - pos.avg) * pos.qty;
        line += ` | ${money >= 0 ? "+" : ""}${fmt(money)}đ`;
      }
      lines.push(line);
    }
    if (lines.length)
      blocks.push(`👤 ${u.name || uid}\n` + lines.join("\n"));
  }
  if (!blocks.length) {
    return onlyUserId
      ? `${askerName || "Bạn"} chưa có vị thế nào. Dùng /avg MÃ giá_vốn.`
      : "Chưa ai đặt giá vốn. Dùng /avg để bắt đầu.";
  }
  const when = st.snapshot_time
    ? new Date(st.snapshot_time).toLocaleString("vi-VN",
        { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", minute: "2-digit" })
    : "?";
  return `💼 Lời/lỗ (giá lúc ${when})\n` + blocks.join("\n— — —\n") +
         "\n(Gợi ý vị thế chi tiết sẽ có trong /pl từ bot chính " +
         "và báo cáo cuối ngày)";
}

// ----------------- Ghi lenh vao hang doi + kich hoat -----------------
async function queueCommand(env, msg) {
  const ts = Date.now();
  const rand = Math.random().toString(36).slice(2, 8);
  const path = `queue/cmd-${ts}-${rand}.json`;
  const content = btoa(unescape(encodeURIComponent(JSON.stringify({
    user_id: msg.from.id,
    user_name: msg.from.first_name || "",
    chat_id: msg.chat.id,
    text: msg.text,
    ts,
  }))));
  const r = await fetch(
    `https://api.github.com/repos/${env.REPO}/contents/${path}`,
    { method: "PUT",
      headers: ghHeaders(env),
      body: JSON.stringify({
        message: `queue: ${msg.text.split(" ")[0]}`,
        content, branch: env.BRANCH }) });
  if (!r.ok) throw new Error(`ghi hàng đợi thất bại (${r.status})`);
}

async function triggerWorkflow(env) {
  await fetch(
    `https://api.github.com/repos/${env.REPO}/actions/workflows/` +
    `tracker.yml/dispatches`,
    { method: "POST",
      headers: ghHeaders(env),
      body: JSON.stringify({ ref: env.BRANCH }) });
  // Khong throw neu that bai - lenh van se duoc xu ly o chu ky 5 phut
}

function ghHeaders(env) {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "stock-tracker-worker",
    "Content-Type": "application/json",
  };
}
