# -*- coding: utf-8 -*-
"""
Stock Tracker (da ma) - Bot theo doi nhieu co phieu tu dong
Chay tren GitHub Actions, thong bao qua Telegram.

Cach chay:
  python main.py check    -> chu ky kiem tra trong phien (moi 5 phut)
  python main.py report   -> bao cao tong ket cuoi ngay (15h30)
"""

import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
MAX_SYMBOLS = 10  # gioi han de moi lan chay khong qua lau

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

DEFAULT_MANUAL = {
    "buy_zone_low": 0,
    "buy_zone_high": 0,
    "breakout_level": 0,
    "stoploss_level": 0,
    "target_low": 0,
    "target_high": 0,
}


# ---------------------------------------------------------------
# Tien ich: config & state
# ---------------------------------------------------------------

def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config():
    return load_json(CONFIG_FILE)


def load_state():
    return load_json(STATE_FILE, default={
        "last_update_id": 0,
        "last_alerts": {},
        "last_prices": {},
    })


# ---------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------

def tg_send(text, parse_mode="HTML"):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Thieu TELEGRAM_TOKEN / TELEGRAM_CHAT_ID")
        print(text)
        return
    try:
        requests.post(
            f"{TG_API}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
                  "parse_mode": parse_mode},
            timeout=15,
        )
    except Exception as e:
        print(f"[ERR] Gui Telegram that bai: {e}")


def tg_get_updates(offset):
    try:
        r = requests.get(
            f"{TG_API}/getUpdates",
            params={"offset": offset + 1, "timeout": 0},
            timeout=15,
        )
        return r.json().get("result", [])
    except Exception as e:
        print(f"[ERR] getUpdates: {e}")
        return []


# ---------------------------------------------------------------
# Du lieu gia (vnstock)
# ---------------------------------------------------------------

def fetch_history(symbol, days=120):
    """Lay du lieu OHLCV ngay. Tra ve DataFrame co cot:
    time, open, high, low, close, volume (gia don vi: dong)."""
    from vnstock import Vnstock
    end = datetime.now(VN_TZ).date()
    start = end - timedelta(days=days * 2)
    stock = Vnstock().stock(symbol=symbol, source="VCI")
    df = stock.quote.history(
        start=str(start), end=str(end), interval="1D"
    )
    df = df.rename(columns=str.lower)
    # vnstock co the tra gia don vi nghin dong -> chuan hoa ve dong
    if df["close"].iloc[-1] < 500:
        for c in ["open", "high", "low", "close"]:
            df[c] = df[c] * 1000
    df = df.dropna().reset_index(drop=True)
    return df.tail(days).reset_index(drop=True)


def symbol_exists(symbol):
    """Kiem tra ma co du lieu hay khong (dung khi /add)."""
    try:
        df = fetch_history(symbol, days=30)
        return len(df) >= 5
    except Exception:
        return False


# ---------------------------------------------------------------
# Chi bao ky thuat
# ---------------------------------------------------------------

def compute_indicators(df, cfg):
    s = cfg["signals"]
    close = df["close"]

    df["ma_short"] = close.rolling(s["ma_short"]).mean()
    df["ma_long"] = close.rolling(s["ma_long"]).mean()

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(s["rsi_period"]).mean()
    loss = (-delta.clip(upper=0)).rolling(s["rsi_period"]).mean()
    rs = gain / loss.replace(0, 1e-9)
    df["rsi"] = 100 - 100 / (1 + rs)

    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    # Volume trung binh (khong tinh phien hien tai de tranh tu lam loang
    # tin hieu dot bien)
    df["vol_avg"] = (
        df["volume"].shift(1).rolling(s["volume_avg_period"]).mean()
    )

    return df


def session_elapsed_fraction(now=None):
    """Ty le thoi gian phien giao dich da troi qua (0..1).
    Phien HOSE/HNX: 9:00-11:30 va 13:00-14:45 = 255 phut giao dich."""
    now = now or datetime.now(VN_TZ)
    minutes = 0
    t = now.hour * 60 + now.minute
    m0900, m1130 = 9 * 60, 11 * 60 + 30
    m1300, m1445 = 13 * 60, 14 * 60 + 45
    # Sang
    minutes += max(0, min(t, m1130) - m0900)
    # Chieu
    minutes += max(0, min(t, m1445) - m1300)
    frac = minutes / 255
    # Chan duoi 0.2 de tranh phong dai qua muc dau phien,
    # va coi ngoai gio la phien da xong (frac = 1)
    if frac <= 0:
        return 1.0
    return max(0.2, min(1.0, frac))


def volume_ratio(last, candle_is_today=True):
    """Ty le volume so voi TB20, an toan voi NaN va quy doi theo
    thoi gian phien da troi qua neu nen hien tai la nen dang hinh thanh."""
    vol_avg = last["vol_avg"]
    if not pd.notna(vol_avg) or vol_avg <= 0:
        return 0.0
    vol = last["volume"]
    if candle_is_today:
        vol = vol / session_elapsed_fraction()
    return float(vol / vol_avg)


def is_today_candle(df):
    """Nen cuoi cung co phai nen cua ngay hom nay khong."""
    try:
        last_date = pd.to_datetime(df.iloc[-1]["time"]).date()
        return last_date == datetime.now(VN_TZ).date()
    except Exception:
        return False


def resolve_levels(df, cfg, sym_cfg):
    """Xac dinh vung mua / khang cu cho 1 ma theo mode cua ma do."""
    if sym_cfg.get("mode", "auto") == "auto":
        a = cfg["auto_defaults"]
        support = float(df["low"].tail(a["support_lookback_days"]).min())
        resistance = float(df["high"].tail(a["resistance_lookback_days"]).max())
        margin = a["buy_zone_margin_pct"] / 100
        return {
            "buy_zone_low": round(support),
            "buy_zone_high": round(support * (1 + margin)),
            "breakout_level": round(resistance),
            "stoploss_level": round(support * (1 - margin * 1.5)),
            "target_low": round(resistance * 1.15),
            "target_high": round(resistance * 1.30),
        }
    return dict(sym_cfg.get("manual", DEFAULT_MANUAL))


# ---------------------------------------------------------------
# Phat hien tin hieu (cho 1 ma)
# ---------------------------------------------------------------

def detect_signals(symbol, df, cfg, levels):
    s = cfg["signals"]
    last = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []

    price = last["close"]
    vol_ratio = volume_ratio(last, candle_is_today=is_today_candle(df))

    # 1. DIEM MUA: gia vao vung mua + RSI thap
    if levels["buy_zone_low"] and \
            levels["buy_zone_low"] <= price <= levels["buy_zone_high"]:
        if last["rsi"] <= s["rsi_oversold"] + 10:
            signals.append((
                "BUY_ZONE",
                f"🟢 <b>[{symbol}] ĐIỂM MUA TIỀM NĂNG</b>\n"
                f"Giá {price:,.0f}đ đã vào vùng mua "
                f"{levels['buy_zone_low']:,}-{levels['buy_zone_high']:,}đ\n"
                f"RSI: {last['rsi']:.1f} | Volume: {vol_ratio:.1f}x TB20\n"
                f"⛔ Stoploss đề xuất: dưới {levels['stoploss_level']:,}đ"
            ))

    # 2. BREAKOUT: vuot khang cu + volume dot bien
    if levels["breakout_level"] and price > levels["breakout_level"] \
            and prev["close"] <= levels["breakout_level"]:
        if vol_ratio >= s["volume_spike_ratio"]:
            signals.append((
                "BREAKOUT",
                f"🚀 <b>[{symbol}] BREAKOUT XÁC NHẬN</b>\n"
                f"Giá {price:,.0f}đ vượt kháng cự {levels['breakout_level']:,}đ\n"
                f"Volume: {vol_ratio:.1f}x TB20 (đạt chuẩn ≥{s['volume_spike_ratio']}x)\n"
                f"🎯 Mục tiêu: {levels['target_low']:,}-{levels['target_high']:,}đ\n"
                f"⛔ Dời stoploss lên dưới {levels['breakout_level']:,}đ"
            ))
        else:
            signals.append((
                "BREAKOUT_WEAK",
                f"⚠️ <b>[{symbol}] Vượt kháng cự nhưng volume yếu</b>\n"
                f"Giá {price:,.0f}đ > {levels['breakout_level']:,}đ "
                f"nhưng volume chỉ {vol_ratio:.1f}x TB20.\n"
                "Cẩn trọng bull trap, chờ xác nhận thêm."
            ))

    # 3. STOPLOSS: thung ho tro
    if levels["stoploss_level"] and price < levels["stoploss_level"] \
            and prev["close"] >= levels["stoploss_level"]:
        signals.append((
            "STOPLOSS",
            f"🔴 <b>[{symbol}] CẢNH BÁO STOPLOSS</b>\n"
            f"Giá {price:,.0f}đ đã thủng mức {levels['stoploss_level']:,}đ.\n"
            "Cấu trúc tăng bị phá vỡ - cân nhắc thoát vị thế."
        ))

    # 4. VOLUME DOT BIEN (bao som du chua co tin hieu gia)
    if vol_ratio >= s["volume_spike_ratio"] * 1.5:
        signals.append((
            "VOL_SPIKE",
            f"📊 <b>[{symbol}] Khối lượng đột biến</b>\n"
            f"Volume hiện tại gấp {vol_ratio:.1f}x TB20 phiên.\n"
            f"Giá: {price:,.0f}đ ({(price/prev['close']-1)*100:+.1f}%)"
        ))

    # 5. MACD cat len
    if prev["macd"] <= prev["macd_signal"] and last["macd"] > last["macd_signal"]:
        signals.append((
            "MACD_CROSS",
            f"📈 <b>[{symbol}] MACD cắt lên đường tín hiệu</b>\n"
            f"Động lượng tăng đang hình thành. Giá: {price:,.0f}đ"
        ))

    return signals


def alert_allowed(state, symbol, key, cooldown_min):
    last = state["last_alerts"].get(f"{symbol}:{key}")
    if not last:
        return True
    last_dt = datetime.fromisoformat(last)
    return datetime.now(VN_TZ) - last_dt >= timedelta(minutes=cooldown_min)


# ---------------------------------------------------------------
# Trang thai / bao cao cho 1 ma
# ---------------------------------------------------------------

def build_status_block(symbol, df, cfg, sym_cfg, levels):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    vol_ratio = volume_ratio(last, candle_is_today=is_today_candle(df))
    chg = (last["close"] / prev["close"] - 1) * 100
    ma_ok = last["ma_short"] > last["ma_long"]
    macd_ok = last["macd"] > last["macd_signal"]
    return (
        f"<b>[{symbol}]</b> {last['close']:,.0f}đ ({chg:+.2f}%)"
        f" | chế độ: {sym_cfg.get('mode', 'auto')}\n"
        f"RSI: {last['rsi']:.1f} | Vol: {vol_ratio:.1f}x"
        f" | MA {'✅' if ma_ok else '⚠️'} | MACD {'✅' if macd_ok else '⚠️'}\n"
        f"Mua: {levels['buy_zone_low']:,}-{levels['buy_zone_high']:,}"
        f" | KC: {levels['breakout_level']:,}"
        f" | SL: {levels['stoploss_level']:,}"
    )


def build_report_block(symbol, df, cfg, levels):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    week_ago = df.iloc[-6] if len(df) >= 6 else prev
    # Bao cao chay sau gio dong cua -> nen da hoan chinh, khong quy doi
    vol_ratio = volume_ratio(last, candle_is_today=False)
    dist_buy = (last["close"] / levels["buy_zone_high"] - 1) * 100 \
        if levels["buy_zone_high"] else 0
    dist_res = (levels["breakout_level"] / last["close"] - 1) * 100 \
        if levels["breakout_level"] else 0
    rsi_note = ("quá mua ⚠️" if last["rsi"] >= cfg["signals"]["rsi_overbought"]
                else "quá bán 🟢" if last["rsi"] <= cfg["signals"]["rsi_oversold"]
                else "trung tính")
    return (
        f"<b>▍{symbol}</b>\n"
        f"Đóng cửa: <b>{last['close']:,.0f}đ</b> "
        f"({(last['close']/prev['close']-1)*100:+.2f}% ngày, "
        f"{(last['close']/week_ago['close']-1)*100:+.2f}% tuần)\n"
        f"KL: {last['volume']:,.0f} ({vol_ratio:.1f}x TB20)\n"
        f"RSI {last['rsi']:.1f} ({rsi_note}) | "
        f"MA20 {'>' if last['ma_short'] > last['ma_long'] else '<'} MA50 | "
        f"MACD {'✅' if last['macd'] > last['macd_signal'] else '⚠️'}\n"
        f"Cách vùng mua: {dist_buy:+.1f}% | Cách kháng cự: {dist_res:.1f}%"
    )


# ---------------------------------------------------------------
# Xu ly lenh Telegram (2 chieu)
# ---------------------------------------------------------------

HELP_TEXT = (
    "<b>Các lệnh hỗ trợ:</b>\n"
    "/list - Danh sách mã đang theo dõi\n"
    "/add &lt;MÃ&gt; - Thêm mã (mặc định chế độ auto), vd: /add HQC\n"
    "/remove &lt;MÃ&gt; - Bỏ theo dõi mã, vd: /remove HQC\n"
    "/status - Trạng thái tất cả mã\n"
    "/status &lt;MÃ&gt; - Trạng thái 1 mã\n"
    "/config - Xem cấu hình đầy đủ\n"
    "/mode &lt;MÃ&gt; auto|manual - Đổi chế độ ngưỡng của mã\n"
    "/set &lt;MÃ&gt; &lt;khóa&gt; &lt;giá trị&gt; - Đặt ngưỡng riêng, vd:\n"
    "   /set NRC buy_zone_low 5200\n"
    "   /set HQC breakout_level 2800\n"
    "/setsignal &lt;khóa&gt; &lt;giá trị&gt; - Ngưỡng tín hiệu chung, vd:\n"
    "   /setsignal volume_spike_ratio 3\n"
    "/help - Danh sách lệnh"
)

SET_KEYS_MANUAL = {"buy_zone_low", "buy_zone_high", "breakout_level",
                   "stoploss_level", "target_low", "target_high"}
SET_KEYS_SIGNAL = {"volume_spike_ratio", "rsi_oversold", "rsi_overbought"}


def parse_number(raw):
    val = float(raw)
    return int(val) if val == int(val) else val


def process_commands(state, cfg, market):
    """market: dict {symbol: (df, levels)} cua cac ma da tai duoc."""
    updates = tg_get_updates(state["last_update_id"])
    config_changed = False

    for u in updates:
        state["last_update_id"] = max(state["last_update_id"], u["update_id"])
        msg = u.get("message", {})
        text = (msg.get("text") or "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != str(TELEGRAM_CHAT_ID) or not text.startswith("/"):
            continue

        parts = text.split()
        cmd = parts[0].lower()
        symbols = cfg["symbols"]

        if cmd == "/list":
            lines = [f"• <b>{s}</b> ({c.get('mode', 'auto')})"
                     for s, c in symbols.items()]
            tg_send("<b>Đang theo dõi "
                    f"{len(symbols)}/{MAX_SYMBOLS} mã:</b>\n" + "\n".join(lines))

        elif cmd == "/add" and len(parts) == 2:
            sym = parts[1].upper()
            if sym in symbols:
                tg_send(f"ℹ️ {sym} đã có trong danh sách.")
            elif len(symbols) >= MAX_SYMBOLS:
                tg_send(f"❌ Đã đạt giới hạn {MAX_SYMBOLS} mã. "
                        "Hãy /remove bớt trước khi thêm.")
            elif not symbol_exists(sym):
                tg_send(f"❌ Không tìm thấy dữ liệu cho mã <b>{sym}</b>. "
                        "Kiểm tra lại mã có đúng không.")
            else:
                symbols[sym] = {"mode": "auto",
                                "manual": dict(DEFAULT_MANUAL)}
                config_changed = True
                tg_send(f"✅ Đã thêm <b>{sym}</b> (chế độ auto - ngưỡng tự "
                        "tính theo đáy 30 / đỉnh 50 phiên).\n"
                        f"Muốn đặt ngưỡng tay: /mode {sym} manual rồi "
                        f"/set {sym} buy_zone_low ...")

        elif cmd == "/remove" and len(parts) == 2:
            sym = parts[1].upper()
            if sym in symbols:
                if len(symbols) == 1:
                    tg_send("❌ Không thể xóa mã cuối cùng. "
                            "Hãy /add mã khác trước.")
                else:
                    del symbols[sym]
                    config_changed = True
                    tg_send(f"✅ Đã bỏ theo dõi <b>{sym}</b>")
            else:
                tg_send(f"❌ {sym} không có trong danh sách. Gõ /list để xem.")

        elif cmd == "/status":
            want = parts[1].upper() if len(parts) == 2 else None
            blocks = []
            for sym, (df, levels) in market.items():
                if want and sym != want:
                    continue
                blocks.append(build_status_block(
                    sym, df, cfg, symbols.get(sym, {}), levels))
            if blocks:
                header = (f"<b>📋 Trạng thái</b> "
                          f"({datetime.now(VN_TZ).strftime('%H:%M %d/%m')})\n")
                tg_send(header + "\n— — —\n".join(blocks))
            else:
                tg_send(f"❌ Không có dữ liệu cho {want}. Gõ /list để xem "
                        "danh sách mã.")

        elif cmd == "/config":
            tg_send("<b>Cấu hình hiện tại:</b>\n<pre>"
                    + json.dumps(cfg, ensure_ascii=False, indent=1)
                    + "</pre>")

        elif cmd == "/help":
            tg_send(HELP_TEXT)

        elif cmd == "/mode" and len(parts) == 3 \
                and parts[2] in ("auto", "manual"):
            sym = parts[1].upper()
            if sym in symbols:
                symbols[sym]["mode"] = parts[2]
                config_changed = True
                tg_send(f"✅ <b>{sym}</b> chuyển sang chế độ <b>{parts[2]}</b>")
            else:
                tg_send(f"❌ {sym} không có trong danh sách.")

        elif cmd == "/set" and len(parts) == 4:
            sym, key, raw = parts[1].upper(), parts[2], parts[3]
            if sym not in symbols:
                tg_send(f"❌ {sym} không có trong danh sách. Gõ /list để xem.")
            elif key not in SET_KEYS_MANUAL:
                tg_send(f"❌ Khóa không hợp lệ: {key}\n{HELP_TEXT}")
            else:
                try:
                    val = parse_number(raw)
                    symbols[sym].setdefault("manual", dict(DEFAULT_MANUAL))
                    symbols[sym]["manual"][key] = val
                    config_changed = True
                    note = ""
                    if symbols[sym].get("mode") != "manual":
                        note = (f"\nℹ️ {sym} đang ở chế độ auto - ngưỡng này "
                                f"chỉ áp dụng khi chuyển /mode {sym} manual")
                    tg_send(f"✅ [{sym}] <b>{key}</b> = {val:,}{note}")
                except ValueError:
                    tg_send("❌ Giá trị phải là số. "
                            "Ví dụ: /set NRC buy_zone_low 5200")

        elif cmd == "/setsignal" and len(parts) == 3:
            key, raw = parts[1], parts[2]
            if key not in SET_KEYS_SIGNAL:
                tg_send(f"❌ Khóa không hợp lệ: {key}\n{HELP_TEXT}")
            else:
                try:
                    cfg["signals"][key] = parse_number(raw)
                    config_changed = True
                    tg_send(f"✅ Ngưỡng chung <b>{key}</b> = "
                            f"{cfg['signals'][key]} (áp dụng mọi mã)")
                except ValueError:
                    tg_send("❌ Giá trị phải là số.")

        else:
            tg_send("Lệnh không hợp lệ.\n" + HELP_TEXT)

    if config_changed:
        save_json(CONFIG_FILE, cfg)
    return config_changed


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    cfg = load_config()
    state = load_state()

    # Tai du lieu tung ma; ma nao loi thi bao va bo qua, khong sap ca he thong
    market = {}
    errors = []
    for sym, sym_cfg in list(cfg["symbols"].items()):
        try:
            df = fetch_history(sym)
            df = compute_indicators(df, cfg)
            levels = resolve_levels(df, cfg, sym_cfg)
            market[sym] = (df, levels)
        except Exception as e:
            errors.append(f"{sym}: {e}")
            print(f"[ERR] Loi tai du lieu {sym}: {e}")

    if errors and not market:
        tg_send("❌ Lỗi lấy dữ liệu tất cả các mã:\n" + "\n".join(errors))
        sys.exit(1)

    # Xu ly lenh nguoi dung truoc (co the them/bot ma, doi nguong)
    changed = process_commands(state, cfg, market)
    if changed:
        cfg = load_config()
        # Tai du lieu cho ma vua duoc /add ma chua co trong market
        for sym, sym_cfg in cfg["symbols"].items():
            if sym not in market:
                try:
                    df = fetch_history(sym)
                    df = compute_indicators(df, cfg)
                    market[sym] = (df, resolve_levels(df, cfg, sym_cfg))
                except Exception as e:
                    print(f"[ERR] {sym}: {e}")
        # Bo ma vua bi /remove
        market = {s: v for s, v in market.items() if s in cfg["symbols"]}
        # Tinh lai levels theo config moi
        for sym in market:
            df, _ = market[sym]
            market[sym] = (df, resolve_levels(df, cfg, cfg["symbols"][sym]))

    if action == "report":
        if cfg["alerts"]["daily_report_enabled"] and market:
            blocks = [build_report_block(sym, df, cfg, levels)
                      for sym, (df, levels) in market.items()]
            report = (
                f"<b>📊 BÁO CÁO CUỐI NGÀY</b> - "
                f"{datetime.now(VN_TZ).strftime('%d/%m/%Y')}\n"
                "═══════════════\n"
                + "\n═══════════════\n".join(blocks)
                + "\n═══════════════\n"
                "Gõ /status để xem cập nhật bất cứ lúc nào."
            )
            if errors:
                report += "\n⚠️ Mã lỗi dữ liệu hôm nay: " + ", ".join(
                    e.split(":")[0] for e in errors)
            tg_send(report)
    else:
        cooldown = cfg["alerts"]["cooldown_minutes"]
        for sym, (df, levels) in market.items():
            for key, message in detect_signals(sym, df, cfg, levels):
                if alert_allowed(state, sym, key, cooldown):
                    tg_send(message)
                    state["last_alerts"][f"{sym}:{key}"] = \
                        datetime.now(VN_TZ).isoformat()

    for sym, (df, _) in market.items():
        state["last_prices"][sym] = float(df.iloc[-1]["close"])
    save_json(STATE_FILE, state)
    print(f"[OK] {action} xong luc {datetime.now(VN_TZ)} - "
          f"{len(market)} ma, {len(errors)} loi")


if __name__ == "__main__":
    main()
