# -*- coding: utf-8 -*-
"""
Stock Tracker v3 - Bot theo doi nhieu co phieu, phan tich da tang
Chay tren GitHub Actions, thong bao qua Telegram (ho tro group).

  python main.py check    -> chu ky kiem tra trong phien
  python main.py report   -> bao cao tong ket cuoi ngay
"""

import glob
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from analysis import (VN_TZ, all_divergences, compute_indicators,
                      fibonacci_zones, is_today_candle,
                      latest_swing_summary, multi_timeframe_trends,
                      volume_ratio)
from patterns import (chart_breakout_signals, confluence_score,
                      describe_tracked, detect_candles,
                      track_chart_patterns)
import portfolio as pfm

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
QUEUE_DIR = "queue"
MAX_SYMBOLS = 10

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

DEFAULT_MANUAL = {"buy_zone_low": 0, "buy_zone_high": 0,
                  "breakout_level": 0, "stoploss_level": 0,
                  "target_low": 0, "target_high": 0}


# ---------------------------------------------------------------
# JSON helpers
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
        "last_update_id": 0, "last_alerts": {},
        "snapshot": {}, "snapshot_time": None,
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
        requests.post(f"{TG_API}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
                            "parse_mode": parse_mode}, timeout=15)
    except Exception as e:
        print(f"[ERR] Gui Telegram that bai: {e}")


def tg_get_updates(offset):
    """Doc lenh qua polling. Neu da cai webhook (Worker), Telegram tra
    loi 409 -> bo qua trong im lang, lenh se den qua hang doi."""
    try:
        r = requests.get(f"{TG_API}/getUpdates",
                         params={"offset": offset + 1, "timeout": 0},
                         timeout=15)
        if r.status_code == 409:
            return []
        return r.json().get("result", [])
    except Exception as e:
        print(f"[ERR] getUpdates: {e}")
        return []


# ---------------------------------------------------------------
# Du lieu gia (vnstock) - tang len 200 nen cho khung 9 thang
# ---------------------------------------------------------------

def fetch_history(symbol, days=200):
    from vnstock import Vnstock
    end = datetime.now(VN_TZ).date()
    start = end - timedelta(days=days * 2)
    stock = Vnstock().stock(symbol=symbol, source="VCI")
    df = stock.quote.history(start=str(start), end=str(end), interval="1D")
    df = df.rename(columns=str.lower)
    if df["close"].iloc[-1] < 500:
        for c in ["open", "high", "low", "close"]:
            df[c] = df[c] * 1000
    return df.dropna().reset_index(drop=True).tail(days).reset_index(drop=True)


def symbol_exists(symbol):
    try:
        return len(fetch_history(symbol, days=30)) >= 5
    except Exception:
        return False


# ---------------------------------------------------------------
# Muc/nguong gia
# ---------------------------------------------------------------

def resolve_levels(df, cfg, sym_cfg):
    if sym_cfg.get("mode", "auto") == "auto":
        a = cfg["auto_defaults"]
        support = float(df["low"].tail(a["support_lookback_days"]).min())
        resistance = float(df["high"].tail(a["resistance_lookback_days"]).max())
        margin = a["buy_zone_margin_pct"] / 100
        return {"buy_zone_low": round(support),
                "buy_zone_high": round(support * (1 + margin)),
                "breakout_level": round(resistance),
                "stoploss_level": round(support * (1 - margin * 1.5)),
                "target_low": round(resistance * 1.15),
                "target_high": round(resistance * 1.30)}
    return dict(sym_cfg.get("manual", DEFAULT_MANUAL))


# ---------------------------------------------------------------
# Phan tich day du 1 ma -> goi "profile"
# ---------------------------------------------------------------

def analyze_symbol(sym, df, cfg, sym_cfg):
    levels = resolve_levels(df, cfg, sym_cfg)
    today = is_today_candle(df)
    last = df.iloc[-1]
    vr = volume_ratio(last, candle_is_today=today)
    return {
        "df": df, "levels": levels, "vol_ratio": vr,
        "candle_is_today": today,
        "trends": multi_timeframe_trends(df),
        "swings": latest_swing_summary(df),
        "divergences": all_divergences(df, cfg),
        "fib": fibonacci_zones(df),
        "candles": detect_candles(df),
        "chart_patterns": track_chart_patterns(df),
    }


# ---------------------------------------------------------------
# Tin hieu (muc gia + nen + mau hinh cum)
# ---------------------------------------------------------------

def detect_signals(symbol, prof, cfg):
    s = cfg["signals"]
    df = prof["df"]
    levels = prof["levels"]
    last, prev = df.iloc[-1], df.iloc[-2]
    price = last["close"]
    vr = prof["vol_ratio"]
    signals = []

    # --- Tin hieu muc gia (nhu phien ban truoc) ---
    if levels["buy_zone_low"] and \
            levels["buy_zone_low"] <= price <= levels["buy_zone_high"] \
            and last["rsi"] <= s["rsi_oversold"] + 10:
        signals.append(("BUY_ZONE",
            f"🟢 <b>[{symbol}] ĐIỂM MUA TIỀM NĂNG</b>\n"
            f"Giá {price:,.0f}đ vào vùng mua "
            f"{levels['buy_zone_low']:,}-{levels['buy_zone_high']:,}đ\n"
            f"RSI: {last['rsi']:.1f} | Volume: {vr:.1f}x TB20\n"
            f"⛔ Stoploss đề xuất: dưới {levels['stoploss_level']:,}đ"))

    if levels["breakout_level"] and price > levels["breakout_level"] \
            and prev["close"] <= levels["breakout_level"]:
        if vr >= s["volume_spike_ratio"]:
            signals.append(("BREAKOUT",
                f"🚀 <b>[{symbol}] BREAKOUT XÁC NHẬN</b>\n"
                f"Giá {price:,.0f}đ vượt kháng cự "
                f"{levels['breakout_level']:,}đ\n"
                f"Volume: {vr:.1f}x TB20 (chuẩn ≥{s['volume_spike_ratio']}x)\n"
                f"🎯 Mục tiêu: {levels['target_low']:,}-"
                f"{levels['target_high']:,}đ\n"
                f"⛔ Dời stoploss lên dưới {levels['breakout_level']:,}đ"))
        else:
            signals.append(("BREAKOUT_WEAK",
                f"⚠️ <b>[{symbol}] Vượt kháng cự nhưng volume yếu</b>\n"
                f"Giá {price:,.0f}đ > {levels['breakout_level']:,}đ, "
                f"volume chỉ {vr:.1f}x TB20. Cẩn trọng bull trap."))

    if levels["stoploss_level"] and price < levels["stoploss_level"] \
            and prev["close"] >= levels["stoploss_level"]:
        signals.append(("STOPLOSS",
            f"🔴 <b>[{symbol}] CẢNH BÁO STOPLOSS</b>\n"
            f"Giá {price:,.0f}đ thủng {levels['stoploss_level']:,}đ — "
            "cấu trúc tăng bị phá vỡ, cân nhắc thoát vị thế."))

    if vr >= s["volume_spike_ratio"] * 1.5:
        signals.append(("VOL_SPIKE",
            f"📊 <b>[{symbol}] Khối lượng đột biến</b>\n"
            f"Volume gấp {vr:.1f}x TB20. Giá {price:,.0f}đ "
            f"({(price/prev['close']-1)*100:+.1f}%)"))

    if prev["macd"] <= prev["macd_signal"] and \
            last["macd"] > last["macd_signal"]:
        signals.append(("MACD_CROSS",
            f"📈 <b>[{symbol}] MACD cắt lên</b> — động lượng tăng "
            f"hình thành. Giá: {price:,.0f}đ"))

    # --- Mo hinh nen + cham diem hop luu (muc 1) ---
    conf_min = s.get("candle_confluence_min", 3)
    pending = "⏳ nến chưa đóng - chờ xác nhận cuối phiên\n" \
        if prof["candle_is_today"] else ""
    for name, direction in prof["candles"]:
        if direction == "neutral":
            continue
        score, detail = confluence_score(
            direction, price, levels, last, vr, prof["trends"],
            s["rsi_oversold"], s["rsi_overbought"])
        if score >= conf_min:
            icon = "🕯️🟢" if direction == "bull" else "🕯️🔴"
            kind = "đáy" if direction == "bull" else "đỉnh"
            signals.append((f"CANDLE_{name[:12]}",
                f"{icon} <b>[{symbol}] {name}</b>\n{pending}"
                f"Hợp lưu {score}/5: {', '.join(detail)}\n"
                f"→ Tín hiệu {kind} tiềm năng "
                f"{'MẠNH' if score >= 4 else 'trung bình'} | "
                f"Giá {price:,.0f}đ"))

    # --- Pha vo mau hinh cum (muc 5) ---
    signals.extend(chart_breakout_signals(
        symbol, df, prof["chart_patterns"], vr, s["volume_spike_ratio"]))

    return signals


def alert_allowed(state, symbol, key, cooldown_min):
    last = state["last_alerts"].get(f"{symbol}:{key}")
    if not last:
        return True
    return datetime.now(VN_TZ) - datetime.fromisoformat(last) \
        >= timedelta(minutes=cooldown_min)


# ---------------------------------------------------------------
# Snapshot cho Worker (phan hoi tuc thoi) + hien thi
# ---------------------------------------------------------------

def build_snapshot(market):
    snap = {}
    for sym, prof in market.items():
        df = prof["df"]
        last, prev = df.iloc[-1], df.iloc[-2]
        snap[sym] = {
            "price": float(last["close"]),
            "chg_pct": round((last["close"] / prev["close"] - 1) * 100, 2),
            "rsi": round(float(last["rsi"]), 1)
                   if pd.notna(last["rsi"]) else None,
            "vol_ratio": round(prof["vol_ratio"], 2),
            "ma_ok": bool(last["ma_short"] > last["ma_long"])
                     if pd.notna(last["ma_long"]) else None,
            "macd_ok": bool(last["macd"] > last["macd_signal"]),
            "levels": prof["levels"],
            "trends": prof["trends"],
            "swings": prof["swings"],
            "tracked_patterns": describe_tracked(prof["chart_patterns"]),
            "candles": [n for n, _ in prof["candles"]],
        }
    return snap


def build_status_block(sym, prof, sym_cfg):
    df = prof["df"]
    last, prev = df.iloc[-1], df.iloc[-2]
    lv = prof["levels"]
    chg = (last["close"] / prev["close"] - 1) * 100
    tr = prof["trends"]
    lines = [
        f"<b>[{sym}]</b> {last['close']:,.0f}đ ({chg:+.2f}%) "
        f"| chế độ: {sym_cfg.get('mode', 'auto')}",
        f"RSI: {last['rsi']:.1f} | Vol: {prof['vol_ratio']:.1f}x | "
        f"MA {'✅' if last['ma_short'] > last['ma_long'] else '⚠️'} | "
        f"MACD {'✅' if last['macd'] > last['macd_signal'] else '⚠️'}",
        "Xu hướng: " + " | ".join(
            f"{k}: {v.split(' (')[0]}" for k, v in tr.items()),
        f"Mua: {lv['buy_zone_low']:,}-{lv['buy_zone_high']:,} | "
        f"KC: {lv['breakout_level']:,} | SL: {lv['stoploss_level']:,}",
    ]
    sw = prof["swings"]
    if sw:
        parts = []
        if "swing_high" in sw:
            parts.append(f"đỉnh {sw['swing_high']['price']:,.0f} "
                         f"({sw['swing_high']['date']})")
        if "swing_low" in sw:
            parts.append(f"đáy {sw['swing_low']['price']:,.0f} "
                         f"({sw['swing_low']['date']})")
        lines.append("Swing gần nhất: " + ", ".join(parts))
    if prof["divergences"]:
        lines.append("Phân kỳ: " + "; ".join(
            f"{a} ({b})" for a, b in prof["divergences"]))
    tp = describe_tracked(prof["chart_patterns"])
    if tp:
        lines.append(f"Mẫu hình đang theo dõi: {tp}")
    if prof["candles"]:
        lines.append("Nến hôm nay: " + ", ".join(
            n for n, _ in prof["candles"]))
    return "\n".join(lines)


def build_report_block(sym, prof, cfg):
    df = prof["df"]
    last, prev = df.iloc[-1], df.iloc[-2]
    week_ago = df.iloc[-6] if len(df) >= 6 else prev
    lv = prof["levels"]
    vr = volume_ratio(last, candle_is_today=False)
    rsi_note = ("quá mua ⚠️"
                if last["rsi"] >= cfg["signals"]["rsi_overbought"]
                else "quá bán 🟢"
                if last["rsi"] <= cfg["signals"]["rsi_oversold"]
                else "trung tính")
    lines = [
        f"<b>▍{sym}</b>",
        f"Đóng cửa: <b>{last['close']:,.0f}đ</b> "
        f"({(last['close']/prev['close']-1)*100:+.2f}% ngày, "
        f"{(last['close']/week_ago['close']-1)*100:+.2f}% tuần) | "
        f"KL {vr:.1f}x TB20",
        f"RSI {last['rsi']:.1f} ({rsi_note}) | "
        f"MA20 {'>' if last['ma_short'] > last['ma_long'] else '<'} MA50 | "
        f"MACD {'✅' if last['macd'] > last['macd_signal'] else '⚠️'}",
        "Đa khung: " + " | ".join(
            f"{k}: {v}" for k, v in prof["trends"].items()),
    ]
    if prof["candles"]:
        lines.append("Nến hôm nay: " + ", ".join(
            n for n, _ in prof["candles"]))
    tp = describe_tracked(prof["chart_patterns"])
    if tp:
        lines.append(f"Mẫu hình: {tp}")
    if prof["divergences"]:
        lines.append("Phân kỳ: " + "; ".join(
            f"{a} ({b})" for a, b in prof["divergences"]))
    fib = prof["fib"]
    if fib:
        fp = []
        if fib["nearest_above"]:
            k, v = fib["nearest_above"]
            fp.append(f"cản trên {k} ~{v:,.0f}đ")
        if fib["nearest_below"]:
            k, v = fib["nearest_below"]
            fp.append(f"đỡ dưới {k} ~{v:,.0f}đ")
        if fp:
            lines.append("Fibonacci: " + " | ".join(fp))
    return "\n".join(lines)


# ---------------------------------------------------------------
# Bo lenh Telegram (muc 6, 7, 9, 10, 11)
# ---------------------------------------------------------------

SET_KEYS = {
    "buy_zone_low": "cận dưới vùng mua",
    "buy_zone_high": "cận trên vùng mua",
    "breakout_level": "mốc kháng cự / breakout",
    "stoploss_level": "mốc cắt lỗ",
    "target_low": "mục tiêu giá thấp",
    "target_high": "mục tiêu giá cao",
}

HELP_TEXT = (
    "<b>📖 Các lệnh hỗ trợ</b>\n"
    "— Theo dõi mã —\n"
    "/list — danh sách mã đang theo dõi\n"
    "/add MÃ — thêm mã (mặc định auto), vd: /add HQC\n"
    "/remove MÃ — bỏ theo dõi\n"
    "/status — trạng thái tất cả mã (kèm xu hướng đa khung, mẫu hình)\n"
    "/status MÃ — trạng thái 1 mã\n"
    "/config — xem cấu hình\n"
    "/mode MÃ auto|manual — đổi chế độ ngưỡng\n"
    "— Ngưỡng giá (chế độ manual) —\n"
    "/set MÃ khóa giá_trị — vd: /set NRC buy_zone_low 5200\n"
    "Các khóa dùng được:\n"
    + "\n".join(f"   • <code>{k}</code> — {v}" for k, v in SET_KEYS.items())
    + "\n— Danh mục cá nhân (tính riêng từng người) —\n"
    "/avg MÃ giá_vốn [số_lượng] — đặt/cập nhật giá vốn\n"
    "   vd: /avg NRC 5400 hoặc /avg NRC 5400 2000\n"
    "/unavg MÃ — xóa mã khỏi danh mục của bạn\n"
    "/pl — lời/lỗ danh mục của bạn kèm gợi ý vị thế\n"
    "/plall — tổng hợp danh mục cả nhóm\n"
    "/help — danh sách lệnh"
)


def norm_cmd(text):
    """Chuan hoa lenh: cat duoi @botname (muc 7)."""
    parts = text.strip().split()
    if parts and "@" in parts[0]:
        parts[0] = parts[0].split("@")[0]
    return parts


def collect_events(state):
    """Gop lenh tu 2 nguon: hang doi Worker (queue/*.json) + getUpdates.
    Tra ve list dict {user_id, user_name, text, source, path?}."""
    events = []
    for path in sorted(glob.glob(f"{QUEUE_DIR}/cmd-*.json")):
        d = load_json(path)
        if d.get("text"):
            events.append({"user_id": str(d.get("user_id", "")),
                           "user_name": d.get("user_name", ""),
                           "text": d["text"], "source": "queue",
                           "path": path})
    for u in tg_get_updates(state["last_update_id"]):
        state["last_update_id"] = max(state["last_update_id"],
                                      u["update_id"])
        msg = u.get("message", {})
        text = (msg.get("text") or "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != str(TELEGRAM_CHAT_ID) or not text.startswith("/"):
            continue
        frm = msg.get("from", {})
        events.append({"user_id": str(frm.get("id", "")),
                       "user_name": frm.get("first_name", ""),
                       "text": text, "source": "poll"})
    return events


def process_commands(state, cfg, market, pf):
    """Xu ly toan bo lenh. Moi thanh vien group deu co quyen (muc 6)."""
    events = collect_events(state)
    cfg_changed = pf_changed = False
    snapshot = build_snapshot(market)
    levels_map = {s: p["levels"] for s, p in market.items()}
    fib_map = {s: p["fib"] for s, p in market.items()}

    for ev in events:
        parts = norm_cmd(ev["text"])
        if not parts or not parts[0].startswith("/"):
            continue
        cmd = parts[0].lower()
        symbols = cfg["symbols"]

        if cmd == "/help":
            tg_send(HELP_TEXT)

        elif cmd == "/list":
            lines = [f"• <b>{s}</b> ({c.get('mode', 'auto')})"
                     for s, c in symbols.items()]
            tg_send(f"<b>Đang theo dõi {len(symbols)}/{MAX_SYMBOLS} mã:"
                    f"</b>\n" + "\n".join(lines))

        elif cmd == "/config":
            tg_send("<b>Cấu hình:</b>\n<pre>"
                    + json.dumps(cfg, ensure_ascii=False, indent=1)
                    + "</pre>")

        elif cmd == "/status":
            want = parts[1].upper() if len(parts) == 2 else None
            blocks = [build_status_block(s, p, symbols.get(s, {}))
                      for s, p in market.items()
                      if want is None or s == want]
            if blocks:
                tg_send(f"<b>📋 Trạng thái</b> "
                        f"({datetime.now(VN_TZ).strftime('%H:%M %d/%m')})\n"
                        + "\n— — —\n".join(blocks))
            else:
                tg_send(f"❌ Không có dữ liệu cho {want}. /list để xem.")

        elif cmd == "/add" and len(parts) == 2:
            sym = parts[1].upper()
            if sym in symbols:
                tg_send(f"ℹ️ {sym} đã có trong danh sách.")
            elif len(symbols) >= MAX_SYMBOLS:
                tg_send(f"❌ Đã đạt giới hạn {MAX_SYMBOLS} mã.")
            elif not symbol_exists(sym):
                tg_send(f"❌ Không tìm thấy dữ liệu mã <b>{sym}</b>.")
            else:
                symbols[sym] = {"mode": "auto",
                                "manual": dict(DEFAULT_MANUAL)}
                cfg_changed = True
                tg_send(f"✅ Đã thêm <b>{sym}</b> (chế độ auto).")

        elif cmd == "/remove" and len(parts) == 2:
            sym = parts[1].upper()
            if sym not in symbols:
                tg_send(f"❌ {sym} không có trong danh sách.")
            elif len(symbols) == 1:
                tg_send("❌ Không thể xóa mã cuối cùng.")
            else:
                del symbols[sym]
                cfg_changed = True
                tg_send(f"✅ Đã bỏ theo dõi <b>{sym}</b>")

        elif cmd == "/mode" and len(parts) == 3 \
                and parts[2] in ("auto", "manual"):
            sym = parts[1].upper()
            if sym in symbols:
                symbols[sym]["mode"] = parts[2]
                cfg_changed = True
                tg_send(f"✅ <b>{sym}</b> → chế độ <b>{parts[2]}</b>")
            else:
                tg_send(f"❌ {sym} không có trong danh sách.")

        elif cmd == "/set" and len(parts) == 4:
            sym, key, raw = parts[1].upper(), parts[2], parts[3]
            if sym not in symbols:
                tg_send(f"❌ {sym} không có trong danh sách.")
            elif key not in SET_KEYS:
                tg_send("❌ Khóa không hợp lệ. Gõ /help xem danh sách khóa.")
            else:
                try:
                    val = float(raw)
                    val = int(val) if val == int(val) else val
                    symbols[sym].setdefault("manual", dict(DEFAULT_MANUAL))
                    symbols[sym]["manual"][key] = val
                    cfg_changed = True
                    note = ("" if symbols[sym].get("mode") == "manual"
                            else f"\nℹ️ {sym} đang ở auto — áp dụng khi "
                                 f"/mode {sym} manual")
                    tg_send(f"✅ [{sym}] <b>{key}</b> = {val:,}{note}")
                except ValueError:
                    tg_send("❌ Giá trị phải là số.")

        elif cmd == "/avg" and len(parts) in (3, 4):
            sym = parts[1].upper()
            try:
                price = float(parts[2])
                qty = int(parts[3]) if len(parts) == 4 else None
                if price <= 0:
                    raise ValueError
                ok, msg = pfm.set_avg(pf, ev["user_id"], ev["user_name"],
                                      sym, price, qty)
                pf_changed = True
                if sym not in symbols:
                    msg += (f"\nℹ️ {sym} chưa được theo dõi — "
                            f"gõ /add {sym} để bot cập nhật giá cho mã này")
                tg_send(msg)
            except ValueError:
                tg_send("❌ Cú pháp: /avg MÃ giá_vốn [số_lượng]\n"
                        "vd: /avg NRC 5400 2000")

        elif cmd == "/unavg" and len(parts) == 2:
            ok, msg = pfm.remove_avg(pf, ev["user_id"], parts[1].upper())
            pf_changed = pf_changed or ok
            tg_send(msg)

        elif cmd == "/pl":
            u = pf["users"].get(ev["user_id"])
            block = pfm.build_pl_block(u, snapshot, levels_map, fib_map) \
                if u else None
            name = ev["user_name"] or "bạn"
            tg_send(f"<b>💼 Danh mục của {name}</b>\n{block}" if block
                    else f"{name} chưa có vị thế nào. "
                         "Dùng /avg MÃ giá_vốn để bắt đầu.")

        elif cmd == "/plall":
            blocks = []
            for uid, u in pf.get("users", {}).items():
                b = pfm.build_pl_block(u, snapshot, levels_map, fib_map,
                                       detail=False)
                if b:
                    blocks.append(f"<b>👤 {u.get('name', uid)}</b>\n{b}")
            tg_send("<b>💼 Danh mục cả nhóm</b>\n"
                    + "\n— — —\n".join(blocks) if blocks
                    else "Chưa ai đặt giá vốn. Dùng /avg để bắt đầu.")

        else:
            tg_send("Lệnh không hợp lệ.\n" + HELP_TEXT)

        # Xoa file hang doi da xu ly
        if ev["source"] == "queue" and ev.get("path"):
            try:
                os.remove(ev["path"])
            except OSError:
                pass

    if cfg_changed:
        save_json(CONFIG_FILE, cfg)
    if pf_changed:
        pfm.save_portfolio(pf)
    return cfg_changed


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    cfg = load_config()
    state = load_state()
    pf = pfm.load_portfolio()

    market, errors = {}, []
    for sym, sym_cfg in list(cfg["symbols"].items()):
        try:
            df = compute_indicators(fetch_history(sym), cfg)
            market[sym] = analyze_symbol(sym, df, cfg, sym_cfg)
        except Exception as e:
            errors.append(f"{sym}: {e}")
            print(f"[ERR] {sym}: {e}")

    if errors and not market:
        tg_send("❌ Lỗi lấy dữ liệu tất cả các mã:\n" + "\n".join(errors))
        sys.exit(1)

    changed = process_commands(state, cfg, market, pf)
    if changed:
        cfg = load_config()
        for sym, sym_cfg in cfg["symbols"].items():
            if sym not in market:
                try:
                    df = compute_indicators(fetch_history(sym), cfg)
                    market[sym] = analyze_symbol(sym, df, cfg, sym_cfg)
                except Exception as e:
                    print(f"[ERR] {sym}: {e}")
        market = {s: v for s, v in market.items() if s in cfg["symbols"]}

    snapshot = build_snapshot(market)
    levels_map = {s: p["levels"] for s, p in market.items()}

    if action == "report":
        if cfg["alerts"]["daily_report_enabled"] and market:
            blocks = [build_report_block(s, p, cfg)
                      for s, p in market.items()]
            report = (f"<b>📊 BÁO CÁO CUỐI NGÀY</b> - "
                      f"{datetime.now(VN_TZ).strftime('%d/%m/%Y')}\n"
                      "═══════════════\n"
                      + "\n═══════════════\n".join(blocks))
            pl_blocks = []
            for uid, u in pf.get("users", {}).items():
                b = pfm.build_pl_block(u, snapshot, levels_map,
                                       {s: p["fib"] for s, p
                                        in market.items()}, detail=False)
                if b:
                    pl_blocks.append(f"<b>👤 {u.get('name', uid)}</b>\n{b}")
            if pl_blocks:
                report += ("\n═══════════════\n<b>💼 Danh mục nhóm</b>\n"
                           + "\n".join(pl_blocks))
            if errors:
                report += "\n⚠️ Mã lỗi dữ liệu: " + ", ".join(
                    e.split(":")[0] for e in errors)
            tg_send(report)
    else:
        cooldown = cfg["alerts"]["cooldown_minutes"]
        for sym, prof in market.items():
            for key, message in detect_signals(sym, prof, cfg):
                if alert_allowed(state, sym, key, cooldown):
                    tg_send(message)
                    state["last_alerts"][f"{sym}:{key}"] = \
                        datetime.now(VN_TZ).isoformat()
        # Canh bao vi the danh muc (muc 11)
        pos_alerts, pf_dirty = pfm.position_alerts(pf, cfg, snapshot,
                                                   levels_map)
        for _uid, msg in pos_alerts:
            tg_send(msg)
        if pf_dirty:
            pfm.save_portfolio(pf)

    state["snapshot"] = snapshot
    state["snapshot_time"] = datetime.now(VN_TZ).isoformat()
    save_json(STATE_FILE, state)
    print(f"[OK] {action} xong - {len(market)} ma, {len(errors)} loi")


if __name__ == "__main__":
    main()
